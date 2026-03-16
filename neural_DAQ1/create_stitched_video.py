#!/usr/bin/env python3
"""
Create a stitched video from DAQ1+DAQ2 by picking the best frame from each pair,
split into 1-hour chunks. Also create debug videos of broken frames.

Output:
  output/WL27_stitched_chunk_XX.avi   — stitched 1h chunks (best frame from each matched pair)
  output/debug_broken_daq1.avi        — all broken DAQ1 frames (from matched pairs)
  output/debug_broken_daq2.avi        — all broken DAQ2 frames (from matched pairs)
  output/debug_both_broken.avi        — frames where both DAQs were broken
"""

import csv
import json
import glob
import os
import sys
import numpy as np
import cv2

BASE_DIR = "/Users/mbrosch/Documents/9h_long_recording_December2025"
DAQ1_DIR = os.path.join(BASE_DIR, "neural_DAQ1")
DAQ2_DIR = os.path.join(BASE_DIR, "neural_DAQ2")
OUTPUT_DIR = os.path.join(BASE_DIR, "neural_DAQ1", "output")

FPS = 20.0
FRAME_W = 200
FRAME_H = 200
FRAMES_PER_HOUR = int(FPS * 3600)  # 72000

# Segment pairs: (DAQ1 csv/avi label, DAQ1 results label, DAQ2 csv/avi label, DAQ2 results label)
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

# Trimming: last N seconds to remove (miniscope was off)
TRIM_SECONDS = {
    "long-2": 30,
    "long-9": 155,
}


def get_frame_timestamps(csv_path):
    """Extract per-frame completion timestamps from buffer-level CSV.
    Returns dict: frame_index -> last_buffer_unix_time
    """
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
    """Load broken frame indices as a set, plus per-type sets."""
    with open(results_json_path) as f:
        d = json.load(f)
    broken = set()
    black_set = set()
    gradient_set = set()
    for entry in d["black_frames"]:
        broken.add(entry["frame"])
        black_set.add(entry["frame"])
    for entry in d["gradient_frames"]:
        broken.add(entry["frame"])
        gradient_set.add(entry["frame"])
    for entry in d["both_frames"]:
        broken.add(entry["frame"])
        black_set.add(entry["frame"])
        gradient_set.add(entry["frame"])
    for entry in d.get("bright_frames", []):
        broken.add(entry["frame"])
    return broken, black_set, gradient_set, d["total_frames"]


def find_avi(directory, label):
    """Find AVI file for a given label (handles extra suffixes like long-8-002.avi)."""
    # Try exact match first
    pattern = os.path.join(directory, f"*_{label}.avi")
    matches = glob.glob(pattern)
    if matches:
        return matches[0]
    # Try with extra suffix (e.g., long-8-002.avi)
    pattern = os.path.join(directory, f"*_{label}-*.avi")
    matches = glob.glob(pattern)
    if matches:
        return matches[0]
    # Try ending with label.avi (for "long" without dash)
    pattern = os.path.join(directory, f"*{label}.avi")
    matches = glob.glob(pattern)
    if matches:
        # Filter out false matches (e.g., "long" matching "long-2")
        for m in matches:
            base = os.path.basename(m).replace(".avi", "")
            # Check the part after the last underscore or the full name
            if base.endswith(f"_{label}") or base.endswith(f"-{label}") or base == label:
                return m
        return matches[0]
    return None


def find_csv(directory, label):
    """Find CSV file for a given label."""
    pattern = os.path.join(directory, f"*_{label}.csv")
    matches = glob.glob(pattern)
    if matches:
        return matches[0]
    pattern = os.path.join(directory, f"*{label}.csv")
    matches = glob.glob(pattern)
    if matches:
        for m in matches:
            base = os.path.basename(m).replace(".csv", "")
            if base.endswith(f"_{label}") or base.endswith(f"-{label}"):
                return m
        return matches[0]
    return None


def find_results_json(directory, label):
    """Find results JSON for a given label."""
    path = os.path.join(directory, "results", f"{label}.json")
    return path if os.path.exists(path) else None


