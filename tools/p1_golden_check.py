"""Check the pytheas1 package against golden outputs, stage by stage.

Each stage gets exactly the inputs the original code had (copied from the
golden folder), runs through pytheas1.stages.run_stage, and every file it
writes is compared with the golden one:

  exact      byte-identical (after replacing machine-specific paths)
  unordered  the same lines in another order. Accepted only where the
             original's order comes from Python's set/hash order, which
             differs between Python versions even with a fixed hash seed.
  targets    digest: identical target ions; decoys are a random draw, so
             only their number is checked
  names      images: the same files exist (pixels not compared)

usage: python p1_golden_check.py <golden dir> <out dir> [stage ...]
(run with the pytheas1 venv's python)
"""
import collections
import json
import os
import random
import re
import shutil
import sys

# order follows Python set/hash order in the original code -> 'unordered' is acceptable
HASH_ORDERED = ("output.1", "output.2", "output.3.MS2", "seq_output")


def _norm(text, roots):
    for r in roots:
        text = text.replace(r, "<ROOT>")
    return text


def _fnmatch(name, patterns):
    import fnmatch
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def set_order_free(fields):
    """Fields with the items Python lists in set order sorted: SeqX
    alternatives ('|', e.g. sequence_mod) and sequence locations (';').
    No m/z or other numeric field contains either character, so every
    value is still compared as written."""
    out = []
    for x in fields:
        if ";" in x:
            x = ";".join(sorted(x.split(";")))
        if "|" in x:
            x = "|".join(sorted(x.split("|")))
        out.append(x)
    return tuple(out)


def digest_parts(text):
    rows = [l.split() for l in text.splitlines() if l.strip() and not l.startswith("#")]
    head = [l for l in text.splitlines() if l.startswith("#")]
    hdr = rows[0]
    mid = hdr.index("molecule_ID")
    targets = {set_order_free(r[:13]): frozenset(r[13:]) for r in rows[1:] if not r[mid].startswith("decoy")}
    n_decoys = sum(1 for r in rows[1:] if r[mid].startswith("decoy"))
    return head, hdr, targets, n_decoys


def compare_file(name, golden_path, mine_path, roots):
    if name.endswith(".png"):
        return "names", ""
    g = _norm(open(golden_path, errors="replace").read(), roots)
    m = _norm(open(mine_path, errors="replace").read(), roots)
    if name.endswith("_mapping.html"):          # pandas >= 2 no longer writes border="0"
        g = g.replace(' border="0"', "")
        m = m.replace(' border="0"', "")
    if g == m:
        return "exact", ""
    if name.startswith("Digest_"):
        hg, cg, tg, dg = digest_parts(g)
        hm, cm, tm, dm = digest_parts(m)
        problems = []
        if cg != cm:
            problems.append("column header differs")
        if tg.keys() != tm.keys():
            problems.append(f"target precursors differ ({len(tg)} vs {len(tm)})")
        elif any(tg[k] != tm[k] for k in tg):
            problems.append(f"{sum(tg[k] != tm[k] for k in tg)} target ion sets differ")
        if dg != dm:
            problems.append(f"decoy count {dg} vs {dm}")
        if [l for l in hg if not l.startswith(("#TARGETS", "#DECOYS"))] != \
           [l for l in hm if not l.startswith(("#TARGETS", "#DECOYS"))]:
            problems.append("header lines differ")
        return ("targets", f"{len(tg)} target precursors, {dg} decoys") if not problems else ("DIFF", "; ".join(problems))
    if name == "output.3.MS2":                  # consolidated sequences, decoys appended by the decoy step
        gt = collections.Counter(set_order_free(l.split()) for l in g.splitlines() if " decoy " not in l)
        mt = collections.Counter(set_order_free(l.split()) for l in m.splitlines() if " decoy " not in l)
        gd = sum(" decoy " in l for l in g.splitlines())
        md = sum(" decoy " in l for l in m.splitlines())
        if gt == mt and gd == md:
            return "targets", f"{sum(gt.values())} target lines identical, {gd} decoys"
        return "DIFF", f"target lines identical: {gt == mt}; decoys {gd} vs {md}"
    if sorted(g.splitlines()) == sorted(m.splitlines()):
        return ("unordered", "") if _fnmatch(name, HASH_ORDERED) else ("DIFF", "same lines, different order")
    gl, ml = g.splitlines(), m.splitlines()
    first = next((i for i, (a, b) in enumerate(zip(gl, ml)) if a != b), min(len(gl), len(ml)))
    return "DIFF", (f"{len(gl)} vs {len(ml)} lines; first difference at line {first + 1}:\n"
                    f"      golden: {gl[first][:160] if first < len(gl) else '<end>'}\n"
                    f"      mine:   {ml[first][:160] if first < len(ml) else '<end>'}")


def main():
    golden, out = sys.argv[1], sys.argv[2]
    only = sys.argv[3:]
    manifest = json.load(open(os.path.join(golden, "manifest.json")))
    from pytheas1.stages import data_dir, run_stage, StageError
    paper = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "paper_data")
    os.makedirs(out, exist_ok=True)
    seed = 0
    failures = 0
    for stage, g in manifest["stages"].items():
        if only and stage not in only:
            continue
        wd = os.path.join(out, stage)
        if os.path.exists(wd):
            shutil.rmtree(wd)
        os.makedirs(wd)
        gdir = os.path.join(golden, stage)
        for f in g["inputs"]:
            shutil.copy2(os.path.join(gdir, f), os.path.join(wd, f))
        def expand(v):
            if isinstance(v, list):
                return [expand(x) for x in v]
            if isinstance(v, str):
                return (v.replace("@STAGE", wd).replace("@PAPER", paper).replace("@DATA", data_dir())
                        .replace("@TOOLS", os.path.dirname(os.path.abspath(__file__))))
            return v
        params = {k: expand(v) for k, v in g["params"].items()}
        random.seed(seed)
        try:
            rec = run_stage(stage, params, wd)
        except StageError as e:
            print(f"{stage:10s} FAILED  {str(e).splitlines()[0]}")
            failures += 1
            continue
        mine = {os.path.relpath(f, wd) for f in rec["outputs"] if not os.path.relpath(f, wd).startswith("js" + os.sep)}
        theirs = set(g["outputs"])
        print(f"{stage:10s} ok in {rec['seconds']} s")
        for name in sorted(theirs | mine):
            if name not in mine or name not in theirs:
                print(f"    {name:48s} DIFF  only in {'golden' if name in theirs else 'package'}")
                failures += 1
                continue
            if name.startswith("scored_spectra"):
                continue
            verdict, detail = compare_file(os.path.basename(name), os.path.join(gdir, name), os.path.join(wd, name),
                                           roots=[gdir, wd, paper, data_dir(), os.path.dirname(os.path.abspath(__file__))])
            if verdict == "DIFF":
                failures += 1
            print(f"    {name:48s} {verdict}  {detail}")
        spectra = sorted(n for n in theirs if n.startswith("scored_spectra"))
        if spectra:
            same = all(n in mine for n in spectra)
            print(f"    {'scored_spectra_*/ (' + str(len(spectra)) + ' images)':48s} {'names' if same else 'DIFF'}")
    print(f"\n{failures} difference(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
