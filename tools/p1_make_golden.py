"""Make golden outputs: the original Pytheas 1 code, one stage at a time.

Each stage runs in its own folder, with its input files copied in from the
previous stages' folders (as a user of the original scripts would have had
them), PYTHONHASHSEED and the decoy seed fixed. manifest.json records, per
stage, the parameters, the input files and the files the stage wrote.

usage: python p1_make_golden.py <python> <GUI_version dir> <dataset.json> <out dir>
                                [--stages digest,match,...] [--prune]
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.join(HERE, "p1_run_stage.py")
STAGES = ("digest", "match", "stats", "report", "mapping", "visualize")

# which earlier output feeds which input: (stage, param) -> (earlier stage, filename glob)
CHAIN = {
    ("match", "Theoretical_digest"): ("digest", "Digest_*.txt"),
    ("stats", "Targets"): ("match", "targets_*.csv"),
    ("stats", "Decoys"): ("match", "decoys_*.csv"),
    ("stats", "Match_output"): ("match", "match_output_*.txt"),
    ("report", "Match_output"): ("match", "match_output_*.txt"),
    ("mapping", "Final_report"): ("report", "final_report_*.csv"),
    ("visualize", "Theoretical_digest"): ("digest", "Digest_*.txt"),
    ("visualize", "Match_output"): ("match", "match_output_*.txt"),
}


REPO = os.path.dirname(HERE)


def expand(value, data_dir):
    """@PAPER -> the repo's paper_data, @DATA -> the folder holding nts/charge files."""
    if isinstance(value, str):
        return (value.replace("@PAPER", os.path.join(REPO, "paper_data")).replace("@DATA", data_dir)
                .replace("@TOOLS", HERE))
    if isinstance(value, list):
        return [expand(v, data_dir) for v in value]
    return value


def snapshot(folder):
    out = {}
    for root, _, files in os.walk(folder):
        for f in files:
            p = os.path.join(root, f)
            out[os.path.relpath(p, folder)] = os.stat(p).st_mtime_ns
    return out


def main():
    py, code, dataset_path, out = sys.argv[1], os.path.abspath(sys.argv[2]), sys.argv[3], os.path.abspath(sys.argv[4])
    dataset = json.load(open(dataset_path))
    os.makedirs(out, exist_ok=False)
    manifest = {"dataset": os.path.basename(dataset_path), "seed": dataset.get("seed", 0),
                "hashseed": dataset.get("hashseed", 0), "stages": {}}
    import fnmatch
    only = sys.argv[sys.argv.index("--stages") + 1].split(",") if "--stages" in sys.argv else STAGES
    for stage in STAGES:
        if stage not in dataset["stages"] or stage not in only:
            continue
        wd = os.path.join(out, stage)
        os.makedirs(wd)
        params = {k: expand(v, os.path.join(os.path.abspath(code), "in_silico_digestion"))
                  for k, v in dataset["stages"][stage].items()}
        inputs = []
        for (st, key), (src_stage, pattern) in CHAIN.items():
            if st != stage or params.get(key) not in (None, "auto"):
                continue
            src_dir = os.path.join(out, src_stage)
            produced = manifest["stages"][src_stage]["outputs"]
            hits = sorted(f for f in produced if fnmatch.fnmatch(os.path.basename(f), pattern)
                          and os.path.basename(f) != "Digest_MS1.txt")
            if len(hits) != 1:
                raise SystemExit(f"{stage}.{key}: expected one {pattern} from {src_stage}, got {hits}")
            shutil.copy2(os.path.join(src_dir, hits[0]), os.path.join(wd, os.path.basename(hits[0])))
            params[key] = os.path.join(wd, os.path.basename(hits[0]))
            inputs.append(os.path.basename(hits[0]))
        if stage in ("mapping", "visualize"):
            shutil.copytree(os.path.join(code, "sequence_mapping", "js"), os.path.join(wd, "js"))
        before = snapshot(wd)
        env = dict(os.environ, PYTHONHASHSEED=str(dataset.get("hashseed", 0)))
        p = subprocess.run([py, DRIVER, "--code", code, "--stage", stage, "--workdir", wd, "--args", json.dumps(params),
                            "--seed", str(dataset.get("seed", 0))], capture_output=True, text=True, env=env)
        open(os.path.join(out, f"{stage}.log"), "w").write(p.stdout + "\n--- stderr ---\n" + p.stderr)
        res = [l for l in p.stdout.splitlines() if l.startswith("P1_STAGE_RESULT ")]
        res = json.loads(res[-1][16:]) if res else {"status": "crash", "error": p.stderr[-1500:]}
        after = snapshot(wd)
        outputs = sorted(f for f, m in after.items() if before.get(f) != m and not f.startswith("js" + os.sep))
        data_dir = os.path.join(os.path.abspath(code), "in_silico_digestion")

        def portable(v):
            if isinstance(v, list):
                return [portable(x) for x in v]
            if isinstance(v, str):
                return (v.replace(wd, "@STAGE").replace(os.path.join(REPO, "paper_data"), "@PAPER")
                        .replace(data_dir, "@DATA").replace(HERE, "@TOOLS"))
            return v
        manifest["stages"][stage] = {"params": {k: portable(v) for k, v in params.items()},
                                     "inputs": inputs, "outputs": outputs,
                                     "status": res["status"], "seconds": res.get("seconds")}
        print(f"{stage:10s} {res['status']:6s} {res.get('seconds')}s  {len(outputs)} outputs", flush=True)
        if res["status"] != "ok":
            print(res.get("error"))
            break
    json.dump(manifest, open(os.path.join(out, "manifest.json"), "w"), indent=1)
    if "--prune" in sys.argv:
        prune(out, os.path.join(code, "in_silico_digestion"))


def prune(out, data_dir):
    """Make the golden folder fit to commit: drop images (only their names
    are checked), copied js/ folders and stage logs, and replace the absolute
    paths the original code writes into its outputs with <ROOT>, the token
    p1_golden_check.py normalises to."""
    for stage in STAGES:
        wd = os.path.join(out, stage)
        if not os.path.isdir(wd):
            continue
        for d in os.listdir(wd):
            path = os.path.join(wd, d)
            if os.path.isdir(path) and (d == "js" or d.startswith("scored_spectra")):
                shutil.rmtree(path)
        for root, _, files in os.walk(wd):
            for f in files:
                path = os.path.join(root, f)
                if f.endswith(".png"):
                    os.remove(path)
                    continue
                text = open(path, errors="surrogateescape").read()
                new = text
                roots = [os.path.join(out, st) for st in STAGES] + [out, os.path.join(REPO, "paper_data"),
                                                                    os.path.abspath(data_dir), HERE]
                for r in sorted(roots, key=len, reverse=True):
                    new = new.replace(r, "<ROOT>")
                if new != text:
                    open(path, "w", errors="surrogateescape").write(new)
        log = os.path.join(out, f"{stage}.log")
        if os.path.exists(log):
            os.remove(log)


if __name__ == "__main__":
    main()
