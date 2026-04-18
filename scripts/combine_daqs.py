#!/usr/bin/env python3
"""Match DAQ1 and DAQ2 frames by unix timestamp and compute combined error rate."""

import csv
import json
import glob
import os
import numpy as np

BASE_DIR = "/Users/mbrosch/Documents/9h_long_recording_December2025"
DAQ1_DIR = os.path.join(BASE_DIR, "neural_DAQ1")
DAQ2_DIR = os.path.join(BASE_DIR, "neural_DAQ2")

# Pairs: (DAQ1 csv, DAQ1 results json, DAQ2 csv, DAQ2 results json)
PAIRS = [
    ("long-2",  "long-2",   "long",     "long"),
    ("long-4",  "long-4",   "long-2",   "long-2"),
    ("long-6",  "long-6",   "long-4",   "long-4"),
    ("long-8",  "long-8",   "long-6",   "long-6"),
    ("long-9",  "long-9",   "long-7",   "long-7"),
    ("long-10", "long-10",  "long-8",   "long-8"),
    ("long-12", "long-12",  "long-9",   "long-9"),
    ("long-13", "long-13",  "long-10",  "long-10"),
]


def get_frame_timestamps(csv_path):
    """Extract per-frame completion timestamps from buffer-level CSV.
    Returns dict: frame_index -> last_buffer_unix_time
    """
    frame_times = {}
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            fidx = int(row["reconstructed_frame_index"])
            t = float(row["buffer_recv_unix_time"])
            # Keep the latest (last) buffer time for each frame
            if fidx not in frame_times or t > frame_times[fidx]:
                frame_times[fidx] = t
    return frame_times


def get_broken_set(results_json_path):
    """Load broken frame indices as a set."""
    with open(results_json_path) as f:
        d = json.load(f)
    broken = set()
    for entry in d["black_frames"]:
        broken.add(entry["frame"])
    for entry in d["gradient_frames"]:
        broken.add(entry["frame"])
    for entry in d["both_frames"]:
        broken.add(entry["frame"])
    for entry in d.get("bright_frames", []):
        broken.add(entry["frame"])
    return broken, d["total_frames"], d["total_broken"]


def find_csv(directory, label):
    """Find the CSV file matching the label."""
    pattern = os.path.join(directory, f"*{label}.csv")
    matches = glob.glob(pattern)
    if not matches:
        # Try without trailing part
        for f in glob.glob(os.path.join(directory, "*.csv")):
            base = os.path.basename(f).replace(".csv", "")
            if base.endswith(f"_{label}") or base.endswith(f"-{label}") or base == label:
                return f
    return matches[0] if matches else None


def find_results_json(directory, label):
    """Find the results JSON matching the label."""
    path = os.path.join(directory, "results", f"{label}.json")
    if os.path.exists(path):
        return path
    return None


