# Silent Frame Drop Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `scripts/analyze_silent_drops.py` — a per-DAQ, per-file detector for frames that never reached the AVI (invisible to pixel-based detection) using 4 CSV-derived signals.

**Architecture:** Single-file Python script. Small pure functions for each of the 4 detectors (easy to unit-test with synthetic data). A per-file `analyze_file()` orchestrates CSV load → per-frame reduction → trim → run detectors → write JSON. A main runner iterates the 8 PAIRS per DAQ, writes per-file JSONs, a combined summary JSON, and a grouped-bar plot.

**Tech Stack:** Python 3, numpy, pandas (for `groupby`), matplotlib. Plain-assert tests (no pytest — matches existing codebase).

**Spec reference:** `docs/superpowers/specs/2026-04-17-silent-drops-design.md`

---

## File Structure

- `scripts/analyze_silent_drops.py` — main script (created)
- `tests/test_silent_drops.py` — plain-assert unit tests for the 4 detectors + per-frame reduction + trim (created)
- Output artifacts (generated at runtime, not committed):
  - `neural_DAQ{1,2}/results/<csv_stem>.silent_drops.json`
  - `output/silent_drops_summary.json`
  - `output/silent_drops.png`

---

## Task 1: Skeleton and constants

**Files:**
- Create: `scripts/analyze_silent_drops.py`

