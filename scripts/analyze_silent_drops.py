#!/usr/bin/env python3
"""Per-DAQ, per-file silent frame drop detection.

Detects frames that never reached the AVI file (all 8 buffers lost) using the
host-side arrival timestamp `buffer_recv_unix_time`: any inter-frame gap
> 75 ms (1.5× the 50 ms expected period at 20 FPS) is treated as a silent
drop of round(dt / 50ms) - 1 frames.

Per-DAQ, per-file only: miniscope restarts between files, so counters and
timestamps reset. Files analyzed: the 8 chunks in analyze_drops.py's PAIRS.
TRIM_SECONDS applied end-of-file to DAQ1 only (matches analyze_drops.py).

Note on scope: device-side fields (frame_num, device timestamp ms,
dropped_buffer_count) carry wireless-transmission bit-flip corruption
(occasional uint32-sentinel values like 0xFFFFFFFF and within-range bit
errors), so we rely only on the host clock, which is written locally and
uncorrupted.
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
EXPECTED_PERIOD_MS = 1000.0 / FPS  # 50 ms
GAP_THRESHOLD_MS = 1.5 * EXPECTED_PERIOD_MS  # 75 ms
GAP_THRESHOLD_S = GAP_THRESHOLD_MS / 1000.0  # 0.075 s for host unix time

# Matches analyze_drops.py PAIRS exactly (DAQ1 label, DAQ2 label)
PAIRS = [
    ("long-2",  "long-2"),
    ("long-4",  "long-4"),
    ("long-6",  "long-6"),
    ("long-8",  "long-8"),
    ("long-9",  "long-7"),
    ("long-10", "long-8"),
    ("long-12", "long-9"),
    ("long-13", "long-10"),
]

# DAQ1 only, end-of-file trim (matches analyze_drops.py)
TRIM_SECONDS_DAQ1 = {"long-2": 30, "long-9": 155}


def detect_timestamp_gaps(timestamps, threshold, period, unit_label):
    """Detect timestamp gaps larger than `threshold`.

    timestamps: monotonic list/array of per-frame timestamps.
    threshold:  gap size above which we flag (same units as timestamps).
    period:     expected inter-frame period (same units); used to estimate
                missed frame count = round(dt / period) - 1.
    unit_label: "ms" or "s". Controls the event dict key ("dt_ms" vs "dt_s").
    """
    dt_key = f"dt_{unit_label}"
    events = []
    total_missed = 0
    for i in range(1, len(timestamps)):
        dt = timestamps[i] - timestamps[i - 1]
        if dt > threshold:
            missed = int(round(dt / period)) - 1
            if missed < 1:
                missed = 1
            events.append({
                "at_frame_idx": i,
                dt_key: float(dt),
                "missed": missed,
            })
            total_missed += missed
    return {
        "silent_drops": total_missed,
        "gap_events": len(events),
        "events": events,
    }


def reduce_to_per_frame(df):
    """Collapse buffer-level rows to one row per reconstructed_frame_index.

    Returns a DataFrame sorted by reconstructed_frame_index with columns:
      - reconstructed_frame_index
      - buffer_recv_unix_time    (min — host arrival of earliest buffer)
    """
    per_frame = (
        df.groupby("reconstructed_frame_index", sort=True)
        .agg(buffer_recv_unix_time=("buffer_recv_unix_time", "min"))
        .reset_index()
    )
    return per_frame


def apply_trim(per_frame, daq, label):
    """Drop the last N frames from DAQ1 files in the trim table.

    Returns (trimmed_df, trim_frames_dropped). DAQ2 is never trimmed.
    """
    if daq != 1:
        return per_frame, 0
    trim_s = TRIM_SECONDS_DAQ1.get(label, 0)
    if trim_s <= 0:
        return per_frame, 0
    trim_frames = int(trim_s * FPS)
    if trim_frames >= len(per_frame):
        return per_frame.iloc[0:0].copy(), len(per_frame)
    return per_frame.iloc[:-trim_frames].copy(), trim_frames


def find_csv(directory, label):
    """Find the CSV for a given chunk label (e.g., 'long-2').

    Matches patterns used in analyze_drops.py. Returns the first match or None.
    """
    for pattern in [f"*_{label}.csv", f"*_{label}-*.csv", f"*{label}.csv"]:
        matches = glob.glob(os.path.join(directory, pattern))
        if matches:
            return matches[0]
    return None


def analyze_file(csv_path, daq, label):
    """Run the host-timestamp silent-drop detector on one CSV."""
    df = pd.read_csv(csv_path)
    total_frames_in_csv = int(df["reconstructed_frame_index"].nunique())

    per_frame = reduce_to_per_frame(df)
    per_frame, trim_frames = apply_trim(per_frame, daq=daq, label=label)

    host_ts = per_frame["buffer_recv_unix_time"].tolist()
    host_result = detect_timestamp_gaps(
        host_ts, threshold=GAP_THRESHOLD_S, period=EXPECTED_PERIOD_MS / 1000.0, unit_label="s"
    )

    return {
        "file": os.path.basename(csv_path),
        "daq": daq,
        "fps": FPS,
        "expected_period_ms": EXPECTED_PERIOD_MS,
        "gap_threshold_ms": GAP_THRESHOLD_MS,
        "total_frames_in_csv": total_frames_in_csv,
        "trim_seconds": TRIM_SECONDS_DAQ1.get(label, 0) if daq == 1 else 0,
        "trim_frames": trim_frames,
        "analyzed_frames": len(per_frame),
        "host_timestamp": host_result,
    }


def write_per_file_json(result, daq_dir):
    """Write the per-file JSON next to the existing results/ for that DAQ."""
    results_dir = os.path.join(daq_dir, "results")
    os.makedirs(results_dir, exist_ok=True)
    stem = os.path.splitext(result["file"])[0]
    out_path = os.path.join(results_dir, f"{stem}.silent_drops.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    return out_path


def build_summary(per_daq_results):
    """Build the combined summary dict from per-file results grouped by DAQ."""
    summary = {
        "fps": FPS,
        "gap_threshold_ms": GAP_THRESHOLD_MS,
    }
    for daq_key in ("DAQ1", "DAQ2"):
        files = per_daq_results.get(daq_key, [])
        per_file_rows = []
        totals = {
            "analyzed_frames": 0,
            "host_ts_drops": 0,
            "host_ts_gap_events": 0,
        }
        for r in files:
            row = {
                "file": r["file"],
                "analyzed_frames": r["analyzed_frames"],
                "host_ts_drops": r["host_timestamp"]["silent_drops"],
                "host_ts_gap_events": r["host_timestamp"]["gap_events"],
            }
            per_file_rows.append(row)
            for k in totals:
                totals[k] += row[k]
        summary[daq_key] = {"per_file": per_file_rows, "totals": totals}
    return summary


def plot_summary(summary, out_path):
    """Two stacked panels (DAQ1, DAQ2). One bar per file = host-timestamp silent drops."""
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=False)
    for ax, daq_key in zip(axes, ("DAQ1", "DAQ2")):
        rows = summary[daq_key]["per_file"]
        if not rows:
            ax.set_title(f"{daq_key}: no files")
            continue
        labels = [r["file"].replace(".csv", "") for r in rows]
        x = np.arange(len(labels))
        drops = [r["host_ts_drops"] for r in rows]
        events = [r["host_ts_gap_events"] for r in rows]
        bar_w = 0.4
        ax.bar(x - bar_w / 2, drops, width=bar_w, color="#2ca02c", label="silent drops")
        ax.bar(x + bar_w / 2, events, width=bar_w, color="#1f77b4", label="gap events")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)
        ax.set_ylabel("count")
        totals = summary[daq_key]["totals"]
        ax.set_title(
            f"{daq_key} — host-timestamp silent drops: {totals['host_ts_drops']} "
            f"across {totals['host_ts_gap_events']} gap events "
            f"(analyzed_frames={totals['analyzed_frames']})"
        )
        ax.legend(loc="upper right", fontsize=8)
        ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def run():
    per_daq_results = {"DAQ1": [], "DAQ2": []}

    # PAIRS can reference the same DAQ2 file more than once (when two DAQ1
    # chunks overlap one DAQ2 chunk). Dedupe per DAQ to avoid double-counting.
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
            print(
                f"DAQ{daq} {label}: analyzed={result['analyzed_frames']} "
                f"host_ts_drops={result['host_timestamp']['silent_drops']} "
                f"gap_events={result['host_timestamp']['gap_events']} "
                f"-> {out_path}"
            )

    summary = build_summary(per_daq_results)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    summary_path = os.path.join(OUTPUT_DIR, "silent_drops_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSummary written to: {summary_path}")

    plot_path = os.path.join(OUTPUT_DIR, "silent_drops.png")
    plot_summary(summary, plot_path)
    print(f"Plot written to: {plot_path}")

    return per_daq_results, summary


if __name__ == "__main__":
    run()
