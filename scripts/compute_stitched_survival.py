#!/usr/bin/env python3
"""Join stitched timestamps to per-RFI survival to get stitched-track survival.

Input:
  output/WL27_stitched_timestamps.csv  (645,790 rows; one per stitched output frame)
    columns: stitched_frame, chunk, chunk_frame, unix_time, source, segment,
             daq1_frame, daq2_frame, daq1_broken, daq2_broken
  output/rfi_survival_all.csv          (per-RFI survival across all DAQ1/DAQ2 chunks)
    columns: daq, segment, reconstructed_frame_index, n_buffers, fn_mode,
             surviving_ge8, surviving_ge7, surviving_ge6, trimmed

Output:
  output/WL27_stitched_survival.csv
    original stitched columns + MCU-level and RFI-level survival flags for both
    DAQs, the stitched (picked-source) flag, and either/neither-survived flags
  output/survival_rate_stitched.json
    MCU-level (headline) and RFI-level (diagnostic) summaries, with per-chunk
    and per-source (DAQ1 vs DAQ2 — which did the stitcher pick) breakdowns

Two survival flavors (both recorded; MCU-level is the publication headline):
  MCU-level: the MCU frame the stitcher wrote DID get reconstructed somewhere
             on that DAQ (some RFI for that fn_mode had ≥N buffers). Honest
             answer to "did this frame make it across the wireless link."
  RFI-level: the specific RFI the stitcher wrote had ≥N buffers. Stricter —
             catches cases where the stitcher picked a short fragment even
             when a full RFI existed for the same MCU frame.

Stitched-survival logic (per stitched frame):
  - If source == "DAQ1": stitched_survived = daq1_survived
  - If source == "DAQ2": stitched_survived = daq2_survived

Segment-to-DAQ2-label mapping: same PAIRS as analyze_frame_num_drops.py.

Denominator: the stitched output's total frame count (per-stitched-frame loss
rate — matches the old metric's denominator).
"""

import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import analyze_frame_num_drops as afd

BASE = "/Users/mbrosch/Documents/9h_long_recording_December2025"
OUT_DIR = f"{BASE}/output"
STITCHED_TS = f"{OUT_DIR}/WL27_stitched_timestamps.csv"
RFI_SURVIVAL = f"{OUT_DIR}/rfi_survival_all.csv"

OUT_CSV = f"{OUT_DIR}/WL27_stitched_survival.csv"
OUT_JSON = f"{OUT_DIR}/survival_rate_stitched.json"

THRESHOLDS = [8, 7]


def _segment_to_daq2_label():
    """Map DAQ1 segment label → DAQ2 label using PAIRS."""
    return {p[0]: p[1] for p in afd.PAIRS}


def _summarize(df, group_col=None):
    out = {}
    if group_col is None:
        groups = [("", df)]
    else:
        groups = list(df.groupby(group_col))
    for key, g in groups:
        row = {"total": int(len(g))}
        for flavor in ("mcu", "rfi"):
            for th in THRESHOLDS:
                surv = int(g[f"stitched_{flavor}_ge{th}"].sum())
                lost = int(len(g) - surv)
                row[f"stitched_surviving_{flavor}_ge{th}"] = surv
                row[f"stitched_lost_{flavor}_ge{th}"] = lost
                row[f"stitched_loss_pct_{flavor}_ge{th}"] = round(
                    100.0 * lost / len(g), 4
                ) if len(g) else None
                either = int(g[f"either_{flavor}_ge{th}"].sum())
                neither = int(len(g) - either)
                row[f"either_{flavor}_ge{th}"] = either
                row[f"neither_{flavor}_ge{th}"] = neither
                row[f"neither_loss_pct_{flavor}_ge{th}"] = round(
                    100.0 * neither / len(g), 4
                ) if len(g) else None
        out[str(key) if key != "" else "all"] = row
    return out


