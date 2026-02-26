import PyInstaller.__main__
import os
import shutil
import sys

# Define base paths
BASE_DIR = os.getcwd()
FRONTEND_DIST = os.path.join(BASE_DIR, 'frontend', 'dist')
ENTRY_POINT = os.path.join(BASE_DIR, 'run_safe.py') # MIGRATED TO SAFE ENTRY POINT

# Verify frontend build exists
if not os.path.exists(FRONTEND_DIST):
    print("Error: Frontend build not found. Please run 'npm run build' in frontend directory first.")
    exit(1)

print("Starting robust build process...")

# 1. CORE DATA AND DLL HOOKS
add_data_args = []
add_binary_args = []

# Fetch WebView2 DLLs dynamically based on current environment
import webview
webview_lib_dir = os.path.join(os.path.dirname(webview.__file__), 'lib')

if os.path.exists(webview_lib_dir):
    print(f"Collecting WebView2 architecture dependent DLLs from: {webview_lib_dir}")
    # Walk the lib directory to guarantee all arch runtimes are included (win-x64, win-arm64, win-x86)
    for root, dirs, files in os.walk(webview_lib_dir):
        for file in files:
            if file.endswith('.dll') or file.endswith('.jar'):
                src_path = os.path.join(root, file)
                # Calculate relative destination string path inside package
                rel_path = os.path.relpath(root, webview_lib_dir)
                dest_dir = 'webview/lib' if rel_path == '.' else f'webview/lib/{rel_path}'
                dest_dir = dest_dir.replace('\\', '/') # Ensure correct internal formatting
                
                add_binary_args.append(f'--add-binary={src_path};{dest_dir}')
else:
    print("CRITICAL WARNING: WebView library paths not found. Program will likely crash.")

# Explicitly collect Pythonnet
import pythonnet
pythonnet_dir = os.path.dirname(pythonnet.__file__)
runtime_dll_path = os.path.join(pythonnet_dir, 'runtime', 'Python.Runtime.dll')

if os.path.exists(runtime_dll_path):
    print(f"Explicitly enforcing Python.Runtime.dll from: {runtime_dll_path}")
    # Inject it directly into root AND pythonnet/runtime to survive ClrLoader searches
    add_binary_args.append(f'--add-binary={runtime_dll_path};.')
    add_binary_args.append(f'--add-binary={runtime_dll_path};pythonnet/runtime')

# Explicitly collect clr_loader architecture DLLs
import clr_loader
clr_loader_dir = os.path.join(os.path.dirname(clr_loader.__file__), 'ffi', 'dlls')
if os.path.exists(clr_loader_dir):
    for march in ['amd64', 'x86']:
        dll_src = os.path.join(clr_loader_dir, march, 'ClrLoader.dll')
        if os.path.exists(dll_src):
             add_binary_args.append(f'--add-binary={dll_src};clr_loader/ffi/dlls/{march}')

# 2. HIDDEN IMPORTS
hidden_imports = [
    'engineio.async_drivers.threading',
    'System',
    'System.IO',
    'System.Windows.Forms',
    'clr_loader',
    'clr_loader.util',
    'clr_loader.util.find',
    'pythonnet',
    'app',                 # Make sure the delegated app module is frozen
    'backend',
    'backend.core',
    'backend.version',
    'backend.updater',
    'requests'
]
hidden_import_args = [f'--hidden-import={h}' for h in hidden_imports]

# 3. CONSTRUCT ARGS
args = [
    ENTRY_POINT,                            # Safe Entry point
    '--name=KoreanGlossaryReview',
    '--onedir',                             # Directory mode handles heavy Webview DLLs better
    '--windowed',                           # Hide the DOS popup
    '--icon=icon.ico',                      
    f'--add-data={FRONTEND_DIST};frontend/dist', # Complete frontend tree
    '--clean',                              
    '--noconfirm',                          
]

args.extend(add_data_args)
args.extend(add_binary_args)
args.extend(hidden_import_args)

print(f"Running PyInstaller with {len(args)} robust target arguments...")
PyInstaller.__main__.run(args)

print("\nBuild complete. Executable is in dist/KoreanGlossaryReview/KoreanGlossaryReview.exe")

# 4. POST-BUILD ENVIRONMENT SETTING
dist_dir = os.path.join(BASE_DIR, 'dist', 'KoreanGlossaryReview')
config_src = os.path.join(BASE_DIR, 'cfg.json.example')
config_dst = os.path.join(dist_dir, 'cfg.json')

if os.path.exists(config_src):
    shutil.copy(config_src, config_dst)

print("Package ready. Launching dist/KoreanGlossaryReview/KoreanGlossaryReview.exe now uses Crash Logger.")
