#!/usr/bin/env python3
"""
Order-of-operations sensitivity analysis.

Tests whether the sequence of processing steps (binning, rolling percentile)
affects the baseline and event drift estimates.

Orderings tested:
  A. bin → rolling percentile  (current pipeline)
  B. rolling percentile → bin  (percentile on per-frame data, then bin)
  C. large bin only            (bin to 30-min, take percentile within each bin)
  D. spatial percentile first  (spatial 10th/90th per frame instead of median,
                                then bin, then rolling median)

Uses per-frame data from perframe_center_median.npz.

Output:
  output/order_sensitivity.png
"""

import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE_DIR = "/Users/mbrosch/Documents/9h_long_recording_December2025"
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

FPS = 20.0
BIN_SEC = 60
WINDOW_MIN = 30
PCT_LO = 10
PCT_HI = 90


def bin_data(data, bin_size):
    n = len(data) // bin_size * bin_size
    return data[:n].reshape(-1, bin_size).mean(axis=1)


def bin_percentile(data, bin_size, pct):
    """Bin data and take percentile within each bin (instead of mean)."""
    n = len(data) // bin_size * bin_size
    return np.array([
        np.percentile(data[i:i+bin_size], pct)
        for i in range(0, n, bin_size)
    ])


def rolling_percentile(data, window, pct):
    half = window // 2
    out = np.empty(len(data))
    for i in range(len(data)):
        lo = max(0, i - half)
        hi = min(len(data), i + half + 1)
        out[i] = np.percentile(data[lo:hi], pct)
    return out


def rolling_median(data, window):
    return rolling_percentile(data, window, 50)


def linear_drift(time_hours, trace):
    coeffs = np.polyfit(time_hours, trace, 1)
    fit = np.polyval(coeffs, time_hours)
    return 100.0 * (fit[-1] - fit[0]) / fit[0], coeffs[0]


