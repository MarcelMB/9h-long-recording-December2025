#!/usr/bin/env python3
"""Dual-DAQ stitched survival via direct MCU frame_num union (honest method).

WHY THIS REPLACES THE OLD JOIN
------------------------------
The previous version joined the stitcher's per-frame `daq1_frame`/`daq2_frame`
columns to per-RFI survival. Those columns can only reference frames that WERE
reconstructed, so frames lost on a DAQ have no RFI and are simply ABSENT from
the stitched denominator instead of being counted as lost. That made the
stitched loss collapse to ~0.00% — right by luck, wrong by construction (the
join found only 162 DAQ2 failures vs the true 2,475).

CORRECT METHOD (verified 2026-06-09)
------------------------------------
The device MCU `frame_num` is the SAME counter on both DAQs within a paired
recording chunk (it resets per chunk). Alignment is exact: surviving-frame sets
overlap 77,315/77,317 in the worst pair, and the same frame_num arrives within
~4 ms on both DAQs. So we align DAQ1↔DAQ2 directly by frame_num:

  S1 = {frame_num that survived (>=8 buffers) on DAQ1}
  S2 = {frame_num that survived on DAQ2}
  stitched-covered = S1 ∪ S2 ;  both-lost = frames in neither set.

Data-driven tail handling (no magic trim constants)
---------------------------------------------------
Each chunk is a SEPARATE recording session (frame_num resets; 26–574 s wall-
clock gaps between chunks). At every session end BOTH optical links collapse to
half-buffer delivery (meanbuf ≈4 of 8, survival 0%) for the final seconds —
buffers in flight when acquisition stops, not data loss. We exclude this
terminal collapse principledly: the analyzable span for each pair runs from the
FIRST to the LAST frame that EITHER DAQ delivered. Frames after the last
delivered frame (the terminal collapse) are outside the span; both-lost frames
INSIDE the span are genuine mid-recording simultaneous dropouts.

Inputs:
  output/rfi_survival_all.csv   — per-RFI survival (daq, segment, fn_mode,
                                   mcu_surviving_ge8, ...)
  neural_DAQ{1,2}/*.csv         — raw buffers, for both-lost frame timestamps
  PAIRS                         — canonical DAQ1↔DAQ2 chunk mapping (afd)

All three headline numbers (DAQ1 alone, DAQ2 alone, dual-DAQ stitched) are
computed over the SAME per-pair span, so they share one principled session-end
boundary instead of the old hand-tuned, DAQ1-only `TRIM_SECONDS_DAQ1`. Per pair:
  DAQ1-alone lost = frames in [lo, hi] not in S1
  DAQ2-alone lost = frames in [lo, hi] not in S2
  stitched lost   = frames in [lo, hi] in neither (both-lost)
with [lo, hi] = first..last frame either DAQ delivered.

Outputs:
  output/survival_summary.json  — DAQ1/DAQ2/stitched totals + per-pair breakdown
  output/stitched_both_lost.csv — one row per dual-DAQ both-lost frame
                                  (for the timeline panel)
"""

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import analyze_frame_num_drops as afd

# ── Paths ──
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = f"{BASE}/output"
DAQ1_DIR = f"{BASE}/neural_DAQ1"
DAQ2_DIR = f"{BASE}/neural_DAQ2"
RFI_SURVIVAL = f"{OUT_DIR}/rfi_survival_all.csv"

OUT_JSON = f"{OUT_DIR}/survival_summary.json"
OUT_CSV = f"{OUT_DIR}/stitched_both_lost.csv"

SURVIVAL_THRESHOLD = 8  # buffers required for a frame to count as delivered


# ── Survival sets ──
def surviving_frame_nums(rs: pd.DataFrame, daq: int, segment: str) -> set[int]:
    """Set of MCU frame_num values that survived (>=8 buffers) on this chunk."""
    g = rs[(rs["daq"] == daq) & (rs["segment"] == segment)]
    return set(g.loc[g["mcu_surviving_ge8"], "fn_mode"].astype(int))


def delivering_span_both_lost(s1: set[int], s2: set[int]) -> tuple[int, int, list[int]]:
    """Return (lo, hi, both_lost) for the union-coverage span.

    lo/hi are the first/last frame_num delivered by EITHER DAQ; both_lost is the
    sorted list of frame_nums inside [lo, hi] that neither DAQ delivered.
    """
    union = s1 | s2
    if not union:
        return 0, -1, []
    lo, hi = min(union), max(union)
    both_lost = sorted(set(range(lo, hi + 1)) - union)
    return lo, hi, both_lost


# ── Timestamps for both-lost frames (for the timeline panel) ──
def frame_timestamps(csv_path: str, frame_nums: set[int]) -> pd.Series:
    """Min buffer_recv_unix_time for each requested frame_num in a raw CSV.

    Both-lost frames are present sub-threshold (some buffers arrived), so their
    arrival time is recoverable from the raw rows. Returns an empty Series if
    none of the frame_nums appear.
    """
    if not frame_nums:
        return pd.Series(dtype=float)
    df = pd.read_csv(csv_path, usecols=["frame_num", "buffer_recv_unix_time"])
    hit = df[df["frame_num"].isin(frame_nums)]
    if len(hit) == 0:
        return pd.Series(dtype=float)
    return hit.groupby("frame_num")["buffer_recv_unix_time"].min()