- [ ] **Step 1: Create the file with shebang, docstring, imports, and constants**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add scripts/analyze_silent_drops.py
git commit -m "Add skeleton for silent drop analysis script"
```

---

## Task 2: Detector — frame_num gaps (pure function + test)

**Files:**
- Modify: `scripts/analyze_silent_drops.py` (append function)
- Create: `tests/test_silent_drops.py`

- [ ] **Step 1: Write the failing test first**

Create `tests/test_silent_drops.py`:

```python
#!/usr/bin/env python3
"""Plain-assert unit tests for scripts/analyze_silent_drops.py.

Run with: python tests/test_silent_drops.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import analyze_silent_drops as asd  # noqa: E402


def test_detect_frame_num_gaps_no_gaps():
    frame_nums = [10, 11, 12, 13, 14]
    result = asd.detect_frame_num_gaps(frame_nums)
    assert result["silent_drops"] == 0, result
    assert result["gap_events"] == 0, result
    assert result["events"] == [], result


def test_detect_frame_num_gaps_single_gap_of_2():
    frame_nums = [10, 11, 14, 15]  # gap of 3 between 11 and 14 → 2 missed
    result = asd.detect_frame_num_gaps(frame_nums)
    assert result["silent_drops"] == 2, result
    assert result["gap_events"] == 1, result
    assert result["events"] == [
        {"at_frame_idx": 2, "frame_num_before": 11, "frame_num_after": 14, "missed": 2}
    ], result


def test_detect_frame_num_gaps_multiple_gaps():
    frame_nums = [0, 1, 3, 4, 10]  # gap of 1 (2→3 missed), gap of 5 (4→10 missed)
    result = asd.detect_frame_num_gaps(frame_nums)
    assert result["silent_drops"] == 1 + 5, result
    assert result["gap_events"] == 2, result


def test_detect_frame_num_gaps_empty():
    assert asd.detect_frame_num_gaps([])["silent_drops"] == 0
    assert asd.detect_frame_num_gaps([42])["silent_drops"] == 0


if __name__ == "__main__":
    test_detect_frame_num_gaps_no_gaps()
    test_detect_frame_num_gaps_single_gap_of_2()
    test_detect_frame_num_gaps_multiple_gaps()
    test_detect_frame_num_gaps_empty()
    print("frame_num gap tests: OK")
```

- [ ] **Step 2: Run the test and verify it fails**

```bash
python tests/test_silent_drops.py
```

Expected: `AttributeError: module 'analyze_silent_drops' has no attribute 'detect_frame_num_gaps'`

- [ ] **Step 3: Implement the detector**

Append to `scripts/analyze_silent_drops.py`:

```python
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
```

- [ ] **Step 4: Run the test and verify it passes**

```bash
python tests/test_silent_drops.py
```

Expected: `frame_num gap tests: OK`

- [ ] **Step 5: Commit**

```bash
git add scripts/analyze_silent_drops.py tests/test_silent_drops.py
git commit -m "Add frame_num gap detector with tests"
```

---

## Task 3: Detector — timestamp gaps (pure function + test)

**Files:**
- Modify: `scripts/analyze_silent_drops.py`
- Modify: `tests/test_silent_drops.py`

- [ ] **Step 1: Add failing tests for the timestamp gap detector**

Append to `tests/test_silent_drops.py` (before the `if __name__` block):

```python
def test_detect_timestamp_gaps_device_ms_no_gaps():
    # 50 ms spacing, no gaps
    ts = [0, 50, 100, 150, 200]
    result = asd.detect_timestamp_gaps(ts, threshold=75.0, period=50.0, unit_label="ms")
    assert result["silent_drops"] == 0, result
    assert result["gap_events"] == 0, result


def test_detect_timestamp_gaps_device_ms_one_gap():
    # 200 ms gap between idx 2 and 3 → round(200/50) - 1 = 3 missed
    ts = [0, 50, 100, 300, 350]
    result = asd.detect_timestamp_gaps(ts, threshold=75.0, period=50.0, unit_label="ms")
    assert result["silent_drops"] == 3, result
    assert result["gap_events"] == 1, result
    assert result["events"][0]["at_frame_idx"] == 3
    assert abs(result["events"][0]["dt_ms"] - 200.0) < 1e-6
    assert result["events"][0]["missed"] == 3


def test_detect_timestamp_gaps_host_seconds():
    # Host timestamps are in unix seconds; threshold/period passed in seconds
    ts = [1000.000, 1000.050, 1000.100, 1000.300]  # 0.2 s gap at idx 3
    result = asd.detect_timestamp_gaps(ts, threshold=0.075, period=0.050, unit_label="s")
    assert result["silent_drops"] == 3, result
    assert result["gap_events"] == 1, result
    assert abs(result["events"][0]["dt_s"] - 0.2) < 1e-6


def test_detect_timestamp_gaps_just_under_threshold():
    # 70 ms — below the 75 ms threshold, should NOT flag
    ts = [0, 50, 120, 170]
    result = asd.detect_timestamp_gaps(ts, threshold=75.0, period=50.0, unit_label="ms")
    assert result["silent_drops"] == 0, result
```

And add to the `if __name__` block:

```python
    test_detect_timestamp_gaps_device_ms_no_gaps()
    test_detect_timestamp_gaps_device_ms_one_gap()
    test_detect_timestamp_gaps_host_seconds()
    test_detect_timestamp_gaps_just_under_threshold()
    print("timestamp gap tests: OK")
```

- [ ] **Step 2: Run the tests and verify they fail**

```bash
python tests/test_silent_drops.py
```

Expected: `AttributeError: module 'analyze_silent_drops' has no attribute 'detect_timestamp_gaps'`

- [ ] **Step 3: Implement the detector**

Append to `scripts/analyze_silent_drops.py`:

```python
def detect_timestamp_gaps(timestamps, threshold, period, unit_label):
    """Detect timestamp gaps larger than `threshold`.

    timestamps: monotonic list/array of per-frame timestamps.
    threshold:  gap size above which we flag (same units as timestamps).
    period:     expected inter-frame period (same units); used to estimate
                missed frame count = round(dt / period) - 1.
    unit_label: "ms" for device timestamp, "s" for host unix time. Controls
                the event dict key ("dt_ms" vs "dt_s").

    Returns {"silent_drops": int, "gap_events": int, "events": [...]}.
    """
    dt_key = f"dt_{unit_label}"
    events = []
    total_missed = 0
    for i in range(1, len(timestamps)):
        dt = timestamps[i] - timestamps[i - 1]
        if dt > threshold:
            missed = int(round(dt / period)) - 1
            if missed < 1:
                missed = 1  # gap was over threshold, so at least 1 missed
            events.append({
                "at_frame_idx": i,
                dt_key: float(dt),
                "missed": missed,
            })
            total_missed += missed
    return {
        "silent_drops": total_missed,
        "gap_events": len(events),
        "events": events,
    }
```

- [ ] **Step 4: Run the tests and verify they pass**

```bash
python tests/test_silent_drops.py
```

Expected: `frame_num gap tests: OK` and `timestamp gap tests: OK`

- [ ] **Step 5: Commit**

```bash
git add scripts/analyze_silent_drops.py tests/test_silent_drops.py
git commit -m "Add timestamp gap detector with tests"
```

---

## Task 4: Detector — dropped_buffer_count deltas

**Files:**
- Modify: `scripts/analyze_silent_drops.py`
- Modify: `tests/test_silent_drops.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_silent_drops.py` (before the `if __name__` block):

```python
def test_detect_dropped_buffer_deltas_none():
    counts = [0, 0, 0, 0]
    result = asd.detect_dropped_buffer_deltas(counts)
    assert result["total_delta"] == 0, result
    assert result["nonzero_deltas"] == 0, result
    assert result["events"] == [], result


def test_detect_dropped_buffer_deltas_cumulative():
    # Firmware-reported drops accumulate: 0 → 0 → 4 → 4 → 7
    counts = [0, 0, 4, 4, 7]
    result = asd.detect_dropped_buffer_deltas(counts)
    assert result["total_delta"] == 7, result
    assert result["nonzero_deltas"] == 2, result
    assert result["events"] == [
        {"at_frame_idx": 2, "delta": 4},
        {"at_frame_idx": 4, "delta": 3},
    ], result


def test_detect_dropped_buffer_deltas_ignores_decreases():
    # Counter should be monotonic; if it decreases (e.g., restart within file),
    # treat as 0 delta rather than a negative number.
    counts = [10, 10, 3, 5]  # idx 2 decreases — skip; idx 3 delta = 5-3 = 2
    result = asd.detect_dropped_buffer_deltas(counts)
    assert result["total_delta"] == 2, result
    assert result["nonzero_deltas"] == 1, result
    assert result["events"] == [{"at_frame_idx": 3, "delta": 2}], result
```

And add to the `if __name__` block:

```python
    test_detect_dropped_buffer_deltas_none()
    test_detect_dropped_buffer_deltas_cumulative()
    test_detect_dropped_buffer_deltas_ignores_decreases()
    print("dropped_buffer_count delta tests: OK")
```

- [ ] **Step 2: Run the tests and verify they fail**

```bash
python tests/test_silent_drops.py
```

Expected: `AttributeError: module 'analyze_silent_drops' has no attribute 'detect_dropped_buffer_deltas'`

- [ ] **Step 3: Implement the detector**

Append to `scripts/analyze_silent_drops.py`:

```python
def detect_dropped_buffer_deltas(counts):
    """Sum positive deltas of the firmware-reported dropped_buffer_count.

    The counter is cumulative. Decreases are treated as 0 delta (defensive —
    should not happen within a single file since the device doesn't restart
    mid-file, but guards against data quirks).
    """
    events = []
    total = 0
    for i in range(1, len(counts)):
        delta = int(counts[i] - counts[i - 1])
        if delta > 0:
            events.append({"at_frame_idx": i, "delta": delta})
            total += delta
    return {
        "total_delta": total,
        "nonzero_deltas": len(events),
        "events": events,
    }
```

- [ ] **Step 4: Run the tests and verify they pass**

```bash
python tests/test_silent_drops.py
```

Expected: all three test groups print OK.

- [ ] **Step 5: Commit**

```bash
git add scripts/analyze_silent_drops.py tests/test_silent_drops.py
git commit -m "Add dropped_buffer_count delta detector with tests"
```

---

## Task 5: CSV loading and per-frame reduction

**Files:**
- Modify: `scripts/analyze_silent_drops.py`
- Modify: `tests/test_silent_drops.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_silent_drops.py` (before the `if __name__` block):

```python
import io
import pandas as pd


def _synthetic_csv(rows):
    """Build a CSV string with the columns the real data has."""
    header = (
        "linked_list,frame_num,buffer_count,frame_buffer_count,write_buffer_count,"
        "dropped_buffer_count,timestamp,pixel_count,write_timestamp,battery_voltage_raw,"
        "input_voltage_raw,buffer_recv_index,buffer_recv_unix_time,black_padding_px,"
        "reconstructed_frame_index\n"
    )
    return header + "\n".join(rows) + "\n"


def test_reduce_to_per_frame_basic(tmp_path=None):
    # Two frames, each with 2 buffers (simplified from 8 for the test)
    # Frame 0: device ts 1000, 1002; host 10.000, 10.005
    # Frame 1: device ts 1050, 1052; host 10.050, 10.055
    csv_text = _synthetic_csv([
        "0,100,0,0,0,0,1000,5032,0,195,181,0,10.000,0,0",
        "1,100,1,1,1,0,1002,5032,0,195,181,1,10.005,0,0",
        "0,101,0,0,0,0,1050,5032,0,195,181,2,10.050,0,1",
        "1,101,1,1,1,0,1052,5032,0,195,181,3,10.055,0,1",
    ])
    df = pd.read_csv(io.StringIO(csv_text))
    per_frame = asd.reduce_to_per_frame(df)
    # Two rows, one per reconstructed_frame_index
    assert len(per_frame) == 2, per_frame
    # Sorted by reconstructed_frame_index
    assert list(per_frame["reconstructed_frame_index"]) == [0, 1]
    assert list(per_frame["frame_num"]) == [100, 101]
    assert list(per_frame["timestamp"]) == [1000, 1050]  # min per group
    assert list(per_frame["buffer_recv_unix_time"]) == [10.000, 10.050]
    assert list(per_frame["dropped_buffer_count"]) == [0, 0]  # max per group


def test_reduce_to_per_frame_with_firmware_drops():
    # Frame 1 has dropped_buffer_count rising from 0 to 3 within its buffers.
    # We take max per frame → reports the end-of-frame cumulative value.
    csv_text = _synthetic_csv([
        "0,100,0,0,0,0,1000,5032,0,195,181,0,10.000,0,0",
        "1,100,1,1,1,0,1002,5032,0,195,181,1,10.005,0,0",
        "0,101,0,0,0,0,1050,5032,0,195,181,2,10.050,0,1",
        "1,101,1,1,1,3,1052,5032,0,195,181,3,10.055,0,1",
    ])
    df = pd.read_csv(io.StringIO(csv_text))
    per_frame = asd.reduce_to_per_frame(df)
    assert list(per_frame["dropped_buffer_count"]) == [0, 3]
```

And add to the `if __name__` block:

```python
    test_reduce_to_per_frame_basic()
    test_reduce_to_per_frame_with_firmware_drops()
    print("per-frame reduction tests: OK")
```

- [ ] **Step 2: Run the tests and verify they fail**

```bash
python tests/test_silent_drops.py
```

Expected: `AttributeError: module 'analyze_silent_drops' has no attribute 'reduce_to_per_frame'`

- [ ] **Step 3: Implement the reducer**

Append to `scripts/analyze_silent_drops.py`:

```python
def reduce_to_per_frame(df):
    """Collapse buffer-level rows to one row per reconstructed_frame_index.

    Returns a DataFrame sorted by reconstructed_frame_index with columns:
      - reconstructed_frame_index
      - frame_num                (the group's frame_num; should be constant)
      - timestamp                (min within group — device frame-start ms)
      - buffer_recv_unix_time    (min within group — host arrival of earliest buffer)
      - dropped_buffer_count     (max within group — cumulative firmware counter)
    """
    per_frame = (
        df.groupby("reconstructed_frame_index", sort=True)
        .agg(
            frame_num=("frame_num", "first"),
            timestamp=("timestamp", "min"),
            buffer_recv_unix_time=("buffer_recv_unix_time", "min"),
            dropped_buffer_count=("dropped_buffer_count", "max"),
        )
        .reset_index()
    )
    return per_frame
```

- [ ] **Step 4: Run the tests and verify they pass**

```bash
python tests/test_silent_drops.py
```

Expected: all four test groups print OK.

- [ ] **Step 5: Commit**

```bash
git add scripts/analyze_silent_drops.py tests/test_silent_drops.py
git commit -m "Add per-frame CSV reduction with tests"
```

---

## Task 6: Trim application

**Files:**
- Modify: `scripts/analyze_silent_drops.py`
- Modify: `tests/test_silent_drops.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_silent_drops.py` (before the `if __name__` block):

```python
def test_apply_trim_daq1_matched_label():
    # FPS=20, trim=30s → drop last 600 frames
    per_frame = pd.DataFrame({"reconstructed_frame_index": list(range(1000))})
    trimmed, trim_frames = asd.apply_trim(per_frame, daq=1, label="long-2")
    assert trim_frames == 600
    assert len(trimmed) == 400
    assert list(trimmed["reconstructed_frame_index"]) == list(range(400))


def test_apply_trim_daq1_no_matching_label():
    per_frame = pd.DataFrame({"reconstructed_frame_index": list(range(100))})
    trimmed, trim_frames = asd.apply_trim(per_frame, daq=1, label="long-4")
    assert trim_frames == 0
    assert len(trimmed) == 100


def test_apply_trim_daq2_never_trims():
    # Even if a DAQ2 label matches a DAQ1 key, we must not trim DAQ2
    per_frame = pd.DataFrame({"reconstructed_frame_index": list(range(1000))})
    trimmed, trim_frames = asd.apply_trim(per_frame, daq=2, label="long-2")
    assert trim_frames == 0
    assert len(trimmed) == 1000
```

And add to the `if __name__` block:

```python
    test_apply_trim_daq1_matched_label()
    test_apply_trim_daq1_no_matching_label()
    test_apply_trim_daq2_never_trims()
    print("trim tests: OK")
```

- [ ] **Step 2: Run the tests and verify they fail**

```bash
python tests/test_silent_drops.py
```

Expected: `AttributeError: module 'analyze_silent_drops' has no attribute 'apply_trim'`

- [ ] **Step 3: Implement the trimmer**

Append to `scripts/analyze_silent_drops.py`:

```python
def apply_trim(per_frame, daq, label):
    """Drop the last N frames from DAQ1 files in the trim table.

    Returns (trimmed_df, trim_frames_dropped). DAQ2 is never trimmed.
    """
    if daq != 1:
        return per_frame, 0
    trim_s = TRIM_SECONDS_DAQ1.get(label, 0)
    if trim_s <= 0:
        return per_frame, 0
    trim_frames = int(trim_s * FPS)
    if trim_frames >= len(per_frame):
        return per_frame.iloc[0:0].copy(), len(per_frame)
    return per_frame.iloc[:-trim_frames].copy(), trim_frames
```

- [ ] **Step 4: Run the tests and verify they pass**

```bash
python tests/test_silent_drops.py
```

Expected: all five test groups print OK.

- [ ] **Step 5: Commit**

```bash
git add scripts/analyze_silent_drops.py tests/test_silent_drops.py
git commit -m "Add DAQ1 end-of-file trim with tests"
```

---

## Task 7: Per-file analysis orchestrator

**Files:**
- Modify: `scripts/analyze_silent_drops.py`

- [ ] **Step 1: Add the file-finder helper and per-file analyzer**

Append to `scripts/analyze_silent_drops.py`:

```python
def find_csv(directory, label):
    """Find the CSV for a given chunk label (e.g., 'long-2').

    Matches patterns used in analyze_drops.py. Returns the first match or None.
    """
    for pattern in [f"*_{label}.csv", f"*_{label}-*.csv", f"*{label}.csv"]:
        matches = glob.glob(os.path.join(directory, pattern))
        if matches:
            return matches[0]
    return None


def analyze_file(csv_path, daq, label):
    """Run the 4 detectors on one DAQ's CSV for one chunk.

    Returns the per-file result dict (see spec Output section).
    """
    df = pd.read_csv(csv_path)
    total_frames_in_csv = int(df["reconstructed_frame_index"].nunique())

    per_frame = reduce_to_per_frame(df)
    per_frame, trim_frames = apply_trim(per_frame, daq=daq, label=label)

    frame_nums = per_frame["frame_num"].tolist()
    device_ts = per_frame["timestamp"].tolist()
    host_ts = per_frame["buffer_recv_unix_time"].tolist()
    drop_counts = per_frame["dropped_buffer_count"].tolist()

    fn_result = detect_frame_num_gaps(frame_nums)
    dev_result = detect_timestamp_gaps(
        device_ts, threshold=GAP_THRESHOLD_MS, period=EXPECTED_PERIOD_MS, unit_label="ms"
    )
    host_result = detect_timestamp_gaps(
        host_ts, threshold=GAP_THRESHOLD_S, period=EXPECTED_PERIOD_MS / 1000.0, unit_label="s"
    )
    drop_result = detect_dropped_buffer_deltas(drop_counts)

    return {
        "file": os.path.basename(csv_path),
        "daq": daq,
        "fps": FPS,
        "expected_period_ms": EXPECTED_PERIOD_MS,
        "gap_threshold_ms": GAP_THRESHOLD_MS,
        "total_frames_in_csv": total_frames_in_csv,
        "trim_seconds": TRIM_SECONDS_DAQ1.get(label, 0) if daq == 1 else 0,
        "trim_frames": trim_frames,
        "analyzed_frames": len(per_frame),
        "frame_num": fn_result,
        "device_timestamp": dev_result,
        "host_timestamp": host_result,
        "dropped_buffer_count": drop_result,
    }
```

- [ ] **Step 2: Smoke-test against one real CSV**

Run the following one-liner to confirm it loads and returns sane counts:

```bash
python -c "
import sys
sys.path.insert(0, 'scripts')
import analyze_silent_drops as asd
csv = asd.find_csv(asd.DAQ1_DIR, 'long-2')
print('csv:', csv)
r = asd.analyze_file(csv, daq=1, label='long-2')
print('analyzed_frames:', r['analyzed_frames'])
print('trim_frames:', r['trim_frames'])
print('frame_num silent_drops:', r['frame_num']['silent_drops'])
print('device_ts silent_drops:', r['device_timestamp']['silent_drops'])
print('host_ts silent_drops:', r['host_timestamp']['silent_drops'])
print('buffer_drops total_delta:', r['dropped_buffer_count']['total_delta'])
"
```

Expected: finds a CSV, prints non-error numbers for each detector. trim_frames should be 600 (20 FPS × 30 s).

- [ ] **Step 3: Commit**

```bash
git add scripts/analyze_silent_drops.py
git commit -m "Add per-file silent drop analyzer"
```

---

## Task 8: Main runner — iterate PAIRS and write JSONs

**Files:**
- Modify: `scripts/analyze_silent_drops.py`

- [ ] **Step 1: Add the main runner**

Append to `scripts/analyze_silent_drops.py`:

```python
def write_per_file_json(result, daq_dir):
    """Write the per-file JSON next to the existing results/ for that DAQ."""
    results_dir = os.path.join(daq_dir, "results")
    os.makedirs(results_dir, exist_ok=True)
    stem = os.path.splitext(result["file"])[0]
    out_path = os.path.join(results_dir, f"{stem}.silent_drops.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    return out_path


def build_summary(per_daq_results):
    """Build the combined summary dict from per-file results grouped by DAQ."""
    summary = {
        "fps": FPS,
        "gap_threshold_ms": GAP_THRESHOLD_MS,
    }
    for daq_key in ("DAQ1", "DAQ2"):
        files = per_daq_results.get(daq_key, [])
        per_file_rows = []
        totals = {
            "analyzed_frames": 0,
            "frame_num_drops": 0,
            "device_ts_drops": 0,
            "host_ts_drops": 0,
            "buffer_drops": 0,
        }
        for r in files:
            row = {
                "file": r["file"],
                "analyzed_frames": r["analyzed_frames"],
                "frame_num_drops": r["frame_num"]["silent_drops"],
                "device_ts_drops": r["device_timestamp"]["silent_drops"],
                "host_ts_drops": r["host_timestamp"]["silent_drops"],
                "buffer_drops": r["dropped_buffer_count"]["total_delta"],
            }
            per_file_rows.append(row)
            for k in totals:
                totals[k] += row[k]
        summary[daq_key] = {"per_file": per_file_rows, "totals": totals}
    return summary


def run():
    per_daq_results = {"DAQ1": [], "DAQ2": []}

    for daq1_label, daq2_label in PAIRS:
        for daq, daq_dir, label in [
            (1, DAQ1_DIR, daq1_label),
            (2, DAQ2_DIR, daq2_label),
        ]:
            csv_path = find_csv(daq_dir, label)
            if csv_path is None:
                print(f"SKIP DAQ{daq} {label}: CSV not found")
                continue
            result = analyze_file(csv_path, daq=daq, label=label)
            out_path = write_per_file_json(result, daq_dir)
            per_daq_results[f"DAQ{daq}"].append(result)
            print(
                f"DAQ{daq} {label}: analyzed={result['analyzed_frames']} "
                f"frame_num={result['frame_num']['silent_drops']} "
                f"device_ts={result['device_timestamp']['silent_drops']} "
                f"host_ts={result['host_timestamp']['silent_drops']} "
                f"buffer={result['dropped_buffer_count']['total_delta']} "
                f"-> {out_path}"
            )

    summary = build_summary(per_daq_results)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    summary_path = os.path.join(OUTPUT_DIR, "silent_drops_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSummary written to: {summary_path}")

    return per_daq_results, summary


if __name__ == "__main__":
    run()
```

- [ ] **Step 2: Run the script end-to-end**

```bash
python scripts/analyze_silent_drops.py
```

Expected: prints one line per (DAQ, chunk) pair (16 lines), then a "Summary written to" line. No crashes.

- [ ] **Step 3: Inspect the summary**

```bash
python -c "import json; d = json.load(open('output/silent_drops_summary.json')); print(json.dumps({k: d[k]['totals'] for k in ['DAQ1','DAQ2']}, indent=2))"
```

Expected: four integer totals per DAQ (`frame_num_drops`, `device_ts_drops`, `host_ts_drops`, `buffer_drops`, `analyzed_frames`). Record these numbers for later comparison.

- [ ] **Step 4: Commit**

```bash
git add scripts/analyze_silent_drops.py
git commit -m "Add main runner producing per-file JSONs and combined summary"
```

---

## Task 9: Plot

**Files:**
- Modify: `scripts/analyze_silent_drops.py`

- [ ] **Step 1: Add the plotting function and wire it into `run()`**

Append to `scripts/analyze_silent_drops.py` (and update `run()` to call it):

```python
def plot_summary(summary, out_path):
    """Two stacked panels (DAQ1, DAQ2). Grouped bars per file, one bar per detector."""
    detectors = [
        ("frame_num_drops", "frame_num", "#1f77b4"),
        ("device_ts_drops", "device ts", "#ff7f0e"),
        ("host_ts_drops", "host ts", "#2ca02c"),
        ("buffer_drops", "dropped_buffers", "#d62728"),
    ]

    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=False)
    for ax, daq_key in zip(axes, ("DAQ1", "DAQ2")):
        rows = summary[daq_key]["per_file"]
        if not rows:
            ax.set_title(f"{daq_key}: no files")
            continue
        labels = [r["file"].replace(".csv", "") for r in rows]
        x = np.arange(len(labels))
        bar_w = 0.2
        for i, (key, pretty, color) in enumerate(detectors):
            vals = [r[key] for r in rows]
            ax.bar(x + (i - 1.5) * bar_w, vals, width=bar_w, color=color, label=pretty)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)
        ax.set_ylabel("silent drops (frames)")
        totals = summary[daq_key]["totals"]
        ax.set_title(
            f"{daq_key} — totals: frame_num={totals['frame_num_drops']} "
            f"device_ts={totals['device_ts_drops']} host_ts={totals['host_ts_drops']} "
            f"buffer={totals['buffer_drops']} "
            f"(analyzed_frames={totals['analyzed_frames']})"
        )
        ax.legend(loc="upper right", fontsize=8)
        ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()
```

Update the end of `run()` to also produce the plot:

```python
    plot_path = os.path.join(OUTPUT_DIR, "silent_drops.png")
    plot_summary(summary, plot_path)
    print(f"Plot written to: {plot_path}")

    return per_daq_results, summary
```

- [ ] **Step 2: Re-run the script**

```bash
python scripts/analyze_silent_drops.py
```

Expected: prints the 16 per-file lines, "Summary written to", "Plot written to". File `output/silent_drops.png` exists.

- [ ] **Step 3: Visually sanity-check the plot**

```bash
open output/silent_drops.png
```

Expected: two panels stacked, 8 file labels on each x-axis, four colored bars per file group, title shows totals.

- [ ] **Step 4: Commit**

```bash
git add scripts/analyze_silent_drops.py
git commit -m "Add summary plot (grouped bars per file, per DAQ)"
```

---

## Task 10: Final verification

**Files:** (no code changes — verification only)

- [ ] **Step 1: Re-run all tests**

```bash
python tests/test_silent_drops.py
```

Expected: all five "OK" lines print.

- [ ] **Step 2: Re-run the full pipeline**

```bash
python scripts/analyze_silent_drops.py
```

Expected: completes without errors; 16 per-file lines, summary and plot paths printed.

- [ ] **Step 3: Verify output files exist**

```bash
ls neural_DAQ1/results/*.silent_drops.json neural_DAQ2/results/*.silent_drops.json output/silent_drops_summary.json output/silent_drops.png
```

Expected: 8 + 8 + 1 + 1 = 18 paths printed (8 per-file JSONs per DAQ, summary, plot).

- [ ] **Step 4: Sanity-check one per-file JSON structure**

```bash
python -c "
import json
d = json.load(open('neural_DAQ1/results/WL27_DAQ1_25_12_10_long-2.silent_drops.json'))
required = ['file','daq','fps','expected_period_ms','gap_threshold_ms','total_frames_in_csv','trim_seconds','trim_frames','analyzed_frames','frame_num','device_timestamp','host_timestamp','dropped_buffer_count']
for k in required:
    assert k in d, f'missing: {k}'
for det in ['frame_num','device_timestamp','host_timestamp']:
    assert set(d[det].keys()) == {'silent_drops','gap_events','events'}, f'{det}: {d[det].keys()}'
assert set(d['dropped_buffer_count'].keys()) == {'total_delta','nonzero_deltas','events'}
print('schema OK')
print('analyzed_frames:', d['analyzed_frames'], 'trim_frames:', d['trim_frames'])
"
```

Expected: prints `schema OK` and numbers.

- [ ] **Step 5: Cross-check trim was applied correctly for long-2 DAQ1**

```bash
python -c "
import json
d = json.load(open('neural_DAQ1/results/WL27_DAQ1_25_12_10_long-2.silent_drops.json'))
assert d['trim_seconds'] == 30, d['trim_seconds']
assert d['trim_frames'] == 600, d['trim_frames']
assert d['analyzed_frames'] == d['total_frames_in_csv'] - 600, (d['analyzed_frames'], d['total_frames_in_csv'])
print('trim OK: analyzed', d['analyzed_frames'], '/', d['total_frames_in_csv'])
"
```

Expected: `trim OK: analyzed N / N+600`.

- [ ] **Step 6: Cross-check DAQ2 was NOT trimmed**

```bash
python -c "
import json, glob
for p in sorted(glob.glob('neural_DAQ2/results/*.silent_drops.json')):
    d = json.load(open(p))
    assert d['trim_seconds'] == 0 and d['trim_frames'] == 0, (p, d['trim_seconds'], d['trim_frames'])
print('DAQ2 no-trim check: OK across all files')
"
```

Expected: `DAQ2 no-trim check: OK across all files`.

---

## Self-Review Notes

**Spec coverage:**
- 4 detectors — Tasks 2, 3, 4 (frame_num, timestamp ×2, dropped_buffer_count) ✓
- Per-frame reduction via groupby + min/max — Task 5 ✓
- DAQ1-only end-of-file trim — Task 6 ✓
- PAIRS-based file selection — Task 8 ✓
- Per-file JSON next to results/ — Task 8 ✓
- Combined summary JSON — Task 8 ✓
- Grouped-bar plot with two DAQ panels — Task 9 ✓
- Constants (FPS=20, period=50ms, threshold=75ms) — Task 1 ✓

**Type/name consistency:** Function names used consistently across tests and implementation (`detect_frame_num_gaps`, `detect_timestamp_gaps`, `detect_dropped_buffer_deltas`, `reduce_to_per_frame`, `apply_trim`, `analyze_file`, `find_csv`, `write_per_file_json`, `build_summary`, `plot_summary`, `run`). Event dict keys (`at_frame_idx`, `dt_ms`/`dt_s`, `missed`, `delta`, `frame_num_before`/`frame_num_after`) match the spec JSON schema.

**No placeholders** — all steps contain concrete code, exact commands, expected output.
