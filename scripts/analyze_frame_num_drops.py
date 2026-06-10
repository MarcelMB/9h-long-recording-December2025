#!/usr/bin/env python3
"""Per-DAQ, per-file silent frame drop detection via MCU `frame_num` counter.

Independent check of scripts/analyze_silent_drops.py (which uses host unix
timestamps). The MCU increments `frame_num` for every frame it intends to send,
regardless of whether the wireless link delivers it. By comparing the device's
counter range in a chunk to the number of distinct `frame_num` values that
actually show up in the CSV, we get an estimate of silent drops that does NOT
depend on timestamp jitter.

Per-chunk algorithm:
  1. Load CSV, keep `frame_num` column.
  2. Filter wireless bit-flip corruption:
       - drop uint32 sentinel values (0xFFFFFFFF, 0xFFFE0000, 0x80000000,
         0x7FFFFFFF)
       - drop anything above FRAME_NUM_VALID_MAX (200_000: well above any
         plausible per-chunk counter at 20 FPS for ~90 min chunks)
  3. `fn_start` = min valid frame_num in the first HEAD_WINDOW rows.
  4. `fn_end`   = max valid frame_num in the last  TAIL_WINDOW rows.
  5. intended = fn_end - fn_start + 1
  6. delivered = count of unique valid frame_num values in [fn_start, fn_end]
  7. silent drops = intended - delivered

Sanity guards per chunk:
  - fn_end > fn_start
  - intended <= IMPLAUSIBLE_INTENDED (150_000)
  - delivered <= intended (if delivered > intended, filter missed corruption;
    flag and do not trust the number)

Same PAIRS as analyze_silent_drops.py so results line up for comparison.
Host-timestamp method remains the source of truth for the existing pipeline;
this script writes alongside it, not on top of it.
"""

import glob
import json
import os

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


BASE_DIR = "/Users/mbrosch/Documents/9h_long_recording_December2025"
DAQ1_DIR = os.path.join(BASE_DIR, "neural_DAQ1")
DAQ2_DIR = os.path.join(BASE_DIR, "neural_DAQ2")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

FPS = 20.0

# DAQ1 chunk label -> time-aligned DAQ2 chunk label.
# DAQ2's first chunk is the un-numbered base file (...long.csv), so the DAQ2
# numbering runs one behind DAQ1. Alignment confirmed by both
# buffer_recv_unix_time windows and frame_num ranges, and matches the
# timestamp-based mapping in combine_daqs.py. (Earlier versions had the first
# four DAQ2 labels shifted by one, which skipped DAQ2's first hour and
# double-counted long-8.)
PAIRS = [
    ("long-2", "long"),
    ("long-4", "long-2"),
    ("long-6", "long-4"),
    ("long-8", "long-6"),
    ("long-9", "long-7"),
    ("long-10", "long-8"),
    ("long-12", "long-9"),
    ("long-13", "long-10"),
]

# Known wireless bit-flip sentinels and plausibility cap
SENTINELS = {0xFFFFFFFF, 0xFFFE0000, 0x80000000, 0x7FFFFFFF}
FRAME_NUM_VALID_MAX = 200_000  # 20 FPS × 90 min = 108_000, so 200k is generous
IMPLAUSIBLE_INTENDED = 150_000  # post-compute sanity guard

# How many head/tail rows to look at when picking the clean start/end value
HEAD_WINDOW = 20
TAIL_WINDOW = 20


def valid_mask(frame_num):
    """Return a pandas boolean Series of rows with a plausible frame_num."""
    sentinel_mask = frame_num.isin(SENTINELS)
    return (frame_num > 0) & (frame_num < FRAME_NUM_VALID_MAX) & ~sentinel_mask


def _quorum_extreme(values, extreme, min_count=2):
    """Return the extreme-valued `frame_num` that appears at least `min_count`
    times in `values` (a series of valid frame_num values in a head/tail window).

    A real MCU frame appears as 8 buffers with the same `frame_num`, so a
    head/tail window of ~20 rows covers ~2–3 frames; each real value should
    occur 7–8 times. A within-range bit-flip shows up as a lone outlier.
    Requiring quorum (≥2 occurrences) filters those out. Falls back to the
    plain extreme if no value clears quorum.

    extreme: `min` or `max`.
    """
    if len(values) == 0:
        return None
    counts = values.value_counts()
    qualified = counts[counts >= min_count].index
    if len(qualified) > 0:
        return int(extreme(qualified))
    return int(extreme(values))


