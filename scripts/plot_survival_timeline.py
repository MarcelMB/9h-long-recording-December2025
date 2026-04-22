#!/usr/bin/env python3
"""Timeline of lost MCU frames — DAQ1 alone, DAQ2 alone, Dual-DAQ stitched.

Same visual design as scripts/plot_drop_timeline.py (horizontal strips + bar
sidebar). Uses the survival metric instead of the AVI broken-frame detector,
so a single MCU frame counts once regardless of bit-flip amplification.

Inputs:
  output/survival_rate.json            — per-DAQ trimmed totals + per-chunk
  output/WL27_stitched_survival.csv    — stitched-track survival
  neural_DAQ{1,2}/*.csv                — for per-RFI timestamps (min arrival)

Timeline marks (one mark per row):
  DAQ1:     RFIs whose MCU fn_mode is in the lost set for that DAQ1 chunk
  DAQ2:     same, DAQ2
  Stitched: stitched frames where the picked source didn't survive (MCU-level)

Outputs:
  output/publication_survival_timeline.png / .pdf
  output/publication_survival_bar.png / .pdf    — old vs new metric side by side
"""

import glob
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import analyze_frame_num_drops as afd

BASE = "/Users/mbrosch/Documents/9h_long_recording_December2025"
DAQ1_DIR = f"{BASE}/neural_DAQ1"
DAQ2_DIR = f"{BASE}/neural_DAQ2"
OUT_DIR = f"{BASE}/output"

TRIM_SECONDS_DAQ1 = {"long-2": 30, "long-9": 155}
FPS = 20.0

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 10,
    "axes.linewidth": 0.8,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "xtick.major.width": 0.8,
    "ytick.major.width": 0.8,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.15,
})

C_DAQ1 = "#D55E00"
C_DAQ2 = "#0072B2"
C_COMBINED = "#009E73"


def _lost_rfi_timestamps(csv_path, daq, label, t_ref=None):
    """Return (unix_times_of_lost_rfis, t0_of_chunk).

    "Lost" here = the RFI's majority frame_num (fn_mode) is NOT in the
    chunk's surviving-MCU-frame set. One timestamp per such RFI. DAQ1 chunks
    in TRIM_SECONDS_DAQ1 have their trimmed tail dropped.
    """
    df = pd.read_csv(
        csv_path,
        usecols=["frame_num", "reconstructed_frame_index", "buffer_recv_unix_time"],
    )

    fn_start, fn_end, _, _ = afd.pick_start_end(df["frame_num"])
    if fn_start is None:
        return np.array([]), None

    mask = afd.valid_mask(df["frame_num"])
    per_rfi = df[mask].groupby("reconstructed_frame_index").agg(
        n_buffers=("frame_num", "size"),
        fn_mode=("frame_num", lambda s: s.mode().iat[0] if len(s) else -1),
        ts=("buffer_recv_unix_time", "min"),
    )
    per_rfi = per_rfi.sort_index()

    # Surviving fn_modes (any RFI with >=8 buffers whose fn_mode is in range)
    in_range = (per_rfi["fn_mode"] >= fn_start) & (per_rfi["fn_mode"] <= fn_end)
    surviving_fn = set(per_rfi.loc[(per_rfi["n_buffers"] >= 8) & in_range, "fn_mode"].unique())

    # Apply tail trim for DAQ1
    trim_frames = int(TRIM_SECONDS_DAQ1.get(label, 0) * FPS) if daq == 1 else 0
    if trim_frames > 0 and len(per_rfi) > trim_frames:
        per_rfi = per_rfi.iloc[:-trim_frames]

    # Lost = RFIs whose fn_mode is in range but NOT in the surviving set.
    # Collapse to one mark per lost fn_mode (use the first RFI's timestamp).
    lost = per_rfi[(per_rfi["fn_mode"] >= fn_start) &
                   (per_rfi["fn_mode"] <= fn_end) &
                   (~per_rfi["fn_mode"].isin(surviving_fn))]
    if len(lost) == 0:
        times = np.array([])
    else:
        times = lost.groupby("fn_mode")["ts"].min().values

    t0 = float(per_rfi["ts"].min())
    return times, t0


