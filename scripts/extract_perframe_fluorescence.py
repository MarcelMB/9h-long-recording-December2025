#!/usr/bin/env python3
"""
Extract per-frame spatial median for center 50x50 ROI from stitched videos.

Saves raw per-frame values (no binning) for use in sensitivity analysis.

Output:
  output/perframe_center_median.npz
"""

import os
import numpy as np
import cv2

BASE_DIR = "/Users/mbrosch/Documents/9h_long_recording_December2025"
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

FPS = 20.0
FIRST_CHUNK = 2
LAST_CHUNK = 9
TRIM_FRAMES = int(10 * 60 * FPS)  # 10 min = 12000 frames

ROI_R0, ROI_R1 = 75, 125
ROI_C0, ROI_C1 = 75, 125


def main():
    all_medians = []
    all_means = []
    total = 0

    for chunk_idx in range(FIRST_CHUNK, LAST_CHUNK + 1):
        avi_path = os.path.join(OUTPUT_DIR, f"WL27_stitched_chunk_{chunk_idx:02d}.avi")
        print(f"Processing {os.path.basename(avi_path)} ...")

        cap = cv2.VideoCapture(avi_path)
        if not cap.isOpened():
            print(f"  ERROR: Cannot open {avi_path}")
            continue

        chunk_count = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if len(frame.shape) == 3:
                frame = frame[:, :, 0]

            roi = frame[ROI_R0:ROI_R1, ROI_C0:ROI_C1]
            all_medians.append(np.median(roi))
            all_means.append(np.mean(roi))
            chunk_count += 1

        total += chunk_count
        cap.release()
        print(f"  {chunk_count} frames ({total} total)")

    medians = np.array(all_medians, dtype=np.float32)
    means = np.array(all_means, dtype=np.float32)

    # Trim first 10 min
    medians = medians[TRIM_FRAMES:]
    means = means[TRIM_FRAMES:]

    out_path = os.path.join(OUTPUT_DIR, "perframe_center_median.npz")
    np.savez(out_path, median=medians, mean=means, fps=FPS)
    print(f"\nSaved {len(medians)} frames to {out_path}")
    print(f"Trimmed first {TRIM_FRAMES} frames (10 min)")
    print(f"Median range: {medians.min():.1f} — {medians.max():.1f}")


if __name__ == "__main__":
    main()
