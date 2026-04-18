#!/usr/bin/env python3
"""Timeline of dropped frames across the 9h recording — DAQ1, DAQ2, and both-broken."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import csv
import json
import glob
import os
import numpy as np

BASE_DIR = "/Users/mbrosch/Documents/9h_long_recording_December2025"
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
DAQ1_DIR = os.path.join(BASE_DIR, "neural_DAQ1")
DAQ2_DIR = os.path.join(BASE_DIR, "neural_DAQ2")

plt.rcParams.update({
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
})

# Colors — match the bar chart palette
C_DAQ1     = "#D55E00"   # vermillion
C_DAQ2     = "#0072B2"   # blue
C_COMBINED = "#009E73"   # green (both broken — matches frame composition plot)

# ── Chunk pairing table ──
PAIRS = [
    # (daq1_csv_label, daq1_res_label, daq2_csv_label, daq2_res_label, trim_s)
    ("long-2",  "long-2",   "long",     "long",     30),
    ("long-4",  "long-4",   "long-2",   "long-2",   0),
    ("long-6",  "long-6",   "long-4",   "long-4",   0),
    ("long-8",  "long-8",   "long-6",   "long-6",   0),
    ("long-9",  "long-9",   "long-7",   "long-7",   155),
    ("long-10", "long-10",  "long-8",   "long-8",   0),
    ("long-12", "long-12",  "long-9",   "long-9",   0),
    ("long-13", "long-13",  "long-10",  "long-10",  0),
]

def get_frame_timestamps(csv_path):
    frame_times = {}
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            fidx = int(row["reconstructed_frame_index"])
            t = float(row["buffer_recv_unix_time"])
            if fidx not in frame_times or t > frame_times[fidx]:
                frame_times[fidx] = t
    return frame_times

def get_broken_set(results_json_path):
    with open(results_json_path) as f:
        d = json.load(f)
    broken = set()
    for key in ["black_frames", "gradient_frames", "both_frames", "bright_frames"]:
        for entry in d.get(key, []):
            broken.add(entry["frame"])
    return broken, d["total_frames"]

def find_csv(directory, label):
    pattern = os.path.join(directory, f"*{label}.csv")
    matches = glob.glob(pattern)
    if not matches:
        for f in glob.glob(os.path.join(directory, "*.csv")):
            base = os.path.basename(f).replace(".csv", "")
            if base.endswith(f"_{label}") or base.endswith(f"-{label}") or base == label:
                return f
    return matches[0] if matches else None

print("Computing dropped frame timestamps for all 3 conditions...")
daq1_drop_times = []    # DAQ1 broken (regardless of DAQ2)
daq2_drop_times = []    # DAQ2 broken (regardless of DAQ1)
both_drop_times = []    # both DAQs broken simultaneously
t0_global = None

for daq1_csv_label, daq1_res_label, daq2_csv_label, daq2_res_label, trim_s in PAIRS:
    daq1_csv = find_csv(DAQ1_DIR, daq1_csv_label)
    daq2_csv = find_csv(DAQ2_DIR, daq2_csv_label)
    daq1_json = os.path.join(DAQ1_DIR, "results", f"{daq1_res_label}.json")
    daq2_json = os.path.join(DAQ2_DIR, "results", f"{daq2_res_label}.json")

    daq1_broken, daq1_total = get_broken_set(daq1_json)
    daq2_broken, daq2_total = get_broken_set(daq2_json)

    daq1_ftimes = {k: v for k, v in get_frame_timestamps(daq1_csv).items() if k < daq1_total}
    daq2_ftimes = {k: v for k, v in get_frame_timestamps(daq2_csv).items() if k < daq2_total}

    daq2_frames_sorted = sorted(daq2_ftimes.keys(), key=lambda k: daq2_ftimes[k])
    daq2_times_sorted = np.array([daq2_ftimes[k] for k in daq2_frames_sorted])

    # Find the last valid timestamp for trimming
    all_daq1_times = sorted(daq1_ftimes.values())
    if trim_s > 0 and all_daq1_times:
        max_time = all_daq1_times[-1] - trim_s
    else:
        max_time = float("inf")

    for daq1_fidx in sorted(daq1_ftimes.keys()):
        t1 = daq1_ftimes[daq1_fidx]
        if t1 > max_time:
            continue  # trimmed tail

        idx = np.searchsorted(daq2_times_sorted, t1)
        best_dist = float("inf")
        best_daq2_fidx = None
        for candidate in [idx - 1, idx]:
            if 0 <= candidate < len(daq2_times_sorted):
                dist = abs(daq2_times_sorted[candidate] - t1)
                if dist < best_dist:
                    best_dist = dist
                    best_daq2_fidx = daq2_frames_sorted[candidate]

        if best_dist > 0.025:
            continue

        if t0_global is None:
            t0_global = t1

        # Classify this matched frame pair
        d1_broken = daq1_fidx in daq1_broken
        d2_broken = best_daq2_fidx in daq2_broken

        if d1_broken:
            daq1_drop_times.append(t1)
        if d2_broken:
            daq2_drop_times.append(t1)
        if d1_broken and d2_broken:
            both_drop_times.append(t1)

# Convert to hours relative to recording start
daq1_drops_h = np.array([(t - t0_global) / 3600 for t in daq1_drop_times])
daq2_drops_h = np.array([(t - t0_global) / 3600 for t in daq2_drop_times])
both_drops_h = np.array([(t - t0_global) / 3600 for t in both_drop_times])

print(f"DAQ1 broken frames (raw):  {len(daq1_drops_h)}")
print(f"DAQ2 broken frames (raw):  {len(daq2_drops_h)}")
print(f"Both broken frames (raw):  {len(both_drops_h)}")

# Official trimmed counts from combine_daqs summary
total_matched = 645_619
official_daq1  = round(total_matched * 5.33 / 100)   # 34,411
official_daq2  = round(total_matched * 0.75 / 100)    #  4,842
official_both  = 1_290

# Scale factors to map raw counts → official trimmed counts
scale_daq1 = official_daq1 / len(daq1_drops_h)
scale_daq2 = official_daq2 / len(daq2_drops_h)
scale_both = official_both / len(both_drops_h)
print(f"Scale factors: DAQ1={scale_daq1:.3f}, DAQ2={scale_daq2:.3f}, Both={scale_both:.3f}")

# ── Combined figure: 3 horizontal timelines + horizontal bars ──
fps = 20.0
daq1_pct = 5.33
daq2_pct = 0.75
combined_pct = 100 * official_both / total_matched  # 0.20%

# Layout: 3 rows x 2 columns (timeline | bar)
fig = plt.figure(figsize=(10, 4.5))
gs = fig.add_gridspec(3, 2, width_ratios=[4, 1.5], wspace=0.15, hspace=0.4)

datasets = [
    (0, daq1_drops_h, C_DAQ1,     "DAQ 1 alone",        daq1_pct,     official_daq1),
    (1, daq2_drops_h, C_DAQ2,     "DAQ 2 alone",        daq2_pct,     official_daq2),
    (2, both_drops_h, C_COMBINED, "Dual-DAQ stitched",   combined_pct, official_both),
]

ax_t_first = None
ax_b_first = None

for row, drops_h, color, label, pct, n_official in datasets:
    # Timeline axis
    if ax_t_first is None:
        ax_t = fig.add_subplot(gs[row, 0])
        ax_t_first = ax_t
    else:
        ax_t = fig.add_subplot(gs[row, 0], sharex=ax_t_first)

    # Bar axis
    if ax_b_first is None:
        ax_b = fig.add_subplot(gs[row, 1])
        ax_b_first = ax_b
    else:
        ax_b = fig.add_subplot(gs[row, 1], sharex=ax_b_first)

    # ── Timeline: horizontal strip, drops as vertical lines ──
    ax_t.axhspan(0, 1, color="#F5F5F5", zorder=0)

    for t in drops_h:
        ax_t.plot([t, t], [0, 1], color=color, lw=0.01, alpha=0.9, zorder=2)

    ax_t.set_xlim(-0.2, 9.2)
    ax_t.set_ylim(-0.05, 1.05)
    ax_t.set_yticks([])
    ax_t.spines["left"].set_visible(False)
    ax_t.spines["right"].set_visible(False)
    ax_t.spines["top"].set_visible(False)

    # Row label on the left
    ax_t.set_ylabel(label, fontsize=9, rotation=0, ha="right", va="center",
                    labelpad=10)

    # Only bottom row gets x-axis label
    if row < 2:
        ax_t.tick_params(axis="x", labelbottom=False)
    else:
        ax_t.set_xlabel("Recording time (hours)", fontsize=10)
        ax_t.xaxis.set_major_locator(mtick.MultipleLocator(1))
        ax_t.xaxis.set_minor_locator(mtick.MultipleLocator(0.5))

    # ── Bar: horizontal bar for this condition ──
    ax_b.barh([0], [pct], height=0.55, color=color,
              edgecolor="white", linewidth=0.5)

    # Percentage label
    ax_b.text(pct + 0.12, 0, f"{pct:.2f}%",
              ha="left", va="center", fontsize=9, fontweight="bold")
    # Time annotation in min:sec
    secs = n_official / fps
    mins = int(secs // 60)
    remaining_secs = secs - mins * 60
    sec_label = f"{mins} min {remaining_secs:.0f} s of ~9 h"
    ax_b.text(pct + 0.12, -0.25, sec_label,
              ha="left", va="top", fontsize=7, color="0.4")

    ax_b.set_yticks([])
    ax_b.set_ylim(-0.5, 0.5)
    ax_b.spines["left"].set_visible(False)
    ax_b.spines["right"].set_visible(False)
    ax_b.spines["top"].set_visible(False)

    # Only bottom row gets x-axis label
    if row < 2:
        ax_b.tick_params(axis="x", labelbottom=False)
    else:
        ax_b.set_xlabel("Corrupted\nframes (%)", fontsize=9)
        ax_b.xaxis.set_major_locator(mtick.MultipleLocator(1))
        ax_b.xaxis.set_minor_locator(mtick.MultipleLocator(0.5))
        ax_b.set_xlim(0, 7.5)

fig.savefig(f"{OUTPUT_DIR}/publication_drop_timeline.png")
fig.savefig(f"{OUTPUT_DIR}/publication_drop_timeline.pdf")
print("Saved: publication_drop_timeline.png/.pdf")
plt.close(fig)
