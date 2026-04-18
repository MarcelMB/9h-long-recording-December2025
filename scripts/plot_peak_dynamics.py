#!/usr/bin/env python3
"""
Peak calcium dynamics over time — photobleaching sensitivity test.

If photobleaching is occurring, peak ΔF/F₀ amplitudes shrink over time
because indicator molecules degrade. This is a more sensitive test than
tracking baseline alone.

Pipeline:
  1. ALS baseline (F₀) on all 561k per-frame spatial medians
  2. Compute ΔF/F₀ = (F - F₀) / F₀ per frame
  3. In sliding windows, track percentiles of ΔF/F₀ (95th, 99th)
  4. Linear fit on peak percentiles to check for decline

Output:
  output/peak_dynamics_over_time.png
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

    print(f"Computing ALS baseline on {n_frames:,} frames...")
    baseline = als_baseline(median, lam=1e10, p=0.01, niter=15)
    print("Done.")

    # --- ΔF/F₀ per frame ---
    # Fixed F₀: global mean of ALS baseline across entire recording
    f0_fixed = baseline.mean()
    print(f"Fixed F₀ (global mean ALS baseline): {f0_fixed:.1f} AU")

    dff = (median - baseline) / f0_fixed

    # --- Sliding window percentiles ---
    # 10-min windows (~12000 frames), stepped every 5 min
    window_frames = int(10 * 60 * fps)  # 12000
    step_frames = int(5 * 60 * fps)     # 6000

    starts = np.arange(0, n_frames - window_frames + 1, step_frames)
    n_windows = len(starts)

    win_time = np.empty(n_windows)
    win_p50 = np.empty(n_windows)
    win_p75 = np.empty(n_windows)
    win_p90 = np.empty(n_windows)
    win_p95 = np.empty(n_windows)
    win_p99 = np.empty(n_windows)

    for i, s in enumerate(starts):
        chunk = dff[s:s + window_frames]
        win_time[i] = time_hours[s + window_frames // 2]
        win_p50[i] = np.percentile(chunk, 50)
        win_p75[i] = np.percentile(chunk, 75)
        win_p90[i] = np.percentile(chunk, 90)
        win_p95[i] = np.percentile(chunk, 95)
        win_p99[i] = np.percentile(chunk, 99)

    # --- Linear fits on peak percentiles ---
    def fit_drift(t, y):
        c = np.polyfit(t, y, 1)
        fit = np.polyval(c, t)
        drift = 100.0 * (fit[-1] - fit[0]) / fit[0] if fit[0] != 0 else 0
        return c, fit, drift

    c50, fit50, drift50 = fit_drift(win_time, win_p50)
    c90, fit90, drift90 = fit_drift(win_time, win_p90)
    c95, fit95, drift95 = fit_drift(win_time, win_p95)
    c99, fit99, drift99 = fit_drift(win_time, win_p99)

    # --- Figure: 2 panels, publication style ---
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7, 5), sharex=True,
                                    gridspec_kw={"height_ratios": [1.2, 1]})

    # Top panel: 95th percentile + shaded range to median
    ax1.fill_between(win_time, win_p50, win_p95, color="#1a9641", alpha=0.10,
                     zorder=0)
    ax1.plot(win_time, win_p95, linewidth=1.2, color="#e66101", zorder=1)
    ax1.plot(win_time, win_p50, linewidth=0.8, color="#999999", zorder=1)
    ax1.plot(win_time, fit95, linewidth=1.5, color="#e66101", linestyle="--",
             zorder=2)

    ax1.text(0.97, 0.06,
             f"95th pct slope: {c95[0]:+.4f} h$^{{-1}}$ ({drift95:+.1f}%)",
             transform=ax1.transAxes, ha="right", va="bottom",
             fontsize=8, color="#e66101",
             bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                       edgecolor="none", alpha=0.8))

    ax1.set_ylabel("\u0394F/F\u2080", fontsize=10)
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)
    ax1.spines["left"].set_linewidth(0.6)
    ax1.spines["bottom"].set_linewidth(0.6)
    ax1.tick_params(labelsize=9, width=0.6)

    # Bottom panel: raw ΔF/F₀ trace
    ds = 20
    ax2.plot(time_hours[::ds], dff[::ds], linewidth=0.12, color="#999999",
             alpha=0.5, rasterized=True, zorder=0)
    ax2.axhline(0, color="#333333", linewidth=0.5, zorder=1)

    ax2.set_ylabel("\u0394F/F\u2080", fontsize=10)
    ax2.set_xlabel("Time (h)", fontsize=10)
    ax2.set_xlim(0, time_hours[-1])
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    ax2.spines["left"].set_linewidth(0.6)
    ax2.spines["bottom"].set_linewidth(0.6)
    ax2.tick_params(labelsize=9, width=0.6)

    ax1.xaxis.set_major_locator(ticker.MultipleLocator(1))
    ax1.xaxis.set_minor_locator(ticker.MultipleLocator(0.5))
    ax2.xaxis.set_major_locator(ticker.MultipleLocator(1))
    ax2.xaxis.set_minor_locator(ticker.MultipleLocator(0.5))

    fig.tight_layout()

    for ext in ["png", "pdf"]:
        path = os.path.join(OUTPUT_DIR, f"peak_dynamics_over_time.{ext}")
        fig.savefig(path, dpi=300, bbox_inches="tight")
        print(f"Saved: {path}")

    # --- Stats ---
    print(f"\n--- Peak dynamics drift ---")
    print(f"50th pct (median ΔF/F₀): {drift50:+.1f}% (slope: {c50[0]:+.4f} /hr)")
    print(f"90th pct:                 {drift90:+.1f}% (slope: {c90[0]:+.4f} /hr)")
    print(f"95th pct:                 {drift95:+.1f}% (slope: {c95[0]:+.4f} /hr)")
    print(f"99th pct:                 {drift99:+.1f}% (slope: {c99[0]:+.4f} /hr)")
    print(f"\nMean ΔF/F₀: {dff.mean():.4f}")
    print(f"95th pct mean: {win_p95.mean():.4f}")
    print(f"99th pct mean: {win_p99.mean():.4f}")


if __name__ == "__main__":
    main()
