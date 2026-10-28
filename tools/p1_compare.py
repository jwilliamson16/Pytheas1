"""Compare two Pytheas 1 job folders file by file.

Text outputs are compared exactly first. When they differ, digest files are
compared as sets of ions per precursor (ion order follows Python's set
ordering), and CSV tables cell by cell with a numeric tolerance.

usage: python p1_compare.py <job A> <job B> [--tol 1e-9]
"""
import os
import sys

import pandas as pd

a_dir, b_dir = sys.argv[1], sys.argv[2]
tol = float(sys.argv[sys.argv.index("--tol") + 1]) if "--tol" in sys.argv else 1e-9
SKIP_EXT = (".png", ".html", ".log", ".json", ".js")


def listing(d):
    out = {}
    for root, _, files in os.walk(d):
        rel_root = os.path.relpath(root, d)
        if rel_root.split(os.sep)[0] == "js":
            continue
        for f in files:
            rel = os.path.normpath(os.path.join(rel_root, f))
            if not f.startswith("_") and not f.endswith(SKIP_EXT):
                out[rel] = os.path.join(root, f)
    return out


def digest_ions(path):
    rows = [l.split() for l in open(path) if not l.startswith("#") and l.strip()]
    hdr = rows[0]
    first_ion = hdr.index("CID_series_fragment_masses") if "CID_series_fragment_masses" in hdr else 13
    return {tuple(r[:first_ion]): frozenset(r[first_ion:]) for r in rows[1:]}, [l for l in open(path) if l.startswith("#")]


def compare_csv(pa, pb):
    da, db = pd.read_csv(pa), pd.read_csv(pb)
    if list(da.columns) != list(db.columns) or da.shape != db.shape:
        return f"shape/columns differ {da.shape} vs {db.shape}"
    worst, ncell = 0.0, 0
    for c in da.columns:
        x, y = da[c], db[c]
        if pd.api.types.is_numeric_dtype(x) and pd.api.types.is_numeric_dtype(y):
            d = (x - y).abs()
            both_nan = x.isna() & y.isna()
            bad = (d > tol) & ~both_nan
            ncell += int(bad.sum())
            if bad.any():
                worst = max(worst, float(d[bad].max()))
        else:
            ncell += int(((x != y) & ~(x.isna() & y.isna())).sum())
    return "equal within tol" if ncell == 0 else f"{ncell} cells differ (max numeric diff {worst:g})"


A, B = listing(a_dir), listing(b_dir)
for rel in sorted(set(A) | set(B)):
    if rel not in A or rel not in B:
        print(f"{rel:55s} only in {'A' if rel in A else 'B'}")
        continue
    ta, tb = open(A[rel], "rb").read(), open(B[rel], "rb").read()
    if ta == tb:
        print(f"{rel:55s} byte-identical")
        continue
    if os.path.basename(rel).startswith("Digest_"):
        (ia, ha), (ib, hb) = digest_ions(A[rel]), digest_ions(B[rel])
        same_prec = ia.keys() == ib.keys()
        same_ions = sum(ia[k] == ib.get(k) for k in ia)
        print(f"{rel:55s} differs as text; precursors identical={same_prec}, ion sets identical {same_ions}/{len(ia)}")
    elif rel.endswith(".csv"):
        print(f"{rel:55s} differs as text; {compare_csv(A[rel], B[rel])}")
    else:
        la, lb = ta.decode(errors="replace").splitlines(), tb.decode(errors="replace").splitlines()
        nd = sum(x != y for x, y in zip(la, lb)) + abs(len(la) - len(lb))
        same_sorted = sorted(la) == sorted(lb)
        print(f"{rel:55s} differs as text; {nd} of {max(len(la), len(lb))} lines differ"
              f"{' (same lines, different order)' if same_sorted else ''}")
