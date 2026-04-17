#!/usr/bin/env python3
"""Per-DAQ, per-file silent frame drop detection.

Detects frames that never reached the AVI file (all 8 buffers lost) using 4
CSV-derived signals:
  1. frame_num gaps      — device frame counter skipped values
  2. device timestamp    — ms gap > 75 ms (expected 50 ms at 20 FPS)
  3. host timestamp      — same threshold applied to buffer_recv_unix_time
  4. dropped_buffer_count — firmware-reported drops (positive deltas)

Per-DAQ, per-file only: miniscope restarts between files, so counters and
timestamps reset. Files analyzed: the 8 chunks in analyze_drops.py's PAIRS.
TRIM_SECONDS applied end-of-file to DAQ1 only (matches analyze_drops.py).
"""

import csv
import glob
import json
import os
from collections import defaultdict

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


BASE_DIR = "/Users/mbrosch/Documents/9h_long_recording_December2025"
DAQ1_DIR = os.path.join(BASE_DIR, "neural_DAQ1")
DAQ2_DIR = os.path.join(BASE_DIR, "neural_DAQ2")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

FPS = 20.0
EXPECTED_PERIOD_MS = 1000.0 / FPS  # 50 ms
GAP_THRESHOLD_MS = 1.5 * EXPECTED_PERIOD_MS  # 75 ms
GAP_THRESHOLD_S = GAP_THRESHOLD_MS / 1000.0  # 0.075 s for host unix time

# Matches analyze_drops.py PAIRS exactly (DAQ1 label, DAQ2 label)
PAIRS = [
    ("long-2",  "long-2"),
    ("long-4",  "long-4"),
    ("long-6",  "long-6"),
    ("long-8",  "long-8"),
    ("long-9",  "long-7"),
    ("long-10", "long-8"),
    ("long-12", "long-9"),
    ("long-13", "long-10"),
]

# DAQ1 only, end-of-file trim (matches analyze_drops.py)
TRIM_SECONDS_DAQ1 = {"long-2": 30, "long-9": 155}


def detect_frame_num_gaps(frame_nums):
    """Detect gaps in the device frame_num counter.

    A gap of (frame_nums[i] - frame_nums[i-1]) > 1 means (diff - 1) frames
    were produced by the device but never reached the host.
    """
    events = []
    total_missed = 0
    for i in range(1, len(frame_nums)):
        diff = frame_nums[i] - frame_nums[i - 1]
        if diff > 1:
            missed = int(diff - 1)
            events.append({
                "at_frame_idx": i,
                "frame_num_before": int(frame_nums[i - 1]),
                "frame_num_after": int(frame_nums[i]),
                "missed": missed,
            })
            total_missed += missed
    return {
        "silent_drops": total_missed,
        "gap_events": len(events),
        "events": events,
    }
