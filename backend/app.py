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

app = Flask(__name__, static_folder=static_folder, template_folder=template_folder)
app.register_blueprint(api_blueprint, url_prefix='/api')

@app.route('/')
def index():
    return render_template('index.html')

def start_flask():
    app.run(host='127.0.0.1', port=5000, threaded=True, use_reloader=False)

class JSApi:
    def select_folder(self):
        window = webview.windows[0]
        result = window.create_file_dialog(webview.FOLDER_DIALOG)
        return result[0] if result else None

def start_app():
    t = threading.Thread(target=start_flask)
    t.daemon = True
    t.start()

    js_api = JSApi()
    webview.create_window(
        title='AI 术语审查工具',
        url='http://127.0.0.1:5000',
        width=1280,
        height=850,
        resizable=True,
        min_size=(1024, 768),
        js_api=js_api
    )
    webview.start()

if __name__ == '__main__':
    start_app()