def main():
    grand_daq1_total = 0
    grand_daq1_broken = 0
    grand_daq2_total = 0
    grand_daq2_broken = 0
    grand_matched = 0
    grand_both_broken = 0
    grand_daq1_only_broken = 0
    grand_daq2_only_broken = 0
    grand_unmatched_daq1 = 0
    grand_unmatched_daq2 = 0

    print("=" * 110)
    print(f"{'Segment':<18} {'DAQ1':>8} {'DAQ1 err':>9} {'DAQ2':>8} {'DAQ2 err':>9} {'Matched':>8} {'Both bad':>9} {'Rescued':>8} {'Combined %':>11}")
    print("=" * 110)

    for daq1_csv_label, daq1_res_label, daq2_csv_label, daq2_res_label in PAIRS:
        # Find files
        daq1_csv = find_csv(DAQ1_DIR, daq1_csv_label)
        daq2_csv = find_csv(DAQ2_DIR, daq2_csv_label)
        daq1_json = find_results_json(DAQ1_DIR, daq1_res_label)
        daq2_json = find_results_json(DAQ2_DIR, daq2_res_label)

        if not all([daq1_csv, daq2_csv, daq1_json, daq2_json]):
            print(f"SKIP {daq1_csv_label}: missing files")
            continue

        # Load broken frame sets
        daq1_broken, daq1_total, daq1_n_broken = get_broken_set(daq1_json)
        daq2_broken, daq2_total, daq2_n_broken = get_broken_set(daq2_json)

        # Get frame timestamps, clamp to frames that actually exist in AVI
        daq1_ftimes = {k: v for k, v in get_frame_timestamps(daq1_csv).items() if k < daq1_total}
        daq2_ftimes = {k: v for k, v in get_frame_timestamps(daq2_csv).items() if k < daq2_total}

        # Build sorted arrays for DAQ2 for fast nearest-neighbor lookup
        daq2_frames_sorted = sorted(daq2_ftimes.keys(), key=lambda k: daq2_ftimes[k])
        daq2_times_sorted = np.array([daq2_ftimes[k] for k in daq2_frames_sorted])

        # Match each DAQ1 frame to nearest DAQ2 frame by timestamp
        matched = 0
        both_broken = 0
        daq1_only_broken = 0  # broken in DAQ1, rescued by DAQ2
        daq2_only_broken = 0  # broken in DAQ2, DAQ1 is fine
        unmatched_daq1 = 0
        matched_daq2_frames = set()

        for daq1_fidx in sorted(daq1_ftimes.keys()):
            t1 = daq1_ftimes[daq1_fidx]

            # Find nearest DAQ2 frame
            idx = np.searchsorted(daq2_times_sorted, t1)
            best_dist = float("inf")
            best_daq2_fidx = None

            for candidate in [idx - 1, idx]:
                if 0 <= candidate < len(daq2_times_sorted):
                    dist = abs(daq2_times_sorted[candidate] - t1)
                    if dist < best_dist:
                        best_dist = dist
                        best_daq2_fidx = daq2_frames_sorted[candidate]

            if best_dist > 0.025:  # >25ms = no match (half of 50ms frame interval)
                unmatched_daq1 += 1
                continue

            matched += 1
            matched_daq2_frames.add(best_daq2_fidx)

            d1_bad = daq1_fidx in daq1_broken
            d2_bad = best_daq2_fidx in daq2_broken

            if d1_bad and d2_bad:
                both_broken += 1
            elif d1_bad:
                daq1_only_broken += 1  # rescued!
            elif d2_bad:
                daq2_only_broken += 1

        unmatched_daq2 = len(daq2_ftimes) - len(matched_daq2_frames)

        combined_pct = 100 * both_broken / matched if matched > 0 else 0
        rescued = daq1_only_broken + daq2_only_broken
        seg_name = f"DAQ1:{daq1_csv_label}"

        print(f"{seg_name:<18} {daq1_total:>8} {daq1_n_broken:>9} {daq2_total:>8} {daq2_n_broken:>9} {matched:>8} {both_broken:>9} {rescued:>8} {combined_pct:>10.2f}%")

        grand_daq1_total += daq1_total
        grand_daq1_broken += daq1_n_broken
        grand_daq2_total += daq2_total
        grand_daq2_broken += daq2_n_broken
        grand_matched += matched
        grand_both_broken += both_broken
        grand_daq1_only_broken += daq1_only_broken
        grand_daq2_only_broken += daq2_only_broken
        grand_unmatched_daq1 += unmatched_daq1
        grand_unmatched_daq2 += unmatched_daq2

    print("=" * 110)
    combined_pct = 100 * grand_both_broken / grand_matched if grand_matched > 0 else 0
    total_rescued = grand_daq1_only_broken + grand_daq2_only_broken
    print(f"{'TOTAL':<18} {grand_daq1_total:>8} {grand_daq1_broken:>9} {grand_daq2_total:>8} {grand_daq2_broken:>9} {grand_matched:>8} {grand_both_broken:>9} {total_rescued:>8} {combined_pct:>10.2f}%")

    print()
    print("SUMMARY")
    print("-" * 50)
    print(f"DAQ1 alone:     {grand_daq1_broken:>6} / {grand_daq1_total:>6} broken ({100*grand_daq1_broken/grand_daq1_total:.2f}%)")
    print(f"DAQ2 alone:     {grand_daq2_broken:>6} / {grand_daq2_total:>6} broken ({100*grand_daq2_broken/grand_daq2_total:.2f}%)")
    print(f"Combined stream: {grand_both_broken:>5} / {grand_matched:>6} broken ({combined_pct:.2f}%)")
    print(f"Frames matched:  {grand_matched:>6} (unmatched: DAQ1={grand_unmatched_daq1}, DAQ2={grand_unmatched_daq2})")
    print(f"Frames rescued:  {total_rescued:>6} (DAQ1 bad->DAQ2 good: {grand_daq1_only_broken}, DAQ2 bad->DAQ1 good: {grand_daq2_only_broken})")


if __name__ == "__main__":
    main()
