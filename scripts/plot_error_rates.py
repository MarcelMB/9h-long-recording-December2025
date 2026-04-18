#!/usr/bin/env python3
"""Publication-quality figures for dual-DAQ error rate comparison (trimmed data)."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np

OUTPUT_DIR = "/Users/mbrosch/Documents/9h_long_recording_December2025/output"

# ── Trimmed data from summary.json ──
total_matched = 645_619
both_broken = 1_290
rescued_total = 35_775
both_good = total_matched - both_broken - rescued_total  # 608,554

# Error rates (trimmed)
daq1_pct = 5.33
daq2_pct = 0.75
combined_pct = 0.20

# Approximate rescued split using untrimmed ratio (32904:3008)
rescued_from_daq1 = round(rescued_total * 32904 / (32904 + 3008))  # DAQ1 bad, DAQ2 good
rescued_from_daq2 = rescued_total - rescued_from_daq1               # DAQ2 bad, DAQ1 good

# ── Shared style ──
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

# Colors — colorblind-friendly palette
C_DAQ1     = "#D55E00"   # vermillion
C_DAQ2     = "#0072B2"   # blue
C_COMBINED = "#009E73"   # green
C_GOOD     = "#E8E8E8"   # light gray
C_RESCUED1 = "#56B4E9"   # sky blue (rescued from DAQ1 noise)
C_RESCUED2 = "#F0E442"   # yellow  (rescued from DAQ2 noise)
C_LOST     = "#CC79A7"   # pink    (both broken)



# ═══════════════════════════════════════════════════
# Figure 3: Vertical bar chart — corrupted % only
# ═══════════════════════════════════════════════════
pct_lost = 100 * both_broken / total_matched

fig3, ax3 = plt.subplots(figsize=(3.0, 3.2))

conditions = ["DAQ 1\nalone", "DAQ 2\nalone", "Dual-DAQ\nstitched"]
rates = [daq1_pct, daq2_pct, pct_lost]
colors = [C_DAQ1, C_DAQ2, C_COMBINED]

bars = ax3.bar(conditions, rates, width=0.55, color=colors, edgecolor="white", linewidth=0.5)

# Value labels on bars
for bar, rate in zip(bars, rates):
    label = f"{rate:.2f}%" if rate < 1 else f"{rate}%"
    ax3.text(
        bar.get_x() + bar.get_width() / 2,
        bar.get_height() + 0.12,
        label,
        ha="center", va="bottom", fontsize=9, fontweight="bold",
    )

# "64.5 s of ~9 h" under the combined bar value
ax3.text(
    bars[2].get_x() + bars[2].get_width() / 2,
    rates[2] + 0.55,
    "64.5 s of ~9 h",
    ha="center", va="bottom", fontsize=7, color="0.4",
)

ax3.set_ylabel("Corrupted frames (%)", fontsize=10)
ax3.set_ylim(0, 6.5)
ax3.yaxis.set_major_locator(mtick.MultipleLocator(1))
ax3.yaxis.set_minor_locator(mtick.MultipleLocator(0.5))
ax3.tick_params(axis="x", length=0)
ax3.set_title("Dual-DAQ redundancy reduces frame loss", fontsize=10, pad=8)

fig3.savefig(f"{OUTPUT_DIR}/publication_frame_composition.png")
fig3.savefig(f"{OUTPUT_DIR}/publication_frame_composition.pdf")
print(f"Saved: publication_frame_composition.png/.pdf")
plt.close(fig3)

print("\nDone. Numbers used (trimmed):")
print(f"  Good in both:       {both_good:>8} ({100*both_good/total_matched:.2f}%)")
print(f"  Rescued from DAQ1:  {rescued_from_daq1:>8} ({100*rescued_from_daq1/total_matched:.2f}%)")
print(f"  Rescued from DAQ2:  {rescued_from_daq2:>8} ({100*rescued_from_daq2/total_matched:.2f}%)")
print(f"  Lost (both broken): {both_broken:>8} ({100*both_broken/total_matched:.2f}%)")
print(f"  Total matched:      {total_matched:>8}")
