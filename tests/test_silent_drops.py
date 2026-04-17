#!/usr/bin/env python3
"""Plain-assert unit tests for scripts/analyze_silent_drops.py.

Run with: python tests/test_silent_drops.py
"""

import io
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import analyze_silent_drops as asd  # noqa: E402


def _synthetic_csv(rows):
    header = (
        "linked_list,frame_num,buffer_count,frame_buffer_count,write_buffer_count,"
        "dropped_buffer_count,timestamp,pixel_count,write_timestamp,battery_voltage_raw,"
        "input_voltage_raw,buffer_recv_index,buffer_recv_unix_time,black_padding_px,"
        "reconstructed_frame_index\n"
    )
    return header + "\n".join(rows) + "\n"


def test_detect_timestamp_gaps_no_gaps():
    ts = [0, 50, 100, 150, 200]
    result = asd.detect_timestamp_gaps(ts, threshold=75.0, period=50.0, unit_label="ms")
    assert result["silent_drops"] == 0, result
    assert result["gap_events"] == 0, result


def test_detect_timestamp_gaps_one_gap():
    ts = [0, 50, 100, 300, 350]  # 200 ms gap at idx 3 → round(200/50) - 1 = 3 missed
    result = asd.detect_timestamp_gaps(ts, threshold=75.0, period=50.0, unit_label="ms")
    assert result["silent_drops"] == 3, result
    assert result["gap_events"] == 1, result
    assert result["events"][0]["at_frame_idx"] == 3
    assert abs(result["events"][0]["dt_ms"] - 200.0) < 1e-6
    assert result["events"][0]["missed"] == 3


def test_detect_timestamp_gaps_host_seconds():
    ts = [1000.000, 1000.050, 1000.100, 1000.300]  # 0.2 s gap at idx 3
    result = asd.detect_timestamp_gaps(ts, threshold=0.075, period=0.050, unit_label="s")
    assert result["silent_drops"] == 3, result
    assert result["gap_events"] == 1, result
    assert abs(result["events"][0]["dt_s"] - 0.2) < 1e-6


def test_detect_timestamp_gaps_just_under_threshold():
    ts = [0, 50, 120, 170]  # 70 ms < 75 ms threshold
    result = asd.detect_timestamp_gaps(ts, threshold=75.0, period=50.0, unit_label="ms")
    assert result["silent_drops"] == 0, result


def test_reduce_to_per_frame_basic():
    csv_text = _synthetic_csv([
        "0,100,0,0,0,0,1000,5032,0,195,181,0,10.000,0,0",
        "1,100,1,1,1,0,1002,5032,0,195,181,1,10.005,0,0",
        "0,101,0,0,0,0,1050,5032,0,195,181,2,10.050,0,1",
        "1,101,1,1,1,0,1052,5032,0,195,181,3,10.055,0,1",
    ])
    df = pd.read_csv(io.StringIO(csv_text))
    per_frame = asd.reduce_to_per_frame(df)
    assert len(per_frame) == 2, per_frame
    assert list(per_frame["reconstructed_frame_index"]) == [0, 1]
    assert list(per_frame["buffer_recv_unix_time"]) == [10.000, 10.050]


def test_reduce_to_per_frame_takes_min_host_time():
    # First buffer of each frame carries the earliest host arrival time
    csv_text = _synthetic_csv([
        "0,100,0,0,0,0,1000,5032,0,195,181,0,10.010,0,0",
        "1,100,1,1,1,0,1002,5032,0,195,181,1,10.005,0,0",  # earlier
        "0,101,0,0,0,0,1050,5032,0,195,181,2,10.055,0,1",
        "1,101,1,1,1,0,1052,5032,0,195,181,3,10.060,0,1",
    ])
    df = pd.read_csv(io.StringIO(csv_text))
    per_frame = asd.reduce_to_per_frame(df)
    assert list(per_frame["buffer_recv_unix_time"]) == [10.005, 10.055]


def test_apply_trim_daq1_matched_label():
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
    per_frame = pd.DataFrame({"reconstructed_frame_index": list(range(1000))})
    trimmed, trim_frames = asd.apply_trim(per_frame, daq=2, label="long-2")
    assert trim_frames == 0
    assert len(trimmed) == 1000


if __name__ == "__main__":
    test_detect_timestamp_gaps_no_gaps()
    test_detect_timestamp_gaps_one_gap()
    test_detect_timestamp_gaps_host_seconds()
    test_detect_timestamp_gaps_just_under_threshold()
    print("timestamp gap tests: OK")
    test_reduce_to_per_frame_basic()
    test_reduce_to_per_frame_takes_min_host_time()
    print("per-frame reduction tests: OK")
    test_apply_trim_daq1_matched_label()
    test_apply_trim_daq1_no_matching_label()
    test_apply_trim_daq2_never_trims()
    print("trim tests: OK")
