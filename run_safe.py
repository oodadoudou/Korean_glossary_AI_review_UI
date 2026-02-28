import sys
import os
import traceback
import ctypes

def remove_zone_identifier(file_path):
    if os.name != 'nt':
        return False
    try:
        os.remove(f"{file_path}:Zone.Identifier")
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False

def unblock_runtime_files():
    """Best-effort unblock for critical bundled .NET files."""
    if os.name != 'nt':
        return 0

    if getattr(sys, 'frozen', False):
        base_dirs = [os.path.dirname(sys.executable)]
    else:
        base_dirs = [os.path.abspath(os.path.dirname(__file__))]

    target_rel_paths = [
        'internal/Python.Runtime.dll',
        '_internal/Python.Runtime.dll',
        'internal/pythonnet/runtime/Python.Runtime.dll',
        '_internal/pythonnet/runtime/Python.Runtime.dll',
        'internal/pythonnet/runtime/Python.Runtime.deps.json',
        '_internal/pythonnet/runtime/Python.Runtime.deps.json',
        'internal/clr_loader/ffi/dlls/amd64/ClrLoader.dll',
        '_internal/clr_loader/ffi/dlls/amd64/ClrLoader.dll',
        'internal/clr_loader/ffi/dlls/x86/ClrLoader.dll',
        '_internal/clr_loader/ffi/dlls/x86/ClrLoader.dll',
    ]

    removed_count = 0
    seen = set()
    for base_dir in base_dirs:
        for rel_path in target_rel_paths:
            candidate = os.path.normpath(os.path.join(base_dir, rel_path))
            key = os.path.normcase(candidate)
            if key in seen:
                continue
            seen.add(key)
            if os.path.exists(candidate) and remove_zone_identifier(candidate):
                removed_count += 1
    return removed_count

def show_error_dialog(title, message):
    """显示原生 Windows 错误弹窗。"""
    try:
        # MB_ICONERROR = 0x10, MB_OK = 0x0
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x10 | 0x0)
    except Exception:
        pass # Fallback if ctypes fails

def main():
    try:
        # Prevent pythonnet loader failures when files are marked as downloaded.
        unblock_runtime_files()
        # Directly import and run the main app
        from backend.app import start_app
        start_app()
    except Exception as e:
        error_msg = f"Application crashed unexpectedly:\n{str(e)}\n\n"
        error_msg += traceback.format_exc()
        
        # Write logs next to the executable in frozen mode for consistent user support.
        if getattr(sys, 'frozen', False):
            log_base_dir = os.path.dirname(sys.executable)
        else:
            log_base_dir = os.getcwd()
        log_path = os.path.join(log_base_dir, 'fatal_crash_log.txt')
        try:
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write(error_msg)
        except Exception:
            pass

        # Display native UI alert to the user
        show_error_dialog("应用启动失败",
                          f"应用启动时发生异常。\n\n"
                          f"错误详情已写入：\n{log_path}\n\n"
                          f"异常信息：\n{str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()
