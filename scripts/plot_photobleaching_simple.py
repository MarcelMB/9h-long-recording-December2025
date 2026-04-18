#!/usr/bin/env python3
"""
Single-panel photobleaching summary figure.

Simple pipeline: spatial median per frame → 1-min bins → linear fit.
No rolling percentiles or additional smoothing.

Uses pre-computed data from fluorescence_percentiles.npz.

Output:
  output/photobleaching_simple.png
"""

import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE_DIR = "/Users/mbrosch/Documents/9h_long_recording_December2025"
OUTPUT_DIR = os.path.join(BASE_DIR, "output")


def main():
    # --- Load existing data ---
    npz_path = os.path.join(OUTPUT_DIR, "fluorescence_percentiles.npz")
    data = np.load(npz_path)
    time_hours = data["time_hours"]
    trace = data["center_p50"]  # spatial median per 1-min bin, center 50x50
    bin_min = data["center_bin_min"]
    bin_max = data["center_bin_max"]

    # --- Linear fit directly on 1-min binned data ---
    coeffs = np.polyfit(time_hours, trace, 1)
    lin_fit = np.polyval(coeffs, time_hours)
    drift_pct = 100.0 * (lin_fit[-1] - lin_fit[0]) / lin_fit[0]

    # --- Plot ---
    fig, ax = plt.subplots(figsize=(10, 5))

    # Per-bin min/max shading
    ax.fill_between(time_hours, bin_min, bin_max, color="#cccccc", alpha=0.3,
                    label="Per-bin min\u2013max (frame-level)", zorder=0)

    # 1-min binned trace
    ax.plot(time_hours, trace, linewidth=0.8, color="#2c7bb6",
            label="1-min bins (spatial median)", zorder=1)

    # Linear fit
    ax.plot(time_hours, lin_fit, linewidth=2, color="#d7191c", linestyle="--",
            label=f"Linear fit ({drift_pct:+.1f}% over {time_hours[-1]:.1f} h)", zorder=2)

    # Drift annotation
    ax.annotate(
        f"Drift: {drift_pct:+.1f}% ({coeffs[0]:+.2f} AU/hr)",
        xy=(0.98, 0.05), xycoords="axes fraction",
        ha="right", va="bottom", fontsize=10, fontfamily="monospace",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white", edgecolor="#cccccc", alpha=0.8)
    )

    ax.set_xlabel("Time (hours)", fontsize=12)
    ax.set_ylabel("Fluorescence Intensity (8-bit)", fontsize=12)
    ax.set_xlim(0, 8.0)
    ax.set_ylim(0, 255)
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=10, frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # Caption
    caption = (
        "GCaMP6f fluorescence from dCA1 hippocampus recorded with a wireless Miniscope Zero over ~8 hours.\n"
        "Center ROI (50\u00d750 px, rows 75\u2013125, cols 75\u2013125) from 200\u00d7200 frames at 20 fps.\n"
        "Y-axis spans the full 8-bit image sensor range (0\u2013255).\n"
        "\n"
        "Processing: for each frame, the spatial median across 2500 pixels was computed,\n"
        "then averaged into 1-minute bins (~1200 frames per bin). No further smoothing applied.\n"
        "Grey shading: min\u2013max of per-frame spatial medians within each 1-min bin.\n"
        "Red dashed: linear least-squares fit on the 1-min binned trace."
    )
    fig.text(0.02, -0.02, caption, ha="left", va="top", fontsize=8, color="#444444",
             transform=fig.transFigure, fontfamily="sans-serif", style="italic",
             linespacing=1.5)

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.25)

    png_path = os.path.join(OUTPUT_DIR, "photobleaching_simple.png")
    fig.savefig(png_path, dpi=150, bbox_inches="tight")
    print(f"Saved: {png_path}")
    print(f"\nDrift: {drift_pct:+.1f}% ({coeffs[0]:+.2f} AU/hr)")
    print(f"Trace: start={trace[0]:.1f}, end={trace[-1]:.1f}")


if __name__ == "__main__":
    main()