def gather_timestamps():
    """Compute DAQ1, DAQ2, stitched lost-frame unix_times and the global t0."""
    print("Gathering DAQ1 lost MCU-frame timestamps...")
    daq1_times = []
    daq1_t0 = None
    for seg in dict.fromkeys(p[0] for p in afd.PAIRS):
        csv = afd.find_csv(DAQ1_DIR, seg)
        if csv is None:
            continue
        t, t0 = _lost_rfi_timestamps(csv, daq=1, label=seg)
        daq1_times.append(t)
        daq1_t0 = t0 if daq1_t0 is None else min(daq1_t0, t0)
        print(f"  DAQ1 {seg}: {len(t):,} lost MCU frames")
    daq1_times = np.concatenate(daq1_times) if daq1_times else np.array([])

    print("Gathering DAQ2 lost MCU-frame timestamps...")
    daq2_times = []
    daq2_t0 = None
    for seg in dict.fromkeys(p[1] for p in afd.PAIRS):
        csv = afd.find_csv(DAQ2_DIR, seg)
        if csv is None:
            continue
        t, t0 = _lost_rfi_timestamps(csv, daq=2, label=seg)
        daq2_times.append(t)
        daq2_t0 = t0 if daq2_t0 is None else min(daq2_t0, t0)
        print(f"  DAQ2 {seg}: {len(t):,} lost MCU frames")
    daq2_times = np.concatenate(daq2_times) if daq2_times else np.array([])

    print("Gathering stitched lost-frame timestamps...")
    st = pd.read_csv(f"{OUT_DIR}/WL27_stitched_survival.csv")
    st_known = st[st["picked_in_table"]]
    st_lost = st_known[~st_known["stitched_mcu_ge8"]]
    stitched_times = st_lost["unix_time"].values
    print(f"  stitched analyzable rows: {len(st_known):,}  lost: {len(stitched_times):,}")

    t0_global = min(
        daq1_t0 if daq1_t0 is not None else float("inf"),
        daq2_t0 if daq2_t0 is not None else float("inf"),
        float(st["unix_time"].min()),
    )
    return daq1_times, daq2_times, stitched_times, t0_global


def load_survival_json():
    with open(f"{OUT_DIR}/survival_rate.json") as f:
        return json.load(f)


def load_stitched_json():
    with open(f"{OUT_DIR}/survival_rate_stitched.json") as f:
        return json.load(f)


def plot_timeline(daq1_h, daq2_h, stitched_h, daq1_pct, daq2_pct, stitched_pct,
                  daq1_n, daq2_n, stitched_n, out_path_png, out_path_pdf):
    fig = plt.figure(figsize=(10, 4.5))
    gs = fig.add_gridspec(3, 2, width_ratios=[4, 1.5], wspace=0.15, hspace=0.4)

    datasets = [
        (0, daq1_h, C_DAQ1, "DAQ 1 alone", daq1_pct, daq1_n),
        (1, daq2_h, C_DAQ2, "DAQ 2 alone", daq2_pct, daq2_n),
        (2, stitched_h, C_COMBINED, "Dual-DAQ stitched", stitched_pct, stitched_n),
    ]

    ax_t_first = None
    ax_b_first = None

    x_max_bar = max(daq1_pct, daq2_pct, stitched_pct, 0.5) * 1.35

    for row, drops_h, color, label, pct, n_official in datasets:
        if ax_t_first is None:
            ax_t = fig.add_subplot(gs[row, 0])
            ax_t_first = ax_t
        else:
            ax_t = fig.add_subplot(gs[row, 0], sharex=ax_t_first)

        if ax_b_first is None:
            ax_b = fig.add_subplot(gs[row, 1])
            ax_b_first = ax_b
        else:
            ax_b = fig.add_subplot(gs[row, 1], sharex=ax_b_first)

        ax_t.axhspan(0, 1, color="#F5F5F5", zorder=0)
        for t in drops_h:
            ax_t.plot([t, t], [0, 1], color=color, lw=0.01, alpha=0.9, zorder=2)

        ax_t.set_xlim(-0.2, 9.2)
        ax_t.set_ylim(-0.05, 1.05)
        ax_t.set_yticks([])
        ax_t.spines["left"].set_visible(False)
        ax_t.spines["right"].set_visible(False)
        ax_t.spines["top"].set_visible(False)
        ax_t.set_ylabel(label, fontsize=9, rotation=0, ha="right", va="center", labelpad=10)

        if row < 2:
            ax_t.tick_params(axis="x", labelbottom=False)
        else:
            ax_t.set_xlabel("Recording time (hours)", fontsize=10)
            ax_t.xaxis.set_major_locator(mtick.MultipleLocator(1))
            ax_t.xaxis.set_minor_locator(mtick.MultipleLocator(0.5))

        ax_b.barh([0], [pct], height=0.55, color=color, edgecolor="white", linewidth=0.5)
        ax_b.text(pct + 0.02 * x_max_bar, 0, f"{pct:.2f}%",
                  ha="left", va="center", fontsize=9, fontweight="bold")
        secs = n_official / FPS
        mins = int(secs // 60)
        remaining_secs = secs - mins * 60
        sec_label = f"{mins} min {remaining_secs:.0f} s of ~9 h"
        ax_b.text(pct + 0.02 * x_max_bar, -0.25, sec_label,
                  ha="left", va="top", fontsize=7, color="0.4")

        ax_b.set_yticks([])
        ax_b.set_ylim(-0.5, 0.5)
        ax_b.set_xlim(0, x_max_bar)
        ax_b.spines["left"].set_visible(False)
        ax_b.spines["right"].set_visible(False)
        ax_b.spines["top"].set_visible(False)

        if row < 2:
            ax_b.tick_params(axis="x", labelbottom=False)
        else:
            ax_b.set_xlabel("Lost MCU frames (%)", fontsize=9)
            step = 1 if x_max_bar > 4 else 0.5
            ax_b.xaxis.set_major_locator(mtick.MultipleLocator(step))
            ax_b.xaxis.set_minor_locator(mtick.MultipleLocator(step / 2))

    fig.savefig(out_path_png)
    fig.savefig(out_path_pdf)
    plt.close(fig)


def plot_bar_compare(old_pcts, new_pcts, labels, out_path_png, out_path_pdf):
    """Side-by-side bars: old AVI-broken vs new MCU-survival loss rates."""
    fig, ax = plt.subplots(figsize=(7, 4))
    x = np.arange(len(labels))
    width = 0.38

    bars_old = ax.bar(x - width / 2, old_pcts, width, color="#CCCCCC",
                      edgecolor="white", label="Old (AVI broken-frame detector)")
    bars_new = ax.bar(x + width / 2, new_pcts, width,
                      color=[C_DAQ1, C_DAQ2, C_COMBINED],
                      edgecolor="white", label="New (MCU survival, all 8 buffers)")

    for bar, v in zip(bars_old, old_pcts):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 0.1,
                f"{v:.2f}%", ha="center", va="bottom", fontsize=9, color="0.3")
    for bar, v in zip(bars_new, new_pcts):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 0.1,
                f"{v:.2f}%", ha="center", va="bottom", fontsize=9, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Frame loss rate (%)")
    ax.set_title("Frame loss: AVI-broken (old) vs MCU-survival (new)\n"
                 "Old metric double-counts the mio bit-flip amplification")
    ax.legend(loc="upper right", fontsize=9, frameon=False)
    ax.grid(axis="y", alpha=0.3)
    ax.set_ylim(0, max(max(old_pcts), max(new_pcts)) * 1.25)

    fig.tight_layout()
    fig.savefig(out_path_png)
    fig.savefig(out_path_pdf)
    plt.close(fig)


