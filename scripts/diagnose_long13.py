#!/usr/bin/env python3
"""Diagnostic: why does DAQ1 long-13 show 242 frame_num drops when its
timestamp-method count is only 2?

Compares long-13 against a clean reference chunk (long-8, which both methods
agree on — 2 timestamp drops, 0 frame_num drops) along several axes:

  1. Corruption rate (sentinels vs within-range anomalies)
  2. Distribution of "missing" frame_nums — clustered (real loss) or scattered
     (corruption-induced artefacts)?
  3. Buffers-per-frame histogram — are frames in long-13 systematically
     short on buffers? That would suggest real loss.
  4. Whether the "missing" frame_nums are near the file boundaries (first/last
     20 rows) vs. in the middle
  5. Whether any within-range values outside [fn_start, fn_end] suggest
     corruption we're missing
"""

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import analyze_frame_num_drops as afd


BASE = "/Users/mbrosch/Documents/9h_long_recording_December2025"
LONG13 = os.path.join(BASE, "neural_DAQ1/WL27_DAQ1_25_12_10_long-13.csv")
LONG8 = os.path.join(BASE, "neural_DAQ1/WL27_DAQ1_25_12_10_long-8.csv")


def diagnose(path, label):
    print(f"\n{'=' * 70}")
    print(f"{label}: {os.path.basename(path)}")
    print(f"{'=' * 70}")

    df = pd.read_csv(
        path,
        usecols=[
            "frame_num",
            "reconstructed_frame_index",
            "buffer_count",
            "frame_buffer_count",
        ],
    )
    total_rows = len(df)

    # 1. Corruption rate
    mask = afd.valid_mask(df["frame_num"])
    n_filtered = int((~mask).sum())
    valid = df[mask].copy()
    print(f"\n1. Corruption:")
    print(f"   Total rows:      {total_rows:>10,}")
    print(f"   Filtered rows:   {n_filtered:>10,}  ({100 * n_filtered / total_rows:.4f}%)")
    print(f"   Filtered values (unique): "
          f"{df.loc[~mask, 'frame_num'].nunique()}")
    bad_samples = df.loc[~mask, "frame_num"].head(5).tolist()
    print(f"   Sample filtered: {bad_samples}")

    # Window pick
    fn_start, fn_end, head_raw, tail_raw = afd.pick_start_end(df["frame_num"])
    print(f"\n2. Window pick:")
    print(f"   fn_start:        {fn_start}")
    print(f"   fn_end:          {fn_end}")
    print(f"   head (first 5 frame_num):  {head_raw[:5]}")
    print(f"   tail (last 5 frame_num):   {tail_raw[-5:]}")

    # 3. Within-range valid frame_num stats
    vfn = valid["frame_num"]
    print(f"\n3. Valid frame_num distribution:")
    print(f"   min:             {int(vfn.min())}")
    print(f"   max:             {int(vfn.max())}")
    print(f"   unique count:    {vfn.nunique():,}")
    print(f"   range span:      {int(vfn.max() - vfn.min() + 1):,}")
    above_end = int((vfn > fn_end).sum())
    below_start = int((vfn < fn_start).sum())
    print(f"   below fn_start: {below_start} rows "
          f"(unique values: {valid.loc[valid['frame_num'] < fn_start, 'frame_num'].nunique()})")
    print(f"   above fn_end:   {above_end} rows "
          f"(unique values: {valid.loc[valid['frame_num'] > fn_end, 'frame_num'].nunique()})")

    # If we have below/above, print a few
    if below_start:
        sample = valid.loc[valid["frame_num"] < fn_start, "frame_num"].head(5).tolist()
        print(f"     sample below:  {sample}")
    if above_end:
        sample = valid.loc[valid["frame_num"] > fn_end, "frame_num"].head(5).tolist()
        print(f"     sample above:  {sample}")

    # 4. Missing frame_nums: which MCU counter values in [fn_start, fn_end]
    # never appear?
    expected = set(range(fn_start, fn_end + 1))
    in_range = vfn[(vfn >= fn_start) & (vfn <= fn_end)]
    present = set(in_range.astype(int).unique().tolist())
    missing = sorted(expected - present)
    print(f"\n4. Missing frame_nums (in [{fn_start}, {fn_end}] but never seen):")
    print(f"   total missing:   {len(missing):,}")
    if missing:
        # Cluster: group consecutive runs
        runs = []
        run_start = missing[0]
        prev = missing[0]
        for m in missing[1:]:
            if m == prev + 1:
                prev = m
            else:
                runs.append((run_start, prev))
                run_start = m
                prev = m
        runs.append((run_start, prev))
        print(f"   number of clusters (consecutive runs): {len(runs)}")
        run_sizes = [r[1] - r[0] + 1 for r in runs]
        print(f"   largest cluster: {max(run_sizes)} frames")
        print(f"   mean cluster:    {np.mean(run_sizes):.2f}")
        print(f"   median cluster:  {int(np.median(run_sizes))}")
        print(f"   first 10 clusters: {runs[:10]}")
        if len(runs) > 10:
            print(f"   last  10 clusters: {runs[-10:]}")

    # 5. Buffers-per-frame distribution (of what arrived)
    # A healthy frame has 8 buffers; genuine frame loss in flight would show
    # frames with 1-7 buffers too.
    buf_per_frame = valid.groupby("frame_num").size()
    print(f"\n5. Buffers-per-frame (of arrived frames):")
    vc = buf_per_frame.value_counts().sort_index()
    for k, v in vc.head(15).items():
        print(f"   {k:>3} buffers: {v:>8,}  ({100 * v / len(buf_per_frame):.2f}%)")
    if len(vc) > 15:
        print(f"   ... ({len(vc)} unique bucket counts total)")

    return {
        "label": label,
        "n_filtered": n_filtered,
        "fn_start": fn_start,
        "fn_end": fn_end,
        "missing": missing,
        "total_rows": total_rows,
    }


def main():
    print("Diagnosing DAQ1 long-13 vs long-8 (clean reference)")
    d13 = diagnose(LONG13, "DAQ1 long-13")
    d8 = diagnose(LONG8, "DAQ1 long-8")

    print(f"\n{'=' * 70}\nSide-by-side summary\n{'=' * 70}")
    print(f"{'':30} {'long-13':>15} {'long-8':>15}")
    print(f"{'total rows':30} {d13['total_rows']:>15,} {d8['total_rows']:>15,}")
    print(f"{'filtered rows':30} {d13['n_filtered']:>15,} {d8['n_filtered']:>15,}")
    print(f"{'fn_start':30} {d13['fn_start']:>15} {d8['fn_start']:>15}")
    print(f"{'fn_end':30} {d13['fn_end']:>15} {d8['fn_end']:>15}")
    print(f"{'missing frame_num count':30} {len(d13['missing']):>15,} {len(d8['missing']):>15,}")


if __name__ == "__main__":
    main()
