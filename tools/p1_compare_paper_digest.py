"""Compare a digest with a published paper_data digest, target lines only.

Lines are compared field by field, with the parts whose order follows
Python's set order normalised: SeqX alternatives in sequence_mod ('|'),
sequence locations (';') and the set of MS2 ions. Decoys are a random draw
and are only counted.

usage: python p1_compare_paper_digest.py <our digest> <published digest>
"""
import collections
import sys


def load(path):
    rows = [l.split() for l in open(path) if l.strip() and not l.startswith("#")]
    hdr = rows[0]
    mid = hdr.index("molecule_ID")
    targets, decoys = collections.Counter(), 0
    for r in rows[1:]:
        if r[mid].startswith("decoy"):
            decoys += 1
            continue
        head = list(r[:13])
        head[8] = "|".join(sorted(head[8].split("|")))
        head[12] = ";".join(sorted(head[12].split(";")))
        targets[(tuple(head), frozenset(r[13:]))] += 1
    return hdr[:13], targets, decoys


def main():
    ho, o, od = load(sys.argv[1])
    hp, p, pd_ = load(sys.argv[2])
    same = sum((o & p).values())
    print(f"target lines: ours {sum(o.values())}, published {sum(p.values())}, identical {same}"
          f" ({100 * same / max(1, sum(p.values())):.2f}% of published); decoys ours {od}, published {pd_}")
    if ho != hp:
        print("  column headers differ")
    for label, extra in (("only ours", o - p), ("only published", p - o)):
        if extra:
            print(f"  {label}: {sum(extra.values())}")
            for (head, ions), _ in list(extra.items())[:3]:
                print(f"    {' '.join(head[:11])}  ({len(ions)} ions)")
    return 0 if same == sum(p.values()) == sum(o.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