def pick_start_end(frame_num_series, head=HEAD_WINDOW, tail=TAIL_WINDOW):
    """Return (fn_start, fn_end, head_window, tail_window).

    fn_start: smallest valid frame_num that appears at least twice in the
              first `head` rows (quorum filter — rejects single within-range
              bit-flips that survive the sentinel filter).
    fn_end:   largest valid frame_num that appears at least twice in the
              last `tail` rows.
    Windows are returned for auditing.
    """
    head_rows = frame_num_series.iloc[:head]
    tail_rows = frame_num_series.iloc[-tail:]

    head_raw = head_rows.tolist()
    tail_raw = tail_rows.tolist()

    head_valid = head_rows[valid_mask(head_rows)]
    tail_valid = tail_rows[valid_mask(tail_rows)]

    if len(head_valid) == 0 or len(tail_valid) == 0:
        return None, None, head_raw, tail_raw

    fn_start = _quorum_extreme(head_valid, min)
    fn_end = _quorum_extreme(tail_valid, max)
    return fn_start, fn_end, head_raw, tail_raw


def analyze_file(csv_path, daq, label):
    """Run the frame_num silent-drop detector on one CSV."""
    df = pd.read_csv(csv_path, usecols=["frame_num", "reconstructed_frame_index"])
    total_rows = len(df)

    mask = valid_mask(df["frame_num"])
    n_filtered = int((~mask).sum())
    valid_fn = df["frame_num"][mask]

    fn_start, fn_end, head_window, tail_window = pick_start_end(df["frame_num"])

    flags = []
    if fn_start is None or fn_end is None:
        flags.append("no_valid_frame_num_in_head_or_tail")
        return {
            "file": os.path.basename(csv_path),
            "daq": daq,
            "total_rows": total_rows,
            "filtered_rows": n_filtered,
            "fn_start": None,
            "fn_end": None,
            "head_window_frame_num": head_window,
            "tail_window_frame_num": tail_window,
            "intended": None,
            "delivered": None,
            "silent_drops": None,
            "flags": flags,
        }

    if fn_end <= fn_start:
        flags.append("fn_end_not_greater_than_fn_start")

    intended = fn_end - fn_start + 1
    if intended > IMPLAUSIBLE_INTENDED:
        flags.append(f"intended_exceeds_{IMPLAUSIBLE_INTENDED}")

    in_range = valid_fn[(valid_fn >= fn_start) & (valid_fn <= fn_end)]
    delivered = int(in_range.nunique())

    silent_drops = intended - delivered
    if delivered > intended:
        flags.append("delivered_exceeds_intended")

    # Also record overall min/max among valid frame_num values in the whole file
    # — if these differ from (fn_start, fn_end) we have within-range values
    # outside the start/end window worth noting.
    whole_file_min = int(valid_fn.min())
    whole_file_max = int(valid_fn.max())
    if whole_file_min < fn_start:
        flags.append("valid_frame_num_below_fn_start")
    if whole_file_max > fn_end:
        flags.append("valid_frame_num_above_fn_end")

    total_frames_in_csv = int(df["reconstructed_frame_index"].nunique())

    return {
        "file": os.path.basename(csv_path),
        "daq": daq,
        "total_rows": total_rows,
        "total_frames_reconstructed": total_frames_in_csv,
        "filtered_rows": n_filtered,
        "filtered_rate_pct": round(100.0 * n_filtered / max(total_rows, 1), 4),
        "fn_start": fn_start,
        "fn_end": fn_end,
        "whole_file_min_valid_fn": whole_file_min,
        "whole_file_max_valid_fn": whole_file_max,
        "head_window_frame_num": head_window,
        "tail_window_frame_num": tail_window,
        "intended": intended,
        "delivered": delivered,
        "silent_drops": silent_drops,
        "flags": flags,
    }


def find_csv(directory, label):
    """Locate the CSV for a chunk label; matches analyze_silent_drops.py."""
    for pattern in [f"*_{label}.csv", f"*_{label}-*.csv", f"*{label}.csv"]:
        matches = glob.glob(os.path.join(directory, pattern))
        if matches:
            return matches[0]
    return None


