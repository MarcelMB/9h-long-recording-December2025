#!/usr/bin/env python3
"""
Two-panel photobleaching summary figure with rolling percentile baselines.

Pipeline: spatial median per frame → 1-min bins → rolling 10th/90th temporal
percentile (30-min window) → 15-min moving average → linear fits.

Uses pre-computed data from fluorescence_percentiles.npz.

Output:
  output/photobleaching_summary.png
"""

import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE_DIR = "/Users/mbrosch/Documents/9h_long_recording_December2025"
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

ROLLING_WINDOW = 30        # minutes


def rolling_percentile(data, window, pct):
    """Rolling percentile with symmetric window, edge-aware."""
    half_win = window // 2
    return np.array([
        np.percentile(data[max(0, i - half_win):i + half_win + 1], pct)
        for i in range(len(data))
    ])


def smooth_ma(data, window=15):
    """Moving average with edge-aware (shrinking) window."""
    half = window // 2
    out = np.empty_like(data)
    for i in range(len(data)):
        lo = max(0, i - half)
        hi = min(len(data), i + half + 1)
        out[i] = np.mean(data[lo:hi])
    return out


def main():
    # --- Load existing data ---
    npz_path = os.path.join(OUTPUT_DIR, "fluorescence_percentiles.npz")
    data = np.load(npz_path)
    time_hours = data["time_hours"]
    trace = data["center_p50"]  # spatial median per 1-min bin, center 50x50

    # --- Rolling baselines (30-min window) ---
    # Smooth rolling percentiles with 15-min moving average to remove staircase artifacts
    baseline = smooth_ma(rolling_percentile(trace, ROLLING_WINDOW, 10))
    baseline_lo = smooth_ma(rolling_percentile(trace, ROLLING_WINDOW, 5))
    baseline_hi = smooth_ma(rolling_percentile(trace, ROLLING_WINDOW, 15))

    events = smooth_ma(rolling_percentile(trace, ROLLING_WINDOW, 90))
    events_lo = smooth_ma(rolling_percentile(trace, ROLLING_WINDOW, 85))
    events_hi = smooth_ma(rolling_percentile(trace, ROLLING_WINDOW, 95))

    # Per-bin min/max (frame-level variability)
    bin_min = data["center_bin_min"]
    bin_max = data["center_bin_max"]

    # --- Linear fits on baseline and event floor ---
    coeffs_bl = np.polyfit(time_hours, baseline, 1)
    lin_bl = np.polyval(coeffs_bl, time_hours)
    drift_bl = 100.0 * (lin_bl[-1] - lin_bl[0]) / lin_bl[0]

    coeffs_ev = np.polyfit(time_hours, events, 1)
    lin_ev = np.polyval(coeffs_ev, time_hours)
    drift_ev = 100.0 * (lin_ev[-1] - lin_ev[0]) / lin_ev[0]

    # --- Plot: two panels ---
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

    for ax, line, lo, hi, lin_fit, color, label, band_label, drift, coeffs in [
        (ax1, baseline, baseline_lo, baseline_hi, lin_bl, "#2c7bb6",
         "Baseline fluor. (rolling 10th pct)", "5th\u201315th pct range", drift_bl, coeffs_bl),
        (ax2, events, events_lo, events_hi, lin_ev, "#d7191c",
         "Ca\u00b2\u207a event fluor. (rolling 90th pct)", "85th\u201395th pct range", drift_ev, coeffs_ev),
    ]:
        # Per-bin min/max shading (outer, frame-level)
        ax.fill_between(time_hours, bin_min, bin_max, color="#cccccc", alpha=0.25,
                        label="Per-bin min\u2013max (frame-level)", zorder=0)

        # Percentile band shading (inner, around the line)
        ax.fill_between(time_hours, lo, hi, color=color, alpha=0.2,
                        label=band_label, zorder=1)

        # Main line
        ax.plot(time_hours, line, linewidth=1.8, color=color, label=label, zorder=2)

        # Linear fit
        ax.plot(time_hours, lin_fit, linewidth=1.5, color=color, linestyle="--",
                label=f"Linear fit ({drift:+.1f}%)", zorder=3)

        # Drift annotation
        ax.annotate(
            f"Drift: {drift:+.1f}% ({coeffs[0]:+.2f} AU/hr)",
            xy=(0.98, 0.05), xycoords="axes fraction",
            ha="right", va="bottom", fontsize=9, fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="white", edgecolor="#cccccc", alpha=0.8)
        )

        ax.set_ylabel("Fluorescence Intensity (8-bit)", fontsize=11)
        ax.set_ylim(0, 255)
        ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=9, frameon=False)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    ax2.set_xlabel("Time (hours)", fontsize=12)
    ax1.set_xlim(0, 8.0)

    # Caption
    caption = (
        "GCaMP6f fluorescence from dCA1 hippocampus recorded with a wireless Miniscope Zero over ~8 hours.\n"
        "Center ROI (50\u00d750 px, rows 75\u2013125, cols 75\u2013125) from 200\u00d7200 frames at 20 fps.\n"
        "Y-axis spans the full 8-bit image sensor range (0\u2013255).\n"
        "\n"
        "For each frame, the spatial median pixel intensity across the 2500-pixel ROI was computed,\n"
        "then averaged into 1-minute bins (~1200 frames per bin). Because the spatial median aggregates\n"
        "many pixels, individual cell transients are averaged out and the dynamic range between baseline\n"
        "and Ca\u00b2\u207a events is smaller than for single-cell traces.\n"
        "\n"
        "Blue: rolling 10th temporal percentile (30-min window), baseline fluorescence (F0).\n"
        "Red: rolling 90th temporal percentile, Ca\u00b2\u207a event fluorescence.\n"
        "GCaMP calcium transients are one-sided (only positive deflections from baseline), so the 10th\n"
        "percentile tracks the resting fluorescence unbiased by neural activity, while the 90th percentile\n"
        "captures bins with elevated activity.\n"
        "Dashed lines: linear fits on baseline and event floor.\n"
        "\n"
        "Baseline fluorescence is stable (\u22120.5% over 8 h), indicating no detectable photobleaching.\n"
        "The +6% upward drift in the Ca\u00b2\u207a event floor may reflect artifacts from the wireless system\n"
        "(e.g. thermal effects on the image sensor) rather than a change in neural activity, but this remains unclear."
    )
    fig.text(0.02, -0.02, caption, ha="left", va="top", fontsize=7.5, color="#444444",
             transform=fig.transFigure, fontfamily="sans-serif", style="italic",
             linespacing=1.6)

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.30)

    png_path = os.path.join(OUTPUT_DIR, "photobleaching_summary.png")
    fig.savefig(png_path, dpi=150, bbox_inches="tight")
    print(f"Saved: {png_path}")
    gap = events.mean() - baseline.mean()
    print(f"\nBaseline:  drift={drift_bl:+.1f}% ({coeffs_bl[0]:+.2f} AU/hr)")
    print(f"Ca2+ events: drift={drift_ev:+.1f}% ({coeffs_ev[0]:+.2f} AU/hr)")
    print(f"Baseline (10th pct): start={baseline[0]:.1f}, end={baseline[-1]:.1f}")
    print(f"Events (90th pct):   start={events[0]:.1f}, end={events[-1]:.1f}")
    print(f"Gap: {gap:.1f} AU average")


if __name__ == "__main__":
    main()
