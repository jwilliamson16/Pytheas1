"""Validate the package on several datasets: golden run, then package check.

For each dataset, in parallel up to --jobs at a time:
  1. golden  -- the original code in the reference environment, stage by stage
               (p1_make_golden.py); skipped if a complete golden folder exists
  2. check   -- the package on the same inputs (p1_golden_check.py), with
               FutureWarnings as errors
Results go to <out>/<dataset>/{golden,check,golden.out,check.out}; a summary
table is printed at the end and written to <out>/summary.txt.

usage: python p1_validate.py --ref_python PY --pkg_python PY --out DIR [--jobs N] dataset.json ...
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def golden_complete(gdir):
    m = os.path.join(gdir, "manifest.json")
    if not os.path.exists(m):
        return False
    stages = json.load(open(m))["stages"]
    return len(stages) == 6 and all(s["status"] == "ok" for s in stages.values())


def run_one(ds_path, args):
    name = os.path.splitext(os.path.basename(ds_path))[0]
    base = os.path.join(args.out, name)
    os.makedirs(base, exist_ok=True)
    gdir, cdir = os.path.join(base, "golden"), os.path.join(base, "check")
    t0 = time.time()
    if not golden_complete(gdir):
        if os.path.exists(gdir):
            os.rename(gdir, gdir + f".incomplete.{int(t0)}")
        with open(os.path.join(base, "golden.out"), "w") as fh:
            subprocess.run([sys.executable, os.path.join(HERE, "p1_make_golden.py"), args.ref_python,
                            os.path.join(REPO, "GUI_version"), ds_path, gdir], stdout=fh, stderr=subprocess.STDOUT)
    t1 = time.time()
    if not golden_complete(gdir):
        return name, {"golden": "FAILED", "golden_s": round(t1 - t0)}
    with open(os.path.join(base, "check.out"), "w") as fh:
        subprocess.run([args.pkg_python, "-W", "error::FutureWarning", os.path.join(HERE, "p1_golden_check.py"),
                        gdir, cdir], stdout=fh, stderr=subprocess.STDOUT, env=dict(os.environ, PYTHONHASHSEED="0"))
    t2 = time.time()
    text = open(os.path.join(base, "check.out")).read()
    verdicts = {}
    for v in ("exact", "unordered", "targets", "names", "DIFF"):
        verdicts[v] = len(re.findall(rf"^\s{{4}}\S.*\s{v}\b", text, flags=re.M))
    nd = re.search(r"^(\d+) difference\(s\)", text, flags=re.M)
    golden_secs = {s: r["seconds"] for s, r in json.load(open(os.path.join(gdir, "manifest.json")))["stages"].items()}
    return name, {"golden": "ok", "golden_s": round(t1 - t0), "check_s": round(t2 - t1), "golden_stage_s": golden_secs,
                  "differences": int(nd.group(1)) if nd else None, "verdicts": verdicts,
                  "failed_stages": re.findall(r"^(\w+)\s+FAILED", text, flags=re.M)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref_python", required=True)
    ap.add_argument("--pkg_python", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("datasets", nargs="+")
    args = ap.parse_args()
    args.out = os.path.abspath(args.out)
    os.makedirs(args.out, exist_ok=True)
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = dict(pool.map(lambda d: run_one(os.path.abspath(d), args), args.datasets))
    lines = [f"{'dataset':24s} {'golden':7s} {'golden min':>10s} {'check min':>9s} {'differences':>11s}  verdicts"]
    for name, r in results.items():
        lines.append(f"{name:24s} {r['golden']:7s} {r['golden_s'] / 60:10.1f} {r.get('check_s', 0) / 60:9.1f} "
                     f"{str(r.get('differences')):>11s}  {r.get('verdicts', '')} {r.get('failed_stages') or ''}")
    text = "\n".join(lines)
    print(text)
    open(os.path.join(args.out, "summary.txt"), "w").write(text + "\n")
    json.dump(results, open(os.path.join(args.out, "summary.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
