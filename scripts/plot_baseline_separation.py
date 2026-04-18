#!/usr/bin/env python3
"""
Baseline separation comparison: rolling percentile vs robust regression vs ALS.

Implements three methods to separate baseline fluorescence from Ca2+ events
on the 1-min binned spatial-median trace:

  1. Rolling 10th percentile (existing approach, 30-min window)
  2. Robust regression (Huber regressor, polynomial features)
  3. Asymmetric least squares (ALS / Whittaker smoother)

Output:
  output/baseline_separation_comparison.png  — 4-panel comparison figure
  output/baseline_separation_als_sensitivity.png — ALS parameter sensitivity
"""

import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import sparse
from scipy.sparse.linalg import spsolve
from sklearn.linear_model import HuberRegressor
from sklearn.preprocessing import PolynomialFeatures

BASE_DIR = "/Users/mbrosch/Documents/9h_long_recording_December2025"
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

ROLLING_WINDOW = 30  # minutes


# ---------------------------------------------------------------------------
# Method 1: Rolling percentile (same as existing pipeline)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Method 2: Robust regression (Huber)
# ---------------------------------------------------------------------------

def robust_baseline(time, trace, degree=3, epsilon=1.35):
    """Fit baseline using Huber robust regression with polynomial features.

    Huber loss downweights large positive residuals (Ca2+ transients)
    while fitting tightly to the baseline floor.
    """
    poly = PolynomialFeatures(degree=degree, include_bias=False)
    X = poly.fit_transform(time.reshape(-1, 1))

    huber = HuberRegressor(epsilon=epsilon, max_iter=200)
    huber.fit(X, trace)
    baseline = huber.predict(X)
    return baseline


# ---------------------------------------------------------------------------
# Method 3: Asymmetric Least Squares (ALS)
# ---------------------------------------------------------------------------

def als_baseline(y, lam=1e6, p=0.01, niter=20):
    """Asymmetric least squares baseline estimation (Eilers & Boelens, 2005).

    Parameters
    ----------
    y : array
        Signal (1-min binned trace).
    lam : float
        Smoothness parameter (larger = smoother baseline).
    p : float
        Asymmetry parameter (0 < p < 1). Small p penalizes going above
        the data, so the baseline hugs the bottom of the signal.
    niter : int
        Number of reweighted iterations.

    Returns
    -------
    z : array
        Estimated baseline.
    """
    L = len(y)
    # Second-order difference matrix
    D = sparse.diags([1, -2, 1], [0, 1, 2], shape=(L - 2, L))
    D = D.T.dot(D)
    w = np.ones(L)
    for _ in range(niter):
        W = sparse.diags(w, 0)
        Z = W + lam * D
        z = spsolve(Z, w * y)
        w = p * (y > z) + (1 - p) * (y <= z)
    return z


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def linear_drift(time, baseline):
    """Return linear fit line and drift percentage."""
    coeffs = np.polyfit(time, baseline, 1)
    lin = np.polyval(coeffs, time)
    drift = 100.0 * (lin[-1] - lin[0]) / lin[0]
    return lin, drift, coeffs


