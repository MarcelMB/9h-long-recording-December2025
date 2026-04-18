#!/usr/bin/env python3
"""Analyze temporal distribution of dropped frames (both DAQs broken) in the stitched stream."""

import csv
import json
import os
import numpy as np
import matplotlib.pyplot as plt

BASE_DIR = "/Users/mbrosch/Documents/9h_long_recording_December2025"
DAQ1_DIR = os.path.join(BASE_DIR, "neural_DAQ1")
DAQ2_DIR = os.path.join(BASE_DIR, "neural_DAQ2")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

FPS = 20.0

PAIRS = [
    ("long-2",  "long-2",  "long",    "long"),
    ("long-4",  "long-4",  "long-2",  "long-2"),
    ("long-6",  "long-6",  "long-4",  "long-4"),
    ("long-8",  "long-8",  "long-6",  "long-6"),
    ("long-9",  "long-9",  "long-7",  "long-7"),
    ("long-10", "long-10", "long-8",  "long-8"),
    ("long-12", "long-12", "long-9",  "long-9"),
    ("long-13", "long-13", "long-10", "long-10"),
]

TRIM_SECONDS = {"long-2": 30, "long-9": 155}


def get_frame_timestamps(csv_path):
    frame_times = {}
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            fidx = int(row["reconstructed_frame_index"])
            t = float(row["buffer_recv_unix_time"])
            if fidx not in frame_times or t > frame_times[fidx]:
                frame_times[fidx] = t
    return frame_times


def get_broken_set(results_json_path):
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
    return broken, d["total_frames"]


def find_file(directory, label, ext, subdir=None):
    import glob
    search_dir = os.path.join(directory, subdir) if subdir else directory
    for pattern in [f"*_{label}.{ext}", f"*_{label}-*.{ext}", f"*{label}.{ext}"]:
        matches = glob.glob(os.path.join(search_dir, pattern))
        if matches:
            return matches[0]
    return None


