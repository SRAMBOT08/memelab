# debug_processor.py
import traceback, sys, runpy, time, os

SCRIPT = "pathway_processor.py"

print("DEBUG WRAPPER running", SCRIPT, "from", os.getcwd(), flush=True)
try:
    runpy.run_path(SCRIPT, run_name="__main__")
except SystemExit as e:
    print("SystemExit:", e, file=sys.stderr, flush=True)
    traceback.print_exc()
    print("Press Ctrl+C to exit", flush=True)
    while True:
        time.sleep(1)
except Exception:
    print("Unhandled exception:", file=sys.stderr, flush=True)
    traceback.print_exc()
    print("Press Ctrl+C to exit", flush=True)
    while True:
        time.sleep(1)
