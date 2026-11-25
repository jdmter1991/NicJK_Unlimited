"""Blender: run several of the read-only tool scripts in one session (loading the scene takes minutes).
  blender -b --factory-startup --disable-autoexec <file.blend> --python blender_batch.py -- <jobs.json>
jobs.json: [["script.py", "arg1", "arg2", ...], ...]; each script sees its own arguments after "--"."""
import sys, json, os, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
jobs = json.load(open(sys.argv[sys.argv.index("--") + 1]))
base = sys.argv[:sys.argv.index("--") + 1]
for job in jobs:
    sys.argv = base + job[1:]
    print("BATCH start", job[0], flush=True)
    try:
        src = open(os.path.join(HERE, job[0]), encoding="utf-8").read()
        exec(compile(src, job[0], "exec"), {"__name__": "__main__", "__file__": os.path.join(HERE, job[0])})
    except SystemExit:
        pass
    except Exception:
        print("BATCH failed", job[0]); traceback.print_exc()
print("BATCH done")
