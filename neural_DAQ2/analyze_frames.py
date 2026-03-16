#!/usr/bin/env python3
"""Analyze a single AVI file for broken frames (black rows / checkerboard artifacts)."""

import sys
import json
import cv2
import numpy as np
import os

def analyze_video(avi_path):
    cap = cv2.VideoCapture(avi_path)
    if not cap.isOpened():
        print(f"ERROR: Cannot open {avi_path}", file=sys.stderr)
        sys.exit(1)

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fname = os.path.basename(avi_path)
    print(f"Processing {fname}: {total_frames} frames", file=sys.stderr)

    black_frames = []      # frames with black row artifacts
    checker_frames = []    # frames with checkerboard artifacts
    both_frames = []       # frames with both

    frame_idx = 0
    report_interval = 10000

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if len(frame.shape) == 3:
            frame = frame[:, :, 0]

        # --- Black row detection ---
        row_means = np.mean(frame, axis=1)
        has_black = bool(np.any(row_means < 2))
        n_black_rows = int(np.sum(row_means < 2)) if has_black else 0

        # --- Checkerboard detection ---
        even_cols = frame[:, 0::2].astype(np.float32)
        odd_cols = frame[:, 1::2].astype(np.float32)
        checker_score = np.mean(np.abs(even_cols - odd_cols), axis=1)
        has_checker = bool(np.any(checker_score > 30))
        n_checker_rows = int(np.sum(checker_score > 30)) if has_checker else 0

        if has_black and has_checker:
            both_frames.append({
                "frame": frame_idx,
                "black_rows": n_black_rows,
                "checker_rows": n_checker_rows
            })
        elif has_black:
            black_frames.append({
                "frame": frame_idx,
                "black_rows": n_black_rows
            })
        elif has_checker:
            checker_frames.append({
                "frame": frame_idx,
                "checker_rows": n_checker_rows
            })

        frame_idx += 1
        if frame_idx % report_interval == 0:
            print(f"  {fname}: {frame_idx}/{total_frames} frames processed", file=sys.stderr)

    cap.release()

    total_broken = len(black_frames) + len(checker_frames) + len(both_frames)
    total_good = frame_idx - total_broken

    result = {
        "file": fname,
        "total_frames": frame_idx,
        "total_broken": total_broken,
        "total_good": total_good,
        "black_only_count": len(black_frames),
        "checker_only_count": len(checker_frames),
        "both_count": len(both_frames),
        "black_frames": black_frames,
        "checker_frames": checker_frames,
        "both_frames": both_frames,
    }

    return result


if __name__ == "__main__":
    avi_path = sys.argv[1]
    output_path = sys.argv[2]

    result = analyze_video(avi_path)

    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"Done: {result['file']} — {result['total_broken']}/{result['total_frames']} broken frames", file=sys.stderr)
