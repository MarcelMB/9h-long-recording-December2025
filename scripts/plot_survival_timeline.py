#!/usr/bin/env python3
"""Timeline of lost MCU frames — wireless datastream 1, 2, and combined.

Each DAQ row is a green "frames retained" survival bar (whitened per 1-min bin
by the local loss rate); DAQ1 and DAQ2 also carry a 5-min loss-rate area panel
stacked above the bar. A shared battery-voltage trace sits below. Uses the
MCU-survival metric, so a single MCU frame counts once regardless of mio
bit-flip amplification. All rows are cut to the shared per-pair session-end
boundary (excludes the terminal MCU-reboot collapse).

Inputs:
  output/survival_summary.json   — DAQ1/DAQ2/stitched totals + per-pair spans
                                   (one shared session-end boundary for all three)
  output/stitched_both_lost.csv  — per-frame both-lost list (+ timestamps)
  neural_DAQ{1,2}/*.csv          — for per-frame lost-mark timestamps (min arrival)

Outputs:
  output/publication_survival_timeline.png / .pdf
  output/publication_survival_bar.png / .pdf    — old vs new metric side by side
"""

import glob
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import matplotlib.colors as mcolors

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import analyze_frame_num_drops as afd

# Repo root = parent of scripts/ — derive from this file so the script runs
# regardless of where the checkout lives.
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAQ1_DIR = f"{BASE}/neural_DAQ1"
DAQ2_DIR = f"{BASE}/neural_DAQ2"
OUT_DIR = f"{BASE}/output"

FPS = 20.0

# ── Battery voltage panel ──
# Battery lives on the wireless device; both DAQs decode the same value, so we
# merge good samples from every chunk of both DAQs for full session coverage.
BATTERY_GRID_HZ = 1.0  # uniform interpolation grid for display (1 Hz)
# mio ADCScaling (wireless config wireless-200px.yml / ber-prbs15.yml):
#   volts = raw / 2**bitdepth * ref_voltage * battery_div_factor
# with ref_voltage=1.1, bitdepth=8, battery_div_factor=5  →  raw 191 ≈ 4.10 V
BATT_VOLTS_PER_COUNT = 1.1 * 5.0 / 2**8  # 0.0214844 V per ADC count
BATT_OUTLIER_WINDOW = 501  # rolling-median window for bit-flip rejection
BATT_OUTLIER_TOL = 4  # keep |raw - rolling_median| <= this many counts
# Simple moving-average window over per-sample readings. MiniscopeZeroPlots
# (battery_level.py) uses SMA_WINDOW = 500 on a single ~160 Hz device stream
# (~3 s). We merge both DAQs (~320 Hz), so 1000 gives the same ~3 s smoothing.
BATT_SMA_WINDOW = 1000

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "font.size": 10,
        "axes.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.major.width": 0.8,
        "ytick.major.width": 0.8,
        "figure.dpi": 300,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.15,
    }
)

C_DAQ1 = "#D55E00"
C_DAQ2 = "#0072B2"
C_COMBINED = "#009E73"

# Each DAQ row = a green "frames retained" survival bar, whitened per 1-min bin
# by the local loss rate (green at 0 %, white at >= TIMELINE_VMAX_PCT). DAQ1/DAQ2
# also carry a 5-min loss-rate area panel above the bar.
TIMELINE_BIN_MINUTES = 1.0  # green-bar whitening bin width
TIMELINE_VMAX_PCT = 15.0  # per-bin loss-% mapped to fully white
TIMELINE_XLO, TIMELINE_XHI = -0.2, 9.2

# Loss-rate area panel (above DAQ1/DAQ2): coarser bins so bursts read as smooth
# spears near the mean rather than tall 1-min spikes (peak height scales with
# bin width; the total lost frames are identical either way).
AREA_BIN_MINUTES = 5.0
AREA_YMAX_PCT = 12.0  # headroom above the ~10.6 % worst 5-min bin
C_RETAIN = "#1B9E5A"  # survival-bar green


