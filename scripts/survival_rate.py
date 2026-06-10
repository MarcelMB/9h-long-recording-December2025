#!/usr/bin/env python3
"""Compute per-chunk [surviving frames] / [MCU intended] error rate.

Why this formulation:
  A single wireless bit-flip in a buffer header can cause the host-side
  reconstructor to produce 2–3 RFIs from one real MCU frame. Counting
  "broken AVI frames" double- or triple-counts these events. Counting
  from the MCU-counter side (the frame_num metadata) gives an
  unambiguous denominator: the device sent exactly this many frames, and
  each either survived intact or didn't.

Definitions:
  intended (per chunk) = fn_end − fn_start + 1      (MCU frame_num range)
  surviving (per chunk) = number of MCU frame_nums for which an RFI with
                          >= SURVIVAL_MIN_BUFFERS buffers exists whose
                          majority frame_num equals that value.

  SURVIVAL_MIN_BUFFERS = 8 by default (only fully-reconstructed frames count
    as surviving). Reported at multiple thresholds (8, 7, 6) so you can
    pick the cutoff appropriate for your downstream use.

Trimming (DAQ1 only):
  Matches analyze_silent_drops.py TRIM_SECONDS_DAQ1 so the new metric
  compares apples-to-apples with publication_drop_timeline. For each
  trimmed chunk, drop the last (trim_s × FPS) RFIs and recompute fn_end
  from the kept subset before counting survival.

Outputs:
  output/survival_rate.json            — per-chunk and per-DAQ numbers,
                                         both trimmed and untrimmed
  output/survival_rate.png             — stacked bar of surv vs lost per chunk
  output/rfi_survival_all.csv          — combined per-RFI join table
                                         (daq, segment, reconstructed_frame_index,
                                         n_buffers, fn_mode, surviving_geN, trimmed)
  neural_DAQ{1,2}/results/<stem>.rfi_survival.csv  — per-chunk per-RFI table
"""

import json
import os
import sys

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(__file__))
import analyze_frame_num_drops as afd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAQ1_DIR = f"{BASE}/neural_DAQ1"
DAQ2_DIR = f"{BASE}/neural_DAQ2"
OUT_DIR = f"{BASE}/output"

THRESHOLDS = [8, 7, 6]

# DAQ1-only end-of-file trim, in seconds. Matches analyze_silent_drops.py.
TRIM_SECONDS_DAQ1 = {"long-2": 30, "long-9": 155}
FPS = 20.0


def _by_rfi(df):
    """Per-RFI table: n_buffers and majority frame_num (fn_mode)."""
    mask = afd.valid_mask(df["frame_num"])
    return (
        df[mask]
        .groupby("reconstructed_frame_index")
        .agg(
            n_buffers=("frame_num", "size"),
            fn_mode=("frame_num", lambda s: s.mode().iat[0] if len(s) else -1),
        )
    )


def _survival_from_by_rfi(by_rfi, fn_start, fn_end):
    """Count surviving MCU frame_nums at each buffer threshold."""
    out = {}
    for th in THRESHOLDS:
        ok = by_rfi[
            (by_rfi["n_buffers"] >= th)
            & (by_rfi["fn_mode"] >= fn_start)
            & (by_rfi["fn_mode"] <= fn_end)
        ]
        out[f"surviving_ge{th}"] = int(ok["fn_mode"].nunique())
    return out


def _trim_rfi_range(by_rfi, trim_frames):
    """Drop the last `trim_frames` RFIs from by_rfi (sorted by RFI)."""
    if trim_frames <= 0 or len(by_rfi) == 0:
        return by_rfi
    by_rfi = by_rfi.sort_index()
    keep = max(len(by_rfi) - trim_frames, 0)
    return by_rfi.iloc[:keep]


