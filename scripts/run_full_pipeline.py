#!/usr/bin/env python3
"""Run the full pipeline: analyze all AVIs, combine DAQs, create stitched videos."""

import subprocess
import sys
import os
import time

PYTHON = sys.executable
BASE_DIR = "/Users/mbrosch/Documents/9h_long_recording_December2025"
DAQ1_DIR = os.path.join(BASE_DIR, "neural_DAQ1")
DAQ2_DIR = os.path.join(BASE_DIR, "neural_DAQ2")
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
ANALYZE_SCRIPT = os.path.join(SCRIPTS_DIR, "analyze_frames.py")

# All AVI files to analyze: (daq_dir, avi_filename_glob_label, results_label)
DAQ1_AVIS = [
    ("long-2",  "long-2"),
    ("long-4",  "long-4"),
    ("long-6",  "long-6"),
    ("long-8",  "long-8"),
    ("long-9",  "long-9"),
    ("long-10", "long-10"),
    ("long-12", "long-12"),
    ("long-13", "long-13"),
]

DAQ2_AVIS = [
    ("long",    "long"),
    ("long-2",  "long-2"),
    ("long-4",  "long-4"),
    ("long-6",  "long-6"),
    ("long-7",  "long-7"),
    ("long-8",  "long-8"),
    ("long-9",  "long-9"),
    ("long-10", "long-10"),
]


def find_avi(directory, label):
    """Find AVI file for a given label."""
    import glob
    for pattern in [f"*_{label}.avi", f"*_{label}-*.avi", f"*{label}.avi"]:
        matches = glob.glob(os.path.join(directory, pattern))
        if matches:
            return matches[0]
    return None


def run_step(description, cmd):
    """Run a command and print status."""
    print(f"\n{'='*60}")
    print(f"STEP: {description}")
    print(f"CMD:  {' '.join(cmd)}")
    print(f"{'='*60}")
    t0 = time.time()
    result = subprocess.run(cmd, capture_output=False)
    elapsed = time.time() - t0
    if result.returncode != 0:
        print(f"FAILED (exit code {result.returncode}) after {elapsed:.1f}s")
        return False
    print(f"DONE in {elapsed:.1f}s")
    return True


def main():
    t_start = time.time()

    # Step 1: Analyze all DAQ1 AVIs
    print("\n" + "#"*60)
    print("# PHASE 1: Analyzing DAQ1 AVIs")
    print("#"*60)
    for label, res_label in DAQ1_AVIS:
        avi = find_avi(DAQ1_DIR, label)
        if not avi:
            print(f"WARNING: No AVI found for DAQ1 {label}")
            continue
        out = os.path.join(DAQ1_DIR, "results", f"{res_label}.json")
        dbg = os.path.join(DAQ1_DIR, "debug_detectors")
        if not run_step(f"Analyze DAQ1 {label}", [PYTHON, ANALYZE_SCRIPT, avi, out, dbg]):
            print("Aborting.")
            sys.exit(1)

    # Step 2: Analyze all DAQ2 AVIs
    print("\n" + "#"*60)
    print("# PHASE 2: Analyzing DAQ2 AVIs")
    print("#"*60)
    for label, res_label in DAQ2_AVIS:
        avi = find_avi(DAQ2_DIR, label)
        if not avi:
            print(f"WARNING: No AVI found for DAQ2 {label}")
            continue
        out = os.path.join(DAQ2_DIR, "results", f"{res_label}.json")
        dbg = os.path.join(DAQ2_DIR, "debug_detectors")
        if not run_step(f"Analyze DAQ2 {label}", [PYTHON, ANALYZE_SCRIPT, avi, out, dbg]):
            print("Aborting.")
            sys.exit(1)

    # Step 3: Run combine_daqs
    print("\n" + "#"*60)
    print("# PHASE 3: Combining DAQ statistics")
    print("#"*60)
    run_step("Combine DAQs", [PYTHON, os.path.join(SCRIPTS_DIR, "combine_daqs.py")])

    # Step 4: Remove old output and create stitched videos
    print("\n" + "#"*60)
    print("# PHASE 4: Creating stitched videos")
    print("#"*60)
    if os.path.exists(OUTPUT_DIR):
        import shutil
        print(f"Removing old output: {OUTPUT_DIR}")
        shutil.rmtree(OUTPUT_DIR)
    run_step("Create stitched videos",
             [PYTHON, os.path.join(SCRIPTS_DIR, "create_stitched_video.py")])

    # Step 5: Run drop analysis
    print("\n" + "#"*60)
    print("# PHASE 5: Drop analysis")
    print("#"*60)
    run_step("Analyze drops", [PYTHON, os.path.join(SCRIPTS_DIR, "analyze_drops.py")])

    total_time = time.time() - t_start
    print(f"\n{'#'*60}")
    print(f"# PIPELINE COMPLETE in {total_time:.0f}s ({total_time/60:.1f} min)")
    print(f"{'#'*60}")


if __name__ == "__main__":
    main()
