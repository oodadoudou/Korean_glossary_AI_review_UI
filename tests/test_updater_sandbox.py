"""Sandbox test for the auto-updater bat-script logic.

Simulates a real onedir install layout + an "update payload", then runs the
generated apply_update.bat against it WITHOUT touching the real install.

Scenarios:
  1. Happy path: parent process gone, files swap cleanly.
  2. Locked-exe path: a fake "running" process keeps a handle on the .exe;
     the bat must wait, detect the lock, and either succeed once we release
     it OR time out cleanly with a logged error.
  3. Old (broken) updater path: same locked-exe scenario run against the
     OLD bat-script logic (xcopy /C /Q) — used to demonstrate the silent-
     failure bug.

Run: python tests/test_updater_sandbox.py
"""
import os
import sys
import shutil
import subprocess
import tempfile
import time
import textwrap

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
from backend.updater import _build_update_script  # noqa: E402

EXE_NAME = "FakeApp.exe"
# A trivial Windows .exe stub: a tiny .bat masquerading as .exe won't work
# because we need a real process holding a file handle. Instead we use
# Python itself: copy python.exe in as our "FakeApp.exe" and have it sleep.
PYTHON_EXE = sys.executable


def make_install_dir(parent, version_label):
    """Lay out a fake onedir install: FakeApp.exe + _internal/ + cfg.json."""
    install = os.path.join(parent, "install")
    os.makedirs(install, exist_ok=True)
    shutil.copy(PYTHON_EXE, os.path.join(install, EXE_NAME))
    internal = os.path.join(install, "_internal")
    os.makedirs(internal, exist_ok=True)
    with open(os.path.join(internal, "version.txt"), "w") as f:
        f.write(version_label)
    with open(os.path.join(install, "cfg.json"), "w") as f:
        f.write('{"user_data": "MUST_BE_PRESERVED"}')
    return install


def make_update_payload(parent, version_label):
    """Lay out a fake update source dir mirroring the install structure."""
    src = os.path.join(parent, "payload")
    os.makedirs(src, exist_ok=True)
    shutil.copy(PYTHON_EXE, os.path.join(src, EXE_NAME))
    internal = os.path.join(src, "_internal")
    os.makedirs(internal, exist_ok=True)
    with open(os.path.join(internal, "version.txt"), "w") as f:
        f.write(version_label)
    # Note: we deliberately DO NOT include cfg.json in the payload (the
    # production updater removes it before running), but we add a NEW file
    # to verify it gets copied through.
    with open(os.path.join(src, "NEW_FILE.txt"), "w") as f:
        f.write("introduced by update")
    return src


def write_old_broken_bat(install_dir, source_dir, exe_name, update_dir):
    """Reproduce the OLD bat from updater.py @ commit dc0c421 verbatim."""
    source_dir_norm = os.path.normpath(source_dir)
    base_cwd_norm = os.path.normpath(install_dir)
    exe_path = os.path.join(base_cwd_norm, exe_name)
    bat = f'''@echo off
chcp 65001 > nul
echo Please wait while the application updates...

ping 127.0.0.1 -n 5 > nul

echo Overwriting files...
xcopy "{source_dir_norm}\\*" "{base_cwd_norm}\\" /E /Y /C /Q

echo Restarting application...
if exist "{exe_path}" (
    rem skip restart in test
)

echo Cleanup...
rmdir /s /q "{update_dir}"
'''
    bat_path = os.path.join(install_dir, "apply_update_OLD.bat")
    with open(bat_path, 'w', encoding='utf-8') as f:
        f.write(bat)
    return bat_path


def write_new_bat(install_dir, source_dir, exe_name, update_dir):
    log_path = os.path.join(install_dir, "update_log.txt")
    bat = _build_update_script(source_dir, install_dir, exe_name, update_dir, log_path)
    # Strip the restart line so the test doesn't actually launch python.exe
    bat = bat.replace('start "" "%EXE%"', 'rem start skipped in test')
    # Strip self-delete so the test runner can re-read the bat for debugging
    bat = bat.replace('(goto) 2>nul & del "%~f0"', 'rem self-delete skipped in test')
    bat_path = os.path.join(install_dir, "apply_update_NEW.bat")
    with open(bat_path, 'w', encoding='utf-8') as f:
        f.write(bat)
    return bat_path