def analyze_file(csv_path, daq, label):
    """Compute per-chunk survival (untrimmed + trimmed) and per-RFI survival table.

    Returns a dict with keys:
      untrimmed: {intended, fn_start, fn_end, surviving_ge{8,7,6}, lost_, survival_rate_}
      trimmed:   same shape; equals untrimmed if chunk is not in the trim table
      by_rfi:    DataFrame with columns (n_buffers, fn_mode, surviving_ge{8,7},
                 trimmed) indexed by reconstructed_frame_index
    """
    df = pd.read_csv(csv_path, usecols=["frame_num", "reconstructed_frame_index"])
    by_rfi = _by_rfi(df)

    fn_start_full, fn_end_full, _, _ = afd.pick_start_end(df["frame_num"])
    if fn_start_full is None:
        return None

    def _stats(by_rfi_subset, intended, fn_start, fn_end):
        out = {"intended": int(intended), "fn_start": fn_start, "fn_end": fn_end}
        out.update(_survival_from_by_rfi(by_rfi_subset, fn_start, fn_end))
        for th in THRESHOLDS:
            s = out[f"surviving_ge{th}"]
            out[f"lost_ge{th}"] = int(intended - s)
            out[f"survival_rate_ge{th}_pct"] = (
                round(100.0 * s / intended, 4) if intended else None
            )
            out[f"loss_rate_ge{th}_pct"] = (
                round(100.0 * (intended - s) / intended, 4) if intended else None
            )
        return out

    untrimmed = _stats(
        by_rfi, fn_end_full - fn_start_full + 1, fn_start_full, fn_end_full
    )

    # Trim: only DAQ1 chunks in the table. Drop last N RFIs, then recompute
    # fn_end from the kept RFIs' fn_modes.
    trim_frames = int(TRIM_SECONDS_DAQ1.get(label, 0) * FPS) if daq == 1 else 0
    if trim_frames > 0:
        kept = _trim_rfi_range(by_rfi, trim_frames)
        if len(kept) == 0:
            trimmed = untrimmed.copy()
        else:
            # Recompute fn_end from the kept RFIs' fn_modes (majority per RFI).
            kept_valid = kept[
                (kept["fn_mode"] >= fn_start_full) & (kept["fn_mode"] <= fn_end_full)
            ]
            if len(kept_valid):
                fn_end_trim = int(kept_valid["fn_mode"].max())
            else:
                fn_end_trim = fn_end_full
            trimmed = _stats(
                kept, fn_end_trim - fn_start_full + 1, fn_start_full, fn_end_trim
            )
        trimmed["trim_frames"] = trim_frames
    else:
        trimmed = untrimmed.copy()
        trimmed["trim_frames"] = 0

    # Per-RFI table for the join against stitched timestamps.
    #   surviving_geN        : does THIS specific RFI have >= N buffers (RFI-level)
    #   mcu_surviving_geN    : is the MCU frame_num this RFI represents covered by
    #                          ANY RFI with >= N buffers (MCU-level — the honest
    #                          "did this MCU frame make it across the link" flag)
    per_rfi = by_rfi.copy()
    in_range = (per_rfi["fn_mode"] >= fn_start_full) & (
        per_rfi["fn_mode"] <= fn_end_full
    )
    for th in THRESHOLDS:
        per_rfi[f"surviving_ge{th}"] = (per_rfi["n_buffers"] >= th) & in_range
        # Set of MCU fn_modes with at least one >=th-buffer RFI.
        ok_fn_modes = set(per_rfi.loc[per_rfi[f"surviving_ge{th}"], "fn_mode"].unique())
        per_rfi[f"mcu_surviving_ge{th}"] = (
            per_rfi["fn_mode"].isin(ok_fn_modes) & in_range
        )
    per_rfi["trimmed"] = False
    if trim_frames > 0 and len(per_rfi) > trim_frames:
        trimmed_rfi_idx = per_rfi.sort_index().index[-trim_frames:]
        per_rfi.loc[trimmed_rfi_idx, "trimmed"] = True

    return {
        "untrimmed": untrimmed,
        "trimmed": trimmed,
        "by_rfi": per_rfi,
    }


