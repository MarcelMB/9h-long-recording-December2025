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
