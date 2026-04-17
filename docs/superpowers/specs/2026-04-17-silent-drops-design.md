# Silent Frame Drop Detection — Design

**Date:** 2026-04-17
**Author:** Marcel + Claude
**Script:** `scripts/analyze_silent_drops.py`

## Motivation

The existing broken-frame detectors (`scripts/analyze_frames.py`) scan each AVI for pixel artifacts:
1. Black rows (≥30 consecutive zero pixels across ≥10 rows)
2. Gradient noise (mean |second derivative| per row > 20)

These only fire on frames that reached the AVI file. If **all 8 buffers** of a frame are lost in transmission, the frame never exists in the AVI — it is invisible to pixel-based detection. The CSV logs still record what the device produced and when each buffer arrived, so gaps in the CSV can identify these silent drops.

## Scope

- **Per DAQ, per file.** Each file corresponds to a miniscope restart, so frame counters and timestamps reset between files. No cross-file logic.
- Files analyzed: the 8 chunks in `analyze_drops.py`'s `PAIRS` list (DAQ1: `long-2/4/6/8/9/10/12/13`; DAQ2: matched counterparts).
- `TRIM_SECONDS` applied identically to `analyze_drops.py`: **DAQ1 only**, trimming from the **end** of the file (long-2: last 30s discarded; long-9: last 155s discarded). DAQ2 files are analyzed in full. This matches the frame set used for the aligned drop analysis.

## Detection — 4 independent signals per file

The CSV has one row per buffer. Each frame is 8 buffers (`buffer_count` 0–7). Preprocessing:

1. Group rows by `reconstructed_frame_index`. For each frame take `min(timestamp)` (device clock, frame start), `min(buffer_recv_unix_time)` (host arrival of first buffer), the group's `frame_num` (constant within a group), and `max(dropped_buffer_count)` (firmware's running drop counter at end of frame). Robust to a missing `buffer_count==0` row.
2. For DAQ1 files in the trim table: drop the last `trim_seconds × fps` frames (by `reconstructed_frame_index`). DAQ2 files: no trim.

Then run four detectors independently on the remaining per-frame sequence:

### 1. `frame_num` gaps (device frame counter)
`diff(frame_num)` across consecutive frames. Any `diff > 1` is a silent-drop event; missed count = `diff − 1`. This is the device's own counter — cleanest signal that the sensor produced a frame the host never saw.

### 2. Device `timestamp` gaps (device clock, ms)
`diff(timestamp)` between consecutive frames. Flag if `Δt > 75 ms` (1.5× expected 50 ms period at 20 FPS). Missed count = `round(Δt / 50) − 1`. Detects gaps on the sensor/device side.

### 3. Host `buffer_recv_unix_time` gaps
Same math as (2) but on host arrival time. Catches transport-side stalls where the device clock may still look clean but the host received nothing for an unusual interval.

### 4. `dropped_buffer_count` deltas
This column is set by the firmware. `diff(dropped_buffer_count)` per frame; sum the positive deltas across the file. Also record the per-frame events where `diff > 0`.

All four run side-by-side. Overlap is expected and informative — e.g., an event that shows up in `frame_num` but not `host_timestamp` means the host saw the gap but the device clock didn't stall.

## Constants

- FPS = 20.0
- Expected period = 50.0 ms
- Gap threshold = 75.0 ms (1.5× period)
- Trim table (DAQ1 only, end-of-file): `{"long-2": 30, "long-9": 155}` (seconds)

## Outputs

### Per-file JSON
Path: `neural_DAQ{1,2}/results/<csv_stem>.silent_drops.json`

```json
{
  "file": "WL27_DAQ1_25_12_10_long-2.csv",
  "daq": 1,
  "fps": 20.0,
  "expected_period_ms": 50.0,
  "gap_threshold_ms": 75.0,
  "total_frames_in_csv": 72000,
  "trim_seconds": 30,
  "trim_frames": 600,
  "analyzed_frames": 71400,
  "frame_num": {
    "silent_drops": 12,
    "gap_events": 5,
    "events": [
      {"at_frame_idx": 4321, "frame_num_before": 5893, "frame_num_after": 5897, "missed": 3}
    ]
  },
  "device_timestamp": {
    "silent_drops": 12,
    "gap_events": 5,
    "events": [
      {"at_frame_idx": 4321, "dt_ms": 204.0, "missed": 3}
    ]
  },
  "host_timestamp": {
    "silent_drops": 14,
    "gap_events": 6,
    "events": [
      {"at_frame_idx": 4321, "dt_s": 0.204, "missed": 3}
    ]
  },
  "dropped_buffer_count": {
    "total_delta": 8,
    "nonzero_deltas": 3,
    "events": [
      {"at_frame_idx": 2100, "delta": 4}
    ]
  }
}
```

### Combined summary JSON
Path: `output/silent_drops_summary.json`

```json
{
  "fps": 20.0,
  "gap_threshold_ms": 75.0,
  "DAQ1": {
    "per_file": [
      {"file": "WL27_DAQ1_..._long-2.csv", "analyzed_frames": 71400,
       "frame_num_drops": 12, "device_ts_drops": 12, "host_ts_drops": 14, "buffer_drops": 8}
    ],
    "totals": {"analyzed_frames": 570000,
               "frame_num_drops": 89, "device_ts_drops": 91, "host_ts_drops": 112, "buffer_drops": 34}
  },
  "DAQ2": { "...": "..." }
}
```

### Plot
Path: `output/silent_drops.png`

Two stacked panels (DAQ1, DAQ2). Per file, grouped bars — one bar per detector (`frame_num`, `device_ts`, `host_ts`, `dropped_buffers`). X-axis: file label. Y-axis: drop count.

## Non-goals
- Not merging with `analyze_drops.py`'s both-DAQs-broken definition. Silent drops are a per-DAQ transport property; combined/aligned drop analysis stays in `analyze_drops.py`.
- Not modifying `analyze_frames.py` or any existing outputs.
- Not pixel-based — this script does not open AVI files.

## File layout impact
- New: `scripts/analyze_silent_drops.py`
- New outputs: `neural_DAQ{1,2}/results/*.silent_drops.json`, `output/silent_drops_summary.json`, `output/silent_drops.png`

No changes to existing scripts or outputs.
