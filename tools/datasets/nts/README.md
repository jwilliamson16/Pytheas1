Nucleotide sheets reconstructed for paper_data sets whose sheets are not in
the repo.

- `nts_light_std_reconstructed.xlsx`, `nts_heavy_std_reconstructed.xlsx`:
  for Ecoli_16S. The published digest names `nts_alphabet_light_std.xlsx`
  and `nts_alphabet_heavy_std.xlsx`, which were never shipped. In the shipped
  `nts_light.xlsx`, `m` is mcm5s2U, but `modfile_16S_paper.txt` uses `m`
  for m5C (positions 967 and 1407). These are the shipped sheets with that
  one row changed to m5C (base C5 O1 H6 N3, i.e. cytidine + CH2; the heavy
  sheet has all three N as 15N, like its cytidine row). The composition
  agrees with the m5C row of `paper_data/Yeast_18S/nts_alphabet_5.6DU_light.xlsx`
  once that sheet's deuterium is taken out. Edited with openpyxl; every
  other row is unchanged.
