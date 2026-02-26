from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from backend.core.engine import ReviewEngine
from backend.config_manager import load_config, save_config
from backend.version import __version__
from backend.updater import check_for_updates, perform_update
import os

api_blueprint = Blueprint('api', __name__)
engine = ReviewEngine()

@api_blueprint.route('/config', methods=['GET', 'POST'])
def config():
    if request.method == 'GET':
        return jsonify(load_config())
    else:
        new_config = request.json
        if save_config(new_config):
            # Force reload of AI service config to apply new keys immediately
            engine.ai_service.reload_config()
            return jsonify({"status": "success"})
        return jsonify({"status": "error"}), 500

@api_blueprint.route('/prompts', methods=['GET', 'POST'])
def prompts():
    config = load_config()
    if request.method == 'GET':
        return jsonify(config.get("prompts", {}))
    else:
        new_prompts = request.json
        config["prompts"] = new_prompts
        if save_config(config):
            return jsonify({"status": "success"})
        return jsonify({"status": "error"}), 500

@api_blueprint.route('/test-prompt', methods=['POST'])
def test_prompt():
    data = request.json
    term = data.get('korean_term')
    translation = data.get('chinese_translation')
    context = data.get('context')
    custom_prompt = data.get('custom_prompt') # Optional
    
    # We need the novel background. If not provided, try to load from config or empty
    # For now, let's use the one from the last task config if available, or empty
    config = load_config()
    novel_background = config.get('last_task_context', '')
    
    if not term:
        return jsonify({"error": "Missing term"}), 400
        
    try:
        result = engine.processor.test_single_term(
            term, 
            translation, 
            context, 
            custom_prompt=custom_prompt,
            novel_background=novel_background
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/test-connection', methods=['POST'])
def test_connection():
    try:
        config = request.json
        providers = []
        
        # Check new providers structure
        if config.get("providers"):
            providers = config.get("providers")
        else:
            # Fallback to legacy single fields
            raw_keys = config.get("api_key", "")
            base_url = config.get("base_url")
            model = config.get("model", "deepseek-chat")
            
            if "\n" in raw_keys:
                keys = [k.strip() for k in raw_keys.split("\n") if k.strip()]
            else:
                keys = [raw_keys.strip()] if raw_keys.strip() else []
                
            for k in keys:
                 providers.append({"api_key": k, "base_url": base_url, "model": model})

        if not providers:
             return jsonify({"status": "error", "message": "No API providers configured"})

        import openai
        
        results = []
        valid_count = 0
        
        # Load configurable timeout
        connect_timeout = float(load_config().get("connect_timeout", 120.0))
        
        for idx, p in enumerate(providers):
            # Skip if explicitly disabled
            if not p.get("enabled", True):
                continue

            key = p.get("api_key", "")
            base_url = p.get("base_url", "")
            model = p.get("model", "")
            
            masked_key = f"{key[:6]}..." if len(key) > 6 else key
            provider_name = f"#{idx+1} {model}"
            
            try:
                client = openai.OpenAI(
                    api_key=key, 
                    base_url=base_url, 
                    timeout=connect_timeout,
                    default_headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
                )
                
                # Dynamic prompt to avoid cache
                import time
                import random
                unique_prompt = f"Hi from review tool check {int(time.time())} {random.randint(1000, 9999)}"
                
                client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": unique_prompt}],
                    max_tokens=5,
                    timeout=connect_timeout
                )
                results.append({"key": provider_name, "status": "valid", "msg": "OK"})
                valid_count += 1
            except openai.APITimeoutError:
                 results.append({"key": provider_name, "status": "invalid", "msg": f"Timeout ({int(connect_timeout)}s) - Server did not respond in time."})
            except openai.APIStatusError as e:
                 # Catching 4xx/5xx errors (AuthenticationError is a subclass of this)
                 error_code = e.status_code
                 try:
                     error_body = e.body.get('message', str(e.body)) if isinstance(e.body, dict) else str(e.body)
                 except:
                     error_body = str(e)
                 results.append({"key": provider_name, "status": "invalid", "msg": f"HTTP {error_code}: {error_body}"})
            except Exception as e:
                results.append({"key": provider_name, "status": "invalid", "msg": f"Error: {str(e)}"})

        if valid_count == len(providers):
            msg = "✅ All Providers Operational!"
            status = "success"
        elif valid_count > 0:
            msg = f"⚠️ Partial: {valid_count}/{len(providers)} providers working."
            status = "warning"
        else:
            msg = "❌ All providers failed."
            status = "error"

        return jsonify({
            "status": status,
            "message": msg,
            "results": results
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"System Error: {str(e)}"})

@api_blueprint.route('/check-folder', methods=['POST'])
def check_folder():
    path = request.json.get('path')
    if not path or not os.path.exists(path):
        return jsonify({"valid": False, "error": "Path does not exist"})
    
    # Check for .xlsx files
    files = [f for f in os.listdir(path) if f.endswith('.xlsx') and not f.startswith('~$')]
    if not files:
        return jsonify({"valid": False, "error": "No .xlsx files found in directory"})
        
    return jsonify({"valid": True})

