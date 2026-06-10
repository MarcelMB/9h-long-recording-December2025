#!/usr/bin/env python3
"""TEMP: original-style timeline with raw per-frame errors (orange, alpha 0.1).

Each lost MCU frame is drawn as one faint orange vertical line; dense bursts
build up to a darker band, sparse periods stay light. Reproduces the very first
figure's look (before the binned heatmap / green-bar designs), for comparison.

Reuses gather_timestamps / gather_battery / load_summary from
plot_survival_timeline so the data and session-end cut stay identical.

Output: output/raw_errors_timeline.png / .pdf  (temporary)
"""

import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick

sys.path.insert(0, os.path.dirname(__file__))
import plot_survival_timeline as pt

ORANGE = pt.C_DAQ1
XLO, XHI = pt.TIMELINE_XLO, pt.TIMELINE_XHI


def run():
    daq1_t, daq2_t, st_t, t0 = pt.gather_timestamps()
    h1 = (daq1_t - t0) / 3600.0 if len(daq1_t) else daq1_t
    h2 = (daq2_t - t0) / 3600.0 if len(daq2_t) else daq2_t
    hs = (st_t - t0) / 3600.0 if len(st_t) else st_t
    bh, bv = pt.gather_battery(t0)

    totals = pt.load_summary()["totals"]
    rows = [
        (h1, "Wireless datastream 1", totals["DAQ1"]["loss_pct"]),
        (h2, "Wireless datastream 2", totals["DAQ2"]["loss_pct"]),
        (hs, "Combined (stream 1 + 2)", totals["stitched_both_lost"]["loss_pct"]),
    ]

    fig = plt.figure(figsize=(10, 6.0))
    gs = fig.add_gridspec(
        4, 2, width_ratios=[4, 1.5], height_ratios=[1, 1, 1, 2], wspace=0.15, hspace=0.4
    )
    x_max = (
        max([p for _, _, p in rows] + [0.5]) * 1.35
    )  # auto small axis (original look)

    ax_t0 = ax_b0 = None
    for r, (h, label, pct) in enumerate(rows):
        ax_t = fig.add_subplot(gs[r, 0], sharex=ax_t0)
        ax_t0 = ax_t0 or ax_t
        ax_b = fig.add_subplot(gs[r, 1], sharex=ax_b0)
        ax_b0 = ax_b0 or ax_b

        # Raw errors: one faint orange line per lost frame.
        if len(h):
            ax_t.vlines(h, 0, 1, color=ORANGE, lw=0.5, alpha=0.1, rasterized=True)
        ax_t.set_xlim(XLO, XHI)
        ax_t.set_ylim(0, 1)
        ax_t.set_yticks([])
        for s in ("left", "right", "top"):
            ax_t.spines[s].set_visible(False)
        ax_t.set_ylabel(
            label, fontsize=9, rotation=0, ha="right", va="center", labelpad=10
        )
        ax_t.tick_params(axis="x", labelbottom=False)

        ax_b.barh(
            [0], [pct], height=0.55, color=ORANGE, edgecolor="white", linewidth=0.5
        )
        ax_b.text(
            pct + 0.02 * x_max,
            0,
            f"{pct:.2f}%",
            ha="left",
            va="center",
            fontsize=9,
            fontweight="bold",
        )
        ax_b.set_yticks([])
        ax_b.set_ylim(-0.5, 0.5)
        ax_b.set_xlim(0, x_max)
        for s in ("left", "right", "top"):
            ax_b.spines[s].set_visible(False)
        if r < 2:
            ax_b.tick_params(axis="x", labelbottom=False)
        else:
            ax_b.set_xlabel("Lost MCU frames (%)", fontsize=9)

    ax_batt = fig.add_subplot(gs[3, 0], sharex=ax_t0)
    if len(bh):
        ax_batt.plot(bh, bv, color=pt.C_DAQ2, lw=0.8, rasterized=True)
    ax_batt.set_xlim(XLO, XHI)
    ax_batt.set_ylim(bottom=3.4)
    ax_batt.set_ylabel("Battery (V)", fontsize=9)
    ax_batt.set_xlabel("Recording time (hours)", fontsize=10)
    ax_batt.xaxis.set_major_locator(mtick.MultipleLocator(1))
    ax_batt.xaxis.set_minor_locator(mtick.MultipleLocator(0.5))
    fig.add_subplot(gs[3, 1]).axis("off")

    for ext in ("png", "pdf"):
        fig.savefig(f"{pt.OUT_DIR}/raw_errors_timeline.{ext}")
    plt.close(fig)
    print("Saved: output/raw_errors_timeline.png/.pdf  (temporary)")


if __name__ == "__main__":
    run()
