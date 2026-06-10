#!/usr/bin/env python3
"""Methods schematic for the dual-datastream survival + combine pipeline.

Illustration (not data). Two steps:

  Step 1 — Detect lost frames within each wireless datastream:
    * a frame is delivered only if >= 8 buffers reconstruct it;
    * frame_num resets every ~1 h session (the MCU errors out and reboots);
    * the MCU degrades into a lost "tail" just before each reboot, which the
      session-end cut excludes.

  Step 2 — Combine the two datastreams:
    * align by MCU frame_num and keep a good copy from EITHER datastream;
    * a frame is lost only if both datastreams failed (rare).

Output: output/method_schematic.png / .pdf
"""

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = f"{BASE}/output"

GREEN = "#1B9E5A"  # frame kept / retained
ORANGE = "#D55E00"  # frame lost
GREY = "#C9C9C9"  # missing buffer / trimmed
BLUE = "#0072B2"  # received buffer
INK = "#222222"

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.2,
    }
)


def cell(ax, x, y, w, h, fc, ec="white", hatch=None, lw=1.0, alpha=1.0):
    ax.add_patch(
        Rectangle(
            (x, y),
            w,
            h,
            facecolor=fc,
            edgecolor=ec,
            linewidth=lw,
            hatch=hatch,
            alpha=alpha,
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — per-datastream frame survival
# ─────────────────────────────────────────────────────────────────────────────
def draw_step1(ax):
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    ax.text(
        0,
        97,
        "Step 1   Detect lost frames within each wireless datastream",
        fontsize=13,
        fontweight="bold",
        va="top",
    )

    # ── (A) a frame = 8 buffers; >=8 reconstruct it, else it is lost ──
    ax.text(
        0,
        88,
        "Each MCU frame is sent as 8 buffers over the optical link:",
        fontsize=9.5,
        va="top",
    )

    def buffers(x0, y0, n_ok):
        bw, gap = 2.0, 0.5
        for k in range(8):
            fc = BLUE if k < n_ok else "white"
            ec = BLUE if k < n_ok else GREY
            cell(ax, x0 + k * (bw + gap), y0, bw, 4.5, fc, ec=ec, lw=1.0)

    # good case
    buffers(4, 78, 8)
    ax.annotate(
        "",
        xy=(33, 80.2),
        xytext=(24, 80.2),
        arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.3),
    )
    cell(ax, 34, 77, 7, 6.5, GREEN)
    ax.text(43, 80.2, "8 buffers  →  frame kept", fontsize=9, va="center")

    # lost case
    buffers(4, 69, 5)
    ax.annotate(
        "",
        xy=(33, 71.2),
        xytext=(24, 71.2),
        arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.3),
    )
    cell(ax, 34, 68, 7, 6.5, ORANGE)
    ax.text(
        43,
        71.2,
        "< 8 buffers (dropped / bit-flipped)  →  frame lost",
        fontsize=9,
        va="center",
    )

    # ── (B) a datastream over time: sessions, resets, end tails ──
    ax.text(
        0,
        59,
        "The same datastream over the recording (one row of MCU frames):",
        fontsize=9.5,
        va="top",
    )

    cw, cgap, ch = 2.4, 0.35, 9.0
    ybase = 34
    # 3 sessions; each: good frames, one mid loss, and a trimmed tail
    states = (
        ["g", "g", "g", "x", "g", "g", "g", "t", "t"],
        ["g", "g", "x", "g", "g", "g", "g", "t", "t"],
        ["g", "g", "g", "g", "x", "g", "g", "t", "t"],
    )
    fc_map = {"g": GREEN, "x": ORANGE, "t": ORANGE}
    sess_w = len(states[0]) * (cw + cgap)
    sgap = 7.0
    x_starts = [4 + s * (sess_w + sgap) for s in range(3)]

    for s, x0 in enumerate(x_starts):
        for k, st in enumerate(states[s]):
            x = x0 + k * (cw + cgap)
            hatch = "////" if st == "t" else None
            cell(ax, x, ybase, cw, ch, fc_map[st], hatch=hatch, lw=0.8)
        # frame_num bracket above the session
        x_end = x0 + sess_w - cgap
        ax.annotate(
            "",
            xy=(x_end, ybase + ch + 4),
            xytext=(x0, ybase + ch + 4),
            arrowprops=dict(arrowstyle="-", color=GREY, lw=1.0),
        )
        ax.text(x0, ybase + ch + 5, "0", fontsize=7, color="0.4", ha="center")
        ax.text(x_end, ybase + ch + 5, "~80k", fontsize=7, color="0.4", ha="center")
        ax.text(
            x0 + sess_w / 2,
            ybase + ch + 8.5,
            f"session {s + 1}  ·  frame_num",
            fontsize=7.5,
            color="0.4",
            ha="center",
        )

    # reboot arrows between sessions
    for s in range(2):
        x_gap = x_starts[s] + sess_w + sgap / 2
        ax.annotate(
            "",
            xy=(x_starts[s + 1] - 0.5, ybase + ch / 2),
            xytext=(x_starts[s] + sess_w - 0.5, ybase + ch / 2),
            arrowprops=dict(
                arrowstyle="-|>", color=INK, lw=1.2, connectionstyle="arc3,rad=-0.5"
            ),
        )
        ax.text(
            x_gap,
            ybase + ch + 1.5,
            "reboot\nframe_num → 0",
            fontsize=6.8,
            color=INK,
            ha="center",
            va="bottom",
        )

    # callouts
    ax.text(
        x_starts[0] + 3 * (cw + cgap) + cw / 2,
        ybase - 3,
        "lost frame\n(buffers dropped)",
        fontsize=7.5,
        color=ORANGE,
        ha="center",
        va="top",
    )
    ax.annotate(
        "",
        xy=(x_starts[0] + 3 * (cw + cgap) + cw / 2, ybase - 0.5),
        xytext=(x_starts[0] + 3 * (cw + cgap) + cw / 2, ybase - 2.8),
        arrowprops=dict(arrowstyle="-|>", color=ORANGE, lw=1.1),
    )

    tail_x = x_starts[2] + 7 * (cw + cgap)
    ax.text(
        tail_x + cw,
        ybase - 3,
        "MCU degrades before reboot →\nend tail (excluded by session-end cut)",
        fontsize=7.5,
        color="0.35",
        ha="center",
        va="top",
    )
    ax.annotate(
        "",
        xy=(tail_x + cw, ybase - 0.5),
        xytext=(tail_x + cw, ybase - 2.8),
        arrowprops=dict(arrowstyle="-|>", color="0.35", lw=1.1),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — combine: keep a good frame from either datastream
# ─────────────────────────────────────────────────────────────────────────────
def draw_step2(ax):
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    ax.text(
        0,
        97,
        "Step 2   Combine: keep a good copy from either datastream",
        fontsize=13,
        fontweight="bold",
        va="top",
    )
    ax.text(
        0,
        88,
        "Align both datastreams by MCU frame_num; for each frame keep whichever "
        "datastream delivered it. Lost only if BOTH failed.",
        fontsize=9.5,
        va="top",
    )

    n = 14
    x0 = 26
    cw, cgap, ch = 4.6, 0.5, 11
    y_ds1, y_ds2, y_comb = 64, 50, 28

    # lost columns
    ds1_lost = {3, 8, 11}
    ds2_lost = {6, 11}  # col 11 = both lost (rare)

    def row(y, lost, label):
        ax.text(x0 - 2, y + ch / 2, label, fontsize=9, ha="right", va="center")
        for k in range(n):
            fc = ORANGE if k in lost else GREEN
            cell(ax, x0 + k * (cw + cgap), y, cw, ch, fc, lw=0.8)

    row(y_ds1, ds1_lost, "Wireless\ndatastream 1")
    row(y_ds2, ds2_lost, "Wireless\ndatastream 2")

    # combined row: lost only where both lost
    both_lost = ds1_lost & ds2_lost
    ax.text(
        x0 - 2,
        y_comb + ch / 2,
        "Combined\n(stream 1 + 2)",
        fontsize=9,
        ha="right",
        va="center",
        fontweight="bold",
    )
    for k in range(n):
        fc = ORANGE if k in both_lost else GREEN
        cell(ax, x0 + k * (cw + cgap), y_comb, cw, ch, fc, lw=0.8, ec="white")

    def cx(k):
        return x0 + k * (cw + cgap) + cw / 2

    # rescue arrows: pick the good source into the combined cell
    def rescue(k, y_src):
        ax.annotate(
            "",
            xy=(cx(k), y_comb + ch + 0.5),
            xytext=(cx(k), y_src - 0.5),
            arrowprops=dict(arrowstyle="-|>", color=GREEN, lw=1.6),
        )

    rescue(3, y_ds2)  # ds1 lost → take ds2
    rescue(8, y_ds2)  # ds1 lost → take ds2
    rescue(6, y_ds1)  # ds2 lost → take ds1

    ax.text(
        cx(3) - 1,
        (y_ds2 + y_comb) / 2 + 1,
        "stream 1 lost → keep stream 2",
        fontsize=7.5,
        color=GREEN,
        ha="left",
        va="center",
    )
    ax.text(
        cx(6) + cw,
        (y_ds1 + y_comb) / 2 + 6,
        "stream 2 lost →\nkeep stream 1",
        fontsize=7.5,
        color=GREEN,
        ha="left",
        va="center",
    )

    # both-lost callout
    ax.annotate(
        "both failed → lost (rare, ~0.007 %)",
        xy=(cx(11), y_comb - 0.5),
        xytext=(cx(11) + 3, y_comb - 9),
        fontsize=7.8,
        color=ORANGE,
        ha="left",
        va="center",
        arrowprops=dict(arrowstyle="-|>", color=ORANGE, lw=1.1),
    )

    # legend
    cell(ax, x0, 8, 3.2, 3.2, GREEN)
    ax.text(x0 + 4.2, 9.6, "frame kept", fontsize=8.5, va="center")
    cell(ax, x0 + 26, 8, 3.2, 3.2, ORANGE)
    ax.text(x0 + 30, 9.6, "frame lost", fontsize=8.5, va="center")


def run():
    fig = plt.figure(figsize=(11, 9.5))
    gs = fig.add_gridspec(2, 1, height_ratios=[1.08, 1.0], hspace=0.12)
    draw_step1(fig.add_subplot(gs[0]))
    draw_step2(fig.add_subplot(gs[1]))
    for ext in ("png", "pdf"):
        fig.savefig(f"{OUT_DIR}/method_schematic.{ext}")
    plt.close(fig)
    print("Saved: output/method_schematic.png / .pdf")


if __name__ == "__main__":
    run()