def _per_bin_loss_pct(hours, bin_minutes=TIMELINE_BIN_MINUTES):
    """Per-bin local loss % and the bin edges, over the hours axis.

    Loss % = lost frames in the bin / frames expected at 20 fps for that bin
    width. Wider bins spread bursts over more frames, lowering the peaks.
    """
    nbins = int(round((TIMELINE_XHI - TIMELINE_XLO) * 60.0 / bin_minutes))
    edges = np.linspace(TIMELINE_XLO, TIMELINE_XHI, nbins + 1)
    counts, _ = np.histogram(hours, bins=edges)
    loss_pct = 100.0 * counts / (FPS * bin_minutes * 60.0)
    return loss_pct, edges


def _battery_panel(fig, gs_cell, share_ax, battery_h, battery_v):
    """Shared battery voltage panel (bottom row) on the timeline x-axis."""
    ax = fig.add_subplot(gs_cell, sharex=share_ax)
    if len(battery_h):
        ax.plot(battery_h, battery_v, color=C_DAQ2, lw=0.8, rasterized=True)
        # Average discharge rate = endpoint drop / duration (no fit needed).
        v0, v1 = float(battery_v[0]), float(battery_v[-1])
        dur = float(battery_h[-1] - battery_h[0])
        rate_mv_h = (v0 - v1) / dur * 1000.0
        ax.text(
            0.99,
            0.94,
            f"≈ {rate_mv_h:.0f} mV/h  ({v0:.2f} → {v1:.2f} V over {dur:.1f} h)",
            transform=ax.transAxes,
            ha="right",
            va="top",
            fontsize=8,
            color="black",
        )
    ax.set_xlim(TIMELINE_XLO, TIMELINE_XHI)
    # Fixed 3.4–4.2 V range: 4.2 V is the full-charge ceiling (max), 3.4 V the floor.
    ax.set_ylim(3.4, 4.2)
    ax.set_yticks([3.4, 3.6, 3.8, 4.0, 4.2])
    ax.set_ylabel("Battery (V)", fontsize=9)
    ax.set_xlabel("Recording time (hours)", fontsize=10)
    ax.xaxis.set_major_locator(mtick.MultipleLocator(1))
    ax.xaxis.set_minor_locator(mtick.MultipleLocator(0.5))
    return ax


def _lost_rfi_timestamps(csv_path, span_lo, span_hi):
    """Return (unix_times_of_lost_frames, t0_of_chunk).

    "Lost" = a frame_num inside the shared session span [span_lo, span_hi] that
    this DAQ did NOT survive (no RFI with >=8 buffers); one timestamp per lost
    fn_mode. The span (from survival_summary.json) is the union of both DAQs'
    delivered frames, so the terminal MCU-reboot collapse is excluded — the same
    boundary used for the headline totals.
    """
    df = pd.read_csv(
        csv_path,
        usecols=["frame_num", "reconstructed_frame_index", "buffer_recv_unix_time"],
    )

    fn_start, fn_end, _, _ = afd.pick_start_end(df["frame_num"])
    if fn_start is None:
        return np.array([]), None

    mask = afd.valid_mask(df["frame_num"])
    per_rfi = (
        df[mask]
        .groupby("reconstructed_frame_index")
        .agg(
            n_buffers=("frame_num", "size"),
            fn_mode=("frame_num", lambda s: s.mode().iat[0] if len(s) else -1),
            ts=("buffer_recv_unix_time", "min"),
        )
    )

    # Surviving fn_modes (any RFI with >=8 buffers whose fn_mode is in range)
    in_range = (per_rfi["fn_mode"] >= fn_start) & (per_rfi["fn_mode"] <= fn_end)
    surviving_fn = set(
        per_rfi.loc[(per_rfi["n_buffers"] >= 8) & in_range, "fn_mode"].unique()
    )

    # Lost = fn_modes inside the shared union span that didn't survive here.
    lost = per_rfi[
        (per_rfi["fn_mode"] >= span_lo)
        & (per_rfi["fn_mode"] <= span_hi)
        & (~per_rfi["fn_mode"].isin(surviving_fn))
    ]
    if len(lost) == 0:
        times = np.array([])
    else:
        times = lost.groupby("fn_mode")["ts"].min().values

    t0 = float(per_rfi["ts"].min())
    return times, t0


