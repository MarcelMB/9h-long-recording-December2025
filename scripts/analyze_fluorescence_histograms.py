#!/usr/bin/env python3
"""
Pixel brightness histograms per hour, overlaid to check distribution stability.

For each stitched chunk (1 hour), builds a histogram of all pixel intensities
(sampled every 10th frame for speed) and overlays all hours on one plot.

Output:
  output/fluorescence_histograms.png  — overlaid per-hour histograms
"""

import os
import numpy as np
import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE_DIR = "/Users/mbrosch/Documents/9h_long_recording_December2025"
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

FIRST_CHUNK = 2
LAST_CHUNK = 9
SAMPLE_EVERY = 10  # read every Nth frame


def main():
    fig, ax = plt.subplots(figsize=(10, 6))
    bins = np.arange(257)  # 0-255 + right edge
    colors = plt.cm.viridis(np.linspace(0, 1, LAST_CHUNK - FIRST_CHUNK + 1))

    for i, chunk_idx in enumerate(range(FIRST_CHUNK, LAST_CHUNK + 1)):
        avi_path = os.path.join(OUTPUT_DIR, f"WL27_stitched_chunk_{chunk_idx:02d}.avi")
        print(f"Processing {os.path.basename(avi_path)} ...")

        cap = cv2.VideoCapture(avi_path)
        if not cap.isOpened():
            print(f"  ERROR: Cannot open {avi_path}")
            continue

        hist_accum = np.zeros(256, dtype=np.int64)
        frame_count = 0
        read_count = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            read_count += 1

            if read_count % SAMPLE_EVERY != 0:
                continue

            if len(frame.shape) == 3:
                frame = frame[:, :, 0]

            h = np.bincount(frame.ravel(), minlength=256)
            hist_accum += h
            frame_count += 1

        cap.release()

        # Normalize to density
        total_pixels = hist_accum.sum()
        density = hist_accum / total_pixels

        hour_label = i + 1  # hour 1 = chunk 02, etc.
        ax.plot(np.arange(256), density, linewidth=1.0, color=colors[i],
                alpha=0.8, label=f"Hour {hour_label} (chunk {chunk_idx:02d})")

        print(f"  Done — {frame_count} frames sampled, "
              f"mean={np.average(np.arange(256), weights=density):.1f}")

    ax.set_xlabel("Pixel intensity")
    ax.set_ylabel("Density")
    ax.set_title("WL27 — Pixel brightness distribution per hour (full FOV)")
    ax.set_xlim(0, 255)
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    png_path = os.path.join(OUTPUT_DIR, "fluorescence_histograms.png")
    fig.savefig(png_path, dpi=150)
    print(f"\nSaved plot: {png_path}")


if __name__ == "__main__":
    main()