@api_blueprint.route('/task/config', methods=['POST'])
def task_config():
    data = request.json
    # In a real app, we might save this to a database or session.
    # For now, we can just save it to the global config or return success 
    # since the frontend will pass it to start_task anyway.
    # But to follow the design, let's save it to config_manager to persist across restarts if needed.
    config = load_config()
    config['last_task_directory'] = data.get('directory')
    config['last_task_context'] = data.get('context')
    save_config(config)
    return jsonify({"status": "success"})

@api_blueprint.route('/results/list', methods=['GET'])
def list_results():
    config = load_config()
    # Use the last task directory or default directory
    directory = config.get("last_task_directory") or config.get("default_directory", "")
    
    if not directory or not os.path.exists(directory):
        return jsonify([])
    
    try:
        # Look for modified.json or modified.xlsx
        files = []
        for f in os.listdir(directory):
            if f == 'modified.json' or (f.endswith('.xlsx') and 'modified' in f.lower()):
                 files.append(f)
        return jsonify(files)
    except Exception as e:
        print(f"Error listing results: {e}")
        return jsonify([])

@api_blueprint.route('/results/upload', methods=['POST'])
def upload_result():
    try:
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No file part"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"status": "error", "message": "No selected file"}), 400
            
        # Allow case-insensitive json check
        if file and file.filename.lower().endswith('.json'):
            filename = secure_filename(file.filename)
            config = load_config()
            
            # Priority: Last Task Directory -> Default Directory -> Current Directory
            directory = config.get("last_task_directory")
            if not directory or not os.path.exists(directory):
                 directory = config.get("default_directory")
                 if not directory: 
                     directory = "." # Fallback to current dir if nothing configured
            
            # Ensure directory exists (create if needed, though for last_task usually it should exist)
            if not os.path.exists(directory):
                try:
                    os.makedirs(directory)
                except Exception as e:
                     return jsonify({"status": "error", "message": f"Failed to create directory: {e}"}), 500
                    
            filepath = os.path.join(directory, filename)
            file.save(filepath)
            
            # If we uploaded to a new directory that isn't the current 'last_task_directory', maybe we should update config?
            # User intent: "Import generated modified.json to view results". 
            # If we save it to 'directory', and 'list_results' reads from 'directory', it should show up.
            
            return jsonify({"status": "success", "filename": filename})
        else:
            return jsonify({"status": "error", "message": "Invalid file type. Only .json files allowed."}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": f"Upload failed: {str(e)}"}), 500

@api_blueprint.route('/results/content', methods=['GET'])
def get_result_content():
    filename = request.args.get('filename')
    if not filename:
        return jsonify({"error": "Filename required"}), 400
        
    config = load_config()
    directory = config.get("last_task_directory") or config.get("default_directory", "")
    filepath = os.path.join(directory, filename)
    
    if not os.path.exists(filepath):
        return jsonify({"error": "File not found"}), 404
        
    try:
        if filename.endswith('.json'):
            import json
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return jsonify(data)
        else:
            import pandas as pd
            df = pd.read_excel(filepath)
            # Replace NaN with None (null in JSON)
            df = df.where(pd.notnull(df), None)
            return jsonify(df.to_dict(orient='records'))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_blueprint.route('/control/start', methods=['POST'])
def start_task():
    data = request.json or {}
    config = load_config()
    
    directory = data.get('directory') or config.get('last_task_directory')
    context = data.get('context') or config.get('last_task_context', '')
    
    rounds = data.get('rounds', 1) # Default to 1 round
    
    if not directory:
        return jsonify({"status": "error", "message": "No directory specified and no saved task config found."})
        
    success, msg = engine.start_task(directory, context, rounds)
    return jsonify({"status": "success" if success else "error", "message": msg})

@api_blueprint.route('/control/stop', methods=['POST'])
def stop_task():
    success, msg = engine.stop_task()
    return jsonify({"status": "success" if success else "error", "message": msg})

@api_blueprint.route('/status', methods=['GET'])
def get_status():
    return jsonify(engine.get_status())

@api_blueprint.route('/version', methods=['GET'])
def get_version():
    return jsonify({"version": __version__})

@api_blueprint.route('/check-update', methods=['GET'])
def check_update():
    is_available, info = check_for_updates()
    return jsonify({
        "is_available": is_available,
        "info": info
    })

@api_blueprint.route('/do-update', methods=['POST'])
def do_update():
    data = request.json or {}
    download_url = data.get('download_url')
    if not download_url:
        return jsonify({"status": "error", "message": "Missing download URL"}), 400
        
    # This function will eventually call os._exit(0) shutting down the server
    # We can try to return a response before that, or the client can just expect a hang/close
    success, msg = perform_update(download_url)
    
    # If it fails, it returns here. If it succeeds, the process dies before returning.
    return jsonify({"status": "error", "message": msg}), 500
