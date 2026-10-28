# Validation: the pytheas1 package against the published Pytheas

## In short

- **The analysis code is the published code, unchanged in what it computes.**
  - `src/pytheas1/` is the `GUI_version` library code of
    https://github.com/ldascenzo/pytheas at its latest commit (`6dd15c2`). Commit `68b4b79`
    copied it byte for byte.
  - Since then it has been changed only where current Python, numpy, pandas, matplotlib and
    Biopython no longer run it, or would silently change its output. That is 30 added and
    19 removed lines in 7 files, each one listed in [PORTING.md](PORTING.md).
  - **No other changes were made:** no algorithm, scoring, default or parameter change, and
    no bug fixes. Bugs found along the way are logged in
    [KNOWN_ISSUES.md](KNOWN_ISSUES.md), not fixed.
- **What is new is the interface:**
  - pip packaging;
  - a run API and command line that replace the Gooey entry scripts;
  - a PyQt5 GUI with the same options, order and help text as the original Gooey forms.
- **Sp differs from the paper because of the author's own 2022 bug fix,** which is already
  in the upstream code. The identifications are the same. See the next section.

## Sp compared with the paper

The Sp values printed in the paper come from code that predates upstream commit `6d299ca`
(2022-05-02, "Fixed series counting bug").

**The bug.** The test for consecutive ions looked for `c1`, which also matched `c10`, `c11`
and so on. It therefore over-counted consecutive pairs and inflated the β term of Sp. The
fix changed the test to `c1(`.

**Checks:**
- Running Match from the commit before the fix (`6d299ca^`) reproduces the paper's
  Training_set Sp exactly, for 137 of 137 identifications.
- The current upstream code, and so this package, gives Sp a median 3.5% lower than the
  paper's values (0.87 to 1.00 times the paper's value).
- The identifications themselves are unchanged: the same 137 (spectrum, sequence, charge),
  with identical n/L and modification positions.

**One cosmetic difference.** MS1 offsets are printed with one decimal (upstream `c6779fc`,
2021-09-25), not as integer ppm as in the paper.

## The software stack does not change the results

**Two runs compared on the Training_set:**
- the original code, unmodified, on its original stack: Python 3.9, numpy 1.23.1, pandas
  1.4.1, matplotlib 3.5.0, xlrd 1.2.0, Biopython 1.79, pyteomics 4.1.2;
- the package on a current stack.

**Result:**
- identical Sp and n/L for all 137 identifications;
- Match fed the same digest gives identical output.

Decoys differ between the two runs, as they do between any two runs of the original, which
shuffles them at random.

## Stage-by-stage validation

**Method:**
- The original code, on its original stack, made golden outputs for each paper dataset
  (`tools/p1_make_golden.py`, `tools/p1_validate.py`).
- The package then ran each stage on the same inputs on Python 3.12, numpy 2.5, pandas 3.0,
  matplotlib 3.11 and Biopython 1.88, and its outputs were compared with the golden ones.

| dataset | digest | match, stats, report, mapping, visualize |
|---|---|---|
| Training_set | identical target ions | identical |
| Yeast_tRNA | identical | byte-identical |
| Yeast_18S | 99.34% of lines identical | byte-identical |
| Ecoli_16S (QTOF, Orbitrap Lumos, Synapt G2-S) | 99.62% of lines identical | byte-identical |

**The digest differences come from the original code itself.** Where SeqX consolidation
merges isobaric precursors, the original follows Python's set order. It changes as much
between two hash seeds on its own stack as it does against the package.

**Not run:** the SARS-CoV-2 mRNA dataset.

**Details:** [PORTING.md](PORTING.md), "Verification". `pytest` repeats the Training_set
comparison.

## Kept as in the original

- **Decoys** are an unseeded random shuffle. Ranks, dSp and FDR therefore vary a little from
  run to run.
- **Known bugs** are reproduced, not fixed: [KNOWN_ISSUES.md](KNOWN_ISSUES.md).
