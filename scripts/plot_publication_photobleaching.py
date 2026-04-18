#!/usr/bin/env python3
"""
Publication-quality photobleaching figure.

Linear fit on all 561k per-frame spatial medians, with tight axis limits,
clean typography, and minimal clutter.

Output:
  output/publication_photobleaching_perframe.png
  output/publication_photobleaching_perframe.pdf
"""

import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

BASE_DIR = "/Users/mbrosch/Documents/9h_long_recording_December2025"
OUTPUT_DIR = os.path.join(BASE_DIR, "output")


def main():
    # --- Load per-frame data ---
    data = np.load(os.path.join(OUTPUT_DIR, "perframe_center_median.npz"))
    median = data["median"].astype(np.float64)
    fps = float(data["fps"])
    n_frames = len(median)
    time_hours = np.arange(n_frames) / fps / 3600.0

    # --- Linear fit ---
    coeffs = np.polyfit(time_hours, median, 1)
    lin_fit = np.polyval(coeffs, time_hours)
    drift_pct = 100.0 * (lin_fit[-1] - lin_fit[0]) / lin_fit[0]

    # --- Figure ---
    fig, ax = plt.subplots(figsize=(7, 3.5))

    # Downsample for plotting (every 20th frame = 1/s)
    ds = 20
    ax.plot(time_hours[::ds], median[::ds], linewidth=0.12, color="#999999",
            alpha=0.6, rasterized=True, zorder=0)

    # Linear fit
    ax.plot(time_hours[[0, -1]], lin_fit[[0, -1]], linewidth=1.8,
            color="#c0392b", zorder=2)

    # Drift annotation — compact, inside plot
    ax.text(0.97, 0.06,
            f"slope = {coeffs[0]:+.2f} AU h$^{{-1}}$ ({drift_pct:+.1f}%)",
            transform=ax.transAxes, ha="right", va="bottom",
            fontsize=8, color="#c0392b",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                      edgecolor="none", alpha=0.8))

    # Axes
    y_margin = 10
    y_lo = max(0, median.min() - y_margin)
    y_hi = min(255, median.max() + y_margin)
    ax.set_ylim(y_lo, y_hi)
    ax.set_xlim(0, time_hours[-1])
    ax.set_xlabel("Time (h)", fontsize=10)
    ax.set_ylabel("Fluorescence intensity (AU)", fontsize=10)
    ax.tick_params(labelsize=9)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(1))
    ax.xaxis.set_minor_locator(ticker.MultipleLocator(0.5))
    ax.yaxis.set_major_locator(ticker.MultipleLocator(20))
    ax.yaxis.set_minor_locator(ticker.MultipleLocator(10))

    # Clean spines
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_linewidth(0.6)
    ax.spines["bottom"].set_linewidth(0.6)
    ax.tick_params(width=0.6)

    fig.tight_layout()

    # Save PNG and PDF
    for ext in ["png", "pdf"]:
        path = os.path.join(OUTPUT_DIR, f"publication_photobleaching_perframe.{ext}")
        fig.savefig(path, dpi=300, bbox_inches="tight")
        print(f"Saved: {path}")

    print(f"\nSlope: {coeffs[0]:+.3f} AU/hr ({drift_pct:+.1f}%)")
    print(f"Linear fit: {lin_fit[0]:.1f} -> {lin_fit[-1]:.1f} AU")
    print(f"N = {n_frames:,} frames")


if __name__ == "__main__":
    main()
