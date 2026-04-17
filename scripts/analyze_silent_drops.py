#!/usr/bin/env python3
"""Per-DAQ, per-file silent frame drop detection.

Detects frames that never reached the AVI file (all 8 buffers lost) using 4
CSV-derived signals:
  1. frame_num gaps      — device frame counter skipped values
  2. device timestamp    — ms gap > 75 ms (expected 50 ms at 20 FPS)
  3. host timestamp      — same threshold applied to buffer_recv_unix_time
  4. dropped_buffer_count — firmware-reported drops (positive deltas)

Per-DAQ, per-file only: miniscope restarts between files, so counters and
timestamps reset. Files analyzed: the 8 chunks in analyze_drops.py's PAIRS.
TRIM_SECONDS applied end-of-file to DAQ1 only (matches analyze_drops.py).
"""

import csv
import glob
import json
import os
from collections import defaultdict

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


def detect_frame_num_gaps(frame_nums):
    """Detect gaps in the device frame_num counter.

    A gap of (frame_nums[i] - frame_nums[i-1]) > 1 means (diff - 1) frames
    were produced by the device but never reached the host.
    """
    events = []
    total_missed = 0
    for i in range(1, len(frame_nums)):
        diff = frame_nums[i] - frame_nums[i - 1]
        if diff > 1:
            missed = int(diff - 1)
            events.append({
                "at_frame_idx": i,
                "frame_num_before": int(frame_nums[i - 1]),
                "frame_num_after": int(frame_nums[i]),
                "missed": missed,
            })
            total_missed += missed
    return {
        "silent_drops": total_missed,
        "gap_events": len(events),
        "events": events,
    }


def detect_timestamp_gaps(timestamps, threshold, period, unit_label):
    """Detect timestamp gaps larger than `threshold`.

    timestamps: monotonic list/array of per-frame timestamps.
    threshold:  gap size above which we flag (same units as timestamps).
    period:     expected inter-frame period (same units); used to estimate
                missed frame count = round(dt / period) - 1.
    unit_label: "ms" for device timestamp, "s" for host unix time. Controls
                the event dict key ("dt_ms" vs "dt_s").
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


def detect_dropped_buffer_deltas(counts):
    """Sum positive deltas of the firmware-reported dropped_buffer_count.

    The counter is cumulative. Decreases are treated as 0 delta (defensive —
    should not happen within a single file since the device doesn't restart
    mid-file, but guards against data quirks).
    """
    events = []
    total = 0
    for i in range(1, len(counts)):
        delta = int(counts[i] - counts[i - 1])
        if delta > 0:
            events.append({"at_frame_idx": i, "delta": delta})
            total += delta
    return {
        "total_delta": total,
        "nonzero_deltas": len(events),
        "events": events,
    }


def reduce_to_per_frame(df):
    """Collapse buffer-level rows to one row per reconstructed_frame_index.

    Returns a DataFrame sorted by reconstructed_frame_index with columns:
      - reconstructed_frame_index
      - frame_num                (first — should be constant within group)
      - timestamp                (min — device frame-start ms)
      - buffer_recv_unix_time    (min — host arrival of earliest buffer)
      - dropped_buffer_count     (max — cumulative firmware counter)
    """
    per_frame = (
        df.groupby("reconstructed_frame_index", sort=True)
        .agg(
            frame_num=("frame_num", "first"),
            timestamp=("timestamp", "min"),
            buffer_recv_unix_time=("buffer_recv_unix_time", "min"),
            dropped_buffer_count=("dropped_buffer_count", "max"),
        )
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
    """Run the 4 detectors on one DAQ's CSV for one chunk.

    Returns the per-file result dict (see spec Output section).
    """
    df = pd.read_csv(csv_path)
    total_frames_in_csv = int(df["reconstructed_frame_index"].nunique())

    per_frame = reduce_to_per_frame(df)
    per_frame, trim_frames = apply_trim(per_frame, daq=daq, label=label)

    frame_nums = per_frame["frame_num"].tolist()
    device_ts = per_frame["timestamp"].tolist()
    host_ts = per_frame["buffer_recv_unix_time"].tolist()
    drop_counts = per_frame["dropped_buffer_count"].tolist()

    fn_result = detect_frame_num_gaps(frame_nums)
    dev_result = detect_timestamp_gaps(
        device_ts, threshold=GAP_THRESHOLD_MS, period=EXPECTED_PERIOD_MS, unit_label="ms"
    )
    host_result = detect_timestamp_gaps(
        host_ts, threshold=GAP_THRESHOLD_S, period=EXPECTED_PERIOD_MS / 1000.0, unit_label="s"
    )
    drop_result = detect_dropped_buffer_deltas(drop_counts)

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
        "frame_num": fn_result,
        "device_timestamp": dev_result,
        "host_timestamp": host_result,
        "dropped_buffer_count": drop_result,
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
            "frame_num_drops": 0,
            "device_ts_drops": 0,
            "host_ts_drops": 0,
            "buffer_drops": 0,
        }
        for r in files:
            row = {
                "file": r["file"],
                "analyzed_frames": r["analyzed_frames"],
                "frame_num_drops": r["frame_num"]["silent_drops"],
                "device_ts_drops": r["device_timestamp"]["silent_drops"],
                "host_ts_drops": r["host_timestamp"]["silent_drops"],
                "buffer_drops": r["dropped_buffer_count"]["total_delta"],
            }
            per_file_rows.append(row)
            for k in totals:
                totals[k] += row[k]
        summary[daq_key] = {"per_file": per_file_rows, "totals": totals}
    return summary


def run():
    per_daq_results = {"DAQ1": [], "DAQ2": []}

    for daq1_label, daq2_label in PAIRS:
        for daq, daq_dir, label in [
            (1, DAQ1_DIR, daq1_label),
            (2, DAQ2_DIR, daq2_label),
        ]:
            csv_path = find_csv(daq_dir, label)
            if csv_path is None:
                print(f"SKIP DAQ{daq} {label}: CSV not found")
                continue
            result = analyze_file(csv_path, daq=daq, label=label)
            out_path = write_per_file_json(result, daq_dir)
            per_daq_results[f"DAQ{daq}"].append(result)
            print(
                f"DAQ{daq} {label}: analyzed={result['analyzed_frames']} "
                f"frame_num={result['frame_num']['silent_drops']} "
                f"device_ts={result['device_timestamp']['silent_drops']} "
                f"host_ts={result['host_timestamp']['silent_drops']} "
                f"buffer={result['dropped_buffer_count']['total_delta']} "
                f"-> {out_path}"
            )

    summary = build_summary(per_daq_results)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    summary_path = os.path.join(OUTPUT_DIR, "silent_drops_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSummary written to: {summary_path}")

    return per_daq_results, summary


if __name__ == "__main__":
    run()