def main():
    # Build the full stitched stream frame-by-frame, tracking which are dropped
    # Each entry: (global_stitched_idx, is_dropped, segment_label, timestamp)
    global_idx = 0
    drop_positions = []  # global indices of dropped frames
    all_positions = []   # (global_idx, is_dropped) for every matched frame

    for daq1_label, daq1_res, daq2_label, daq2_res in PAIRS:
        daq1_csv = find_file(DAQ1_DIR, daq1_label, "csv")
        daq2_csv = find_file(DAQ2_DIR, daq2_label, "csv")
        daq1_json = os.path.join(DAQ1_DIR, "results", f"{daq1_res}.json")
        daq2_json = os.path.join(DAQ2_DIR, "results", f"{daq2_res}.json")

        if not all(os.path.exists(p) for p in [daq1_csv, daq2_csv, daq1_json, daq2_json]):
            print(f"SKIP {daq1_label}")
            continue

        daq1_broken, daq1_total = get_broken_set(daq1_json)
        daq2_broken, daq2_total = get_broken_set(daq2_json)
        daq1_ftimes = {k: v for k, v in get_frame_timestamps(daq1_csv).items() if k < daq1_total}
        daq2_ftimes = {k: v for k, v in get_frame_timestamps(daq2_csv).items() if k < daq2_total}

        trim_frames = int(TRIM_SECONDS.get(daq1_label, 0) * FPS)
        if trim_frames > 0:
            max_d1 = daq1_total - trim_frames
            daq1_ftimes = {k: v for k, v in daq1_ftimes.items() if k < max_d1}

        d2_frames_sorted = sorted(daq2_ftimes.keys(), key=lambda k: daq2_ftimes[k])
        d2_times_sorted = np.array([daq2_ftimes[k] for k in d2_frames_sorted])

        for d1_idx in sorted(daq1_ftimes.keys()):
            t1 = daq1_ftimes[d1_idx]
            idx = np.searchsorted(d2_times_sorted, t1)
            best_dist = float("inf")
            best_d2_idx = None
            for candidate in [idx - 1, idx]:
                if 0 <= candidate < len(d2_times_sorted):
                    dist = abs(d2_times_sorted[candidate] - t1)
                    if dist < best_dist:
                        best_dist = dist
                        best_d2_idx = d2_frames_sorted[candidate]
            if best_dist > 0.025:
                continue

            both_bad = (d1_idx in daq1_broken) and (best_d2_idx in daq2_broken)
            if both_bad:
                drop_positions.append(global_idx)
            all_positions.append((global_idx, both_bad))
            global_idx += 1

    total_frames = global_idx
    print(f"Total matched frames: {total_frames}")
    print(f"Total dropped (both broken): {len(drop_positions)}")

    # Find consecutive runs of dropped frames
    runs = []
    if drop_positions:
        run_start = drop_positions[0]
        run_len = 1
        for i in range(1, len(drop_positions)):
            if drop_positions[i] == drop_positions[i-1] + 1:
                run_len += 1
            else:
                runs.append((run_start, run_len))
                run_start = drop_positions[i]
                run_len = 1
        runs.append((run_start, run_len))

    run_lengths = [r[1] for r in runs]
    print(f"\nDrop events (consecutive runs): {len(runs)}")
    if runs:
        print(f"Run length stats:")
        print(f"  Min: {min(run_lengths)} frames ({min(run_lengths)/FPS:.3f}s)")
        print(f"  Max: {max(run_lengths)} frames ({max(run_lengths)/FPS:.3f}s)")
        print(f"  Mean: {np.mean(run_lengths):.1f} frames ({np.mean(run_lengths)/FPS:.3f}s)")
        print(f"  Median: {np.median(run_lengths):.0f} frames ({np.median(run_lengths)/FPS:.3f}s)")

        # Distribution of run lengths
        print(f"\nRun length distribution:")
        max_len = max(run_lengths)
        bins = [1, 2, 3, 4, 5, 10, 20, 50, 100, max_len + 1]
        bin_labels = ["1", "2", "3", "4", "5-9", "10-19", "20-49", "50-99", "100+"]
        for i in range(len(bins) - 1):
            count = sum(1 for r in run_lengths if bins[i] <= r < bins[i+1])
            if count > 0:
                frames_in_bin = sum(r for r in run_lengths if bins[i] <= r < bins[i+1])
                print(f"  {bin_labels[i]:>5} frames: {count:>4} events ({frames_in_bin:>5} frames total, {frames_in_bin/FPS:.1f}s)")

    # --- Plotting ---
    fig, axes = plt.subplots(3, 1, figsize=(16, 12))

    # Plot 1: Timeline showing drop positions
    ax1 = axes[0]
    drop_times_h = np.array(drop_positions) / FPS / 3600
    ax1.eventplot([drop_times_h], lineoffsets=0, linelengths=1, colors='red', linewidths=0.5)
    ax1.set_xlim(0, total_frames / FPS / 3600)
    ax1.set_xlabel("Time (hours)")
    ax1.set_title(f"Dropped frames timeline ({len(drop_positions)} frames dropped across {total_frames} total)")
    ax1.set_yticks([])

    # Plot 2: Run length histogram
    ax2 = axes[1]
    if run_lengths:
        max_display = min(max(run_lengths), 100)
        ax2.hist(run_lengths, bins=range(1, max_display + 2), color='steelblue', edgecolor='black', linewidth=0.5)
        ax2.set_xlabel("Consecutive dropped frames (run length)")
        ax2.set_ylabel("Number of events")
        ax2.set_title(f"Distribution of drop run lengths ({len(runs)} events)")
        ax2.axvline(x=FPS, color='red', linestyle='--', alpha=0.7, label=f'1 second ({int(FPS)} frames)')
        ax2.legend()

    # Plot 3: Drop density over time (drops per minute)
    ax3 = axes[2]
    window_sec = 60  # 1-minute windows
    window_frames = int(window_sec * FPS)
    n_windows = total_frames // window_frames
    drop_arr = np.zeros(total_frames, dtype=np.int8)
    for dp in drop_positions:
        drop_arr[dp] = 1
    drops_per_min = []
    time_min = []
    for w in range(n_windows):
        start = w * window_frames
        end = start + window_frames
        drops_per_min.append(np.sum(drop_arr[start:end]))
        time_min.append((start + window_frames / 2) / FPS / 60)
    ax3.bar(time_min, drops_per_min, width=1.0, color='coral', edgecolor='none')
    ax3.set_xlabel("Time (minutes)")
    ax3.set_ylabel("Dropped frames per minute")
    ax3.set_title("Drop density over time (1-minute bins)")

    plt.tight_layout()
    out_path = os.path.join(OUTPUT_DIR, "drop_analysis.png")
    plt.savefig(out_path, dpi=150)
    print(f"\nPlot saved to: {out_path}")
    plt.close()

    # Also save the raw run data as JSON
    run_data = {
        "total_matched_frames": total_frames,
        "total_dropped": len(drop_positions),
        "total_drop_events": len(runs),
        "run_lengths": run_lengths,
        "runs": [{"global_frame_idx": r[0], "length": r[1], "time_h": r[0]/FPS/3600, "duration_s": r[1]/FPS} for r in runs],
    }
    json_path = os.path.join(OUTPUT_DIR, "drop_analysis.json")
    with open(json_path, "w") as f:
        json.dump(run_data, f, indent=2)
    print(f"Data saved to: {json_path}")


if __name__ == "__main__":
    main()
