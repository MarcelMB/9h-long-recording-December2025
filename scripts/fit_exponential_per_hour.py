#!/usr/bin/env python3
"""
Fit exponential decay to each 1-hour window of raw 1-min binned fluorescence.

Uses the spatial median (p50) from fluorescence_percentiles.npz.
For each hour, fits: f(t) = A * exp(-t/tau) + C
where t is time within that hour (0–60 min).

Output:
  output/exponential_fit_per_hour.png
"""

import os
import numpy as np
from scipy.optimize import curve_fit
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE_DIR = "/Users/mbrosch/Documents/9h_long_recording_December2025"
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
BINS_PER_HOUR = 60


def exp_decay(t, A, tau, C):
    return A * np.exp(-t / tau) + C


def main():
    data = np.load(os.path.join(OUTPUT_DIR, "fluorescence_percentiles.npz"))
    time_hours = data["time_hours"]
    p50 = data["p50"]

    # Split into 1-hour windows
    n_full = len(p50) // BINS_PER_HOUR
    remainder = len(p50) - n_full * BINS_PER_HOUR

    windows = []
    for h in range(n_full):
        s, e = h * BINS_PER_HOUR, (h + 1) * BINS_PER_HOUR
        windows.append((h, time_hours[s:e], p50[s:e]))
    if remainder >= 30:
        s = n_full * BINS_PER_HOUR
        windows.append((n_full, time_hours[s:], p50[s:]))

    n_windows = len(windows)
    cols = 4
    rows = (n_windows + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 3.5 * rows), squeeze=False)

    print(f"{'Hour':>6}  {'A':>8}  {'tau(min)':>10}  {'C':>8}  {'Decay%':>8}  {'R²':>8}")
    print("-" * 60)

    for idx, (h, t_abs, vals) in enumerate(windows):
        ax = axes[idx // cols][idx % cols]
        t_min = (t_abs - t_abs[0]) * 60  # local time in minutes

        ax.plot(t_min, vals, "o", markersize=2.5, color="#2c7bb6", alpha=0.7)

        # Exponential fit
        try:
            p0 = [vals[0] - vals[-1], 20.0, vals[-1]]
            popt, pcov = curve_fit(exp_decay, t_min, vals, p0=p0, maxfev=10000)
            A, tau, C = popt

            t_fit = np.linspace(t_min[0], t_min[-1], 200)
            y_fit = exp_decay(t_fit, *popt)

            # R²
            ss_res = np.sum((vals - exp_decay(t_min, *popt)) ** 2)
            ss_tot = np.sum((vals - np.mean(vals)) ** 2)
            r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

            decay_pct = 100 * (exp_decay(0, *popt) - exp_decay(t_min[-1], *popt)) / exp_decay(0, *popt)

            ax.plot(t_fit, y_fit, "-", linewidth=1.5, color="#d7191c",
                    label=f"τ={tau:.0f} min, {decay_pct:+.1f}%")

            # Also add linear fit for comparison
            coeffs = np.polyfit(t_min, vals, 1)
            lin_fit = np.polyval(coeffs, t_fit)
            ax.plot(t_fit, lin_fit, "--", linewidth=1, color="#999999", alpha=0.7)

            print(f"  {h + 2:>4}  {A:>8.2f}  {tau:>10.1f}  {C:>8.2f}  {decay_pct:>+7.1f}%  {r2:>8.3f}")
        except RuntimeError:
            print(f"  {h + 2:>4}  {'FAIL':>8}")
            r2 = 0

        # Label = recording hour (chunk 02 = hour 2, etc.)
        hour_label = h + 2  # chunk 02 starts at hour 2
        ax.set_title(f"Hour {hour_label} ({t_abs[0]:.1f}–{t_abs[-1]:.1f} h)", fontsize=10)
        ax.set_xlabel("Minutes", fontsize=8)
        if idx % cols == 0:
            ax.set_ylabel("Fluorescence (AU)", fontsize=8)
        ax.legend(fontsize=7, loc="upper right")
        ax.tick_params(labelsize=7)

    # Hide unused axes
    for idx in range(n_windows, rows * cols):
        axes[idx // cols][idx % cols].set_visible(False)

    fig.suptitle("Exponential decay fit per hour — raw 1-min bins (spatial median, full FOV)",
                 fontsize=13, fontweight="bold")
    fig.tight_layout()

    out_path = os.path.join(OUTPUT_DIR, "exponential_fit_per_hour.png")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
