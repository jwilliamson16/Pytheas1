"""Library behaviour that changed under Pytheas 1, reproduced as it was.

Each helper keeps an output identical to what the published code produced
on its original stack (pandas 1.4, numpy 1.23). See PORTING.md.
"""
import numpy as np
import pandas as pd


def merge_outer_v1(left, right, on=None):
    """pd.merge(left, right, how='outer') with the row order of pandas < 2.2.

    pandas 2.2 made outer merges sort their keys lexicographically. Before
    that, keys came in order of first appearance in `left`, followed by keys
    found only in `right` in their order of appearance there; within a key,
    left rows kept their order, each followed by its right matches in order.
    Pytheas 1 depends on that order: the final report and the visualization
    list matches in it, and the sequence map drops rows by position after
    merging, so the new order drops the wrong row.
    """
    if on is None:
        on = [c for c in left.columns if c in right.columns]
    elif isinstance(on, str):
        on = [on]
    lpos, rpos, kpos = "__pytheas1_lpos", "__pytheas1_rpos", "__pytheas1_key"
    out = pd.merge(left.assign(**{lpos: np.arange(len(left))}),
                   right.assign(**{rpos: np.arange(len(right))}), on=on, how="outer")
    # number keys in order of first appearance: left, then right-only, as
    # the old factorization did; the output rows take the same numbers
    keys = pd.concat([left[on], right[on], out[on]], ignore_index=True)
    codes = keys.groupby(on, sort=False, dropna=False).ngroup().to_numpy()
    out[kpos] = codes[len(left) + len(right):]
    out = out.sort_values([kpos, lpos, rpos], kind="stable", na_position="last")
    return out.drop(columns=[lpos, rpos, kpos]).reset_index(drop=True)


def series_float(x):
    """float(x) for a one-element Series, as pandas < 2.1 allowed implicitly.

    The original code passes one-row Series to np.float64() and round(). Old
    pandas converted them to a scalar (and raised for a longer Series);
    pandas 3 returns an array, which round() rejects. Scalars pass through.
    """
    if isinstance(x, pd.Series):
        if len(x) != 1:
            raise TypeError(f"cannot convert a Series of length {len(x)} to float")
        return float(x.iloc[0])
    return x