def run():
    print(f"Loading stitched timestamps: {STITCHED_TS}")
    st = pd.read_csv(STITCHED_TS)
    print(f"  {len(st):,} rows")

    print(f"Loading per-RFI survival: {RFI_SURVIVAL}")
    rs = pd.read_csv(RFI_SURVIVAL)
    print(f"  {len(rs):,} rows")

    seg2daq2 = _segment_to_daq2_label()

    # Split rfi_survival into DAQ1 and DAQ2 tables, keyed by (segment, RFI).
    rfi_cols = [
        "segment", "reconstructed_frame_index",
        "surviving_ge8", "surviving_ge7",
        "mcu_surviving_ge8", "mcu_surviving_ge7",
    ]
    rs_daq1 = rs[rs["daq"] == 1][rfi_cols].rename(columns={
        "surviving_ge8": "daq1_rfi_ge8",
        "surviving_ge7": "daq1_rfi_ge7",
        "mcu_surviving_ge8": "daq1_mcu_ge8",
        "mcu_surviving_ge7": "daq1_mcu_ge7",
    })
    rs_daq2 = rs[rs["daq"] == 2][rfi_cols].rename(columns={
        "surviving_ge8": "daq2_rfi_ge8",
        "surviving_ge7": "daq2_rfi_ge7",
        "mcu_surviving_ge8": "daq2_mcu_ge8",
        "mcu_surviving_ge7": "daq2_mcu_ge7",
        "segment": "daq2_segment",
    })

    # Join DAQ1: (segment, daq1_frame) → daq1_survived_*
    st = st.merge(
        rs_daq1,
        left_on=["segment", "daq1_frame"],
        right_on=["segment", "reconstructed_frame_index"],
        how="left",
    ).drop(columns=["reconstructed_frame_index"])

    # Join DAQ2: (daq2_segment, daq2_frame) → daq2_survived_*
    st["daq2_segment"] = st["segment"].map(seg2daq2)
    st = st.merge(
        rs_daq2,
        left_on=["daq2_segment", "daq2_frame"],
        right_on=["daq2_segment", "reconstructed_frame_index"],
        how="left",
    ).drop(columns=["reconstructed_frame_index", "daq2_segment"])

    # Flag stitched rows whose picked RFI doesn't exist in rfi_survival_all.
    # Happens when the stitcher ran on a slightly different DAQ CSV/AVI generation
    # than the current survival analysis (a few thousand tail RFIs in some
    # chunks). We record it so the headline stats can be reported with or
    # without these "unknown" rows.
    st["daq1_rfi_in_table"] = st["daq1_rfi_ge8"].notna()
    st["daq2_rfi_in_table"] = st["daq2_rfi_ge8"].notna()

    flavor_cols = []
    for flavor in ("rfi", "mcu"):
        for th in THRESHOLDS:
            flavor_cols += [f"daq1_{flavor}_ge{th}", f"daq2_{flavor}_ge{th}"]
    for col in flavor_cols:
        st[col] = st[col].fillna(False).astype(bool)

    # Stitched survival = the picked source's flag (for each flavor × threshold)
    picked = st["source"].where(st["source"].isin(["DAQ1", "DAQ2"]))
    picked_in_table = (
        ((picked == "DAQ1") & st["daq1_rfi_in_table"]) |
        ((picked == "DAQ2") & st["daq2_rfi_in_table"])
    )
    st["picked_in_table"] = picked_in_table
    for flavor in ("rfi", "mcu"):
        for th in THRESHOLDS:
            st[f"stitched_{flavor}_ge{th}"] = (
                ((picked == "DAQ1") & st[f"daq1_{flavor}_ge{th}"]) |
                ((picked == "DAQ2") & st[f"daq2_{flavor}_ge{th}"])
            )
            st[f"either_{flavor}_ge{th}"] = (
                st[f"daq1_{flavor}_ge{th}"] | st[f"daq2_{flavor}_ge{th}"]
            )

    st.to_csv(OUT_CSV, index=False)
    print(f"\nWrote {OUT_CSV} ({len(st):,} rows)")

    # Summaries — headline uses only rows whose picked RFI is in our survival
    # table (picked_in_table=True), because "unknown" rows are not actually
    # counted as lost on their source DAQ — they live outside our analysis.
    st_known = st[st["picked_in_table"]]

    summary = {
        "source_csv": os.path.basename(STITCHED_TS),
        "thresholds": THRESHOLDS,
        "logic": "stitched_survived = the picked source's survival flag",
        "note_unknown_rows": (
            "picked_in_table=False rows reference RFIs not in rfi_survival_all "
            "(stitcher's AVI had more tail frames than the current CSVs can "
            "reconstruct). Headline stats exclude them."
        ),
        "total_stitched_rows": int(len(st)),
        "total_unknown_rows": int((~st["picked_in_table"]).sum()),
        "all": _summarize(st_known)["all"],
        "per_chunk": _summarize(st_known, group_col="chunk"),
        "per_source": _summarize(st_known, group_col="source"),
        "all_including_unknown": _summarize(st)["all"],
    }

    # Cross-check: for rows where both daq1_broken==0 and daq2_broken==0
    # (old-metric good frames), how many fail the new MCU-level survival?
    # Restrict to rows where the picked RFI was in our table — otherwise the
    # mismatch is just "we don't have data" not "actually broken".
    old_good = st_known[(st_known["daq1_broken"] == 0) & (st_known["daq2_broken"] == 0)]
    mismatch_mcu = old_good[~old_good["stitched_mcu_ge8"]]
    mismatch_rfi = old_good[~old_good["stitched_rfi_ge8"]]
    summary["cross_check_old_good_but_new_lost"] = {
        "old_good_frames": int(len(old_good)),
        "new_lost_among_them_mcu": int(len(mismatch_mcu)),
        "new_lost_among_them_rfi": int(len(mismatch_rfi)),
        "mismatch_pct_of_old_good_mcu": round(
            100.0 * len(mismatch_mcu) / len(old_good), 4
        ) if len(old_good) else None,
        "mismatch_pct_of_old_good_rfi": round(
            100.0 * len(mismatch_rfi) / len(old_good), 4
        ) if len(old_good) else None,
    }

    with open(OUT_JSON, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Wrote {OUT_JSON}")

    print(f"\n{'=' * 70}")
    print("Stitched-track survival (per-stitched-frame):")
    print(f"{'=' * 70}")
    a = summary["all"]
    tot = summary["total_stitched_rows"]
    unk = summary["total_unknown_rows"]
    print(f"  total stitched frames:              {tot:,}")
    print(f"  unknown (picked RFI not in table):  {unk:,}  — excluded from headline")
    print(f"  analyzable rows:                    {a['total']:,}")
    print(f"  MCU-level surviving (≥8):           {a['stitched_surviving_mcu_ge8']:,}  "
          f"(loss {a['stitched_loss_pct_mcu_ge8']}%)   ← headline")
    print(f"  RFI-level surviving (≥8):           {a['stitched_surviving_rfi_ge8']:,}  "
          f"(loss {a['stitched_loss_pct_rfi_ge8']}%)   [stricter: specific picked RFI]")
    print(f"  neither DAQ survived MCU (≥8):      {a['neither_mcu_ge8']:,} "
          f"({a['neither_loss_pct_mcu_ge8']}%)   ← new equivalent of old 0.20% "
          f"both-broken rate")
    print(f"\nPer-source (which DAQ the stitcher picked):")
    for src, row in summary["per_source"].items():
        print(f"  {src}: picked {row['total']:,}  "
              f"MCU loss(≥8)={row['stitched_loss_pct_mcu_ge8']}%  "
              f"RFI loss(≥8)={row['stitched_loss_pct_rfi_ge8']}%")

    cc = summary["cross_check_old_good_but_new_lost"]
    print(f"\nCross-check: old-metric good frames ({cc['old_good_frames']:,}) "
          f"that fail new survival: MCU={cc['new_lost_among_them_mcu']:,} "
          f"({cc['mismatch_pct_of_old_good_mcu']}%)  "
          f"RFI={cc['new_lost_among_them_rfi']:,} "
          f"({cc['mismatch_pct_of_old_good_rfi']}%)")


if __name__ == "__main__":
    run()
