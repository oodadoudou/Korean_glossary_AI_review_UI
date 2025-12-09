from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from backend.core.engine import ReviewEngine
from backend.config_manager import load_config, save_config
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

@api_blueprint.route('/test-connection', methods=['POST'])
def test_connection():
    try:
        config = request.json
        # Simple test prompt
        from backend.core.ai_service import AIService
        # Create a temporary service with the provided config
        # We need to mock the config loading or pass it directly. 
        # For simplicity, let's just use the current loaded config but override with provided keys if needed, 
        # or better, just instantiate AIService with the provided keys.
        
        # Since AIService loads config internally, we might need to temporarily save or modify how it works.
        # However, to avoid side effects, let's just use the openai client directly here for testing.
        import openai
        
        client = openai.OpenAI(
            api_key=config.get("api_key"),
            base_url=config.get("base_url")
        )
        
        response = client.chat.completions.create(
            model=config.get("model", "deepseek-chat"),
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=5,
            temperature=0.1
        )
        
        return jsonify({"status": "success", "message": "Connection successful!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

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
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file"}), 400
        
    if file and file.filename.endswith('.json'):
        filename = secure_filename(file.filename)
        config = load_config()
        directory = config.get("last_task_directory") or config.get("default_directory", "")
        
        if not directory or not os.path.exists(directory):
            # Fallback to default directory if last_task_directory is invalid
            directory = config.get("default_directory", ".")
            if not os.path.exists(directory):
                os.makedirs(directory)
                
        filepath = os.path.join(directory, filename)
        file.save(filepath)
        return jsonify({"status": "success", "filename": filename})
    else:
        return jsonify({"status": "error", "message": "Invalid file type. Only JSON allowed."}), 400

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
    
    if not directory:
        return jsonify({"status": "error", "message": "No directory specified and no saved task config found."})
        
    success, msg = engine.start_task(directory, context)
    return jsonify({"status": "success" if success else "error", "message": msg})

@api_blueprint.route('/control/stop', methods=['POST'])
def stop_task():
    success, msg = engine.stop_task()
    return jsonify({"status": "success" if success else "error", "message": msg})

@api_blueprint.route('/status', methods=['GET'])
def get_status():
    return jsonify(engine.get_status())
