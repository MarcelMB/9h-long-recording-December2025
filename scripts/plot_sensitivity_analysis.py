#!/usr/bin/env python3
"""
Parameter sensitivity analysis for fluorescence baseline/event estimation.

Varies one parameter at a time while holding others at default,
and shows how baseline drift and Ca2+ event drift change.

Parameters tested:
  1. Spatial statistic: median vs mean
  2. Bin size: 15s, 30s, 1min, 2min, 5min
  3. Rolling window: 10, 20, 30, 45, 60 min
  4. Percentile: 5/95, 10/90, 15/85, 20/80, 25/75

Uses per-frame data from perframe_center_median.npz (no video reprocessing).

Output:
  output/sensitivity_analysis.png
"""

import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE_DIR = "/Users/mbrosch/Documents/9h_long_recording_December2025"
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

FPS = 20.0

# Defaults
DEFAULT_BIN_SEC = 60
DEFAULT_WINDOW_MIN = 30
DEFAULT_PCT_LO = 10
DEFAULT_PCT_HI = 90


def bin_data(perframe, bin_frames):
    """Bin per-frame data into fixed-size bins (mean within each bin)."""
    n = len(perframe) // bin_frames * bin_frames
    return perframe[:n].reshape(-1, bin_frames).mean(axis=1)


def rolling_percentile(data, window, pct):
    """Rolling percentile with edge-aware symmetric window."""
    half = window // 2
    out = np.empty(len(data))
    for i in range(len(data)):
        lo = max(0, i - half)
        hi = min(len(data), i + half + 1)
        out[i] = np.percentile(data[lo:hi], pct)
    return out


def compute_drift(perframe, bin_sec, window_min, pct_lo, pct_hi):
    """Compute baseline and event drift for a given parameter set."""
    bin_frames = int(FPS * bin_sec)
    binned = bin_data(perframe, bin_frames)
    bins_per_min = 60 / bin_sec
    window_bins = int(window_min * bins_per_min)
    if window_bins < 3:
        window_bins = 3

    time_hours = np.arange(len(binned)) * bin_sec / 3600.0

    baseline = rolling_percentile(binned, window_bins, pct_lo)
    events = rolling_percentile(binned, window_bins, pct_hi)

    # Linear fits
    c_bl = np.polyfit(time_hours, baseline, 1)
    l_bl = np.polyval(c_bl, time_hours)
    drift_bl = 100.0 * (l_bl[-1] - l_bl[0]) / l_bl[0]

    c_ev = np.polyfit(time_hours, events, 1)
    l_ev = np.polyval(c_ev, time_hours)
    drift_ev = 100.0 * (l_ev[-1] - l_ev[0]) / l_ev[0]

    return drift_bl, drift_ev


