import PyInstaller.__main__
import os
import shutil
from PyInstaller.utils.hooks import collect_all

# Define paths
BASE_DIR = os.getcwd()
FRONTEND_DIST = os.path.join(BASE_DIR, 'frontend', 'dist')
ENTRY_POINT = os.path.join(BASE_DIR, 'run.py')

# Verify frontend build exists
if not os.path.exists(FRONTEND_DIST):
    print("Error: Frontend build not found. Please run 'npm run build' in frontend directory first.")
    exit(1)

print("Starting build process...")

# Collect dependencies for pythonnet, clr_loader, and webview
# These packages often have hidden imports and binaries that standard PyInstaller analysis misses
packages_to_collect = ['pythonnet', 'clr_loader', 'webview', 'cffi']
collected_datas = []
collected_binaries = []
collected_hidden_imports = []

print("Collecting runtime data and binaries for: " + ", ".join(packages_to_collect))
for package in packages_to_collect:
    try:
        datas, binaries, hiddenimports = collect_all(package)
        collected_datas.extend(datas)
        collected_binaries.extend(binaries)
        collected_hidden_imports.extend(hiddenimports)
    except Exception as e:
        print(f"Warning: Failed to collect data for {package}: {e}")

# Format for PyInstaller
# --add-data "src;dest" (Windows)
add_data_args = [f'--add-data={src};{dest}' for src, dest in collected_datas]
add_binary_args = [f'--add-binary={src};{dest}' for src, dest in collected_binaries]
hidden_import_args = [f'--hidden-import={h}' for h in collected_hidden_imports]

# Explicitly find and add Python.Runtime.dll
import pythonnet
pythonnet_dir = os.path.dirname(pythonnet.__file__)
runtime_dll_path = os.path.join(pythonnet_dir, 'runtime', 'Python.Runtime.dll')

if os.path.exists(runtime_dll_path):
    print(f"Explicitly adding Python.Runtime.dll from: {runtime_dll_path}")
    # Add to both root and pythonnet folder to be safe
    add_binary_args.append(f'--add-binary={runtime_dll_path};.')
    add_binary_args.append(f'--add-binary={runtime_dll_path};pythonnet/runtime')
else:
    print(f"Warning: Python.Runtime.dll not found at expected path: {runtime_dll_path}")

# Manual hidden imports (explicitly safe to add)
manual_hidden_imports = [
    'engineio.async_drivers.threading',
    'System',
    'System.IO',
    'System.Windows.Forms',
    'clr_loader',
    'clr_loader.util',
    'clr_loader.util.find',
    'pythonnet',
]
hidden_import_args.extend([f'--hidden-import={h}' for h in manual_hidden_imports])

# Construct arguments
args = [
    ENTRY_POINT,                            # Entry point
    '--name=KoreanGlossaryReview',          # Name of the exe
    '--onedir',                             # One directory bundle
    '--console',                            # Show console window (Explicitly requested)
    '--icon=icon.ico',                      # Application Icon
    f'--add-data={FRONTEND_DIST};frontend/dist', # Include frontend assets
    '--clean',                              # Clean cache
    '--noconfirm',                          # Overwrite output directory
]

# Add collected arguments
args.extend(add_data_args)
args.extend(add_binary_args)
args.extend(hidden_import_args)

print(f"Running PyInstaller with {len(args)} arguments...")

PyInstaller.__main__.run(args)

print("\nBuild complete. Executable is in dist/KoreanGlossaryReview/KoreanGlossaryReview.exe")

# Copy default config if it doesn't exist in dist
dist_dir = os.path.join(BASE_DIR, 'dist', 'KoreanGlossaryReview')
config_src = os.path.join(BASE_DIR, 'cfg.json.example')
config_dst = os.path.join(dist_dir, 'cfg.json')

if os.path.exists(config_src):
    try:
        shutil.copy(config_src, config_dst)
        print(f"Copied default config to {config_dst}")
    except Exception as e:
        print(f"Warning: Failed to copy config: {e}")
else:
    print("Warning: cfg.json.example not found, skipping config copy.")