def both_lost_timestamps(
    d1_seg: str, d2_seg: str, both_lost: list[int]
) -> dict[int, float]:
    """Map each both-lost frame_num → earliest arrival time across both DAQs."""
    if not both_lost:
        return {}
    want = set(both_lost)
    ts = {}
    d1_csv = afd.find_csv(DAQ1_DIR, d1_seg)
    d2_csv = afd.find_csv(DAQ2_DIR, d2_seg)
    for csv in (d1_csv, d2_csv):
        if csv is None:
            continue
        s = frame_timestamps(csv, want)
        for fn, t in s.items():
            fn = int(fn)
            ts[fn] = min(t, ts[fn]) if fn in ts else float(t)
    # Interior frames almost always appear sub-threshold; if a frame truly never
    # arrived on either DAQ, interpolate its time linearly within the pair.
    missing = [fn for fn in both_lost if fn not in ts]
    if missing and ts:
        known_fn = np.array(sorted(ts))
        known_t = np.array([ts[fn] for fn in known_fn])
        for fn in missing:
            ts[fn] = float(np.interp(fn, known_fn, known_t))
    return ts


# ── Driver ──
def run() -> None:
    print(f"Loading per-RFI survival: {RFI_SURVIVAL}")
    rs = pd.read_csv(RFI_SURVIVAL)
    print(f"  {len(rs):,} rows\n")

    per_pair = {}
    rows = []
    total_span = 0
    total_daq1 = 0
    total_daq2 = 0
    total_both = 0

    print("Per-pair survival over the shared union span (aligned by frame_num):\n")
    for d1_seg, d2_seg in afd.PAIRS:
        s1 = surviving_frame_nums(rs, 1, d1_seg)
        s2 = surviving_frame_nums(rs, 2, d2_seg)
        lo, hi, both_lost = delivering_span_both_lost(s1, s2)
        if hi < lo:
            continue
        span = hi - lo + 1
        full = set(range(lo, hi + 1))
        daq1_lost = sorted(full - s1)  # DAQ1-alone failures within the span
        daq2_lost = sorted(full - s2)  # DAQ2-alone failures within the span

        total_span += span
        total_daq1 += len(daq1_lost)
        total_daq2 += len(daq2_lost)
        total_both += len(both_lost)

        pair_key = f"{d1_seg}|{d2_seg}"
        per_pair[pair_key] = {
            "daq1_segment": d1_seg,
            "daq2_segment": d2_seg,
            "span_first_fn": lo,
            "span_last_fn": hi,
            "analyzed_frames": span,
            "daq1_lost": len(daq1_lost),
            "daq2_lost": len(daq2_lost),
            "both_lost": len(both_lost),
        }
        print(
            f"  {d1_seg:7s}↔{d2_seg:7s} span={span:,} (fn {lo}-{hi})  "
            f"DAQ1={len(daq1_lost):,} DAQ2={len(daq2_lost):,} both={len(both_lost):,}"
        )

        ts = both_lost_timestamps(d1_seg, d2_seg, both_lost)
        for fn in both_lost:
            rows.append(
                {
                    "daq1_segment": d1_seg,
                    "daq2_segment": d2_seg,
                    "frame_num": fn,
                    "unix_time": ts.get(fn, np.nan),
                }
            )

    both_lost_df = pd.DataFrame(rows)
    both_lost_df.to_csv(OUT_CSV, index=False)

    def pct(n: int) -> float | None:
        return round(100.0 * n / total_span, 4) if total_span else None

    summary = {
        "method": (
            "Direct DAQ1↔DAQ2 alignment by MCU frame_num. Per chunk pair the "
            "analysable span is [first, last] frame delivered by EITHER DAQ "
            "(excludes the terminal MCU-reboot collapse). Over that span: DAQ1/DAQ2 "
            "alone lost = frames that DAQ didn't survive (>=8 buffers); stitched "
            "both-lost = frames neither survived. One boundary for all three."
        ),
        "threshold_buffers": SURVIVAL_THRESHOLD,
        "totals": {
            "analyzed_frames": total_span,
            "DAQ1": {"lost": total_daq1, "loss_pct": pct(total_daq1)},
            "DAQ2": {"lost": total_daq2, "loss_pct": pct(total_daq2)},
            "stitched_both_lost": {"lost": total_both, "loss_pct": pct(total_both)},
        },
        "per_pair": per_pair,
    }
    with open(OUT_JSON, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nWrote {OUT_CSV} ({len(both_lost_df):,} both-lost frames)")
    print(f"Wrote {OUT_JSON}")
    print(f"\n{'=' * 70}")
    print(f"Consistent session-end cut — totals over {total_span:,} analysed frames:")
    print(f"  DAQ1 alone:        {total_daq1:,}  ({pct(total_daq1)}%)")
    print(f"  DAQ2 alone:        {total_daq2:,}  ({pct(total_daq2)}%)")
    print(f"  Dual-DAQ stitched: {total_both:,}  ({pct(total_both)}%)")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    run()