def gather_timestamps():
    """Compute DAQ1, DAQ2, stitched lost-frame unix_times and the global t0.

    DAQ1/DAQ2 lost marks are cut to the same per-pair union span used for the
    headline totals (output/survival_summary.json), so the timeline and the bars
    agree and the MCU-reboot tails are excluded on both DAQs.
    """
    summary = load_summary()
    daq1_span = {
        p["daq1_segment"]: (p["span_first_fn"], p["span_last_fn"])
        for p in summary["per_pair"].values()
    }
    daq2_span = {
        p["daq2_segment"]: (p["span_first_fn"], p["span_last_fn"])
        for p in summary["per_pair"].values()
    }

    print("Gathering DAQ1 lost MCU-frame timestamps...")
    daq1_times = []
    daq1_t0 = None
    for seg in dict.fromkeys(p[0] for p in afd.PAIRS):
        csv = afd.find_csv(DAQ1_DIR, seg)
        if csv is None or seg not in daq1_span:
            continue
        lo, hi = daq1_span[seg]
        t, t0 = _lost_rfi_timestamps(csv, lo, hi)
        daq1_times.append(t)
        daq1_t0 = t0 if daq1_t0 is None else min(daq1_t0, t0)
        print(f"  DAQ1 {seg}: {len(t):,} lost MCU frames")
    daq1_times = np.concatenate(daq1_times) if daq1_times else np.array([])

    print("Gathering DAQ2 lost MCU-frame timestamps...")
    daq2_times = []
    daq2_t0 = None
    for seg in dict.fromkeys(p[1] for p in afd.PAIRS):
        csv = afd.find_csv(DAQ2_DIR, seg)
        if csv is None or seg not in daq2_span:
            continue
        lo, hi = daq2_span[seg]
        t, t0 = _lost_rfi_timestamps(csv, lo, hi)
        daq2_times.append(t)
        daq2_t0 = t0 if daq2_t0 is None else min(daq2_t0, t0)
        print(f"  DAQ2 {seg}: {len(t):,} lost MCU frames")
    daq2_times = np.concatenate(daq2_times) if daq2_times else np.array([])

    print("Gathering stitched both-lost timestamps...")
    # Stitched both-lost = frames that failed on BOTH DAQs mid-recording
    # (frame_num-union method; see compute_stitched_survival.py).
    st = pd.read_csv(f"{OUT_DIR}/stitched_both_lost.csv")
    stitched_times = st["unix_time"].dropna().to_numpy()
    print(f"  stitched both-lost frames: {len(stitched_times):,}")

    # t0 = recording start, taken from the raw DAQ streams (the both-lost file
    # holds only a handful of frames, so its min time is not the session start).
    t0_global = min(
        daq1_t0 if daq1_t0 is not None else float("inf"),
        daq2_t0 if daq2_t0 is not None else float("inf"),
    )
    return daq1_times, daq2_times, stitched_times, t0_global


def _good_battery(csv_path):
    """Return (unix_times, volts) for non-bit-flipped battery samples.

    battery_voltage_raw is bit-flipped by the wireless link like frame_num, so
    reject outliers in raw ADC counts via a rolling-median filter (battery
    drifts slowly, so a small absolute tolerance cleanly catches single-bit
    flips), then convert the survivors to volts.
    """
    df = pd.read_csv(csv_path, usecols=["battery_voltage_raw", "buffer_recv_unix_time"])
    df = df.sort_values("buffer_recv_unix_time")
    raw = df["battery_voltage_raw"].astype(float)

    # Drop NaN and physically impossible ADC counts (8-bit field)
    plausible = raw.notna() & (raw >= 0) & (raw <= 255)

    med = raw.rolling(BATT_OUTLIER_WINDOW, center=True, min_periods=11).median()
    good = plausible & (raw - med).abs().le(BATT_OUTLIER_TOL)

    times = df.loc[good, "buffer_recv_unix_time"].to_numpy()
    volts = raw[good].to_numpy() * BATT_VOLTS_PER_COUNT
    return times, volts


