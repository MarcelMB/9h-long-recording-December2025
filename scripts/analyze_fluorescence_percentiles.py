#!/usr/bin/env python3
"""
Compute multiple spatial percentiles of fluorescence over time (full FOV).

For each frame, computes several percentiles across all pixels, then bins
to 1-minute averages. Plots rolling 10th temporal percentile for each
spatial percentile to assess whether photobleaching is consistent across
brightness levels.

Output:
  output/fluorescence_percentiles.png  — multi-percentile baseline plot
  output/fluorescence_percentiles.npz  — raw data arrays
"""

import os
import numpy as np
import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE_DIR = "/Users/mbrosch/Documents/9h_long_recording_December2025"
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

FPS = 20.0
BIN_FRAMES = int(FPS * 60)  # 1200 frames = 1 minute

FIRST_CHUNK = 2
LAST_CHUNK = 9
TRIM_BINS = 10

# Spatial percentiles to compute per frame
SPATIAL_PCTS = [10, 25, 50, 75, 90]

# Temporal rolling percentile for baseline
TEMPORAL_WINDOW = 30  # minutes
TEMPORAL_PCT = 10


def main():
    n_pcts = len(SPATIAL_PCTS)
    # Accumulators: one sum per spatial percentile
    all_bins = [[] for _ in range(n_pcts)]
    bin_sums = [0.0] * n_pcts
    bin_count = 0
    total_frames = 0

    for chunk_idx in range(FIRST_CHUNK, LAST_CHUNK + 1):
        avi_path = os.path.join(OUTPUT_DIR, f"WL27_stitched_chunk_{chunk_idx:02d}.avi")
        print(f"Processing {os.path.basename(avi_path)} ...")

        cap = cv2.VideoCapture(avi_path)
        if not cap.isOpened():
            print(f"  ERROR: Cannot open {avi_path}")
            continue

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if len(frame.shape) == 3:
                frame = frame[:, :, 0]

            pct_vals = np.percentile(frame, SPATIAL_PCTS)
            for j in range(n_pcts):
                bin_sums[j] += pct_vals[j]
            bin_count += 1
            total_frames += 1

            if bin_count == BIN_FRAMES:
                for j in range(n_pcts):
                    all_bins[j].append(bin_sums[j] / bin_count)
                    bin_sums[j] = 0.0
                bin_count = 0

        # Flush partial bin
        if bin_count > 0:
            for j in range(n_pcts):
                all_bins[j].append(bin_sums[j] / bin_count)
                bin_sums[j] = 0.0
            bin_count = 0

        cap.release()
        print(f"  Done — {total_frames} total frames so far, {len(all_bins[0])} bins")

    # Convert to arrays and trim
    all_bins = [np.array(b)[TRIM_BINS:] for b in all_bins]
    time_hours = np.arange(len(all_bins[0])) / 60.0

    # Save raw data
    npz_path = os.path.join(OUTPUT_DIR, "fluorescence_percentiles.npz")
    save_dict = {"time_hours": time_hours, "spatial_percentiles": np.array(SPATIAL_PCTS)}
    for j, pct in enumerate(SPATIAL_PCTS):
        save_dict[f"p{pct}"] = all_bins[j]
    np.savez(npz_path, **save_dict)
    print(f"\nSaved raw data: {npz_path}")

    # Compute rolling temporal percentile for each spatial percentile
    half_win = TEMPORAL_WINDOW // 2
    rolling_baselines = []
    for j in range(n_pcts):
        trace = all_bins[j]
        baseline = np.array([
            np.percentile(trace[max(0, i - half_win):i + half_win + 1], TEMPORAL_PCT)
            for i in range(len(trace))
        ])
        rolling_baselines.append(baseline)

    # Plot
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

    # Top: raw traces for all percentiles
    for j, pct in enumerate(SPATIAL_PCTS):
        ax1.plot(time_hours, all_bins[j], linewidth=0.5, color=colors[j], alpha=0.6,
                 label=f"Spatial P{pct}")
    ax1.set_ylabel("Fluorescence")
    ax1.set_title("WL27 — Spatial percentiles over time (full FOV, 1-min bins)")
    ax1.set_ylim(0, None)
    ax1.legend(loc="upper right")
    ax1.grid(True, alpha=0.3)

    # Bottom: rolling temporal baselines
    for j, pct in enumerate(SPATIAL_PCTS):
        bl = rolling_baselines[j]
        drift = bl[-1] - bl[0]
        drift_pct = 100.0 * drift / bl[0] if bl[0] != 0 else 0
        ax2.plot(time_hours, bl, linewidth=1.5, color=colors[j],
                 label=f"P{pct} baseline (drift: {drift:+.1f}, {drift_pct:+.1f}%)")
    ax2.set_xlabel("Time (hours)")
    ax2.set_ylabel("Fluorescence")
    ax2.set_title(f"Rolling {TEMPORAL_PCT}th temporal percentile ({TEMPORAL_WINDOW}-min window) — photobleaching check")
    ax2.set_xlim(0, time_hours[-1])
    ax2.set_ylim(0, None)
    ax2.legend(loc="upper right", fontsize=9)
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()

    png_path = os.path.join(OUTPUT_DIR, "fluorescence_percentiles.png")
    fig.savefig(png_path, dpi=150)
    print(f"Saved plot: {png_path}")

    print(f"\nBaseline drift summary:")
    for j, pct in enumerate(SPATIAL_PCTS):
        bl = rolling_baselines[j]
        print(f"  Spatial P{pct:2d}: start={bl[0]:.1f}, end={bl[-1]:.1f}, "
              f"drift={bl[-1]-bl[0]:+.1f} ({100*(bl[-1]-bl[0])/bl[0]:+.1f}%)")
    print(f"\nTotal: {total_frames} frames, {len(all_bins[0])} bins, {time_hours[-1]:.2f} hours")


if __name__ == "__main__":
    main()