def write_per_file_json(result, daq_dir):
    """Write per-file JSON next to the existing results directory."""
    results_dir = os.path.join(daq_dir, "results")
    os.makedirs(results_dir, exist_ok=True)
    stem = os.path.splitext(result["file"])[0]
    out_path = os.path.join(results_dir, f"{stem}.frame_num_drops.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    return out_path


def build_summary(per_daq_results):
    summary = {
        "fps": FPS,
        "method": "frame_num_counter",
        "frame_num_valid_max": FRAME_NUM_VALID_MAX,
        "sentinels": sorted(SENTINELS),
        "head_window": HEAD_WINDOW,
        "tail_window": TAIL_WINDOW,
    }
    for daq_key in ("DAQ1", "DAQ2"):
        files = per_daq_results.get(daq_key, [])
        rows = []
        totals = {"intended": 0, "delivered": 0, "silent_drops": 0, "filtered_rows": 0}
        for r in files:
            row = {
                "file": r["file"],
                "fn_start": r["fn_start"],
                "fn_end": r["fn_end"],
                "intended": r["intended"],
                "delivered": r["delivered"],
                "silent_drops": r["silent_drops"],
                "filtered_rows": r["filtered_rows"],
                "flags": r["flags"],
            }
            rows.append(row)
            for k in ("intended", "delivered", "silent_drops", "filtered_rows"):
                if row[k] is not None:
                    totals[k] += row[k]
        if totals["intended"] > 0:
            totals["silent_drop_rate_pct"] = round(
                100.0 * totals["silent_drops"] / totals["intended"], 4
            )
        summary[daq_key] = {"per_file": rows, "totals": totals}
    return summary


def plot_summary(summary, out_path):
    """Two panels (DAQ1, DAQ2), one bar per file = frame_num silent drops."""
    fig, axes = plt.subplots(2, 1, figsize=(14, 8))
    for ax, daq_key in zip(axes, ("DAQ1", "DAQ2")):
        rows = summary[daq_key]["per_file"]
        if not rows:
            ax.set_title(f"{daq_key}: no files")
            continue
        labels = [r["file"].replace(".csv", "") for r in rows]
        x = np.arange(len(labels))
        drops = [
            r["silent_drops"] if r["silent_drops"] is not None else 0 for r in rows
        ]
        ax.bar(x, drops, color="#d62728", label="frame_num silent drops")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)
        ax.set_ylabel("count")
        totals = summary[daq_key]["totals"]
        rate = totals.get("silent_drop_rate_pct", 0.0)
        ax.set_title(
            f"{daq_key} — frame_num silent drops: {totals['silent_drops']} "
            f"/ intended {totals['intended']}  ({rate}%)"
        )
        ax.legend(loc="upper right", fontsize=8)
        ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def run():
    per_daq_results = {"DAQ1": [], "DAQ2": []}

    daq1_labels = list(dict.fromkeys(p[0] for p in PAIRS))
    daq2_labels = list(dict.fromkeys(p[1] for p in PAIRS))

    for daq, daq_dir, labels in [
        (1, DAQ1_DIR, daq1_labels),
        (2, DAQ2_DIR, daq2_labels),
    ]:
        for label in labels:
            csv_path = find_csv(daq_dir, label)
            if csv_path is None:
                print(f"SKIP DAQ{daq} {label}: CSV not found")
                continue
            result = analyze_file(csv_path, daq=daq, label=label)
            out_path = write_per_file_json(result, daq_dir)
            per_daq_results[f"DAQ{daq}"].append(result)
            flags = ",".join(result["flags"]) if result["flags"] else "-"
            print(
                f"DAQ{daq} {label}: "
                f"fn=[{result['fn_start']}..{result['fn_end']}] "
                f"intended={result['intended']} delivered={result['delivered']} "
                f"drops={result['silent_drops']} filtered={result['filtered_rows']} "
                f"flags={flags} -> {out_path}"
            )

    summary = build_summary(per_daq_results)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    summary_path = os.path.join(OUTPUT_DIR, "frame_num_drops_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSummary written to: {summary_path}")

    plot_path = os.path.join(OUTPUT_DIR, "frame_num_drops.png")
    plot_summary(summary, plot_path)
    print(f"Plot written to: {plot_path}")

    return per_daq_results, summary


if __name__ == "__main__":
    run()
