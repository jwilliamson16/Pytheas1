# Porting notes: the pytheas1 package vs the published code

The analysis code in `src/pytheas1/` is the `GUI_version` library code of
https://github.com/ldascenzo/pytheas (MIT, (c) 2021 Luigi D'Ascenzo). Commit
`68b4b79` copied it byte for byte, with the original module names. Every
change since is listed below. All of them are needed to run on current
libraries without changing results, and together they are 30 added and 19
removed lines in 7 files (`git diff 68b4b79 -- 'src/pytheas1/*/*'`).

The algorithms are unchanged. The package is the current upstream code,
including the author's 2022 fix to consecutive-series counting (`6d299ca`),
which lowers Sp by a median 3.5% against the values printed in the paper;
see VALIDATION.md. Decoys stay random, as in the original.

## Changes to the library code

**Imports.** These now import within the package:
- `calc_mass_gui.py`: `from . import consolidate_tools`.
- `match_library.py`: `from . import stats_tools`.
- `statistics_library.py`: `from ..matching_scoring import stats_tools`. The
  original shipped a second, identical copy of `stats_tools.py` with this
  stage.

**APIs removed from Python and its libraries.** Each replacement behaves
the same:

| change | file(s) | removed in |
|---|---|---|
| `np.warnings`, `np.VisibleDeprecationWarning` -> `warnings`, `np.exceptions.VisibleDeprecationWarning` | `stats_tools.py` | numpy 1.24 / 2.0 |
| `open(..., 'rU')` -> `'r'` | `stats_tools.py` | Python 3.11 |
| `Series.iteritems()` -> `.items()` | `mapping_library.py` | pandas 2.0 |
| `Seq.ungap("-")` -> `str(seq).replace("-", "")` | `mapping_library.py` | Biopython 1.80+ |
| `np.round_` -> `np.round` | `visualization_library.py` | numpy 2.0 |
| plot-title mathtext `$\it{}$` -> `$\mathit{{{}}}$` | `visualization_library.py` | rejected by current matplotlib |
| regex / mathtext literals made raw (`r"[\d]+..."`) | `stats_tools.py`, `visualization_library.py` | invalid escapes warn from Python 3.12 and will become errors |

**Library behaviour that changed, reproduced as it was.** These helpers live
in `_compat.py`:
- `merge_outer_v1()` replaces all four `pd.merge(..., how='outer')` calls:
  final report, match statistics, sequence mapping and visualization. Since
  pandas 2.2 an outer merge sorts its keys as text. Before, keys came in
  order of first appearance (left, then right-only). The original order
  matters:
  - the final report and match tables list rows in it;
  - `mapping_library.merge_dataframes()` drops rows by position after
    merging, so under pandas >= 2.2 the sequence map showed residue numbers
    where the nucleotides belong.

  Checked against pandas 1.4.1 on 269 random merges, including multi-column
  merges and duplicate keys: identical.
- `series_float()`: the visualization passes one-row Series to `np.float64()`
  and `round()`. Old pandas converted them to a number (and raised for longer
  Series); pandas 3 returns an array, which `round()` rejects.

## New code (not in the original)

- `stages.py`: the run API, replacing the Gooey entry scripts.
  - `DEFAULTS` reproduces the six argparse definitions exactly, types
    included.
  - `run_stage()` runs a stage with the job folder as current directory
    (the library reads and writes relative to it) and turns the library's
    `sys.exit()` and exceptions into `StageError`.
  - Bare input-file names fall back to files bundled in `data/`.
  - `chain_inputs()` fills a stage's unset inputs from the stages before it.
- `params.py`: one JSON parameter file for all six stages.
- `cli.py`: `pytheas1 --nogui --load_vars --params FILE --digest --match ... | --all`,
  and `--write_params FILE`. Without `--nogui` it opens the GUI.
- `data/`: `nts_light.xlsx`, `nts_heavy.xlsx`, the charge tables, the
  modification template and the `js/` assets for the HTML outputs, copied
  from the original stage folders.

## Verification

`tests/` runs each package stage on exactly the inputs the original code had
and compares every output with golden files. The golden files come from the
original code on its original stack (Python 3.9, pandas 1.4.1, numpy 1.23.1,
matplotlib 3.5.0, xlrd 1.2.0, Biopython 1.79, pyteomics 4.1.2;
`tools/p1_make_golden.py`). FutureWarnings are turned into errors.

On Python 3.12.8, numpy 2.5.4, pandas 3.0.6, matplotlib 3.11.2 and
Biopython 1.88, for the Training_set:

| stage | result |
|---|---|
| digest | identical target ions (95 precursors, identical ion sets), 92 decoys; `nts_light.csv`, `seq_output` byte-identical |
| match | match output, targets, decoys, FDR and log byte-identical |
| stats | the same plots produced (pixels not compared) |
| report | final report byte-identical |
| mapping | `mapping_output.csv` and the mapping HTML identical (pandas no longer writes `border="0"` on tables) |
| visualize | visualization HTML byte-identical; the same 137 spectrum images produced |

Expected differences, inherited from the original:
- `output.1` and `output.2` (digest intermediates) list the same lines in
  Python's set order, which varies between Python versions even with a
  fixed `PYTHONHASHSEED`.
- Decoys are a random shuffle, so digest decoys, and with them ranks, dSp
  and FDR, vary from run to run, exactly as in the original.
- **Where SeqX consolidation merges precursors, the final digest depends on
  Python's set order.** `mz_consolidate()` walks the lines in that order and
  keeps the m/z text of the first line it reaches. Isobaric anagrams can
  differ in the last printed digit (`1128.137725360` against `...361`), so
  the order decides which ones merge. The original code does this on its
  own stack. On Yeast_18S, the original on Python 3.9 gives 4516 target
  lines at `PYTHONHASHSEED=0` and 4514 at 1, 99.42% identical. The package
  on Python 3.12 gives 4514, 99.34% identical to seed 0 and 99.60% to seed 1.
  The input to consolidation (`output.3.MS2`) is identical, and so is
  everything downstream when it is fed the same digest.
- Several fields list items in set order: SeqX alternatives (`|`) and
  sequence locations (`;`). `tools/p1_golden_check.py` sorts the items in
  those fields before comparing and compares everything else as written.

The other paper datasets go through `tools/p1_validate.py`: a golden run
of the original code, then the package stage by stage on the golden
inputs.

| dataset | digest | match, stats, report, mapping, visualize |
|---|---|---|
| Yeast_tRNA | 7283 target lines identical | byte-identical (3257 spectrum images produced) |
| Yeast_18S | 99.34%, set-order consolidation (above) | byte-identical (5321 spectrum images produced) |
| Ecoli_16S, QTOF | 99.62% (5177 of 5197), set-order consolidation | byte-identical (2899 spectrum images produced) |
| Ecoli_16S, Orbitrap Lumos | same digest as QTOF | byte-identical (2255 spectrum images produced) |
| Ecoli_16S, Synapt G2-S | same digest as QTOF | byte-identical (1403 spectrum images produced) |

In every dataset the input to consolidation (`output.3.MS2`) is identical.
The digest differences are all heavy-channel SeqX merges of isobaric
anagrams. That they come from set order was tested on Yeast_18S only (the
seed comparison above); Ecoli_16S shows the same pattern.

Run the tests with `pytest` (about 3 minutes, all stages) or
`pytest -m "not slow"` (seconds; skips Match and visualization).
