import os
import sys
import tempfile
import zipfile
import subprocess
import requests
import time
import shutil
from backend.version import __version__

# Replace with your actual repo
GITHUB_REPO = "oodadoudou/Korean_glossary_AI_review_UI"
API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

def check_for_updates():
    """
    Check if a newer version is available on GitHub.
    Returns: (is_available, update_info_dict or None)
    """
    try:
        response = requests.get(API_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        latest_tag = data.get("tag_name", "")
        local_ver = __version__.lstrip('v')
        remote_ver = latest_tag.lstrip('v')
        
        # Very basic string comparison for versions.
        if remote_ver and remote_ver != local_ver:
            # Find the zip asset
            assets = data.get("assets", [])
            download_url = None
            for asset in assets:
                if asset.get("name", "").endswith(".zip"):
                    download_url = asset.get("browser_download_url")
                    break
                    
            if download_url:
                return True, {
                    "version": latest_tag,
                    "release_notes": data.get("body", "No release notes provided"),
                    "download_url": download_url
                }
        return False, None
    except Exception as e:
        print(f"Error checking for updates: {e}")
        return False, None

def perform_update(download_url):
    """
    Downloads the update, extracts it, creates a batch script to replace files,
    spawns the script, and kills the current process.
    """
    try:
        # Determine the base directory of the currently running exe
        if getattr(sys, 'frozen', False):
            # If bundled by PyInstaller
            base_cwd = os.path.dirname(sys.executable)
            main_exe_name = os.path.basename(sys.executable)
        else:
            # If running from source
            base_cwd = os.getcwd()
            main_exe_name = "run.py"

        # Create a temp dir inside the app folder or user temp
        update_dir = os.path.join(base_cwd, "temp_update")
        if os.path.exists(update_dir):
            shutil.rmtree(update_dir)
        os.makedirs(update_dir, exist_ok=True)
        
        zip_path = os.path.join(update_dir, "update.zip")
        extracted_dir = os.path.join(update_dir, "extracted")
        os.makedirs(extracted_dir, exist_ok=True)

        # 1. Download the zip
        print(f"Downloading update from {download_url}...")
        response = requests.get(download_url, stream=True, timeout=60)
        response.raise_for_status()
        with open(zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                
        # 2. Extract the zip
        print("Extracting update...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extracted_dir)

        # 3. Validation and flattening
        # PyInstaller zip usually contains a single folder like 'KoreanGlossaryReview'
        items = os.listdir(extracted_dir)
        source_dir = extracted_dir
        if len(items) == 1 and os.path.isdir(os.path.join(extracted_dir, items[0])):
            source_dir = os.path.join(extracted_dir, items[0])
            
        # Basic validation: check if an executable exists in the source_dir
        # If it's a source update, this might not apply perfectly, but assuming exe
        exe_exists = any(f.endswith('.exe') for f in os.listdir(source_dir))
        if not exe_exists and getattr(sys, 'frozen', False):
            raise Exception("Downloaded package does not seem to contain an executable.")

        # 4. PRESERVE CONFIG: Delete cfg.json from the downloaded files so it doesn't overwrite
        new_cfg_path = os.path.join(source_dir, "cfg.json")
        if os.path.exists(new_cfg_path):
            os.remove(new_cfg_path)
            print("Removed cfg.json from update payload to preserve existing config.")

        # 5. Generate Batch Script
        bat_script_path = os.path.join(base_cwd, "apply_update.bat")
        
        # Ensure paths are consistently formatted
        source_dir_norm = os.path.normpath(source_dir)
        base_cwd_norm = os.path.normpath(base_cwd)
        exe_path = os.path.join(base_cwd_norm, main_exe_name)

        # Build a highly resilient batch file
        bat_content = f'''@echo off
chcp 65001 > nul
echo Please wait while the application updates...

:: Wait a moment to allow the calling process to terminate naturally and release file locks
ping 127.0.0.1 -n 5 > nul

echo Overwriting files...
:: Adding trailing backslash to the destination avoids xcopy prompting for File/Directory
:: /E copies subdirectories including empty ones
:: /Y overwrites without prompting
:: /C continues copying even if errors occur 
xcopy "{source_dir_norm}\\*" "{base_cwd_norm}\\" /E /Y /C /Q

echo Restarting application...
if exist "{exe_path}" (
    start "" "{exe_path}"
)

echo Cleanup...
rmdir /s /q "{update_dir}"
del "%~f0"
'''
        with open(bat_script_path, 'w', encoding='utf-8') as f:
            f.write(bat_content)

        # 6. Execute the batch script detached with a NEW CONSOLE
        print("Spawning update script and exiting...")
        # CREATE_NEW_CONSOLE = 0x00000010
        # This is CRITICAL. Without it, the bat script dies the millisecond the parent Python app exits.
        # It also provides a helpful visual window stating 'Please wait' so the user doesn't panic.
        subprocess.Popen(
            ["cmd.exe", "/c", bat_script_path],
            creationflags=0x00000010, 
            cwd=base_cwd
        )

        # 7. Exit current process
        os._exit(0)

    except Exception as e:
        print(f"Update failed: {e}")
        return False, str(e)
