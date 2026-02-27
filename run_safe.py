import sys
import os
import traceback
import ctypes

def show_error_dialog(title, message):
    """Shows a native Windows error dialog."""
    try:
        # MB_ICONERROR = 0x10, MB_OK = 0x0
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x10 | 0x0)
    except Exception:
        pass # Fallback if ctypes fails

def main():
    try:
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
        show_error_dialog("Fatal Application Error", 
                          f"The application failed to start due to an unexpected error.\n\n"
                          f"Error details have been written to:\n{log_path}\n\n"
                          f"Exception:\n{str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main()
