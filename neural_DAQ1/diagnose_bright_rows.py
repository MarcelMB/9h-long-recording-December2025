#!/usr/bin/env python3
"""Scan stitched chunk_01 to find frames with bright row artifacts and characterize them."""

import cv2
import numpy as np
import os

AVI_PATH = "/Users/mbrosch/Documents/9h_long_recording_December2025/neural_DAQ1/output/WL27_stitched_chunk_01.avi"

cap = cv2.VideoCapture(AVI_PATH)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
print(f"Scanning {total} frames...")

# For each frame, check for rows with abnormally high mean
# Normal tissue: row means roughly 42-145
# We'll flag rows with mean > 180 or where a row is much brighter than the frame median

suspect_frames = []
frame_idx = 0

while True:
    ret, frame = cap.read()
    if not ret:
        break
    if len(frame.shape) == 3:
        frame = frame[:, :, 0]

    row_means = np.mean(frame, axis=1)
    row_maxes = np.max(frame, axis=1)
    frame_median_row_mean = np.median(row_means)

    # Detect bright rows: rows where mean is much higher than frame median
    # or rows where mean > some absolute threshold
    bright_mask = row_means > max(frame_median_row_mean + 50, 180)
    n_bright = int(np.sum(bright_mask))

    if n_bright > 0:
        bright_rows = np.where(bright_mask)[0]
        suspect_frames.append({
            "frame": frame_idx,
            "n_bright_rows": n_bright,
            "bright_row_indices": bright_rows.tolist(),
            "bright_row_means": row_means[bright_mask].tolist(),
            "bright_row_maxes": row_maxes[bright_mask].tolist(),
            "frame_median_row_mean": float(frame_median_row_mean),
            "frame_mean": float(np.mean(frame)),
        })

    frame_idx += 1
    if frame_idx % 10000 == 0:
        print(f"  {frame_idx}/{total} — found {len(suspect_frames)} suspect frames so far")

cap.release()

print(f"\nDone. Found {len(suspect_frames)} frames with bright row artifacts.\n")

if suspect_frames:
    # Summarize
    all_bright_means = []
    all_frame_medians = []
    all_n_bright = []
    row_histogram = np.zeros(200, dtype=int)

    for sf in suspect_frames:
        all_bright_means.extend(sf["bright_row_means"])
        all_frame_medians.append(sf["frame_median_row_mean"])
        all_n_bright.append(sf["n_bright_rows"])
        for r in sf["bright_row_indices"]:
            row_histogram[r] += 1

    print(f"Bright row mean values: min={min(all_bright_means):.1f}, max={max(all_bright_means):.1f}, "
          f"median={np.median(all_bright_means):.1f}")
    print(f"Frame median row mean (context): min={min(all_frame_medians):.1f}, max={max(all_frame_medians):.1f}, "
          f"median={np.median(all_frame_medians):.1f}")
    print(f"Bright rows per frame: min={min(all_n_bright)}, max={max(all_n_bright)}, "
          f"mean={np.mean(all_n_bright):.1f}")

    print(f"\nWhich rows are most often bright (top 20):")
    top_rows = np.argsort(row_histogram)[::-1][:20]
    for r in top_rows:
        if row_histogram[r] > 0:
            print(f"  Row {r:>3}: {row_histogram[r]} times")

    print(f"\nFirst 10 suspect frames (details):")
    for sf in suspect_frames[:10]:
        print(f"  Frame {sf['frame']:>6}: {sf['n_bright_rows']} bright rows, "
              f"rows={sf['bright_row_indices'][:10]}, "
              f"means={[f'{m:.0f}' for m in sf['bright_row_means'][:10]]}, "
              f"frame_median={sf['frame_median_row_mean']:.1f}")

    print(f"\nLast 10 suspect frames (details):")
    for sf in suspect_frames[-10:]:
        print(f"  Frame {sf['frame']:>6}: {sf['n_bright_rows']} bright rows, "
              f"rows={sf['bright_row_indices'][:10]}, "
              f"means={[f'{m:.0f}' for m in sf['bright_row_means'][:10]]}, "
              f"frame_median={sf['frame_median_row_mean']:.1f}")
