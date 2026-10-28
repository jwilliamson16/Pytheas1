Charge tables reconstructed from published `paper_data` digests, for datasets
whose tables are not in the repo. Each table lists, for every fragment
length, every charge that appears in the published digest's target lines
(MS1: precursor charge by sequence length; MS2: fragment-ion charge by ion
length). A charge that the m/z window always excluded cannot be recovered
this way, and leaving it out does not change the output.

- `charges_MS1_tRNA_yeast_paper.txt`, `charges_MS2_tRNA_yeast_paper.txt`:
  from `paper_data/Yeast_tRNA/Digest_MS2_tRNA_yeast.txt`.

The file names must contain "MS1" or "MS2": Pytheas 1's `charge_table()`
decides which kind of table it is reading from the name.
