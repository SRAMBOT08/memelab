# run_debug.py
import runpy, traceback, time, sys, os

SCRIPT = "kafka_consumer_worker.py"   # <--- change this to the script that is exiting (the file you start in terminal C)

print("DEBUG WRAPPER: cwd=", os.getcwd(), "running", SCRIPT, flush=True)
try:
    runpy.run_path(SCRIPT, run_name="__main__")
    print("Script finished normally.", flush=True)
except SystemExit as e:
    print("Script called SystemExit:", e, file=sys.stderr, flush=True)
    traceback.print_exc()
    # don't exit immediately — pause so you can read
    print("Paused after SystemExit. Press Ctrl+C to exit.", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
except Exception:
    print("Unhandled exception:", file=sys.stderr, flush=True)
    traceback.print_exc()
    print("Paused after exception. Press Ctrl+C to exit.", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