def gather_battery(t0_global):
    """Battery voltage (V) over the recording, on a uniform hours grid.

    Both DAQs decode the *same* physical device battery, so we merge every good
    battery sample from *all* DAQ1 + DAQ2 chunks (whichever link delivered a
    clean reading at each moment). This covers the full session even where one
    DAQ's chunking leaves gaps. Keeps only good samples, applies a simple
    moving average (BATT_SMA_WINDOW, matching MiniscopeZeroPlots), and
    interpolates across the rejected/missing slots (np.interp).
    Returns (hours_grid, volts_smoothed_interp), or (empty, empty) if no data.
    """
    print("Gathering battery voltage (DAQ1 + DAQ2, all chunks)...")
    all_t, all_v = [], []
    n_good = 0
    for daq_dir, daq_name in ((DAQ1_DIR, "DAQ1"), (DAQ2_DIR, "DAQ2")):
        for csv in sorted(glob.glob(os.path.join(daq_dir, "*.csv"))):
            try:
                t, v = _good_battery(csv)
            except (ValueError, KeyError):
                continue  # chunk lacks the battery columns
            if len(t) == 0:
                continue
            all_t.append(t)
            all_v.append(v)
            n_good += len(t)
            print(f"  {daq_name} {os.path.basename(csv)}: {len(t):,} good samples")

    if not all_t or n_good == 0:
        return np.array([]), np.array([])

    times = np.concatenate(all_t)
    volts = np.concatenate(all_v)
    order = np.argsort(times)
    times, volts = times[order], volts[order]

    # Simple moving average over the time-ordered per-sample series
    # (same as MiniscopeZeroPlots battery_level.py _smooth).
    volts_sma = (
        pd.Series(volts).rolling(BATT_SMA_WINDOW, min_periods=1).mean().to_numpy()
    )

    hours = (times - t0_global) / 3600.0
    grid = np.arange(hours.min(), hours.max(), 1.0 / (3600.0 * BATTERY_GRID_HZ))
    volts_interp = np.interp(grid, hours, volts_sma)

    print(
        f"  total good: {n_good:,} samples from both DAQs; "
        f"SMA window {BATT_SMA_WINDOW}; "
        f"interpolated onto {len(grid):,}-point grid; "
        f"battery {volts_interp[0]:.2f} V → {volts_interp[-1]:.2f} V; "
        f"coverage {hours.min():.2f}–{hours.max():.2f} h"
    )

    np.savez(
        f"{OUT_DIR}/battery_voltage_timeline.npz",
        good_hours=hours,
        good_volts=volts,
        good_volts_sma=volts_sma,
        grid_hours=grid,
        grid_volts=volts_interp,
    )
    return grid, volts_interp


def load_summary():
    """Unified DAQ1/DAQ2/stitched totals + per-pair spans (one boundary for all)."""
    with open(f"{OUT_DIR}/survival_summary.json") as f:
        return json.load(f)


def plot_bar_compare(old_pcts, new_pcts, labels, out_path_png, out_path_pdf):
    """Side-by-side bars: old AVI-broken vs new MCU-survival loss rates."""
    fig, ax = plt.subplots(figsize=(7, 4))
    x = np.arange(len(labels))
    width = 0.38

    bars_old = ax.bar(
        x - width / 2,
        old_pcts,
        width,
        color="#CCCCCC",
        edgecolor="white",
        label="Old (AVI broken-frame detector)",
    )
    bars_new = ax.bar(
        x + width / 2,
        new_pcts,
        width,
        color=[C_DAQ1, C_DAQ2, C_COMBINED],
        edgecolor="white",
        label="New (MCU survival, all 8 buffers)",
    )

    for bar, v in zip(bars_old, old_pcts):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            v + 0.1,
            f"{v:.2f}%",
            ha="center",
            va="bottom",
            fontsize=9,
            color="0.3",
        )
    for bar, v in zip(bars_new, new_pcts):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            v + 0.1,
            f"{v:.2f}%",
            ha="center",
            va="bottom",
            fontsize=9,
            fontweight="bold",
        )

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Frame loss rate (%)")
    ax.set_title(
        "Frame loss: AVI-broken (old) vs MCU-survival (new)\n"
        "Old metric double-counts the mio bit-flip amplification"
    )
    ax.legend(loc="upper right", fontsize=9, frameon=False)
    ax.grid(axis="y", alpha=0.3)
    ax.set_ylim(0, max(max(old_pcts), max(new_pcts)) * 1.25)

    fig.tight_layout()
    fig.savefig(out_path_png)
    fig.savefig(out_path_pdf)
    plt.close(fig)