def write_per_chunk_rfi_csv(per_rfi, daq_dir, csv_path):
    """Write neural_DAQ{1,2}/results/<stem>.rfi_survival.csv."""
    results_dir = os.path.join(daq_dir, "results")
    os.makedirs(results_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(csv_path))[0]
    out_path = os.path.join(results_dir, f"{stem}.rfi_survival.csv")
    cols = [
        "n_buffers",
        "fn_mode",
        "surviving_ge8",
        "surviving_ge7",
        "surviving_ge6",
        "mcu_surviving_ge8",
        "mcu_surviving_ge7",
        "mcu_surviving_ge6",
        "trimmed",
    ]
    per_rfi[cols].to_csv(out_path, index=True, index_label="reconstructed_frame_index")
    return out_path


def collect():
    labels_by_daq = {
        "DAQ1": list(dict.fromkeys(p[0] for p in afd.PAIRS)),
        "DAQ2": list(dict.fromkeys(p[1] for p in afd.PAIRS)),
    }
    per_daq = {"DAQ1": [], "DAQ2": []}
    per_rfi_frames = []  # list of DataFrames to concat for rfi_survival_all.csv

    for daq_key, daq_dir, daq_num in [("DAQ1", DAQ1_DIR, 1), ("DAQ2", DAQ2_DIR, 2)]:
        for label in labels_by_daq[daq_key]:
            csv = afd.find_csv(daq_dir, label)
            if csv is None:
                continue
            r = analyze_file(csv, daq=daq_num, label=label)
            if r is None:
                continue
            r["untrimmed"]["label"] = label
            r["trimmed"]["label"] = label
            per_daq[daq_key].append(
                {
                    "label": label,
                    "untrimmed": r["untrimmed"],
                    "trimmed": r["trimmed"],
                }
            )

            write_per_chunk_rfi_csv(r["by_rfi"], daq_dir, csv)

            rdf = r["by_rfi"].reset_index()
            rdf.insert(0, "daq", daq_num)
            rdf.insert(1, "segment", label)
            per_rfi_frames.append(rdf)

            print(
                f"{daq_key} {label}: untrimmed intended={r['untrimmed']['intended']:,} "
                f"surv(≥8)={r['untrimmed']['surviving_ge8']:,} "
                f"loss(≥8)={r['untrimmed']['loss_rate_ge8_pct']}%   "
                f"| trimmed intended={r['trimmed']['intended']:,} "
                f"surv(≥8)={r['trimmed']['surviving_ge8']:,} "
                f"loss(≥8)={r['trimmed']['loss_rate_ge8_pct']}%"
            )

    return per_daq, per_rfi_frames


def add_totals(per_daq):
    totals = {}
    for daq_key, rows in per_daq.items():
        t = {"untrimmed": {}, "trimmed": {}}
        for variant in ("untrimmed", "trimmed"):
            acc = {"intended": 0}
            for th in THRESHOLDS:
                acc[f"surviving_ge{th}"] = 0
                acc[f"lost_ge{th}"] = 0
            for r in rows:
                sub = r[variant]
                acc["intended"] += sub["intended"]
                for th in THRESHOLDS:
                    acc[f"surviving_ge{th}"] += sub[f"surviving_ge{th}"]
                    acc[f"lost_ge{th}"] += sub[f"lost_ge{th}"]
            for th in THRESHOLDS:
                if acc["intended"]:
                    acc[f"survival_rate_ge{th}_pct"] = round(
                        100.0 * acc[f"surviving_ge{th}"] / acc["intended"], 4
                    )
                    acc[f"loss_rate_ge{th}_pct"] = round(
                        100.0 * acc[f"lost_ge{th}"] / acc["intended"], 4
                    )
            t[variant] = acc
        totals[daq_key] = t
    return totals


