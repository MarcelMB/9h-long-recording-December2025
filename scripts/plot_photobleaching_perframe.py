#!/usr/bin/env python3
"""
Photobleaching test: linear fit on all 561k per-frame spatial medians.

No binning, no smoothing, no asymmetric weighting — just a straight
linear regression on every frame to check for downward drift.

Output:
  output/photobleaching_perframe.png
"""

import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE_DIR = "/Users/mbrosch/Documents/9h_long_recording_December2025"
OUTPUT_DIR = os.path.join(BASE_DIR, "output")


def main():
    # --- Load per-frame data ---
    data = np.load(os.path.join(OUTPUT_DIR, "perframe_center_median.npz"))
    median = data["median"].astype(np.float64)
    fps = float(data["fps"])
    n_frames = len(median)
    time_hours = np.arange(n_frames) / fps / 3600.0

    print(f"Frames: {n_frames:,}")
    print(f"Duration: {time_hours[-1]:.2f} h")

    # --- Linear fit on all frames ---
    coeffs = np.polyfit(time_hours, median, 1)
    lin_fit = np.polyval(coeffs, time_hours)
    drift_pct = 100.0 * (lin_fit[-1] - lin_fit[0]) / lin_fit[0]

    # --- Figure ---
    fig, ax = plt.subplots(figsize=(10, 5))

    # Plot every 20th frame (~1 per second) to keep file size reasonable
    ds = 20
    ax.plot(time_hours[::ds], median[::ds], linewidth=0.15, color="#888888",
            alpha=0.5, rasterized=True, zorder=0)
    # Invisible point for cleaner legend
    ax.plot([], [], linewidth=0.5, color="#888888",
            label=f"Per-frame spatial median ({n_frames:,} frames)")

    ax.plot(time_hours[[0, -1]], lin_fit[[0, -1]], linewidth=2.5, color="#d7191c",
            linestyle="-", label=f"Linear fit ({drift_pct:+.1f}%)", zorder=2)

    ax.annotate(
        f"Drift: {drift_pct:+.1f}% over {time_hours[-1]:.1f} h\n"
        f"Slope: {coeffs[0]:+.3f} AU/hr\n"
        f"Start: {lin_fit[0]:.1f} AU  End: {lin_fit[-1]:.1f} AU\n"
        f"Frames: {n_frames:,} at {fps:.0f} fps",
        xy=(0.98, 0.95), xycoords="axes fraction",
        ha="right", va="top", fontsize=9, fontfamily="monospace",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                  edgecolor="#cccccc", alpha=0.85)
    )

    ax.set_ylabel("Fluorescence Intensity (8-bit)", fontsize=11)
    ax.set_xlabel("Time (hours)", fontsize=11)
    ax.set_ylim(0, 255)
    ax.set_xlim(0, 8.0)
    ax.set_title("Photobleaching Test \u2014 Linear Fit on Per-Frame Spatial Medians",
                 fontsize=11, fontweight="bold")
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=8, frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    caption = (
        "GCaMP6f fluorescence from dCA1 hippocampus recorded with a wireless Miniscope Zero over ~8 hours.\n"
        "Center ROI (50\u00d750 px), spatial median computed per frame at 20 fps.\n"
        "\n"
        "Linear least-squares fit directly on all 561,790 per-frame values.\n"
        "No temporal binning, smoothing, or asymmetric weighting applied.\n"
        "Photobleaching would appear as a negative slope (downward drift)."
    )
    fig.text(0.02, -0.01, caption, ha="left", va="top", fontsize=7.5, color="#444444",
             transform=fig.transFigure, fontfamily="sans-serif", style="italic",
             linespacing=1.6)

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.20)

    png_path = os.path.join(OUTPUT_DIR, "photobleaching_perframe.png")
    fig.savefig(png_path, dpi=150, bbox_inches="tight")
    print(f"Saved: {png_path}")

    print(f"\nDrift: {drift_pct:+.1f}% ({coeffs[0]:+.3f} AU/hr)")
    print(f"Linear fit: {lin_fit[0]:.1f} → {lin_fit[-1]:.1f} AU")


if __name__ == "__main__":
    main()