def plot_timeline(
    daq1_h,
    daq2_h,
    stitched_h,
    daq1_pct,
    daq2_pct,
    stitched_pct,
    battery_h,
    battery_v,
    out_png,
    out_pdf,
):
    """Green survival bar per DAQ (1-min-binned whitening = local loss), with a
    5-min loss-rate area stacked above DAQ1 and DAQ2.

    Green bar = frames retained, whitening where the 1-min loss rate is higher;
    labelled with % retained. DAQ1/DAQ2 also get the 5-min loss area on top
    (dotted overall rate + "% lost" at the right end). Stitched is the bar only.
    """

    retain_cmap = mcolors.LinearSegmentedColormap.from_list(
        "retain", [C_RETAIN, "white"]
    )

    def green_band(ax, hours, pct):
        # 1-min binned loss → green (0 % lost) whitening to white (>= vmax lost).
        loss_pct, _ = _per_bin_loss_pct(hours, TIMELINE_BIN_MINUTES)
        im = ax.imshow(
            loss_pct[np.newaxis, :],
            aspect="auto",
            extent=[TIMELINE_XLO, TIMELINE_XHI, 0, 1],
            origin="lower",
            cmap=retain_cmap,
            vmin=0.0,
            vmax=TIMELINE_VMAX_PCT,
            interpolation="nearest",
            rasterized=True,
        )
        ax.set_xlim(TIMELINE_XLO, TIMELINE_XHI)
        ax.set_ylim(0, 1)
        ax.set_yticks([])
        for s in ("left", "right", "top"):
            ax.spines[s].set_visible(False)
        ax.tick_params(axis="x", labelbottom=False)
        ax.text(
            TIMELINE_XHI - 0.1,
            0.5,
            f"{100.0 - pct:.2f}% retained",
            ha="right",
            va="center",
            fontsize=8,
            fontweight="bold",
            color="white",
            bbox=dict(facecolor=C_RETAIN, edgecolor="none", alpha=0.7, pad=1.5),
        )
        return im

    def area_panel(ax, hours, pct, color, label):
        loss_pct, edges = _per_bin_loss_pct(hours, AREA_BIN_MINUTES)
        centers = 0.5 * (edges[:-1] + edges[1:])
        ax.fill_between(centers, 0, loss_pct, color=color, alpha=0.3, step="mid", lw=0)
        ax.step(centers, loss_pct, where="mid", color=color, lw=0.9)
        ax.axhline(pct, ls=":", lw=1.0, color="black", alpha=0.8)
        ax.set_xlim(TIMELINE_XLO, TIMELINE_XHI)
        ax.set_ylim(0, AREA_YMAX_PCT)
        ax.set_yticks([0, 5, 10])
        ax.tick_params(axis="y", labelsize=7)
        ax.set_ylabel(f"Loss per {AREA_BIN_MINUTES:.0f}-min bin (%)", fontsize=7)
        ax.set_title(label, loc="left", fontsize=9, pad=2)
        # Dotted line = overall rate, with the headline % right behind it.
        ax.text(
            0.005,
            0.93,
            f"dotted = overall rate · {pct:.2f}% lost",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=7.5,
            color="black",
        )
        ax.tick_params(axis="x", labelbottom=False)

    fig = plt.figure(figsize=(10, 7.2))
    # Row 0 hosts the green-bar colorbar; the rest are the data panels. The two
    # datastream rows split into [area, green]; the green sub-row ratio (0.9)
    # matches the combined row so all three green bars are the same height.
    outer = fig.add_gridspec(
        5, 1, height_ratios=[0.22, 2.1, 2.1, 0.9, 2.0], hspace=0.55
    )
    share = None
    green_im = None
    # Consistent loss encoding: orange = lost (both streams), green = retained,
    # blue = battery. Streams are distinguished by their row labels.
    for i, (h, label, pct, color) in enumerate(
        [
            (daq1_h, "Wireless datastream 1", daq1_pct, C_DAQ1),
            (daq2_h, "Wireless datastream 2", daq2_pct, C_DAQ1),
        ]
    ):
        inner = outer[i + 1].subgridspec(2, 1, height_ratios=[1.2, 0.9], hspace=0.06)
        ax_line = fig.add_subplot(inner[0], sharex=share)
        share = share or ax_line
        ax_green = fig.add_subplot(inner[1], sharex=share)
        area_panel(ax_line, h, pct, color, label)
        green_im = green_band(ax_green, h, pct)

    # Combined stream: green band only (no meaningful loss to plot above).
    ax_st = fig.add_subplot(outer[3], sharex=share)
    green_band(ax_st, stitched_h, stitched_pct)
    ax_st.set_title("Combined (stream 1 + 2)", loc="left", fontsize=9, pad=2)

    _battery_panel(fig, outer[4], share, battery_h, battery_v)

    # Colorbar for the 1-min-binned green survival bars (green=kept, white=lost).
    cbar_host = fig.add_subplot(outer[0])
    cbar_host.axis("off")
    cbar_ax = cbar_host.inset_axes([0.30, 0.35, 0.40, 0.45])
    cb = fig.colorbar(green_im, cax=cbar_ax, orientation="horizontal")
    cb.set_label("Survival-bar shading: frames lost per 1-min bin (%)", fontsize=7.5)
    cb.set_ticks([0, 5, 10, 15])
    cb.ax.tick_params(labelsize=7, width=0.6)
    cb.outline.set_linewidth(0.5)

    fig.savefig(out_png)
    fig.savefig(out_pdf)
    plt.close(fig)


