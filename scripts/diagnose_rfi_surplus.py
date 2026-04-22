#!/usr/bin/env python3
"""Verify the hypothesis for why reconstructed_frame_index > unique(frame_num).

Hypothesis (from mio/stream_daq.py:385–504):
  _buffer_to_frame emits a frame whenever `header_data.frame_num` changes.
  A bit-flipped frame_num in a single buffer header breaks a run of real
  frame_nums, triggering a premature emit. When the next buffer arrives with
  the correct frame_num, the state machine treats it as ANOTHER new frame.
  Net effect per corrupted header: +2 reconstructed_frame_index (RFI) values
  compared to unique MCU frame_num count.

For one chunk we measure:
  1. Surplus = unique(RFI) - unique(valid frame_num)
  2. How many real MCU frame_nums are split across >1 RFI value (confirms
     the split-emit mechanism)
  3. How many RFIs have very few buffers (1–2) — these are the spurious
     tiny "frames" emitted from corruption, not real MCU frames
  4. Within-range corruption estimate: rows whose frame_num differs by just
     a few bits from its neighbors (too close to real to be sentinel-caught)
"""

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import analyze_frame_num_drops as afd

BASE = "/Users/mbrosch/Documents/9h_long_recording_December2025"


def diagnose(path, label):
    print(f"\n{'=' * 72}\n{label}: {os.path.basename(path)}\n{'=' * 72}")
    df = pd.read_csv(
        path, usecols=["frame_num", "reconstructed_frame_index", "buffer_count"]
    )
    total = len(df)

    # Valid vs filtered (sentinels + out-of-range)
    mask = afd.valid_mask(df["frame_num"])
    n_sentinel = int((~mask).sum())

    fn_start, fn_end, _, _ = afd.pick_start_end(df["frame_num"])
    valid = df[mask]
    vfn = valid["frame_num"]
    in_range = valid[(vfn >= fn_start) & (vfn <= fn_end)]

    unique_fn = int(in_range["frame_num"].nunique())
    unique_rfi = int(df["reconstructed_frame_index"].nunique())
    surplus = unique_rfi - unique_fn
    intended = fn_end - fn_start + 1

    print(f"  total rows:                {total:>8,}")
    print(f"  sentinel-filtered rows:    {n_sentinel:>8,}")
    print(f"  fn_start..fn_end:          {fn_start} .. {fn_end}")
    print(f"  intended (MCU):            {intended:>8,}")
    print(f"  unique valid frame_num:    {unique_fn:>8,}  (= delivered)")
    print(f"  unique RFI:                {unique_rfi:>8,}")
    print(f"  SURPLUS (RFI − delivered): {surplus:>8,}")

    # 1. MCU frame_nums split across multiple RFIs
    #    If a real frame was emitted in 3 pieces (premature emit, gap, remainder),
    #    its frame_num would map to 3 distinct RFI values.
    rfi_per_fn = in_range.groupby("frame_num")["reconstructed_frame_index"].nunique()
    split_fns = rfi_per_fn[rfi_per_fn > 1]
    print(f"\n  [1] Real frame_nums that got split across >1 RFI:")
    print(f"      count:                 {len(split_fns):>8,}")
    if len(split_fns) > 0:
        split_counts = split_fns.value_counts().sort_index()
        for k, v in split_counts.head(6).items():
            print(f"      {k} RFIs from 1 frame_num: {v:,}")
        total_extra_from_splits = int((split_fns - 1).sum())
        print(f"      extra RFIs from splits:  {total_extra_from_splits:>8,}")

    # 2. Tiny RFI "frames" (1 or 2 buffers) — likely spurious emits from
    #    a single corrupted header, not real 8-buffer frames
    buffers_per_rfi = df.groupby("reconstructed_frame_index").size()
    tiny = buffers_per_rfi[buffers_per_rfi <= 2]
    print(f"\n  [2] RFIs with only 1–2 buffers (likely spurious emits):")
    print(f"      count:                 {len(tiny):>8,}")
    size_counts = buffers_per_rfi.value_counts().sort_index()
    print(f"      buffer-count histogram (first 10 bins):")
    for k, v in size_counts.head(10).items():
        print(f"        {k} buffers → {v:>7,} RFIs")

    # 3. Buffers that are the ONLY buffer of their RFI AND carry a frame_num
    #    not seen elsewhere in the file (stronger signature of a lone bit-flip)
    singletons = buffers_per_rfi[buffers_per_rfi == 1].index
    singleton_rows = df[df["reconstructed_frame_index"].isin(singletons)]
    fn_appears_elsewhere = singleton_rows["frame_num"].isin(
        df["frame_num"].value_counts()[lambda s: s > 1].index
    )
    lone_bitflip_candidates = (~fn_appears_elsewhere).sum()
    print(
        f"\n  [3] 1-buffer RFIs with frame_num seen nowhere else: "
        f"{int(lone_bitflip_candidates):,}"
    )

    return {
        "label": label,
        "surplus": surplus,
        "split_fns": len(split_fns),
        "tiny_rfis": len(tiny),
        "lone_bitflip_candidates": int(lone_bitflip_candidates),
        "n_sentinel": n_sentinel,
    }


def main():
    chunks = [
        (f"{BASE}/neural_DAQ1/WL27_DAQ1_25_12_10_long-4.csv",  "DAQ1 long-4"),   # big surplus
        (f"{BASE}/neural_DAQ1/WL27_DAQ1_25_12_10_long-10.csv", "DAQ1 long-10"),  # smaller
        (f"{BASE}/neural_DAQ2/WL27_DAQ2_25_12_10_long-2.csv",  "DAQ2 long-2"),   # DAQ2 tiny surplus
        (f"{BASE}/neural_DAQ2/WL27_DAQ2_25_12_10_long-7.csv",  "DAQ2 long-7"),   # DAQ2 biggest
    ]
    rows = [diagnose(p, lbl) for p, lbl in chunks]

    print(f"\n{'=' * 72}\nSummary\n{'=' * 72}")
    print(f"{'chunk':<16} {'surplus':>8} {'split_fns':>10} {'tiny_rfi':>9} {'lone_bf':>8} {'sentinel':>9}")
    for r in rows:
        print(
            f"{r['label']:<16} {r['surplus']:>8,} {r['split_fns']:>10,} "
            f"{r['tiny_rfis']:>9,} {r['lone_bitflip_candidates']:>8,} {r['n_sentinel']:>9,}"
        )


if __name__ == "__main__":
    main()
