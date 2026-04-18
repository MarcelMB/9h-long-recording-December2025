#!/usr/bin/env python3
"""Analyze a single AVI file for broken frames.

Detects two artifact types (mio-style):
  1. Black rows:      >= 30 consecutive pixels == 0, and >= 10 such rows per frame
  2. Gradient noise:  mean |second derivative| per row > 20

Optionally writes per-category debug AVIs (black, gradient, both).
"""

import sys
import json
import cv2
import numpy as np
import os


def analyze_video(avi_path, debug_dir=None):
    cap = cv2.VideoCapture(avi_path)
    if not cap.isOpened():
        print(f"ERROR: Cannot open {avi_path}", file=sys.stderr)
        sys.exit(1)

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fname = os.path.basename(avi_path)
    stem = fname.replace(".avi", "")
    print(f"Processing {fname}: {total_frames} frames", file=sys.stderr)

    # Debug video writers
    dbg_black = dbg_gradient = dbg_both = None
    if debug_dir:
        os.makedirs(debug_dir, exist_ok=True)
        fps = cap.get(cv2.CAP_PROP_FPS) or 20.0
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        dbg_black = cv2.VideoWriter(os.path.join(debug_dir, f"{stem}_black.avi"), 0, fps, (w, h), isColor=False)
        dbg_gradient = cv2.VideoWriter(os.path.join(debug_dir, f"{stem}_gradient.avi"), 0, fps, (w, h), isColor=False)
        dbg_both = cv2.VideoWriter(os.path.join(debug_dir, f"{stem}_both.avi"), 0, fps, (w, h), isColor=False)

    black_frames = []
    gradient_frames = []
    both_frames = []       # black + gradient

    frame_idx = 0
    report_interval = 10000

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if len(frame.shape) == 3:
            frame = frame[:, :, 0]

        frame_f32 = frame.astype(np.float32)

        # --- Black row detection (mio-style, vectorized) ---
        # Per-pixel: == 0 is "black"; per-row: >= 30 consecutive zero pixels
        black_mask = (frame == 0).astype(np.float32)
        # Sliding window sum via cumsum for speed
        cs = np.cumsum(black_mask, axis=1)
        run_len = 30
        run_sum = cs[:, run_len:] - cs[:, :-run_len]
        row_has_run = np.any(run_sum >= run_len, axis=1)
        n_black_rows = int(np.sum(row_has_run))
        has_black = n_black_rows >= 10  # require 10+ black rows to flag frame

        # --- Gradient detection (mio-style) ---
        # Second derivative along columns, per-row mean of absolute values
        if frame_f32.shape[1] >= 3:
            second_deriv = np.diff(frame_f32, n=2, axis=1)
            gradient_score = np.abs(second_deriv).mean(axis=1)
            has_gradient = bool(np.any(gradient_score > 20))
            n_gradient_rows = int(np.sum(gradient_score > 20))
        else:
            has_gradient = False
            n_gradient_rows = 0

        # Categorize frame
        if has_black and has_gradient:
            both_frames.append({
                "frame": frame_idx,
                "black_rows": n_black_rows,
                "gradient_rows": n_gradient_rows
            })
            if dbg_both:
                dbg_both.write(frame)
        elif has_black:
            black_frames.append({
                "frame": frame_idx,
                "black_rows": n_black_rows
            })
            if dbg_black:
                dbg_black.write(frame)
        elif has_gradient:
            gradient_frames.append({
                "frame": frame_idx,
                "gradient_rows": n_gradient_rows
            })
            if dbg_gradient:
                dbg_gradient.write(frame)

        frame_idx += 1
        if frame_idx % report_interval == 0:
            print(f"  {fname}: {frame_idx}/{total_frames} frames processed", file=sys.stderr)

    cap.release()
    if dbg_black:
        dbg_black.release()
    if dbg_gradient:
        dbg_gradient.release()
    if dbg_both:
        dbg_both.release()

    total_broken = len(black_frames) + len(gradient_frames) + len(both_frames)
    total_good = frame_idx - total_broken

    result = {
        "file": fname,
        "total_frames": frame_idx,
        "total_broken": total_broken,
        "total_good": total_good,
        "black_only_count": len(black_frames),
        "gradient_only_count": len(gradient_frames),
        "both_count": len(both_frames),
        "black_frames": black_frames,
        "gradient_frames": gradient_frames,
        "both_frames": both_frames,
    }

    return result


if __name__ == "__main__":
    avi_path = sys.argv[1]
    output_path = sys.argv[2]
    debug_dir = sys.argv[3] if len(sys.argv) > 3 else None

    result = analyze_video(avi_path, debug_dir=debug_dir)

    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"Done: {result['file']} — {result['total_broken']}/{result['total_frames']} broken "
          f"(black={result['black_only_count']}, gradient={result['gradient_only_count']}, "
          f"both={result['both_count']})", file=sys.stderr)