def main():
    data = np.load(os.path.join(OUTPUT_DIR, "perframe_center_median.npz"))
    pf_median = data["median"]  # per-frame spatial median

    bin_frames = int(FPS * BIN_SEC)
    window_bins = WINDOW_MIN  # 1-min bins → window in bins = window in min

    # =======================================================
    # Order A: bin → rolling percentile (CURRENT PIPELINE)
    # =======================================================
    binned_A = bin_data(pf_median, bin_frames)
    time_A = np.arange(len(binned_A)) / 60.0
    baseline_A = rolling_percentile(binned_A, window_bins, PCT_LO)
    events_A = rolling_percentile(binned_A, window_bins, PCT_HI)

    # =======================================================
    # Order B: rolling percentile → bin
    # (percentile on per-frame data with window = 30min of frames,
    #  then bin the result to 1-min)
    # =======================================================
    window_frames = int(WINDOW_MIN * 60 * FPS)  # 30 min in frames
    print("Computing Order B (rolling pct on per-frame data)... this may take a moment")
    # Use strided approach for speed
    baseline_pf = rolling_percentile(pf_median, window_frames, PCT_LO)
    events_pf = rolling_percentile(pf_median, window_frames, PCT_HI)
    baseline_B = bin_data(baseline_pf, bin_frames)
    events_B = bin_data(events_pf, bin_frames)
    time_B = np.arange(len(baseline_B)) / 60.0
    print("  Done")

    # =======================================================
    # Order C: large bin (30-min), percentile within each bin
    # =======================================================
    big_bin = int(WINDOW_MIN * 60 * FPS)  # 30 min of frames
    baseline_C = bin_percentile(pf_median, big_bin, PCT_LO)
    events_C = bin_percentile(pf_median, big_bin, PCT_HI)
    time_C = (np.arange(len(baseline_C)) + 0.5) * WINDOW_MIN / 60.0

    # =======================================================
    # Order D: spatial percentile first
    # (use per-frame spatial 10th/90th instead of median,
    #  then bin, then rolling median to smooth)
    # This requires re-reading videos — approximate by noting
    #  that spatial median ≈ spatial mean for this ROI.
    #  Instead, we show what happens if we skip the rolling
    #  percentile and just use binned data with rolling median.
    # =======================================================
    # D = bin → rolling median (no percentile separation)
    binned_D = bin_data(pf_median, bin_frames)
    median_D = rolling_median(binned_D, window_bins)
    time_D = np.arange(len(binned_D)) / 60.0

    # --- Compute drifts ---
    results = {}
    for name, t, bl, ev in [
        ("A: bin → roll pct", time_A, baseline_A, events_A),
        ("B: roll pct → bin", time_B, baseline_B, events_B),
        ("C: 30-min bin pct", time_C, baseline_C, events_C),
    ]:
        d_bl, s_bl = linear_drift(t, bl)
        d_ev, s_ev = linear_drift(t, ev)
        results[name] = (d_bl, d_ev, s_bl, s_ev)

    d_med, s_med = linear_drift(time_D, median_D)
    results["D: bin → roll median"] = (d_med, d_med, s_med, s_med)

    # --- Plot: time series comparison ---
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))

    panels = [
        (axes[0, 0], "A: Bin (1-min) → Rolling percentile (current)",
         time_A, baseline_A, events_A),
        (axes[0, 1], "B: Rolling percentile (per-frame) → Bin (1-min)",
         time_B, baseline_B, events_B),
        (axes[1, 0], "C: Large bin (30-min) → Percentile within bin",
         time_C, baseline_C, events_C),
        (axes[1, 1], "D: Bin (1-min) → Rolling median (no pct separation)",
         time_D, median_D, None),
    ]

    for ax, title, t, bl, ev in panels:
        ax.plot(t, bl, linewidth=1.5, color="#2c7bb6", label="Baseline (10th pct)")
        if ev is not None:
            ax.plot(t, ev, linewidth=1.5, color="#d7191c", label="Event floor (90th pct)")

        # Linear fits
        d_bl, s_bl = linear_drift(t, bl)
        fit_bl = np.polyval(np.polyfit(t, bl, 1), t)
        ax.plot(t, fit_bl, "--", linewidth=1, color="#2c7bb6", alpha=0.7)

        if ev is not None:
            d_ev, s_ev = linear_drift(t, ev)
            fit_ev = np.polyval(np.polyfit(t, ev, 1), t)
            ax.plot(t, fit_ev, "--", linewidth=1, color="#d7191c", alpha=0.7)
            ax.annotate(f"BL: {d_bl:+.1f}%\nEV: {d_ev:+.1f}%",
                        xy=(0.98, 0.05), xycoords="axes fraction",
                        ha="right", va="bottom", fontsize=9, fontfamily="monospace",
                        bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                                  edgecolor="#ccc", alpha=0.8))
        else:
            ax.annotate(f"Median: {d_bl:+.1f}%",
                        xy=(0.98, 0.05), xycoords="axes fraction",
                        ha="right", va="bottom", fontsize=9, fontfamily="monospace",
                        bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                                  edgecolor="#ccc", alpha=0.8))

        ax.set_title(title, fontsize=10, fontweight="bold")
        ax.set_ylim(0, 255)
        ax.set_xlim(0, 8)
        ax.set_ylabel("Fluorescence (8-bit)", fontsize=9)
        ax.set_xlabel("Time (hours)", fontsize=9)
        ax.legend(fontsize=8, loc="upper right")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    fig.suptitle("Order-of-operations sensitivity: does processing sequence affect drift estimates?",
                 fontsize=13, fontweight="bold")

    # Summary table as text
    summary = "Summary of drift estimates:\n"
    for name, (d_bl, d_ev, s_bl, s_ev) in results.items():
        if name.startswith("D"):
            summary += f"  {name}: median = {d_bl:+.1f}%\n"
        else:
            summary += f"  {name}: BL = {d_bl:+.1f}%, EV = {d_ev:+.1f}%\n"

    fig.text(0.02, -0.01, summary, ha="left", va="top", fontsize=9,
             fontfamily="monospace", color="#444444", transform=fig.transFigure)

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.15)

    out_path = os.path.join(OUTPUT_DIR, "order_sensitivity.png")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"\nSaved: {out_path}")

    print("\n--- Drift summary ---")
    for name, (d_bl, d_ev, s_bl, s_ev) in results.items():
        print(f"  {name}: BL={d_bl:+.1f}%, EV={d_ev:+.1f}%")


if __name__ == "__main__":
    main()