def main():
    # Load per-frame data
    data = np.load(os.path.join(OUTPUT_DIR, "perframe_center_median.npz"))
    pf_median = data["median"]
    pf_mean = data["mean"]

    # --- 1. Spatial stat: median vs mean ---
    stat_labels = ["Median", "Mean"]
    stat_bl = []
    stat_ev = []
    for pf in [pf_median, pf_mean]:
        bl, ev = compute_drift(pf, DEFAULT_BIN_SEC, DEFAULT_WINDOW_MIN,
                               DEFAULT_PCT_LO, DEFAULT_PCT_HI)
        stat_bl.append(bl)
        stat_ev.append(ev)

    # --- 2. Bin size ---
    bin_sizes = [15, 30, 60, 120, 300]  # seconds
    bin_labels = ["15s", "30s", "1min", "2min", "5min"]
    bin_bl = []
    bin_ev = []
    for bs in bin_sizes:
        bl, ev = compute_drift(pf_median, bs, DEFAULT_WINDOW_MIN,
                               DEFAULT_PCT_LO, DEFAULT_PCT_HI)
        bin_bl.append(bl)
        bin_ev.append(ev)

    # --- 3. Rolling window ---
    windows = [10, 20, 30, 45, 60]  # minutes
    win_labels = [f"{w}min" for w in windows]
    win_bl = []
    win_ev = []
    for w in windows:
        bl, ev = compute_drift(pf_median, DEFAULT_BIN_SEC, w,
                               DEFAULT_PCT_LO, DEFAULT_PCT_HI)
        win_bl.append(bl)
        win_ev.append(ev)

    # --- 4. Percentile ---
    pct_pairs = [(5, 95), (10, 90), (15, 85), (20, 80), (25, 75)]
    pct_labels = [f"{lo}/{hi}" for lo, hi in pct_pairs]
    pct_bl = []
    pct_ev = []
    for lo, hi in pct_pairs:
        bl, ev = compute_drift(pf_median, DEFAULT_BIN_SEC, DEFAULT_WINDOW_MIN,
                               lo, hi)
        pct_bl.append(bl)
        pct_ev.append(ev)

    # --- Plot: 2x2 grid ---
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))

    datasets = [
        (axes[0, 0], "Spatial statistic", stat_labels, stat_bl, stat_ev,
         f"bin={DEFAULT_BIN_SEC}s, window={DEFAULT_WINDOW_MIN}min, pct={DEFAULT_PCT_LO}/{DEFAULT_PCT_HI}"),
        (axes[0, 1], "Bin size", bin_labels, bin_bl, bin_ev,
         f"spatial=median, window={DEFAULT_WINDOW_MIN}min, pct={DEFAULT_PCT_LO}/{DEFAULT_PCT_HI}"),
        (axes[1, 0], "Rolling window", win_labels, win_bl, win_ev,
         f"spatial=median, bin={DEFAULT_BIN_SEC}s, pct={DEFAULT_PCT_LO}/{DEFAULT_PCT_HI}"),
        (axes[1, 1], "Percentile (lo/hi)", pct_labels, pct_bl, pct_ev,
         f"spatial=median, bin={DEFAULT_BIN_SEC}s, window={DEFAULT_WINDOW_MIN}min"),
    ]

    for ax, title, labels, bl_vals, ev_vals, subtitle in datasets:
        x = np.arange(len(labels))
        w = 0.35
        bars_bl = ax.bar(x - w/2, bl_vals, w, color="#2c7bb6", label="Baseline drift")
        bars_ev = ax.bar(x + w/2, ev_vals, w, color="#d7191c", label="Event drift")

        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.set_xlabel(subtitle, fontsize=8, color="#666666")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=9)
        ax.set_ylabel("Drift over 8h (%)", fontsize=10)
        ax.axhline(0, color="black", linewidth=0.5)
        ax.legend(fontsize=8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        # Value labels on bars
        for bar in list(bars_bl) + list(bars_ev):
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2, h,
                    f"{h:+.1f}%", ha="center", va="bottom" if h >= 0 else "top",
                    fontsize=7)

    fig.suptitle("Sensitivity analysis: how processing parameters affect drift estimates",
                 fontsize=13, fontweight="bold")
    fig.tight_layout()

    out_path = os.path.join(OUTPUT_DIR, "sensitivity_analysis.png")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"Saved: {out_path}")

    # Print summary
    print("\n--- Summary ---")
    print(f"Spatial stat:   BL = {stat_bl}, EV = {stat_ev}")
    print(f"Bin size:       BL = {[f'{v:+.1f}' for v in bin_bl]}")
    print(f"                EV = {[f'{v:+.1f}' for v in bin_ev]}")
    print(f"Window:         BL = {[f'{v:+.1f}' for v in win_bl]}")
    print(f"                EV = {[f'{v:+.1f}' for v in win_ev]}")
    print(f"Percentile:     BL = {[f'{v:+.1f}' for v in pct_bl]}")
    print(f"                EV = {[f'{v:+.1f}' for v in pct_ev]}")


if __name__ == "__main__":
    main()
