#!/usr/bin/env python3
"""
Compute 1-min binned spatial median for center 50x50 ROI from stitched videos.

Adds center_p50 to the existing fluorescence_percentiles.npz.

Output:
  output/fluorescence_percentiles.npz  — updated with center_p50 array
"""

import os
import numpy as np
import cv2

BASE_DIR = "/Users/mbrosch/Documents/9h_long_recording_December2025"
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

FPS = 20.0
BIN_FRAMES = int(FPS * 60)  # 1200 frames = 1 minute

FIRST_CHUNK = 2
LAST_CHUNK = 9
TRIM_BINS = 10

# Center 50x50 ROI in 200x200 frame
ROI_R0, ROI_R1 = 75, 125
ROI_C0, ROI_C1 = 75, 125


def main():
    bins_median = []
    bins_mean = []
    bins_min = []
    bins_max = []
    # Collect per-frame values within each bin
    bin_vals_median = []
    bin_vals_mean = []
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

            roi = frame[ROI_R0:ROI_R1, ROI_C0:ROI_C1]
            bin_vals_median.append(np.median(roi))
            bin_vals_mean.append(np.mean(roi))
            total_frames += 1

            if len(bin_vals_median) == BIN_FRAMES:
                arr = np.array(bin_vals_median)
                bins_median.append(arr.mean())
                bins_min.append(arr.min())
                bins_max.append(arr.max())
                bins_mean.append(np.mean(bin_vals_mean))
                bin_vals_median = []
                bin_vals_mean = []

        # Flush partial bin
        if len(bin_vals_median) > 0:
            arr = np.array(bin_vals_median)
            bins_median.append(arr.mean())
            bins_min.append(arr.min())
            bins_max.append(arr.max())
            bins_mean.append(np.mean(bin_vals_mean))
            bin_vals_median = []
            bin_vals_mean = []

        cap.release()
        print(f"  Done — {total_frames} total frames, {len(bins_median)} bins")

    # Trim same as original
    center_p50 = np.array(bins_median)[TRIM_BINS:]
    center_mean = np.array(bins_mean)[TRIM_BINS:]
    center_min = np.array(bins_min)[TRIM_BINS:]
    center_max = np.array(bins_max)[TRIM_BINS:]

    # Load existing NPZ and add center ROI data
    npz_path = os.path.join(OUTPUT_DIR, "fluorescence_percentiles.npz")
    existing = dict(np.load(npz_path))
    existing["center_p50"] = center_p50
    existing["center_mean"] = center_mean
    existing["center_bin_min"] = center_min
    existing["center_bin_max"] = center_max
    np.savez(npz_path, **existing)

    print(f"\nSaved to {npz_path}")
    print(f"Center ROI: rows {ROI_R0}:{ROI_R1}, cols {ROI_C0}:{ROI_C1}")
    print(f"Median range: {center_p50.min():.1f} — {center_p50.max():.1f}")
    print(f"Bin min range: {center_min.min():.1f} — {center_min.max():.1f}")
    print(f"Bin max range: {center_max.min():.1f} — {center_max.max():.1f}")


if __name__ == "__main__":
    main()