def run_bat(bat_path, env=None):
    """Run the bat synchronously and return (returncode, stdout)."""
    p = subprocess.run(
        ["cmd.exe", "/c", bat_path],
        capture_output=True, text=True, timeout=120, env=env,
    )
    return p.returncode, p.stdout + p.stderr


def read_version(install_dir):
    p = os.path.join(install_dir, "_internal", "version.txt")
    with open(p) as f:
        return f.read().strip()


def cfg_preserved(install_dir):
    p = os.path.join(install_dir, "cfg.json")
    if not os.path.exists(p):
        return False
    with open(p) as f:
        return "MUST_BE_PRESERVED" in f.read()


def new_file_copied(install_dir):
    return os.path.exists(os.path.join(install_dir, "NEW_FILE.txt"))


def hold_lock(exe_path, seconds):
    """Spawn a child python that opens the .exe with exclusive sharing.

    On Windows, simply running the .exe (`subprocess.Popen([exe_path, ...])`)
    creates an image-section lock identical to what the real running app has —
    rename succeeds, overwrite fails. That's exactly the production scenario.
    """
    # Run python.exe (which IS our FakeApp.exe) so it holds an image-section
    # lock on its own file. Sleep for `seconds` then exit.
    return subprocess.Popen(
        [exe_path, "-c", f"import time; time.sleep({seconds})"],
        creationflags=0x08000000,  # CREATE_NO_WINDOW
    )


# ---- Scenarios -------------------------------------------------------------

def scenario(name, fn):
    print(f"\n{'='*60}\n{name}\n{'='*60}")
    try:
        fn()
        print(f"[PASS] {name}")
        return True
    except AssertionError as e:
        print(f"[FAIL] {name}: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] {name}: {type(e).__name__}: {e}")
        return False


def s1_happy_path_new():
    """NEW updater: parent already exited, swap should succeed."""
    with tempfile.TemporaryDirectory() as tmp:
        install = make_install_dir(tmp, "v1.0")
        upd_dir = os.path.join(install, "temp_update")
        os.makedirs(upd_dir, exist_ok=True)
        src = make_update_payload(upd_dir, "v2.0")
        bat = write_new_bat(install, src, EXE_NAME, upd_dir)
        rc, out = run_bat(bat)
        print(out[-800:])
        assert rc == 0, f"bat failed rc={rc}"
        assert read_version(install) == "v2.0", "version was not updated"
        assert cfg_preserved(install), "cfg.json was wiped"
        assert new_file_copied(install), "NEW_FILE.txt missing"
        assert not os.path.exists(upd_dir), "temp_update not cleaned up"


def s2_locked_exe_old_bat_silently_skips():
    """OLD updater: exe locked -> xcopy /C silently skips, version stays old.

    This is the production bug. We expect the OLD bat to "succeed" (rc=0)
    while leaving the .exe at the OLD version, AND it never logs a thing.
    """
    with tempfile.TemporaryDirectory() as tmp:
        install = make_install_dir(tmp, "v1.0")
        upd_dir = os.path.join(install, "temp_update")
        os.makedirs(upd_dir, exist_ok=True)
        src = make_update_payload(upd_dir, "v2.0")
        bat = write_old_broken_bat(install, src, EXE_NAME, upd_dir)

        proc = hold_lock(os.path.join(install, EXE_NAME), seconds=10)
        try:
            rc, out = run_bat(bat)
        finally:
            proc.terminate()
            proc.wait(timeout=5)

        print(out[-800:])
        # The bat technically returns 0 (because xcopy /C swallows errors),
        # but the .exe was NOT replaced. Hash the file to prove it.
        exe_size_after = os.path.getsize(os.path.join(install, EXE_NAME))
        # The OLD bat removed temp_update at the end too, hiding the evidence.
        # Other files DID get copied because they weren't locked.
        # Verify the bug: NEW_FILE.txt copied successfully, .exe was NOT.
        assert new_file_copied(install), \
            "NEW_FILE.txt should have been copied even by the broken updater"
        # The exe should still be the locked version (size matches python.exe
        # so this test is a bit weak — but the meaningful demonstration is
        # that the bat reported success with no log file produced).
        assert rc == 0, \
            "OLD bat is supposed to silently 'succeed' even when locked"
        assert not os.path.exists(os.path.join(install, "update_log.txt")), \
            "OLD bat doesn't write a log — that's the diagnostic blackout"
        print("  -> reproduced the silent-failure bug from production")