def build_matching(daq1_ftimes, daq2_ftimes, daq1_total, daq2_total, daq1_broken, daq2_broken, trim_frames_d1):
    """Build sorted list of matched frame pairs with broken status.
    Returns list of (d1_idx, d2_idx, d1_is_broken, d2_is_broken) sorted by d1_idx.
    """
    # Clamp to frames that exist in the AVI
    d1_ftimes = {k: v for k, v in daq1_ftimes.items() if k < daq1_total}
    d2_ftimes = {k: v for k, v in daq2_ftimes.items() if k < daq2_total}

    # Apply trimming to DAQ1 (trim last N frames)
    if trim_frames_d1 > 0:
        max_d1 = daq1_total - trim_frames_d1
        d1_ftimes = {k: v for k, v in d1_ftimes.items() if k < max_d1}

    # Build sorted DAQ2 arrays for nearest-neighbor lookup
    d2_frames_sorted = sorted(d2_ftimes.keys(), key=lambda k: d2_ftimes[k])
    d2_times_sorted = np.array([d2_ftimes[k] for k in d2_frames_sorted])

    # Also need to trim DAQ2 similarly by timestamp range
    # Find the timestamp range of (trimmed) DAQ1 and only match within that
    if not d1_ftimes:
        return []

    matched = []
    used_d2 = set()

    for d1_idx in sorted(d1_ftimes.keys()):
        t1 = d1_ftimes[d1_idx]
        idx = np.searchsorted(d2_times_sorted, t1)
        best_dist = float("inf")
        best_d2_idx = None

        for candidate in [idx - 1, idx]:
            if 0 <= candidate < len(d2_times_sorted):
                dist = abs(d2_times_sorted[candidate] - t1)
                if dist < best_dist:
                    best_dist = dist
                    best_d2_idx = d2_frames_sorted[candidate]

        if best_dist > 0.025:  # >25ms = no match
            continue

        d1_bad = d1_idx in daq1_broken
        d2_bad = best_d2_idx in daq2_broken
        matched.append((d1_idx, best_d2_idx, d1_bad, d2_bad))

    return matched


def make_writer(path):
    """Create a VideoWriter for raw grayscale AVI (matching original format: fourcc=0)."""
    writer = cv2.VideoWriter(path, 0, FPS, (FRAME_W, FRAME_H), isColor=False)
    if not writer.isOpened():
        # Fallback: try GREY fourcc
        fourcc = cv2.VideoWriter_fourcc(*'GREY')
        writer = cv2.VideoWriter(path, fourcc, FPS, (FRAME_W, FRAME_H), isColor=False)
    if not writer.isOpened():
        print(f"ERROR: Cannot create video writer for {path}", file=sys.stderr)
        sys.exit(1)
    return writer