def run():
    daq1_times, daq2_times, stitched_times, t0_global = gather_timestamps()

    daq1_h = (daq1_times - t0_global) / 3600.0 if len(daq1_times) else daq1_times
    daq2_h = (daq2_times - t0_global) / 3600.0 if len(daq2_times) else daq2_times
    stitched_h = (stitched_times - t0_global) / 3600.0 if len(stitched_times) else stitched_times

    surv = load_survival_json()
    stitched_summary = load_stitched_json()

    daq1_pct = surv["totals"]["DAQ1"]["trimmed"]["loss_rate_ge8_pct"]
    daq2_pct = surv["totals"]["DAQ2"]["trimmed"]["loss_rate_ge8_pct"]
    stitched_pct = stitched_summary["all"]["stitched_loss_pct_mcu_ge8"]

    daq1_n = surv["totals"]["DAQ1"]["trimmed"]["lost_ge8"]
    daq2_n = surv["totals"]["DAQ2"]["trimmed"]["lost_ge8"]
    stitched_n = stitched_summary["all"]["stitched_lost_mcu_ge8"]

    print(f"\nHeadline trimmed loss rates (≥8-buffer survival):")
    print(f"  DAQ1 alone:        {daq1_pct}%  ({daq1_n:,} lost)")
    print(f"  DAQ2 alone:        {daq2_pct}%  ({daq2_n:,} lost)")
    print(f"  Dual-DAQ stitched: {stitched_pct}%  ({stitched_n:,} lost)")

    plot_timeline(
        daq1_h, daq2_h, stitched_h,
        daq1_pct, daq2_pct, stitched_pct,
        daq1_n, daq2_n, stitched_n,
        f"{OUT_DIR}/publication_survival_timeline.png",
        f"{OUT_DIR}/publication_survival_timeline.pdf",
    )
    print(f"\nSaved: publication_survival_timeline.png/.pdf")

    # Old-metric numbers from plot_drop_timeline.py hardcodes + the 0.20%
    # stitched rate. These are the publication numbers being superseded.
    old_daq1 = 5.33
    old_daq2 = 0.75
    old_stitched = 0.20
    plot_bar_compare(
        old_pcts=[old_daq1, old_daq2, old_stitched],
        new_pcts=[daq1_pct, daq2_pct, stitched_pct],
        labels=["DAQ 1 alone", "DAQ 2 alone", "Dual-DAQ stitched"],
        out_path_png=f"{OUT_DIR}/publication_survival_bar.png",
        out_path_pdf=f"{OUT_DIR}/publication_survival_bar.pdf",
    )
    print("Saved: publication_survival_bar.png/.pdf")


if __name__ == "__main__":
    run()
