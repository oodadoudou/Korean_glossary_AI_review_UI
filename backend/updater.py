import os
import sys
import zipfile
import subprocess
import requests
import shutil
from backend.version import __version__

GITHUB_REPO = "oodadoudou/Korean_glossary_AI_review_UI"
API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def _parse_version(text):
    parts = []
    for chunk in text.lstrip('v').split('.'):
        digits = ''.join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


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
        if not latest_tag:
            return False, None

        local_ver = _parse_version(__version__)
        remote_ver = _parse_version(latest_tag)

        if remote_ver > local_ver:
            assets = data.get("assets", [])
            download_url = None
            for asset in assets:
                if asset.get("name", "").lower().endswith(".zip"):
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


def _build_update_script(source_dir, base_cwd, exe_name, update_dir, log_path):
    """Build a robust Windows batch script that replaces app files in place.

    Properties:
    - Waits up to ~60s for the parent .exe to release its lock (rename probe).
    - xcopy without /C — stops on first error so we can report it.
    - Streams progress to update_log.txt and shows a console window.
    - Pauses on failure so the user can read the error before the window closes.
    """
    source = os.path.normpath(source_dir)
    target = os.path.normpath(base_cwd)
    exe_path = os.path.join(target, exe_name)
    upd = os.path.normpath(update_dir)
    log = os.path.normpath(log_path)

    return f'''@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

set "LOG={log}"
set "EXE={exe_path}"
set "TARGET={target}"
set "SOURCE={source}"
set "UPDDIR={upd}"

> "%LOG%" echo === Update started ===
>> "%LOG%" echo Time: %date% %time%
>> "%LOG%" echo Source: %SOURCE%
>> "%LOG%" echo Target: %TARGET%
>> "%LOG%" echo Exe:    %EXE%

echo.
echo ============================================================
echo  Korean Glossary Review - Updater
echo ============================================================
echo  Updating files. DO NOT close this window.
echo  A detailed log is being written to:
echo    %LOG%
echo ============================================================
echo.

echo Copying new files (robocopy will retry locked files automatically)...
>> "%LOG%" echo --- robocopy output ---
:: /E      copy subdirs including empty ones
:: /IS /IT force overwrite of identical / "tweaked" files (we want full sync)
:: /R:30   retry each file 30 times if locked
:: /W:2    wait 2 seconds between retries (max ~60s of waiting for app to exit)
:: /NP     no per-file percentage (cleaner log)
:: /NFL /NDL  no file/dir list (only summary)
:: /TEE    show summary on console too
robocopy "%SOURCE%" "%TARGET%" /E /IS /IT /R:30 /W:2 /NP /NFL /NDL /TEE >> "%LOG%" 2>&1
set "RC=!errorlevel!"
>> "%LOG%" echo --- robocopy exit code: !RC! ---
:: Robocopy success codes: 0-7. 8+ means at least one file failed all retries.
if !RC! GEQ 8 goto copyfailed
if not exist "%EXE%" goto exemissing
goto copyok
:copyfailed
>> "%LOG%" echo ERROR: robocopy reported failure (exit code !RC! ^>= 8).
echo.
echo  ERROR: File copy failed. The application may still be holding files open.
echo  Please close ALL of the app's windows and child processes then re-run:
echo    "%~f0"
echo.
echo  Detailed log:
echo    %LOG%
echo.
pause
exit /b 1
:exemissing
>> "%LOG%" echo ERROR: New executable missing at %EXE%.
echo.
echo  ERROR: The new executable is missing. See:
echo    %LOG%
echo.
pause
exit /b 1
:copyok

>> "%LOG%" echo Launching %EXE%
echo Restarting application...
start "" "%EXE%"

>> "%LOG%" echo Cleaning up temp directory...
rmdir /s /q "%UPDDIR%" 2>nul
>> "%LOG%" echo === Update finished successfully ===

(goto) 2>nul & del "%~f0"
'''


def perform_update(download_url):
    """Download the update zip, lay it out next to the running app, and spawn
    a batch script that replaces files after this process exits.
    """
    try:
        if getattr(sys, 'frozen', False):
            base_cwd = os.path.dirname(sys.executable)
            main_exe_name = os.path.basename(sys.executable)
        else:
            base_cwd = os.getcwd()
            main_exe_name = "run.py"

        update_dir = os.path.join(base_cwd, "temp_update")
        if os.path.exists(update_dir):
            shutil.rmtree(update_dir, ignore_errors=True)
        os.makedirs(update_dir, exist_ok=True)

        zip_path = os.path.join(update_dir, "update.zip")
        extracted_dir = os.path.join(update_dir, "extracted")
        os.makedirs(extracted_dir, exist_ok=True)

        print(f"Downloading update from {download_url}...")
        response = requests.get(download_url, stream=True, timeout=60)
        response.raise_for_status()
        with open(zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        print("Extracting update...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extracted_dir)

        items = os.listdir(extracted_dir)
        source_dir = extracted_dir
        if len(items) == 1 and os.path.isdir(os.path.join(extracted_dir, items[0])):
            source_dir = os.path.join(extracted_dir, items[0])

        if getattr(sys, 'frozen', False):
            exe_in_payload = any(f.lower().endswith('.exe') for f in os.listdir(source_dir))
            if not exe_in_payload:
                raise Exception("Downloaded package does not contain an executable.")

        new_cfg_path = os.path.join(source_dir, "cfg.json")
        if os.path.exists(new_cfg_path):
            os.remove(new_cfg_path)
            print("Removed cfg.json from update payload to preserve existing config.")

        log_path = os.path.join(base_cwd, "update_log.txt")
        bat_script_path = os.path.join(base_cwd, "apply_update.bat")
        bat_content = _build_update_script(source_dir, base_cwd, main_exe_name, update_dir, log_path)
        with open(bat_script_path, 'w', encoding='utf-8') as f:
            f.write(bat_content)

        print("Spawning update script and exiting...")
        # CREATE_NEW_CONSOLE keeps the bat alive after our process dies and
        # shows the user a visible window with progress / errors.
        subprocess.Popen(
            ["cmd.exe", "/c", bat_script_path],
            creationflags=0x00000010,
            cwd=base_cwd
        )

        os._exit(0)

    except Exception as e:
        print(f"Update failed: {e}")
        return False, str(e)
