import os, sys, tempfile, psutil

LOCK_FILE = os.path.join(tempfile.gettempdir(), "O-SAVS.pid")

def ensure_single_instance():
    current_pid = os.getpid()

    if os.path.exists(LOCK_FILE):
        with open(LOCK_FILE, "r") as f:
            try:
                old_pid = int(f.read().strip())
            except ValueError:
                old_pid = None

        if old_pid and psutil.pid_exists(old_pid):
            try:
                proc = psutil.Process(old_pid)
                if "python" in proc.name().lower():
                    print(f"\n[System] FATAL: Another instance is already active.")
                    print(f"[System] Existing Process ID: {old_pid}")
                    print(f"[System] Current Process ID: {current_pid}")
                    print("[System] Shutting down new instance to prevent 'The Chaos'.\n")
                    sys.exit(1)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass 

    with open(LOCK_FILE, "w") as f:
        f.write(str(current_pid))

def cleanup_instance():
    """Removes the lock file on exit."""
    if os.path.exists(LOCK_FILE):
        try:
            os.remove(LOCK_FILE)
            print("[System] Instance lock released.")
        except Exception:
            pass