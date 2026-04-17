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


def test_detect_timestamp_gaps_device_ms_no_gaps():
    ts = [0, 50, 100, 150, 200]
    result = asd.detect_timestamp_gaps(ts, threshold=75.0, period=50.0, unit_label="ms")
    assert result["silent_drops"] == 0, result
    assert result["gap_events"] == 0, result


def test_detect_timestamp_gaps_device_ms_one_gap():
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


def test_detect_dropped_buffer_deltas_none():
    counts = [0, 0, 0, 0]
    result = asd.detect_dropped_buffer_deltas(counts)
    assert result["total_delta"] == 0, result
    assert result["nonzero_deltas"] == 0, result
    assert result["events"] == [], result


def test_detect_dropped_buffer_deltas_cumulative():
    counts = [0, 0, 4, 4, 7]
    result = asd.detect_dropped_buffer_deltas(counts)
    assert result["total_delta"] == 7, result
    assert result["nonzero_deltas"] == 2, result
    assert result["events"] == [
        {"at_frame_idx": 2, "delta": 4},
        {"at_frame_idx": 4, "delta": 3},
    ], result


def test_detect_dropped_buffer_deltas_ignores_decreases():
    counts = [10, 10, 3, 5]  # idx 2 decreases — skip; idx 3 delta = 5-3 = 2
    result = asd.detect_dropped_buffer_deltas(counts)
    assert result["total_delta"] == 2, result
    assert result["nonzero_deltas"] == 1, result
    assert result["events"] == [{"at_frame_idx": 3, "delta": 2}], result


if __name__ == "__main__":
    test_detect_frame_num_gaps_no_gaps()
    test_detect_frame_num_gaps_single_gap_of_2()
    test_detect_frame_num_gaps_multiple_gaps()
    test_detect_frame_num_gaps_empty()
    print("frame_num gap tests: OK")
    test_detect_timestamp_gaps_device_ms_no_gaps()
    test_detect_timestamp_gaps_device_ms_one_gap()
    test_detect_timestamp_gaps_host_seconds()
    test_detect_timestamp_gaps_just_under_threshold()
    print("timestamp gap tests: OK")
    test_detect_dropped_buffer_deltas_none()
    test_detect_dropped_buffer_deltas_cumulative()
    test_detect_dropped_buffer_deltas_ignores_decreases()
    print("dropped_buffer_count delta tests: OK")
