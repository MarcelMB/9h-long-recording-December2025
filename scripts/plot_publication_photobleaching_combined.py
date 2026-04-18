#!/usr/bin/env python3
"""
Publication figure: photobleaching analysis (combined).

Panel A: Linear fit on per-frame spatial medians (baseline stability)
Panel B: 95th percentile ΔF/F₀ over time (peak Ca²⁺ dynamics stability)

Output:
  output/publication_photobleaching_combined.png
  output/publication_photobleaching_combined.pdf
  output/publication_peak_dynamics.png
  output/publication_peak_dynamics.pdf
"""

import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
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
    # --- Load per-frame data ---
    data = np.load(os.path.join(OUTPUT_DIR, "perframe_center_median.npz"))
    median = data["median"].astype(np.float64)
    fps = float(data["fps"])
    n_frames = len(median)
    time_hours = np.arange(n_frames) / fps / 3600.0

    # --- Panel A: linear fit on raw per-frame medians ---
    coeffs = np.polyfit(time_hours, median, 1)
    lin_fit = np.polyval(coeffs, time_hours)
    drift_pct = 100.0 * (lin_fit[-1] - lin_fit[0]) / lin_fit[0]

    # --- Panel B: ALS baseline + peak dynamics ---
    print(f"Computing ALS baseline on {n_frames:,} frames...")
    baseline = als_baseline(median, lam=1e10, p=0.01, niter=15)
    f0_global = baseline.mean()
    dff = (median - baseline) / f0_global
    print(f"Done. Global mean F₀: {f0_global:.1f} AU")

    # 10-min sliding windows, 5-min step
    window_frames = int(10 * 60 * fps)
    step_frames = int(5 * 60 * fps)
    starts = np.arange(0, n_frames - window_frames + 1, step_frames)

    win_time = np.empty(len(starts))
    win_p95 = np.empty(len(starts))
    for i, s in enumerate(starts):
        win_time[i] = time_hours[s + window_frames // 2]
        win_p95[i] = np.percentile(dff[s:s + window_frames], 95)

    c95 = np.polyfit(win_time, win_p95, 1)
    fit95 = np.polyval(c95, win_time)
    drift95 = 100.0 * (fit95[-1] - fit95[0]) / fit95[0]

    # =============================================
    # Figure 1: standalone peak dynamics (single panel)
    # =============================================
    fig1, ax = plt.subplots(figsize=(7, 3))

    ax.plot(win_time, win_p95, linewidth=1.2, color="#e66101", zorder=1)
    ax.plot(win_time, fit95, linewidth=1.5, color="#e66101", linestyle="--", zorder=2)

    ax.text(0.97, 0.06,
            f"slope = {c95[0]:+.4f} h$^{{-1}}$ ({drift95:+.1f}%)",
            transform=ax.transAxes, ha="right", va="bottom",
            fontsize=8, color="#e66101",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                      edgecolor="none", alpha=0.8))

    ax.set_ylabel("\u0394F/F\u2080 (95th pct)", fontsize=10)
    ax.set_xlabel("Time (h)", fontsize=10)
    ax.set_xlim(0, time_hours[-1])
    ax.xaxis.set_major_locator(ticker.MultipleLocator(1))
    ax.xaxis.set_minor_locator(ticker.MultipleLocator(0.5))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_linewidth(0.6)
    ax.spines["bottom"].set_linewidth(0.6)
    ax.tick_params(labelsize=9, width=0.6)

    fig1.tight_layout()
    for ext in ["png", "pdf"]:
        path = os.path.join(OUTPUT_DIR, f"publication_peak_dynamics.{ext}")
        fig1.savefig(path, dpi=300, bbox_inches="tight")
        print(f"Saved: {path}")

    # =============================================
    # Figure 2: combined (A + B)
    # =============================================
    fig, (axA, axB) = plt.subplots(2, 1, figsize=(7, 5.5), sharex=True)

    # Panel A: raw per-frame trace + linear fit
    ds = 20
    axA.plot(time_hours[::ds], median[::ds], linewidth=0.12, color="#999999",
             alpha=0.5, rasterized=True, zorder=0)
    axA.plot(time_hours[[0, -1]], lin_fit[[0, -1]], linewidth=1.8,
             color="#c0392b", zorder=2)

    axA.text(0.97, 0.06,
             f"slope = {coeffs[0]:+.2f} AU h$^{{-1}}$ ({drift_pct:+.1f}%)",
             transform=axA.transAxes, ha="right", va="bottom",
             fontsize=8, color="#c0392b",
             bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                       edgecolor="none", alpha=0.8))

    y_margin = 10
    axA.set_ylim(max(0, median.min() - y_margin), min(255, median.max() + y_margin))
    axA.set_ylabel("Fluorescence (AU)", fontsize=10)
    axA.text(-0.08, 1.05, "A", transform=axA.transAxes, fontsize=14,
             fontweight="bold", va="top")

    # Panel B: 95th percentile ΔF/F₀
    axB.plot(win_time, win_p95, linewidth=1.2, color="#e66101", zorder=1)
    axB.plot(win_time, fit95, linewidth=1.5, color="#e66101", linestyle="--", zorder=2)

    axB.text(0.97, 0.06,
             f"slope = {c95[0]:+.4f} h$^{{-1}}$ ({drift95:+.1f}%)",
             transform=axB.transAxes, ha="right", va="bottom",
             fontsize=8, color="#e66101",
             bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                       edgecolor="none", alpha=0.8))

    axB.set_ylabel("\u0394F/F\u2080 (95th pct)", fontsize=10)
    axB.set_xlabel("Time (h)", fontsize=10)
    axB.text(-0.08, 1.05, "B", transform=axB.transAxes, fontsize=14,
             fontweight="bold", va="top")

    # Shared formatting
    for ax in [axA, axB]:
        ax.set_xlim(0, time_hours[-1])
        ax.xaxis.set_major_locator(ticker.MultipleLocator(1))
        ax.xaxis.set_minor_locator(ticker.MultipleLocator(0.5))
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_linewidth(0.6)
        ax.spines["bottom"].set_linewidth(0.6)
        ax.tick_params(labelsize=9, width=0.6)

    fig.tight_layout()
    for ext in ["png", "pdf"]:
        path = os.path.join(OUTPUT_DIR, f"publication_photobleaching_combined.{ext}")
        fig.savefig(path, dpi=300, bbox_inches="tight")
        print(f"Saved: {path}")

    # --- Stats ---
    print(f"\nPanel A — Baseline:")
    print(f"  Slope: {coeffs[0]:+.3f} AU/hr ({drift_pct:+.1f}%)")
    print(f"  N = {n_frames:,} frames")
    print(f"Panel B — Peak dynamics (95th pct):")
    print(f"  Slope: {c95[0]:+.4f} /hr ({drift95:+.1f}%)")
    print(f"  Global mean F₀: {f0_global:.1f} AU")


if __name__ == "__main__":
    main()