def read_frame_gray(cap):
    """Read a frame and convert to grayscale if needed."""
    ret, frame = cap.read()
    if not ret:
        return None
    if len(frame.shape) == 3:
        frame = frame[:, :, 0]
    return frame


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Open debug video writers — combined across all segments
    debug_d1_writer = make_writer(os.path.join(OUTPUT_DIR, "debug_broken_daq1.avi"))
    debug_d2_writer = make_writer(os.path.join(OUTPUT_DIR, "debug_broken_daq2.avi"))
    debug_both_writer = make_writer(os.path.join(OUTPUT_DIR, "debug_both_broken.avi"))
    # Per-type debug writers
    debug_d1_black_writer = make_writer(os.path.join(OUTPUT_DIR, "debug_broken_daq1_black.avi"))
    debug_d1_gradient_writer = make_writer(os.path.join(OUTPUT_DIR, "debug_broken_daq1_gradient.avi"))
    debug_d2_black_writer = make_writer(os.path.join(OUTPUT_DIR, "debug_broken_daq2_black.avi"))
    debug_d2_gradient_writer = make_writer(os.path.join(OUTPUT_DIR, "debug_broken_daq2_gradient.avi"))

    # Stitched output — chunked by hour
    chunk_idx = 1
    chunk_frame_count = 0
    chunk_path = os.path.join(OUTPUT_DIR, f"WL27_stitched_chunk_{chunk_idx:02d}.avi")
    stitched_writer = make_writer(chunk_path)
    max_proj = None  # running max projection for current chunk
    print(f"Started chunk {chunk_idx}: {chunk_path}")

    total_stitched = 0
    total_debug_d1 = 0
    total_debug_d2 = 0
    total_debug_both = 0

    for daq1_label, daq1_res, daq2_label, daq2_res in PAIRS:
        print(f"\n{'='*60}")
        print(f"Processing segment: DAQ1={daq1_label}, DAQ2={daq2_label}")

        # Find all files
        daq1_avi = find_avi(DAQ1_DIR, daq1_label)
        daq2_avi = find_avi(DAQ2_DIR, daq2_label)
        daq1_csv = find_csv(DAQ1_DIR, daq1_label)
        daq2_csv = find_csv(DAQ2_DIR, daq2_label)
        daq1_json = find_results_json(DAQ1_DIR, daq1_res)
        daq2_json = find_results_json(DAQ2_DIR, daq2_res)

        missing = []
        for name, path in [("DAQ1 AVI", daq1_avi), ("DAQ2 AVI", daq2_avi),
                           ("DAQ1 CSV", daq1_csv), ("DAQ2 CSV", daq2_csv),
                           ("DAQ1 JSON", daq1_json), ("DAQ2 JSON", daq2_json)]:
            if not path:
                missing.append(name)
        if missing:
            print(f"  SKIP: missing {', '.join(missing)}")
            continue

        print(f"  DAQ1 AVI: {os.path.basename(daq1_avi)}")
        print(f"  DAQ2 AVI: {os.path.basename(daq2_avi)}")

        # Load broken sets and timestamps
        daq1_broken, daq1_black, daq1_gradient, daq1_total = get_broken_set(daq1_json)
        daq2_broken, daq2_black, daq2_gradient, daq2_total = get_broken_set(daq2_json)
        daq1_ftimes = get_frame_timestamps(daq1_csv)
        daq2_ftimes = get_frame_timestamps(daq2_csv)

        # Trimming
        trim_seconds = TRIM_SECONDS.get(daq1_label, 0)
        trim_frames = int(trim_seconds * FPS)

        # Build frame matching
        matched = build_matching(daq1_ftimes, daq2_ftimes, daq1_total, daq2_total,
                                 daq1_broken, daq2_broken, trim_frames)
        print(f"  Matched pairs: {len(matched)} (trimmed {trim_frames} frames from DAQ1)")

        if not matched:
            continue

        # Open video captures
        cap1 = cv2.VideoCapture(daq1_avi)
        cap2 = cv2.VideoCapture(daq2_avi)

        if not cap1.isOpened() or not cap2.isOpened():
            print(f"  ERROR: Cannot open video file(s)")
            continue

        d1_pos = 0  # current read position in DAQ1
        d2_pos = 0  # current read position in DAQ2
        seg_stitched = 0
        seg_debug_d1 = 0
        seg_debug_d2 = 0
        seg_debug_both = 0

        for i, (d1_idx, d2_idx, d1_bad, d2_bad) in enumerate(matched):
            # Advance DAQ1 to d1_idx
            while d1_pos < d1_idx:
                cap1.read()
                d1_pos += 1
            frame1 = read_frame_gray(cap1)
            d1_pos += 1

            # Advance DAQ2 to d2_idx (seek if needed)
            if d2_idx < d2_pos:
                cap2.set(cv2.CAP_PROP_POS_FRAMES, d2_idx)
                d2_pos = d2_idx
            while d2_pos < d2_idx:
                cap2.read()
                d2_pos += 1
            frame2 = read_frame_gray(cap2)
            d2_pos += 1

            if frame1 is None or frame2 is None:
                print(f"  WARNING: Failed to read frame at d1={d1_idx}, d2={d2_idx}")
                continue

            # Write debug videos
            if d1_bad:
                debug_d1_writer.write(frame1)
                seg_debug_d1 += 1
                if d1_idx in daq1_black:
                    debug_d1_black_writer.write(frame1)
                if d1_idx in daq1_gradient:
                    debug_d1_gradient_writer.write(frame1)
            if d2_bad:
                debug_d2_writer.write(frame2)
                seg_debug_d2 += 1
                if d2_idx in daq2_black:
                    debug_d2_black_writer.write(frame2)
                if d2_idx in daq2_gradient:
                    debug_d2_gradient_writer.write(frame2)
            if d1_bad and d2_bad:
                # Write both frames to debug_both (use DAQ2 frame)
                debug_both_writer.write(frame2)
                seg_debug_both += 1

            # Write stitched video — pick the best frame
            chosen = None
            if d1_bad and d2_bad:
                # Both broken — skip this frame in stitched output
                pass
            elif d1_bad:
                chosen = frame2
            elif d2_bad:
                chosen = frame1
            else:
                # Both good — use DAQ2 (lower overall error rate)
                chosen = frame2

            if chosen is not None:
                stitched_writer.write(chosen)
                seg_stitched += 1
                chunk_frame_count += 1
                # Update max projection
                if max_proj is None:
                    max_proj = chosen.astype(np.uint16)
                else:
                    np.maximum(max_proj, chosen, out=max_proj)

            # Check if we need to start a new 1h chunk
            if chunk_frame_count >= FRAMES_PER_HOUR:
                stitched_writer.release()
                # Save max projection for this chunk
                if max_proj is not None:
                    mp_path = os.path.join(OUTPUT_DIR, f"WL27_stitched_chunk_{chunk_idx:02d}_maxproj.png")
                    cv2.imwrite(mp_path, np.clip(max_proj, 0, 255).astype(np.uint8))
                    print(f"  Saved max projection: {mp_path}")
                print(f"  Completed chunk {chunk_idx} ({chunk_frame_count} frames)")
                chunk_idx += 1
                chunk_frame_count = 0
                max_proj = None
                chunk_path = os.path.join(OUTPUT_DIR, f"WL27_stitched_chunk_{chunk_idx:02d}.avi")
                stitched_writer = make_writer(chunk_path)
                print(f"  Started chunk {chunk_idx}: {chunk_path}")

            # Progress
            if (i + 1) % 10000 == 0:
                print(f"  Progress: {i+1}/{len(matched)} frames processed")

        cap1.release()
        cap2.release()

        total_stitched += seg_stitched
        total_debug_d1 += seg_debug_d1
        total_debug_d2 += seg_debug_d2
        total_debug_both += seg_debug_both

        print(f"  Segment done: stitched={seg_stitched}, "
              f"debug_d1={seg_debug_d1}, debug_d2={seg_debug_d2}, debug_both={seg_debug_both}")

    # Save max projection for the last chunk
    if max_proj is not None:
        mp_path = os.path.join(OUTPUT_DIR, f"WL27_stitched_chunk_{chunk_idx:02d}_maxproj.png")
        cv2.imwrite(mp_path, np.clip(max_proj, 0, 255).astype(np.uint8))
        print(f"Saved max projection: {mp_path}")

    # Release all writers
    stitched_writer.release()
    debug_d1_writer.release()
    debug_d2_writer.release()
    debug_both_writer.release()
    debug_d1_black_writer.release()
    debug_d1_gradient_writer.release()
    debug_d2_black_writer.release()
    debug_d2_gradient_writer.release()

    print(f"\n{'='*60}")
    print("DONE!")
    print(f"  Stitched frames: {total_stitched} ({total_stitched/FPS:.1f}s, {total_stitched/FPS/3600:.2f}h)")
    print(f"  Chunks created: {chunk_idx}")
    print(f"  Debug broken DAQ1: {total_debug_d1} frames ({total_debug_d1/FPS:.1f}s)")
    print(f"  Debug broken DAQ2: {total_debug_d2} frames ({total_debug_d2/FPS:.1f}s)")
    print(f"  Debug both broken: {total_debug_both} frames ({total_debug_both/FPS:.1f}s)")
    print(f"\nOutput directory: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
