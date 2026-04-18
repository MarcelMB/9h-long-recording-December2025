#!/usr/bin/env python3
"""
Summary figure: ALS baseline estimation on per-frame spatial median values.

Runs ALS directly on all 561k per-frame spatial medians (no binning),
then plots the result downsampled for visualization alongside 1-min bins.
Purpose: confirm stable baseline / no photobleaching over the recording.

Output:
  output/baseline_als_summary.png
"""

import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import sparse
from scipy.sparse.linalg import spsolve

BASE_DIR = "/Users/mbrosch/Documents/9h_long_recording_December2025"
OUTPUT_DIR = os.path.join(BASE_DIR, "output")


def als_baseline(y, lam=1e10, p=0.01, niter=15):
    """Asymmetric least squares baseline (Eilers & Boelens, 2005)."""
    L = len(y)
    D = sparse.diags([1, -2, 1], [0, 1, 2], shape=(L - 2, L))
    D = D.T.dot(D)
    w = np.ones(L)
    for _ in range(niter):
        W = sparse.diags(w, 0)
        Z = W + lam * D
        z = spsolve(Z, w * y)
        w = p * (y > z) + (1 - p) * (y <= z)
    return z


def main():
    # --- Load per-frame data (561k frames) ---
    perframe = np.load(os.path.join(OUTPUT_DIR, "perframe_center_median.npz"))
    median_perframe = perframe["median"].astype(np.float64)
    fps = float(perframe["fps"])
    n_frames = len(median_perframe)
    time_frames = np.arange(n_frames) / fps / 3600.0  # hours

    # --- Load 1-min binned data (for plotting overlay) ---
    binned = np.load(os.path.join(OUTPUT_DIR, "fluorescence_percentiles.npz"))
    time_bins = binned["time_hours"]
    trace_bins = binned["center_p50"]

    print(f"Running ALS on {n_frames} per-frame values...")

    # --- ALS baseline on per-frame data ---
    # lambda=1e10 for 561k points gives smooth baseline (scales with N^4)
    baseline = als_baseline(median_perframe, lam=1e10, p=0.01, niter=15)
    print("ALS done.")

    # --- Downsample baseline to 1-min bins for linear fit ---
    frames_per_bin = int(60 * fps)  # 1200
    n_bins = n_frames // frames_per_bin
    bl_binned = np.array([
        baseline[i * frames_per_bin:(i + 1) * frames_per_bin].mean()
        for i in range(n_bins)
    ])
    time_bl_bins = np.array([
        time_frames[i * frames_per_bin:(i + 1) * frames_per_bin].mean()
        for i in range(n_bins)
    ])

    # --- Linear fit on baseline ---
    coeffs = np.polyfit(time_frames, baseline, 1)
    lin_fit_bins = np.polyval(coeffs, time_bl_bins)
    drift_pct = 100.0 * (np.polyval(coeffs, time_frames[-1]) - np.polyval(coeffs, time_frames[0])) / np.polyval(coeffs, time_frames[0])

    # --- Figure: single panel ---
    fig, ax = plt.subplots(figsize=(10, 5))

    # Plot 1-min binned trace (readable at this scale)
    ax.plot(time_bins, trace_bins, linewidth=0.6, color="#888888",
            label="1-min bins (spatial median)", zorder=1)

    # Plot ALS baseline (downsample for plotting: every 600th frame = 30s)
    ds = 600
    ax.plot(time_frames[::ds], baseline[::ds], linewidth=2, color="#1a9641",
            label=f"ALS baseline F\u2080 (\u03bb=10\u00b9\u2070, p=0.01, per-frame)", zorder=3)

    # Linear fit
    ax.plot(time_bl_bins, lin_fit_bins, linewidth=1.5, color="#1a9641", linestyle="--",
            label=f"Linear fit ({drift_pct:+.1f}%)", zorder=4)

    ax.annotate(
        f"Baseline drift: {drift_pct:+.1f}% over {time_frames[-1]:.1f} h\n"
        f"Slope: {coeffs[0]:+.4f} AU/hr\n"
        f"Mean F\u2080: {baseline.mean():.1f} AU\n"
        f"F\u2080 range: {baseline.min():.1f}\u2013{baseline.max():.1f} AU\n"
        f"Computed on {n_frames:,} frames (no binning)",
        xy=(0.98, 0.95), xycoords="axes fraction",
        ha="right", va="top", fontsize=9, fontfamily="monospace",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                  edgecolor="#cccccc", alpha=0.85)
    )

    ax.set_ylabel("Fluorescence Intensity (8-bit)", fontsize=11)
    ax.set_xlabel("Time (hours)", fontsize=11)
    ax.set_ylim(0, 255)
    ax.set_xlim(0, 8.0)
    ax.set_title("ALS Baseline Estimation (F\u2080) \u2014 GCaMP6f dCA1 (~8 h wireless recording)",
                 fontsize=11, fontweight="bold")
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=8, frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    caption = (
        "GCaMP6f fluorescence from dCA1 hippocampus recorded with a wireless Miniscope Zero over ~8 hours.\n"
        "Center ROI (50\u00d750 px), spatial median per frame at 20 fps (561,790 frames total).\n"
        "\n"
        "ALS baseline F\u2080 computed directly on per-frame spatial medians (no temporal binning).\n"
        "Whittaker smoother with asymmetric weights (\u03bb=10\u00b9\u2070, p=0.01, 15 iterations).\n"
        "The asymmetric penalty fits a smooth curve that hugs the bottom of the signal,\n"
        "unbiased by Ca\u00b2\u207a transients (one-sided). Same approach used by CaImAn and Suite2p.\n"
        "Dashed line = linear fit on F\u2080. Grey = 1-min binned trace for visual reference."
    )
    fig.text(0.02, -0.01, caption, ha="left", va="top", fontsize=7.5, color="#444444",
             transform=fig.transFigure, fontfamily="sans-serif", style="italic",
             linespacing=1.6)

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.24)

    png_path = os.path.join(OUTPUT_DIR, "baseline_als_summary.png")
    fig.savefig(png_path, dpi=150, bbox_inches="tight")
    print(f"Saved: {png_path}")

    print(f"\nBaseline drift: {drift_pct:+.1f}% ({coeffs[0]:+.4f} AU/hr)")
    print(f"Mean F0: {baseline.mean():.1f} AU")
    print(f"F0 range: {baseline.min():.1f} - {baseline.max():.1f} AU")


if __name__ == "__main__":
    main()
