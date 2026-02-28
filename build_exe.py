import PyInstaller.__main__
import os
import shutil
import sys

# Define base paths
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
FRONTEND_DIST = os.path.join(BASE_DIR, 'frontend', 'dist')
ENTRY_POINT = os.path.join(BASE_DIR, 'run_safe.py') # MIGRATED TO SAFE ENTRY POINT
ICON_PATH = os.path.join(BASE_DIR, 'icon.ico')

# Verify frontend build exists
if not os.path.exists(FRONTEND_DIST):
    print("Error: Frontend build not found. Please run 'npm run build' in frontend directory first.")
    exit(1)

print("Starting robust build process...")

# 1. CORE DATA AND DLL HOOKS
add_data_args = []
add_binary_args = []
seen_bundle_pairs = set()

def append_bundle_arg(target_list, switch_name, src_path, dest_dir):
    src_path = os.path.normpath(src_path)
    dest_dir = dest_dir.replace('\\', '/')
    dedupe_key = (switch_name, src_path.lower(), dest_dir)
    if dedupe_key in seen_bundle_pairs:
        return
    seen_bundle_pairs.add(dedupe_key)
    target_list.append(f'--{switch_name}={src_path};{dest_dir}')

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
                append_bundle_arg(add_binary_args, 'add-binary', src_path, dest_dir)
else:
    print("CRITICAL WARNING: WebView library paths not found. Program will likely crash.")

# Explicitly collect Pythonnet
import pythonnet

pythonnet_runtime = os.path.join(os.path.dirname(pythonnet.__file__), 'runtime')
runtime_dll_path = os.path.join(pythonnet_runtime, 'Python.Runtime.dll')

if os.path.exists(runtime_dll_path):
    print(f"Explicitly enforcing Python.Runtime.dll from: {runtime_dll_path}")
    # Inject it directly into root AND pythonnet/runtime to survive ClrLoader searches
    append_bundle_arg(add_binary_args, 'add-binary', runtime_dll_path, '.')
    append_bundle_arg(add_binary_args, 'add-binary', runtime_dll_path, 'pythonnet/runtime')
    
    # Also include deps.json, which is crucial for modern .NET Core loaders (ClrLoader)
    deps_json_path = os.path.join(pythonnet_runtime, 'Python.Runtime.deps.json')
    if os.path.exists(deps_json_path):
        append_bundle_arg(add_data_args, 'add-data', deps_json_path, '.')
        append_bundle_arg(add_data_args, 'add-data', deps_json_path, 'pythonnet/runtime')
else:
    print(f"CRITICAL WARNING: Python.Runtime.dll not found in {pythonnet_runtime}")

# Explicitly collect clr_loader architecture DLLs
import clr_loader
clr_loader_dir = os.path.join(os.path.dirname(clr_loader.__file__), 'ffi', 'dlls')
if os.path.exists(clr_loader_dir):
    for march in ['amd64', 'x86']:
        dll_src = os.path.join(clr_loader_dir, march, 'ClrLoader.dll')
        if os.path.exists(dll_src):
            append_bundle_arg(add_binary_args, 'add-binary', dll_src, f'clr_loader/ffi/dlls/{march}')

# 2. HIDDEN IMPORTS
hidden_imports = [
    'clr_loader',
    'clr_loader.util',
    'clr_loader.util.find',
    'pythonnet',
    'backend.app',         # Make sure the delegated app module is frozen
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
    f'--icon={ICON_PATH}',
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

# 5. POST-BUILD DEPENDENCY VALIDATION
print("\n--- Validating Packaged Dependencies ---")
missing_deps = []
detected_content_root = os.path.join(dist_dir, '_internal')
search_roots = [dist_dir]
if os.path.isdir(detected_content_root):
    search_roots.insert(0, detected_content_root)
    print(f"Detected PyInstaller content directory: {detected_content_root}")
else:
    print("Detected legacy onedir layout (no _internal folder).")

def find_bundled_path(dest, filename):
    relative_path = filename if dest == '.' else os.path.join(os.path.normpath(dest), filename)
    for root in search_roots:
        candidate = os.path.join(root, relative_path)
        if os.path.exists(candidate):
            return candidate
    return None

def check_bundled_items(args_list, item_type):
    for arg in args_list:
        if '=' in arg:
            paths = arg.split('=', 1)[1]
            if ';' in paths:
                src, dest = paths.split(';', 1)
                filename = os.path.basename(src)

                bundled_path = find_bundled_path(dest, filename)
                if not bundled_path:
                    missing_deps.append(f"{item_type}: {dest}/{filename}")

check_bundled_items(add_binary_args, "Binary")
check_bundled_items(add_data_args, "Data")

if missing_deps:
    print("CRITICAL ERROR: The following required files are MISSING from the build output:")
    for dep in missing_deps:
        print(f" - {dep}")
    print("The packaged application will likely crash or fail to initialize.")
    sys.exit(1)
else:
    print("Build validation passed: All explicitly requested binaries and data files are present in the output directory!")

# 6. WRITE FIRST-RUN NOTE (Windows Mark-of-the-Web can block .NET DLL loading)
first_run_note = os.path.join(dist_dir, 'READ_ME_FIRST.txt')
with open(first_run_note, 'w', encoding='utf-8') as note_file:
    note_file.write(
        "KoreanGlossaryReview 首次运行说明\n"
        "===============================\n\n"
        "如果此 ZIP 是从互联网下载的，Windows 可能会阻止 DLL 加载。\n"
        "若启动时报 Python.Runtime/Loader 错误，请按以下步骤操作：\n\n"
        "1) 右键 ZIP 文件 -> 属性 -> 勾选“解除锁定” -> 应用。\n"
        "2) 将 ZIP 解压到普通文件夹（不要在压缩包预览中直接运行）。\n"
        "3) 再启动 KoreanGlossaryReview.exe。\n\n"
        "以上操作可避免 Zone.Identifier 导致的 .NET 程序集加载阻止问题。\n"
    )

# 7. BUILD PORTABLE RELEASE ZIP (ship this archive, not the exe alone)
release_dir = os.path.join(BASE_DIR, 'release')
os.makedirs(release_dir, exist_ok=True)
release_zip_base = os.path.join(release_dir, 'KoreanGlossaryReview')
release_zip_path = shutil.make_archive(
    release_zip_base,
    'zip',
    root_dir=os.path.join(BASE_DIR, 'dist'),
    base_dir='KoreanGlossaryReview'
)

print(f"\nRelease package ready: {release_zip_path}")
print("Distribute this ZIP file directly. End users must extract the full folder before running KoreanGlossaryReview.exe.")
print("已在 dist/KoreanGlossaryReview/READ_ME_FIRST.txt 写入首次运行说明。")
