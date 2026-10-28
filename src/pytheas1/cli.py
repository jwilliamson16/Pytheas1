"""pytheas1 command line.

    pytheas1                                          open the GUI
    pytheas1 --nogui --load_vars --params run.json --digest --match
    pytheas1 --nogui --load_vars --params run.json --all
    pytheas1 --write_params template.json             every setting, at its default

Stages always run in workflow order (digest, match, stats, report, mapping,
visualize), whatever order the flags are given in, and stop at the first
failure. Inputs left unset chain from the stages run before them.
"""
import argparse
import datetime
import json
import os
import platform
import sys

from . import __version__
from .params import default_params, load_params, save_params
from .stages import RUNS_DIR, STAGES, TITLES, StageError, chain_inputs, run_stage

DEFAULT_PARAMS_FILE = "pytheas1_parameters.json"


def _versions():
    import Bio
    import matplotlib
    import numpy
    import pandas
    return {"pytheas1": __version__, "python": platform.python_version(), "numpy": numpy.__version__,
            "pandas": pandas.__version__, "matplotlib": matplotlib.__version__, "biopython": Bio.__version__}


def run_pipeline(params, stages, workdir, records, echo=print):
    """Run the given stages in workflow order, appending one record per stage
    to `records` (a failed stage is recorded too, then StageError is raised)."""
    for stage in [s for s in STAGES if s in stages]:
        stage_params = chain_inputs(stage, params.get(stage, {}), workdir, records, settings=params)
        echo(f"\n=== {TITLES[stage]} ===", flush=True)
        try:
            rec = run_stage(stage, stage_params, workdir)
        except StageError as e:
            records.append({"stage": stage, "status": "failed", "error": str(e), "outputs": [], "params": stage_params})
            raise
        rec["status"] = "ok"
        records.append(rec)
        echo(f"=== {TITLES[stage]}: done in {rec['seconds']} s, {len(rec['outputs'])} file(s) written ===", flush=True)


class _Tee:
    """Write to the console and to the run's log file."""

    def __init__(self, stream, log):
        self.stream, self.log = stream, log

    def write(self, text):
        self.stream.write(text)
        self.log.write(text)
        return len(text)

    def flush(self):
        self.stream.flush()
        self.log.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


def _run_paths(workdir):
    """<workdir>/pytheas1_runs/<time>.json and .log, unique even within a second."""
    folder = os.path.join(workdir, RUNS_DIR)
    os.makedirs(folder, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    base, i = os.path.join(folder, stamp), 1
    while os.path.exists(base + ".json") or os.path.exists(base + ".log"):
        i += 1
        base = os.path.join(folder, f"{stamp}-{i}")
    return base + ".json", base + ".log"


def _write_record(path, params_path, log_path, records):
    with open(path, "w") as fh:
        json.dump({"params_file": params_path, "log": log_path, "versions": _versions(), "stages": records},
                  fh, indent=2, default=str)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pytheas1", description="Pytheas 1: RNA MS/MS analysis")
    ap.add_argument("--nogui", action="store_true", help="run from the command line, without the GUI")
    ap.add_argument("--load_vars", action="store_true",
                    help=f"load settings from --params (default: {DEFAULT_PARAMS_FILE} in the working folder)")
    ap.add_argument("--params", help="Pytheas 1 parameter file (JSON)")
    ap.add_argument("--workdir", help="working folder for inputs and outputs (overrides the file's working_dir)")
    for stage in STAGES:
        ap.add_argument(f"--{stage}", action="store_true", help=f"run {TITLES[stage]}")
    ap.add_argument("--all", action="store_true", help="run all six stages")
    ap.add_argument("--write_params", metavar="FILE", help="write a parameter file with every default, then exit")
    ap.add_argument("--version", action="version", version=f"pytheas1 {__version__}")
    args = ap.parse_args(argv)

    if args.write_params:
        save_params(default_params(), args.write_params, only_changed=False)
        print(f"wrote {args.write_params}")
        return 0

    if not args.nogui:
        try:
            from .gui import main as gui_main
        except ImportError as e:
            print(f"The GUI could not be started ({e}). Use --nogui.", file=sys.stderr)
            return 2
        return gui_main(args)

    stages = [s for s in STAGES if args.all or getattr(args, s)]
    if not stages:
        ap.error("--nogui: choose stages (" + " ".join(f"--{s}" for s in STAGES) + ") or --all")

    params_path = args.params
    if params_path is None and args.load_vars:
        params_path = os.path.join(args.workdir or os.getcwd(), DEFAULT_PARAMS_FILE)
    if params_path is None:
        ap.error("--nogui needs settings: --load_vars --params FILE")
    try:
        params = load_params(params_path)
    except (OSError, ValueError) as e:
        print(f"pytheas1: {e}", file=sys.stderr)
        return 2
    workdir = os.path.abspath(args.workdir or params.get("working_dir") or os.getcwd())

    records = []
    status = 0
    record_path, log_path = _run_paths(workdir)
    out, err = sys.stdout, sys.stderr
    with open(log_path, "w") as log:
        sys.stdout, sys.stderr = _Tee(out, log), _Tee(err, log)
        try:
            print(f"pytheas1 {__version__}: {', '.join(stages)} in {workdir}, settings {os.path.abspath(params_path)}")
            run_pipeline(params, stages, workdir, records)
        except StageError as e:
            print(f"\npytheas1: {e}", file=sys.stderr)
            status = 1
        finally:
            sys.stdout.flush()
            sys.stdout, sys.stderr = out, err
    _write_record(record_path, os.path.abspath(params_path), log_path, records)
    print(f"\nrun record: {record_path}\nlog: {log_path}")
    return status


if __name__ == "__main__":
    sys.exit(main())