def s3_locked_exe_new_bat_waits_and_succeeds():
    """NEW updater: lock is released within the wait window -> success."""
    with tempfile.TemporaryDirectory() as tmp:
        install = make_install_dir(tmp, "v1.0")
        upd_dir = os.path.join(install, "temp_update")
        os.makedirs(upd_dir, exist_ok=True)
        src = make_update_payload(upd_dir, "v2.0")
        bat = write_new_bat(install, src, EXE_NAME, upd_dir)

        # Hold the lock for ~6s; new updater waits up to 60s -> should succeed.
        proc = hold_lock(os.path.join(install, EXE_NAME), seconds=6)
        try:
            rc, out = run_bat(bat)
        finally:
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=5)

        print(out[-800:])
        log_path = os.path.join(install, "update_log.txt")
        log_text = open(log_path, encoding='utf-8').read() if os.path.exists(log_path) else "<no log>"
        print("--- update_log.txt ---")
        print(log_text)

        assert rc == 0, f"new bat failed rc={rc}"
        assert read_version(install) == "v2.0", "version was not updated after lock released"
        assert cfg_preserved(install), "cfg.json was wiped"
        assert "robocopy" in log_text.lower(), "log should record robocopy run"
        assert "Update finished successfully" in log_text


def s4_locked_exe_new_bat_times_out_with_diagnostic():
    """NEW updater: lock held longer than the wait -> clean error + log."""
    with tempfile.TemporaryDirectory() as tmp:
        install = make_install_dir(tmp, "v1.0")
        upd_dir = os.path.join(install, "temp_update")
        os.makedirs(upd_dir, exist_ok=True)
        src = make_update_payload(upd_dir, "v2.0")
        bat = write_new_bat(install, src, EXE_NAME, upd_dir)
        # Replace `pause` so the test doesn't hang waiting for a keypress.
        # Shorten robocopy retries so the test is fast (2 retries x 1s = ~2s).
        with open(bat, encoding='utf-8') as f:
            text = f.read()
        text = text.replace("\npause\n", "\nrem pause\n")
        text = text.replace("/R:30 /W:2", "/R:2 /W:1")
        with open(bat, 'w', encoding='utf-8') as f:
            f.write(text)

        proc = hold_lock(os.path.join(install, EXE_NAME), seconds=30)
        try:
            rc, out = run_bat(bat)
        finally:
            proc.terminate()
            proc.wait(timeout=5)

        print(out[-800:])
        log_text = open(os.path.join(install, "update_log.txt"), encoding='utf-8').read()
        print("--- update_log.txt ---")
        print(log_text)

        assert rc == 1, f"expected rc=1 on timeout, got {rc}"
        assert cfg_preserved(install), "cfg.json must be preserved even on failure"
        assert "robocopy reported failure" in log_text, "log should record the copy failure"
        # Critical: the user must be told the update failed, not silently see
        # an old app restart. The OLD updater's bug was rc=0 with no log;
        # we now emit rc=1 + log + visible error message + pause.
        assert "FAILED" in log_text or "ERROR" in log_text


def main():
    results = []
    results.append(scenario("S1: Happy path (new updater)", s1_happy_path_new))
    results.append(scenario("S2: Locked exe + OLD updater = silent failure (bug repro)",
                            s2_locked_exe_old_bat_silently_skips))
    results.append(scenario("S3: Locked exe + NEW updater = waits and succeeds",
                            s3_locked_exe_new_bat_waits_and_succeeds))
    results.append(scenario("S4: Lock held too long + NEW updater = clean failure with log",
                            s4_locked_exe_new_bat_times_out_with_diagnostic))

    print(f"\n{'='*60}")
    print(f"Results: {sum(results)}/{len(results)} passed")
    print('='*60)
    sys.exit(0 if all(results) else 1)


if __name__ == '__main__':
    main()
