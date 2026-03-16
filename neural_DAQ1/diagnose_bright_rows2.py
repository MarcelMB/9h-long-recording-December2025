#!/usr/bin/env python3
"""Deeper scan: compute per-row max projection and find frames contributing to bright rows."""

import cv2
import numpy as np
import os

AVI_PATH = "/Users/mbrosch/Documents/9h_long_recording_December2025/neural_DAQ1/output/WL27_stitched_chunk_01.avi"

cap = cv2.VideoCapture(AVI_PATH)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
print(f"Scanning {total} frames...")

# Track max pixel value per row across all frames
row_max_projection = np.zeros(200, dtype=np.float64)
# Track which frame produced the max for each row
row_max_frame = np.zeros(200, dtype=int)
# Track per-row max mean across frames
row_mean_max = np.zeros(200, dtype=np.float64)
row_mean_max_frame = np.zeros(200, dtype=int)

# Also collect frames where ANY row deviates significantly from frame median
# Use a more sensitive threshold
suspect_frames = []
frame_idx = 0

while True:
    ret, frame = cap.read()
    if not ret:
        break
    if len(frame.shape) == 3:
        frame = frame[:, :, 0]

    row_means = np.mean(frame, axis=1)
    row_maxes = np.max(frame, axis=1).astype(np.float64)
    frame_median = np.median(row_means)

    # Update max projection tracking
    for r in range(200):
        if row_maxes[r] > row_max_projection[r]:
            row_max_projection[r] = row_maxes[r]
            row_max_frame[r] = frame_idx
        if row_means[r] > row_mean_max[r]:
            row_mean_max[r] = row_means[r]
            row_mean_max_frame[r] = frame_idx

    # Detect: row mean > frame_median + 30 (more sensitive)
    deviation = row_means - frame_median
    bright_mask = deviation > 30
    n_bright = int(np.sum(bright_mask))

    if n_bright > 0:
        bright_rows = np.where(bright_mask)[0]
        suspect_frames.append({
            "frame": frame_idx,
            "n_bright_rows": n_bright,
            "bright_row_indices": bright_rows.tolist(),
            "deviations": deviation[bright_mask].tolist(),
            "bright_row_means": row_means[bright_mask].tolist(),
            "frame_median": float(frame_median),
        })

    frame_idx += 1
    if frame_idx % 10000 == 0:
        print(f"  {frame_idx}/{total} — found {len(suspect_frames)} suspect frames so far")

cap.release()

print(f"\nDone. Found {len(suspect_frames)} frames with bright row deviations (>30 above median).\n")

# Show rows where the max projection is brightest (top and bottom regions)
print("=== Per-row max projection (pixel max across all frames) ===")
print("Top 15 rows (0-14):")
for r in range(15):
    print(f"  Row {r:>3}: max_pixel={row_max_projection[r]:.0f} (frame {row_max_frame[r]}), "
          f"max_mean={row_mean_max[r]:.1f} (frame {row_mean_max_frame[r]})")

print("Bottom 35 rows (165-199):")
for r in range(165, 200):
    print(f"  Row {r:>3}: max_pixel={row_max_projection[r]:.0f} (frame {row_max_frame[r]}), "
          f"max_mean={row_mean_max[r]:.1f} (frame {row_mean_max_frame[r]})")

# Find the unique frames responsible for bright bottom/top rows
print("\n=== Frames responsible for max projection artifacts ===")
artifact_frames = set()
# Bottom rows 160-199
for r in range(160, 200):
    if row_max_projection[r] > 200:
        artifact_frames.add(row_max_frame[r])
# Top rows 0-15
for r in range(0, 16):
    if row_max_projection[r] > 200:
        artifact_frames.add(row_max_frame[r])

print(f"Unique frames causing bright artifacts (pixel > 200) in top/bottom rows: {sorted(artifact_frames)}")

# Also check: frames where row_mean_max is much higher than typical
print(f"\n=== Suspect frames detail ===")
print(f"Total suspect frames: {len(suspect_frames)}")
if suspect_frames:
    for sf in suspect_frames[:30]:
        rows_str = str(sf["bright_row_indices"][:15])
        devs_str = str([f'{d:.0f}' for d in sf["deviations"][:10]])
        print(f"  Frame {sf['frame']:>6}: {sf['n_bright_rows']:>2} bright rows, "
              f"rows={rows_str}, dev={devs_str}, median={sf['frame_median']:.1f}")