def main():
    # --- Load data ---
    npz_path = os.path.join(OUTPUT_DIR, "fluorescence_percentiles.npz")
    data = np.load(npz_path)
    time_hours = data["time_hours"]
    trace = data["center_p50"]
    bin_min = data["center_bin_min"]
    bin_max = data["center_bin_max"]

    # --- Compute baselines ---
    # 1. Rolling percentile
    bl_pct = smooth_ma(rolling_percentile(trace, ROLLING_WINDOW, 10))

    # 2. Robust regression (Huber, degree 3)
    bl_huber = robust_baseline(time_hours, trace, degree=3, epsilon=1.35)

    # 3. ALS (lambda=1e6, p=0.01)
    bl_als = als_baseline(trace, lam=1e6, p=0.01)

    baselines = [
        ("Rolling 10th pct (30-min window)", bl_pct, "#2c7bb6"),
        ("Robust regression (Huber, deg 3)", bl_huber, "#d7191c"),
        ("Asymmetric least squares (ALS)", bl_als, "#1a9641"),
    ]

    # --- Figure 1: 4-panel comparison ---
    fig, axes = plt.subplots(4, 1, figsize=(10, 12), sharex=True)

    # Panel 1: raw trace with all baselines overlaid
    ax = axes[0]
    ax.fill_between(time_hours, bin_min, bin_max, color="#cccccc", alpha=0.25,
                    label="Per-bin min\u2013max", zorder=0)
    ax.plot(time_hours, trace, linewidth=0.6, color="#888888",
            label="1-min bins (spatial median)", zorder=1)
    for label, bl, color in baselines:
        ax.plot(time_hours, bl, linewidth=2, color=color, label=label, zorder=2)
    ax.set_ylabel("Fluorescence (8-bit)")
    ax.set_ylim(0, 255)
    ax.set_title("All baseline methods overlaid", fontsize=11, fontweight="bold")
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=8, frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # Panels 2-4: individual methods with residuals
    for i, (label, bl, color) in enumerate(baselines):
        ax = axes[i + 1]
        residual = trace - bl

        lin, drift, coeffs = linear_drift(time_hours, bl)

        # Trace + baseline
        ax.fill_between(time_hours, bin_min, bin_max, color="#cccccc", alpha=0.2, zorder=0)
        ax.plot(time_hours, trace, linewidth=0.5, color="#aaaaaa", zorder=1)
        ax.plot(time_hours, bl, linewidth=2, color=color, label=label, zorder=2)
        ax.plot(time_hours, lin, linewidth=1.5, color=color, linestyle="--",
                label=f"Linear fit ({drift:+.1f}%)", zorder=3)

        # Shade residuals above baseline (Ca2+ events)
        ax.fill_between(time_hours, bl, trace,
                        where=(trace > bl), color=color, alpha=0.15,
                        label="Above baseline (Ca\u00b2\u207a)", zorder=1)

        ax.annotate(
            f"Drift: {drift:+.1f}% ({coeffs[0]:+.2f} AU/hr)\n"
            f"Mean residual: {residual.mean():.2f} AU\n"
            f"Residual std: {residual.std():.2f} AU",
            xy=(0.98, 0.05), xycoords="axes fraction",
            ha="right", va="bottom", fontsize=8, fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                      edgecolor="#cccccc", alpha=0.8)
        )

        ax.set_ylabel("Fluorescence (8-bit)")
        ax.set_ylim(0, 255)
        ax.set_title(label, fontsize=10, fontweight="bold")
        ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=8, frameon=False)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    axes[-1].set_xlabel("Time (hours)", fontsize=11)
    axes[0].set_xlim(0, 8.0)

    caption = (
        "Comparison of three baseline estimation methods on the 1-min binned spatial-median trace\n"
        "(GCaMP6f, dCA1 hippocampus, wireless Miniscope Zero, ~8 h recording).\n"
        "\n"
        "Rolling 10th percentile: 30-min symmetric window, smoothed with 15-min moving average.\n"
        "Robust regression: Huber regressor (epsilon=1.35) with degree-3 polynomial features.\n"
        "ALS: Whittaker smoother with asymmetric weights (\u03bb=10\u2076, p=0.01, 20 iterations).\n"
        "\n"
        "Shaded regions above baseline indicate bins with elevated Ca\u00b2\u207a activity.\n"
        "Dashed lines: linear fits on each baseline, with drift % over the full recording."
    )
    fig.text(0.02, -0.01, caption, ha="left", va="top", fontsize=7.5, color="#444444",
             transform=fig.transFigure, fontfamily="sans-serif", style="italic",
             linespacing=1.6)

    fig.tight_layout()
    fig.subplots_adjust(bottom=0.18)

    png1 = os.path.join(OUTPUT_DIR, "baseline_separation_comparison.png")
    fig.savefig(png1, dpi=150, bbox_inches="tight")
    print(f"Saved: {png1}")

    # --- Print summary table ---
    print("\n--- Baseline drift comparison ---")
    print(f"{'Method':<40} {'Drift %':>8}  {'Slope (AU/hr)':>14}  {'Mean resid':>11}  {'Std resid':>10}")
    for label, bl, color in baselines:
        lin, drift, coeffs = linear_drift(time_hours, bl)
        resid = trace - bl
        print(f"{label:<40} {drift:>+8.1f}  {coeffs[0]:>+14.3f}  {resid.mean():>11.2f}  {resid.std():>10.2f}")

    # --- Figure 2: ALS parameter sensitivity ---
    fig2, axes2 = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

    # Vary lambda
    ax = axes2[0]
    ax.plot(time_hours, trace, linewidth=0.5, color="#aaaaaa", label="Data", zorder=0)
    lambdas = [1e4, 1e5, 1e6, 1e7, 1e8]
    cmap = plt.cm.viridis
    for j, lam in enumerate(lambdas):
        bl = als_baseline(trace, lam=lam, p=0.01)
        c = cmap(j / (len(lambdas) - 1))
        ax.plot(time_hours, bl, linewidth=1.5, color=c,
                label=f"\u03bb=10\u207b{int(-np.log10(lam)):d}" if lam < 1
                else f"\u03bb=10\u2074" if lam == 1e4
                else f"\u03bb={lam:.0e}")
    ax.set_ylabel("Fluorescence (8-bit)")
    ax.set_ylim(0, 255)
    ax.set_title("ALS sensitivity to \u03bb (smoothness), p=0.01 fixed", fontsize=10, fontweight="bold")
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=8, frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # Vary p
    ax = axes2[1]
    ax.plot(time_hours, trace, linewidth=0.5, color="#aaaaaa", label="Data", zorder=0)
    ps = [0.001, 0.005, 0.01, 0.05, 0.1]
    for j, p in enumerate(ps):
        bl = als_baseline(trace, lam=1e6, p=p)
        c = cmap(j / (len(ps) - 1))
        ax.plot(time_hours, bl, linewidth=1.5, color=c, label=f"p={p}")
    ax.set_ylabel("Fluorescence (8-bit)")
    ax.set_ylim(0, 255)
    ax.set_xlabel("Time (hours)", fontsize=11)
    ax.set_title("ALS sensitivity to p (asymmetry), \u03bb=10\u2076 fixed", fontsize=10, fontweight="bold")
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=8, frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    axes2[0].set_xlim(0, 8.0)

    caption2 = (
        "ALS parameter sensitivity on the 1-min binned spatial-median trace.\n"
        "Top: varying \u03bb (smoothness) with p=0.01. Larger \u03bb produces smoother baselines.\n"
        "Bottom: varying p (asymmetry) with \u03bb=10\u2076. Smaller p pushes baseline closer to the floor.\n"
        "\u03bb=10\u2076, p=0.01 is a reasonable default for this data."
    )
    fig2.text(0.02, -0.01, caption2, ha="left", va="top", fontsize=7.5, color="#444444",
              transform=fig2.transFigure, fontfamily="sans-serif", style="italic",
              linespacing=1.6)

    fig2.tight_layout()
    fig2.subplots_adjust(bottom=0.14)

    png2 = os.path.join(OUTPUT_DIR, "baseline_separation_als_sensitivity.png")
    fig2.savefig(png2, dpi=150, bbox_inches="tight")
    print(f"Saved: {png2}")


if __name__ == "__main__":
    main()
