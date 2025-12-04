import PyInstaller.__main__
import os
import shutil

# Define paths
BASE_DIR = os.getcwd()
FRONTEND_DIST = os.path.join(BASE_DIR, 'frontend', 'dist')
ENTRY_POINT = os.path.join(BASE_DIR, 'run.py')

# Verify frontend build exists
if not os.path.exists(FRONTEND_DIST):
    print("Error: Frontend build not found. Please run 'npm run build' in frontend directory first.")
    exit(1)

print("Starting build process...")

PyInstaller.__main__.run([
    ENTRY_POINT,                            # Entry point
    '--name=KoreanGlossaryReview',          # Name of the exe
    '--onedir',                             # One directory bundle
    '--console',                            # Show console window (Explicitly requested)
    '--icon=icon.ico',                      # Application Icon
    f'--add-data={FRONTEND_DIST};frontend/dist', # Include frontend assets
    '--clean',                              # Clean cache
    '--noconfirm',                          # Overwrite output directory
    # Hidden imports that might be missed
    '--hidden-import=engineio.async_drivers.threading',
    '--hidden-import=webview',
    '--hidden-import=webview.platforms.winforms',
    '--hidden-import=clr', # For pythonnet if used by pywebview on windows
    '--hidden-import=pythonnet',
    '--hidden-import=clr_loader',
    '--hidden-import=System',
    '--hidden-import=System.Windows.Forms',
])

print("Build complete. Executable is in dist/KoreanGlossaryReview/KoreanGlossaryReview.exe")
