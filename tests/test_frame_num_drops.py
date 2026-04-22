#!/usr/bin/env python3
"""Plain-assert unit tests for scripts/analyze_frame_num_drops.py.

Run with: python tests/test_frame_num_drops.py
"""

import io
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import analyze_frame_num_drops as afd  # noqa: E402


def _synthetic_csv(rows):
    header = "frame_num,reconstructed_frame_index\n"
    return header + "\n".join(rows) + "\n"


def _df_from_rows(rows):
    return pd.read_csv(io.StringIO(_synthetic_csv(rows)))


def test_valid_mask_rejects_sentinels():
    df = _df_from_rows([
        "100,0",
        "4294967295,0",   # 0xFFFFFFFF
        "101,1",
        "2147483648,1",   # 0x80000000
        "102,2",
    ])
    m = afd.valid_mask(df["frame_num"])
    assert list(m) == [True, False, True, False, True], list(m)


def test_valid_mask_rejects_above_plausible_max():
    df = _df_from_rows([
        "100,0",
        "500000,0",  # corrupted within uint32 but far above any real counter
        "101,1",
    ])
    m = afd.valid_mask(df["frame_num"])
    assert list(m) == [True, False, True]


def test_valid_mask_rejects_zero():
    df = _df_from_rows(["0,0", "1,0", "2,1"])
    m = afd.valid_mask(df["frame_num"])
    # frame_num==0 is rejected (guards against blank/default values)
    assert list(m) == [False, True, True]


def test_pick_start_end_clean():
    rows = [f"{100 + i},{i // 8}" for i in range(200)]
    df = _df_from_rows(rows)
    fn_start, fn_end, _, _ = afd.pick_start_end(df["frame_num"])
    assert fn_start == 100
    assert fn_end == 299


def test_pick_start_end_ignores_corrupted_in_window():
    # Head has one sentinel; quorum should still resolve to 100 (appears ≥2x)
    # Head rows: [100,100,100,4294967295,100,102,102,102,103,103,103,104,...]
    rows = (
        ["100,0"] * 3
        + ["4294967295,0"]  # sentinel
        + ["100,0", "102,0", "102,0", "102,0", "103,0", "103,0", "103,0"]
        + [f"{104 + i},{(i + 1)}" for i in range(20)]
    )
    df = _df_from_rows(rows)
    fn_start, fn_end, _, _ = afd.pick_start_end(df["frame_num"], head=10, tail=4)
    assert fn_start == 100, fn_start
    # tail is last 4 rows, which are clean
    assert fn_end == df["frame_num"].iloc[-1], fn_end


def test_pick_start_end_quorum_rejects_within_range_bitflip():
    # Head window has ONE within-range bit-flip (193) among real frame 447x8
    # and real frame 448x8. fn_start should be 447, not 193.
    rows = ["447,0"] * 8 + ["193,1"] + ["448,1"] * 8 + ["449,2"] * 8
    tail = ["500,10"] * 8 + ["501,11"] * 8
    df = _df_from_rows(rows + tail)
    # First 17 rows cover 8×447 + 1×193 + 8×448 — quorum should pick min of
    # {447, 448} (both count ≥2) = 447
    fn_start, fn_end, _, _ = afd.pick_start_end(df["frame_num"], head=17, tail=16)
    assert fn_start == 447, fn_start
    assert fn_end == 501, fn_end


def test_pick_start_end_falls_back_to_min_when_no_quorum():
    # Every value is unique — fall back to plain min/max
    rows = [f"{100 + i},{i}" for i in range(20)]
    df = _df_from_rows(rows)
    fn_start, fn_end, _, _ = afd.pick_start_end(df["frame_num"], head=20, tail=20)
    assert fn_start == 100
    assert fn_end == 119


def test_analyze_file_perfect_no_drops(tmp_csv=None):
    # 100 frames, 8 buffers each, frame_num 1000..1099, no corruption
    rows = []
    for f in range(100):
        for b in range(8):
            rows.append(f"{1000 + f},{f}")
    df = _df_from_rows(rows)

    # Simulate file IO by writing to a temp file, since analyze_file reads a CSV
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
        f.write(_synthetic_csv(rows))
        path = f.name
    try:
        result = afd.analyze_file(path, daq=1, label="test")
    finally:
        os.unlink(path)

    assert result["fn_start"] == 1000, result
    assert result["fn_end"] == 1099, result
    assert result["intended"] == 100, result
    assert result["delivered"] == 100, result
    assert result["silent_drops"] == 0, result
    assert result["flags"] == [], result


def test_analyze_file_detects_silent_drops():
    # MCU sent frame_num 1000..1099 (100 frames), but frames 1050..1059 (10) never arrived
    rows = []
    for f in range(100):
        if 50 <= f < 60:
            continue  # all 8 buffers of these frames are silent-dropped
        for b in range(8):
            rows.append(f"{1000 + f},{f if f < 50 else f - 10}")

    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
        f.write(_synthetic_csv(rows))
        path = f.name
    try:
        result = afd.analyze_file(path, daq=1, label="test")
    finally:
        os.unlink(path)

    assert result["fn_start"] == 1000, result
    assert result["fn_end"] == 1099, result
    assert result["intended"] == 100, result
    assert result["delivered"] == 90, result
    assert result["silent_drops"] == 10, result


def test_analyze_file_ignores_corrupted_rows_in_count():
    # 50 clean frames + 2 corrupted rows that must not be counted as real frames
    rows = []
    for f in range(50):
        for b in range(8):
            rows.append(f"{1000 + f},{f}")
    rows.append("4294967295,49")  # sentinel
    rows.append("2147483648,49")  # sentinel

    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
        f.write(_synthetic_csv(rows))
        path = f.name
    try:
        result = afd.analyze_file(path, daq=1, label="test")
    finally:
        os.unlink(path)

    assert result["fn_start"] == 1000, result
    assert result["fn_end"] == 1049, result
    assert result["intended"] == 50, result
    assert result["delivered"] == 50, result
    assert result["silent_drops"] == 0, result
    assert result["filtered_rows"] == 2, result


if __name__ == "__main__":
    test_valid_mask_rejects_sentinels()
    test_valid_mask_rejects_above_plausible_max()
    test_valid_mask_rejects_zero()
    print("valid_mask tests: OK")
    test_pick_start_end_clean()
    test_pick_start_end_ignores_corrupted_in_window()
    test_pick_start_end_quorum_rejects_within_range_bitflip()
    test_pick_start_end_falls_back_to_min_when_no_quorum()
    print("pick_start_end tests: OK")
    test_analyze_file_perfect_no_drops()
    test_analyze_file_detects_silent_drops()
    test_analyze_file_ignores_corrupted_rows_in_count()
    print("analyze_file tests: OK")
