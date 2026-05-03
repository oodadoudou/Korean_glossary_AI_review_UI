import os
import sys
import threading
import webview
from flask import Flask, render_template
from backend.routes import api_blueprint

# Determine if running in a bundle
if getattr(sys, 'frozen', False):
    template_folder = os.path.join(sys._MEIPASS, 'frontend', 'dist')
    static_folder = os.path.join(sys._MEIPASS, 'frontend', 'dist', 'assets')
else:
    base_dir = os.path.abspath(os.path.dirname(__file__))
    template_folder = os.path.join(base_dir, '..', 'frontend', 'dist')
    static_folder = os.path.join(base_dir, '..', 'frontend', 'dist', 'assets')

import logging

app = Flask(__name__, static_folder=static_folder, template_folder=template_folder)
app.register_blueprint(api_blueprint, url_prefix='/api')

# Silence Flask logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

@app.route('/')
def index():
    return render_template('index.html')

def start_flask():
    try:
        # On macOS, threaded=True can sometimes conflict with pywebview's event loop
        # But we need it for polling. If Bus Error persists, consider using a different server.
        app.run(host='127.0.0.1', port=5000, threaded=True, use_reloader=False)
    except Exception as e:
        print(f"Flask server error: {e}")

class JSApi:
    def select_folder(self):
        try:
            if not webview.windows:
                return None
            window = webview.windows[0]
            result = window.create_file_dialog(webview.FOLDER_DIALOG)
            return result[0] if result and len(result) > 0 else None
        except Exception as e:
            print(f"JS API error (select_folder): {e}")
            return None

def start_app():
    # Pre-import engine to ensure native libs are initialized on the main thread if possible
    try:
        from backend.routes import engine
        print("Engine initialized.")
    except Exception as e:
        print(f"Engine initialization error: {e}")

    t = threading.Thread(target=start_flask)
    t.daemon = True
    t.start()

    # Small delay to let Flask start before opening window
    import time
    time.sleep(0.5)

    js_api = JSApi()
    webview.create_window(
        title='AI 术语审查工具 (AI Glossary Review)',
        url='http://127.0.0.1:5000',
        width=1280,
        height=850,
        resizable=True,
        min_size=(1024, 768),
        js_api=js_api
    )
    # Force cocoa on macOS for better stability
    gui_engine = 'cocoa' if sys.platform == 'darwin' else None
    webview.start(gui=gui_engine)

if __name__ == '__main__':
    start_app()