def run():
    daq1_times, daq2_times, stitched_times, t0_global = gather_timestamps()

    daq1_h = (daq1_times - t0_global) / 3600.0 if len(daq1_times) else daq1_times
    daq2_h = (daq2_times - t0_global) / 3600.0 if len(daq2_times) else daq2_times
    stitched_h = (
        (stitched_times - t0_global) / 3600.0 if len(stitched_times) else stitched_times
    )

    battery_h, battery_v = gather_battery(t0_global)

    summary = load_summary()
    totals = summary["totals"]

    daq1_pct = totals["DAQ1"]["loss_pct"]
    daq2_pct = totals["DAQ2"]["loss_pct"]
    stitched_pct = totals["stitched_both_lost"]["loss_pct"]

    daq1_n = totals["DAQ1"]["lost"]
    daq2_n = totals["DAQ2"]["lost"]
    stitched_n = totals["stitched_both_lost"]["lost"]

    print("\nHeadline loss rates (≥8-buffer survival; shared session-end cut):")
    print(f"  DAQ1 alone:        {daq1_pct}%  ({daq1_n:,} lost)")
    print(f"  DAQ2 alone:        {daq2_pct}%  ({daq2_n:,} lost)")
    print(f"  Dual-DAQ stitched: {stitched_pct}%  ({stitched_n:,} lost)")

    plot_timeline(
        daq1_h,
        daq2_h,
        stitched_h,
        daq1_pct,
        daq2_pct,
        stitched_pct,
        battery_h,
        battery_v,
        f"{OUT_DIR}/publication_survival_timeline.png",
        f"{OUT_DIR}/publication_survival_timeline.pdf",
    )
    print("\nSaved: publication_survival_timeline.png/.pdf")

    # Old-metric numbers from plot_drop_timeline.py hardcodes + the 0.20%
    # stitched rate. These are the publication numbers being superseded.
    old_daq1 = 5.33
    old_daq2 = 0.75
    old_stitched = 0.20
    plot_bar_compare(
        old_pcts=[old_daq1, old_daq2, old_stitched],
        new_pcts=[daq1_pct, daq2_pct, stitched_pct],
        labels=["DAQ 1 alone", "DAQ 2 alone", "Dual-DAQ stitched"],
        out_path_png=f"{OUT_DIR}/publication_survival_bar.png",
        out_path_pdf=f"{OUT_DIR}/publication_survival_bar.pdf",
    )
    print("Saved: publication_survival_bar.png/.pdf")


if __name__ == "__main__":
    run()
