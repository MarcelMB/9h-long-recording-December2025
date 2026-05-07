#!/usr/bin/env python3
"""Check for duplicate buffer rows in the per-chunk CSVs.

Tests three stringencies of "duplicate" motivated by miniscope/mio#91
(two data buffers recorded with identical image + timestamp):

  1. Exact-metadata duplicate: rows sharing ALL of
     (frame_num, buffer_count, timestamp, write_timestamp, buffer_recv_unix_time).
     This is the #91-style bug — same buffer replayed byte-for-byte in metadata.

  2. RFI slot collision: rows sharing (reconstructed_frame_index, frame_buffer_count).
     Two buffers claiming the same slot in a host-reconstructed frame. Could
     inflate n_buffers for that RFI and bias MCU-survival upward.

  3. frame_num slot collision: rows sharing (frame_num, buffer_count) where
     frame_num is a valid (non-sentinel) value. Two buffers claiming the
     same position in the same device-frame.

For each CSV we report: total rows, duplicate group count, extra rows
contributed by duplicates (group size - 1, summed), and a few worst-offender
groups. Writes output/duplicate_buffers.json.
"""

import glob
import json
import os

import pandas as pd


BASE_DIR = "/Users/mbrosch/Documents/9h_long_recording_December2025"
DAQ1_DIR = os.path.join(BASE_DIR, "neural_DAQ1")
DAQ2_DIR = os.path.join(BASE_DIR, "neural_DAQ2")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

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

SENTINELS = {0xFFFFFFFF, 0xFFFE0000, 0x80000000, 0x7FFFFFFF}
FRAME_NUM_VALID_MAX = 200_000


def find_csv(daq_dir: str, stem: str) -> str:
    hits = glob.glob(os.path.join(daq_dir, f"*{stem}.csv"))
    if len(hits) != 1:
        raise RuntimeError(f"Expected 1 CSV for {stem} in {daq_dir}, found {len(hits)}")
    return hits[0]


def check_group(df: pd.DataFrame, keys: list, label: str, mask: pd.Series | None = None) -> dict:
    """Group by keys, flag groups with size > 1, return summary + sample."""
    sub = df if mask is None else df[mask]
    if len(sub) == 0:
        return {"label": label, "total_rows": 0, "duplicate_groups": 0,
                "extra_rows": 0, "worst": []}
    sizes = sub.groupby(keys).size()
    dup_sizes = sizes[sizes > 1]
    extra = int((dup_sizes - 1).sum())
    worst = (
        dup_sizes.sort_values(ascending=False).head(5)
        .reset_index().to_dict(orient="records")
    )
    return {
        "label": label,
        "total_rows": int(len(sub)),
        "duplicate_groups": int(len(dup_sizes)),
        "extra_rows": extra,
        "worst": worst,
    }


def analyze_csv(path: str, daq: str, stem: str) -> dict:
    df = pd.read_csv(path)
    out = {"daq": daq, "stem": stem, "csv": os.path.basename(path),
           "n_rows": int(len(df))}

    # 1. Exact metadata duplicate
    out["exact"] = check_group(
        df,
        ["frame_num", "buffer_count", "timestamp",
         "write_timestamp", "buffer_recv_unix_time"],
        "exact metadata match (frame_num, buffer_count, timestamp, write_timestamp, recv_time)",
    )

    # 2. RFI slot collision
    out["rfi_slot"] = check_group(
        df,
        ["reconstructed_frame_index", "frame_buffer_count"],
        "RFI slot collision (reconstructed_frame_index, frame_buffer_count)",
    )

    # 3. frame_num slot collision (filter sentinels + out-of-range)
    fn_valid = ~df["frame_num"].isin(SENTINELS) & (df["frame_num"] < FRAME_NUM_VALID_MAX)
    out["fn_slot"] = check_group(
        df,
        ["frame_num", "buffer_count"],
        "frame_num slot collision (frame_num, buffer_count) [sentinels filtered]",
        mask=fn_valid,
    )

    return out


def main() -> None:
    per_chunk = []
    for daq1_stem, daq2_stem in PAIRS:
        per_chunk.append(analyze_csv(find_csv(DAQ1_DIR, daq1_stem), "DAQ1", daq1_stem))
        per_chunk.append(analyze_csv(find_csv(DAQ2_DIR, daq2_stem), "DAQ2", daq2_stem))

    # Aggregate
    totals = {"DAQ1": {}, "DAQ2": {}}
    for daq in ("DAQ1", "DAQ2"):
        rows = [r for r in per_chunk if r["daq"] == daq]
        totals[daq]["n_chunks"] = len(rows)
        totals[daq]["n_rows"] = sum(r["n_rows"] for r in rows)
        for which in ("exact", "rfi_slot", "fn_slot"):
            totals[daq][which] = {
                "duplicate_groups": sum(r[which]["duplicate_groups"] for r in rows),
                "extra_rows": sum(r[which]["extra_rows"] for r in rows),
            }

    result = {"per_chunk": per_chunk, "totals": totals}

    out_path = os.path.join(OUTPUT_DIR, "duplicate_buffers.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    # Terse stdout summary
    print("=" * 70)
    print("DUPLICATE BUFFER CHECK — miniscope/mio#91")
    print("=" * 70)
    for daq in ("DAQ1", "DAQ2"):
        t = totals[daq]
        print(f"\n{daq}: {t['n_chunks']} chunks, {t['n_rows']:,} total rows")
        for which, nice in [("exact", "Exact metadata dup"),
                            ("rfi_slot", "RFI-slot collision"),
                            ("fn_slot",  "frame_num-slot collision")]:
            g = t[which]["duplicate_groups"]
            e = t[which]["extra_rows"]
            pct = 100.0 * e / t["n_rows"] if t["n_rows"] else 0.0
            print(f"  {nice:<25} {g:>6} groups, {e:>6} extra rows ({pct:.4f} %)")

    print(f"\nWrote: {out_path}")


if __name__ == "__main__":
    main()
