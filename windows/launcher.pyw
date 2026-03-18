"""FastLRSearch Windows Launcher.

Launched by pythonw.exe (no console window). Redirects stdout/stderr
to a log file for crash diagnostics.
"""

import datetime
import os
import sys
import traceback

LOG_DIR = os.path.join(os.environ["LOCALAPPDATA"], "fastlrsearch", "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "FastLRSearch.log")

log = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
sys.stdout = log
sys.stderr = log

now = datetime.datetime.now().isoformat
print(f"{now()}: Launching FastLRSearch...")
print(f"{now()}: Python: {sys.version}")
print(f"{now()}: Executable: {sys.executable}")

try:
    from fastlrsearch.main import main

    main()
except Exception:
    traceback.print_exc()