def plot(per_daq, totals, out_path):
    """Stacked bar per chunk using the TRIMMED numbers."""
    fig, axes = plt.subplots(2, 1, figsize=(14, 9))
    for ax, daq_key in zip(axes, ("DAQ1", "DAQ2")):
        rows = [r["trimmed"] for r in per_daq[daq_key]]
        if not rows:
            continue
        labels = [r["label"] for r in rows]
        x = np.arange(len(labels))
        surv8 = np.array([r["surviving_ge8"] for r in rows])
        intended = np.array([r["intended"] for r in rows])
        lost8 = intended - surv8
        ax.bar(x, surv8, color="#2ca02c", label="surviving (RFI ≥ 8 buffers)")
        ax.bar(
            x,
            lost8,
            bottom=surv8,
            color="#d62728",
            label="lost (no ≥8-buffer RFI for this MCU frame)",
        )
        for i, r in enumerate(rows):
            ax.text(
                x[i],
                intended[i] + intended.max() * 0.01,
                f"{r['survival_rate_ge8_pct']}%",
                ha="center",
                va="bottom",
                fontsize=8,
            )
        t = totals[daq_key]["trimmed"]
        ax.set_title(
            f"{daq_key} (trimmed) — survival (≥8-buffer RFI per MCU frame): "
            f"{t['surviving_ge8']:,} / {t['intended']:,}  "
            f"({t['survival_rate_ge8_pct']}%)   |   "
            f"loss: {t['lost_ge8']:,} ({t['loss_rate_ge8_pct']}%)"
        )
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=9)
        ax.set_ylabel("MCU frames per chunk")
        ax.legend(loc="lower right", fontsize=9)
        ax.grid(axis="y", alpha=0.3)
        ax.set_ylim(0, intended.max() * 1.12)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def run():
    per_daq, per_rfi_frames = collect()
    totals = add_totals(per_daq)

    summary = {
        "denominator": "MCU frame_num range (fn_end − fn_start + 1) per chunk",
        "numerator": "unique MCU frame_nums with at least one RFI ≥ N buffers",
        "thresholds": THRESHOLDS,
        "trim_seconds_daq1": TRIM_SECONDS_DAQ1,
        "per_chunk": per_daq,
        "totals": totals,
    }
    out_json = f"{OUT_DIR}/survival_rate.json"
    with open(out_json, "w") as f:
        json.dump(summary, f, indent=2)
    out_png = f"{OUT_DIR}/survival_rate.png"
    plot(per_daq, totals, out_png)

    all_rfi = pd.concat(per_rfi_frames, ignore_index=True)
    all_rfi_path = f"{OUT_DIR}/rfi_survival_all.csv"
    all_rfi.to_csv(all_rfi_path, index=False)
    print(f"\nCombined RFI survival table: {all_rfi_path} ({len(all_rfi):,} rows)")

    print(f"\n{'=' * 70}")
    print("Totals (TRIMMED; matches publication_drop_timeline trim):")
    print(f"{'=' * 70}")
    for daq_key, t in totals.items():
        tr = t["trimmed"]
        print(
            f"  {daq_key}: intended {tr['intended']:,} / "
            f"surviving {tr['surviving_ge8']:,}  "
            f"→ survival {tr['survival_rate_ge8_pct']}%  "
            f"loss {tr['loss_rate_ge8_pct']}%"
        )
    print("\nUntrimmed totals:")
    for daq_key, t in totals.items():
        ut = t["untrimmed"]
        print(
            f"  {daq_key}: intended {ut['intended']:,} / "
            f"surviving {ut['surviving_ge8']:,}  "
            f"→ survival {ut['survival_rate_ge8_pct']}%  "
            f"loss {ut['loss_rate_ge8_pct']}%"
        )
    print(f"\nOutput: {out_json}  {out_png}  {all_rfi_path}")


if __name__ == "__main__":
    run()
