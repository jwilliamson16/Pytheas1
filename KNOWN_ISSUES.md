# Known issues

Bugs found in Pytheas 1 during the refresh. They are logged here, not
fixed: the package reproduces the published program, bugs included (see
VALIDATION.md).

## 1. Two nucleotides share the letter `o` in the shipped nucleotide sheets

Found 2026-10-23, in a search of human rRNA (NASE, PXD016323).

**What:** `nts_light.xlsx` and `nts_heavy.xlsx` give the one-letter ID `o`
to both m1acp3Y (1-methyl-3-(3-amino-3-carboxypropyl)pseudouridine) and t6A
(N6-threonylcarbamoyladenosine). The digest builds its letter-to-name and
letter-to-mass dictionaries row by row, so the later row, t6A, wins.

**Effect:** a modification file that places m1acp3Y (`o`) gets t6A's mass
and the `[t6A]` label at that position: residue C15H19N6O10P (474.09 Da)
instead of C14H20N3O10P (421.09 Da), 53.0 Da heavy. Fragments containing it
cannot match. Placing t6A works as intended. Human 18S m1acp3Y1248 is the
common case; yeast 18S has m1acp3Y1191.

`h` is also listed twice, as two identical [ho5C] rows, which is harmless.

**Where:** every copy of the default sheets:
- `src/pytheas1/data/nts_light.xlsx`, `nts_heavy.xlsx` (the package defaults);
- `GUI_version/` and `CL_version/in_silico_digestion/nts_light.xlsx`,
  `nts_heavy.xlsx` (the original program);
- `tools/datasets/nts/*_std_reconstructed.xlsx`.

The paper's own per-dataset sheets in `paper_data/` (Yeast_18S, Yeast_tRNA)
have no duplicate letters, so the published results are not affected.

**Workaround:** in a copy of the sheet, delete the row you don't need, or
give one of the two an unused letter. For human rRNA, for example, use a copy
without the t6A row.
