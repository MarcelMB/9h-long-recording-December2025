#!/usr/bin/env python3
"""
Compute average fluorescence over time using the full field of view (200x200).

Same analysis as analyze_fluorescence.py but without ROI cropping.

Output:
  output/fluorescence_over_time_fullFOV.png  — two-panel plot (LPF + baseline)
  output/fluorescence_over_time_fullFOV.npz  — raw data arrays
"""

import os
import numpy as np
import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.signal import butter, filtfilt

BASE_DIR = "/Users/mbrosch/Documents/9h_long_recording_December2025"
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

FPS = 20.0
BIN_FRAMES = int(FPS * 60)  # 1200 frames = 1 minute

FIRST_CHUNK = 2  # skip chunk 01 (wrong excitation light)
LAST_CHUNK = 9
TRIM_BINS = 10  # skip first 10 minutes (excitation ramp-up)
LPF_CUTOFF_MIN = 30.0
PERCENTILE_WINDOW = 30
PERCENTILE = 10


def main():
    all_bin_means = []
    total_frames = 0

    for chunk_idx in range(FIRST_CHUNK, LAST_CHUNK + 1):
        avi_path = os.path.join(OUTPUT_DIR, f"WL27_stitched_chunk_{chunk_idx:02d}.avi")
        print(f"Processing {os.path.basename(avi_path)} ...")

        cap = cv2.VideoCapture(avi_path)
        if not cap.isOpened():
            print(f"  ERROR: Cannot open {avi_path}")
            continue

        bin_sum = 0.0
        bin_count = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if len(frame.shape) == 3:
                frame = frame[:, :, 0]

            bin_sum += frame.mean()
            bin_count += 1
            total_frames += 1

            if bin_count == BIN_FRAMES:
                all_bin_means.append(bin_sum / bin_count)
                bin_sum = 0.0
                bin_count = 0

        if bin_count > 0:
            all_bin_means.append(bin_sum / bin_count)

        cap.release()
        print(f"  Done — {total_frames} total frames so far, {len(all_bin_means)} bins")

    all_bin_means = np.array(all_bin_means)

    # Save raw (untrimmed) data
    raw_time = np.arange(len(all_bin_means)) / 60.0
    npz_path = os.path.join(OUTPUT_DIR, "fluorescence_over_time_fullFOV.npz")
    np.savez(npz_path, time_hours=raw_time, mean_fluorescence=all_bin_means)
    print(f"\nSaved raw data: {npz_path}")

    # Trim first N minutes
    trimmed = all_bin_means[TRIM_BINS:]
    time_hours = np.arange(len(trimmed)) / 60.0

    # LPF
    fs = 1.0
    cutoff_freq = 1.0 / LPF_CUTOFF_MIN
    nyq = fs / 2.0
    b, a = butter(2, cutoff_freq / nyq, btype="low")
    filtered = filtfilt(b, a, trimmed)

    # Rolling 10th percentile
    half_win = PERCENTILE_WINDOW // 2
    rolling_pct = np.array([
        np.percentile(trimmed[max(0, i - half_win):i + half_win + 1], PERCENTILE)
        for i in range(len(trimmed))
    ])

    # Plot: two rows
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

    ax1.plot(time_hours, trimmed, linewidth=0.5, color="forestgreen", alpha=0.5, label="Raw (1-min bins)")
    ax1.plot(time_hours, filtered, linewidth=1.5, color="darkgreen", label=f"LPF ({LPF_CUTOFF_MIN:.0f}-min cutoff)")
    ax1.set_ylabel("Mean fluorescence (full FOV)")
    ax1.set_title("WL27 — Average fluorescence, full FOV (chunks 02–09, first 10 min trimmed)")
    ax1.set_ylim(0, None)
    ax1.legend(loc="upper right")
    ax1.grid(True, alpha=0.3)

    ax2.plot(time_hours, trimmed, linewidth=0.5, color="forestgreen", alpha=0.5, label="Raw (1-min bins)")
    ax2.plot(time_hours, rolling_pct, linewidth=1.5, color="darkred",
             label=f"Rolling {PERCENTILE}th percentile ({PERCENTILE_WINDOW}-min window)")
    ax2.set_xlabel("Time (hours)")
    ax2.set_ylabel("Mean fluorescence (full FOV)")
    ax2.set_title("Baseline estimate (lower envelope — photobleaching indicator)")
    ax2.set_xlim(0, time_hours[-1])
    ax2.set_ylim(0, None)
    ax2.legend(loc="upper right")
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()

    png_path = os.path.join(OUTPUT_DIR, "fluorescence_over_time_fullFOV.png")
    fig.savefig(png_path, dpi=150)
    print(f"Saved plot: {png_path}")
    print(f"\nBaseline (10th pct): start={rolling_pct[0]:.1f}, end={rolling_pct[-1]:.1f}, "
          f"drift={rolling_pct[-1] - rolling_pct[0]:.1f}")
    print(f"Total: {total_frames} frames, {len(trimmed)} bins (after trim), {time_hours[-1]:.2f} hours")


if __name__ == "__main__":
    main()
