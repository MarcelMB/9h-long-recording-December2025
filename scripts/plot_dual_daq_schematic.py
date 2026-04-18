#!/usr/bin/env python3
"""3D-perspective schematic of the dual-DAQ box with two photodetectors."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import numpy as np

OUTPUT_DIR = "/Users/mbrosch/Documents/9h_long_recording_December2025/output"

# ── Isometric projection helpers ──
# Simple oblique projection: (x, y, z) -> (screen_x, screen_y)
# x = left-right, y = depth (into screen), z = up
ANGLE = 20  # degrees for depth axis — flatter to show more top surface
DEPTH_SCALE = 0.55  # foreshortening

def project(x, y, z):
    """Oblique projection from 3D to 2D."""
    rad = np.radians(ANGLE)
    sx = x + y * DEPTH_SCALE * np.cos(rad)
    sy = z + y * DEPTH_SCALE * np.sin(rad)
    return sx, sy

def draw_face(ax, corners_3d, color, edgecolor="0.25", lw=0.8, alpha=1.0, zorder=2):
    """Draw a filled polygon from 3D corners."""
    pts = [project(*c) for c in corners_3d]
    poly = plt.Polygon(pts, facecolor=color, edgecolor=edgecolor, lw=lw, alpha=alpha, zorder=zorder)
    ax.add_patch(poly)
    return pts

# ── Colors ──
C_BOX_TOP    = "#B0B0B0"
C_BOX_FRONT  = "#888888"
C_BOX_SIDE   = "#9A9A9A"
C_DAQ1       = "#D55E00"   # vermillion
C_DAQ2       = "#0072B2"   # blue
C_DAQ1_SIDE  = "#B04D00"
C_DAQ2_SIDE  = "#005A8C"
C_DAQ1_FRONT = "#C05500"
C_DAQ2_FRONT = "#006399"
C_SENSOR     = "#2D2D2D"
C_LED        = "#44BB44"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 10,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.2,
})

fig, ax = plt.subplots(figsize=(5.5, 4.5))
ax.set_aspect("equal")
ax.axis("off")

# ═══════════════════════════════════════════
# Main box — 50x50x50 cm cube
# ═══════════════════════════════════════════
bw, bd, bh = 8, 8, 8  # cube proportions

# Open box — no top face
draw_face(ax, [(0,0,0), (bw,0,0), (bw,0,bh), (0,0,bh)], C_BOX_FRONT, zorder=1)
draw_face(ax, [(bw,0,0), (bw,bd,0), (bw,bd,bh), (bw,0,bh)], C_BOX_SIDE, zorder=1)
# Back wall (visible above front wall from this angle)
draw_face(ax, [(0,bd,0), (bw,bd,0), (bw,bd,bh), (0,bd,bh)], "#A0A0A0", zorder=0)
# Left wall
draw_face(ax, [(0,0,0), (0,bd,0), (0,bd,bh), (0,0,bh)], "#A5A5A5", zorder=0)
# Floor
draw_face(ax, [(0,0,0), (bw,0,0), (bw,bd,0), (0,bd,0)], "#C0C0C0", zorder=0)

# Top rim edges (no filled top face — open box)
for edge in [
    [(0,0,bh), (bw,0,bh)],
    [(bw,0,bh), (bw,bd,bh)],
    [(bw,bd,bh), (0,bd,bh)],
    [(0,bd,bh), (0,0,bh)],
]:
    pts = [project(*p) for p in edge]
    ax.plot([pts[0][0], pts[1][0]], [pts[0][1], pts[1][1]],
            color="0.25", lw=0.8, zorder=2)

# ═══════════════════════════════════════════
# Two small DAQ photodetectors floating ABOVE the box
# ═══════════════════════════════════════════
pw, pd, ph = 1.6, 1.6, 0.45   # small DAQ modules
gap = 1.5                      # gap between them
float_h = 2.0                  # height above box rim
total_w = 2 * pw + gap
margin_x = (bw - total_w) / 2
margin_y = (bd - pd) / 2
dz = bh + float_h             # z base of floating DAQs

# DAQ 1 — left
d1x = margin_x
d1y = margin_y

draw_face(ax,
    [(d1x, d1y, dz), (d1x+pw, d1y, dz), (d1x+pw, d1y, dz+ph), (d1x, d1y, dz+ph)],
    C_DAQ1_FRONT, zorder=3)
draw_face(ax,
    [(d1x+pw, d1y, dz), (d1x+pw, d1y+pd, dz), (d1x+pw, d1y+pd, dz+ph), (d1x+pw, d1y, dz+ph)],
    C_DAQ1_SIDE, zorder=3)
draw_face(ax,
    [(d1x, d1y, dz+ph), (d1x+pw, d1y, dz+ph), (d1x+pw, d1y+pd, dz+ph), (d1x, d1y+pd, dz+ph)],
    C_DAQ1, zorder=3)

# DAQ 2 — right
d2x = d1x + pw + gap
d2y = margin_y

draw_face(ax,
    [(d2x, d2y, dz), (d2x+pw, d2y, dz), (d2x+pw, d2y, dz+ph), (d2x, d2y, dz+ph)],
    C_DAQ2_FRONT, zorder=3)
draw_face(ax,
    [(d2x+pw, d2y, dz), (d2x+pw, d2y+pd, dz), (d2x+pw, d2y+pd, dz+ph), (d2x+pw, d2y, dz+ph)],
    C_DAQ2_SIDE, zorder=3)
draw_face(ax,
    [(d2x, d2y, dz+ph), (d2x+pw, d2y, dz+ph), (d2x+pw, d2y+pd, dz+ph), (d2x, d2y+pd, dz+ph)],
    C_DAQ2, zorder=3)

# ═══════════════════════════════════════════
# Sensor windows (dark rectangles on top of each detector)
# ═══════════════════════════════════════════
sw, sd = 0.7, 0.7  # sensor size

for dx, dy in [(d1x, d1y), (d2x, d2y)]:
    sx = dx + (pw - sw) / 2
    sy = dy + (pd - sd) / 2
    sz = dz + ph
    draw_face(ax,
        [(sx, sy, sz+0.01), (sx+sw, sy, sz+0.01), (sx+sw, sy+sd, sz+0.01), (sx, sy+sd, sz+0.01)],
        C_SENSOR, edgecolor="0.15", lw=0.6, zorder=4)
    # Small LED indicator
    lx, ly = dx + pw * 0.12, dy + pd * 0.75
    led_pts = draw_face(ax,
        [(lx, ly, sz+0.01), (lx+0.15, ly, sz+0.01), (lx+0.15, ly+0.15, sz+0.01), (lx, ly+0.15, sz+0.01)],
        C_LED, edgecolor="0.3", lw=0.3, zorder=4)

# ═══════════════════════════════════════════
# Green processing box above the DAQs
# ═══════════════════════════════════════════
C_PROC       = "#009E73"   # green — matches dual-DAQ color
C_PROC_FRONT = "#008060"
C_PROC_SIDE  = "#007558"

proc_w, proc_d, proc_h = total_w + gap, pd, 0.45
proc_x = margin_x - gap / 2
proc_y = margin_y
proc_z = dz + ph + 2.5  # above the DAQs with space for arrows

draw_face(ax,
    [(proc_x, proc_y, proc_z), (proc_x+proc_w, proc_y, proc_z),
     (proc_x+proc_w, proc_y, proc_z+proc_h), (proc_x, proc_y, proc_z+proc_h)],
    C_PROC_FRONT, zorder=3)
draw_face(ax,
    [(proc_x+proc_w, proc_y, proc_z), (proc_x+proc_w, proc_y+proc_d, proc_z),
     (proc_x+proc_w, proc_y+proc_d, proc_z+proc_h), (proc_x+proc_w, proc_y, proc_z+proc_h)],
    C_PROC_SIDE, zorder=3)
draw_face(ax,
    [(proc_x, proc_y, proc_z+proc_h), (proc_x+proc_w, proc_y, proc_z+proc_h),
     (proc_x+proc_w, proc_y+proc_d, proc_z+proc_h), (proc_x, proc_y+proc_d, proc_z+proc_h)],
    C_PROC, zorder=3)

# ═══════════════════════════════════════════
# Arrows from each DAQ up to the green box
# ═══════════════════════════════════════════
d1_top_cx, d1_top_cy = project(d1x + pw/2, d1y + pd/2, dz + ph + 0.05)
d2_top_cx, d2_top_cy = project(d2x + pw/2, d2y + pd/2, dz + ph + 0.05)
proc_bot_l_cx, proc_bot_l_cy = project(d1x + pw/2, d1y + pd/2, proc_z - 0.05)
proc_bot_r_cx, proc_bot_r_cy = project(d2x + pw/2, d2y + pd/2, proc_z - 0.05)

ax.annotate("", xy=(proc_bot_l_cx, proc_bot_l_cy), xytext=(d1_top_cx, d1_top_cy),
            arrowprops=dict(arrowstyle="-|>", color="0.3", lw=1.2), zorder=5)
ax.annotate("", xy=(proc_bot_r_cx, proc_bot_r_cy), xytext=(d2_top_cx, d2_top_cy),
            arrowprops=dict(arrowstyle="-|>", color="0.3", lw=1.2), zorder=5)

# ═══════════════════════════════════════════
# Labels
# ═══════════════════════════════════════════
# DAQ 1 label
d1_cx, d1_cy = project(d1x + pw/2, d1y + pd/2, dz + ph + 0.01)
ax.text(d1_cx - 3.0, d1_cy + 0.5, "DAQ 1", ha="center", va="bottom",
        fontsize=11, fontweight="bold", color=C_DAQ1,
        bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor=C_DAQ1, alpha=0.9, lw=0.8))
ax.annotate("", xy=(d1_cx, d1_cy + 0.1), xytext=(d1_cx - 3.0, d1_cy + 0.5),
            arrowprops=dict(arrowstyle="-|>", color=C_DAQ1, lw=1.0,
                            connectionstyle="arc3,rad=0.15"))

# DAQ 2 label
d2_cx, d2_cy = project(d2x + pw/2, d2y + pd/2, dz + ph + 0.01)
ax.text(d2_cx + 3.0, d2_cy + 0.5, "DAQ 2", ha="center", va="bottom",
        fontsize=11, fontweight="bold", color=C_DAQ2,
        bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor=C_DAQ2, alpha=0.9, lw=0.8))
ax.annotate("", xy=(d2_cx, d2_cy + 0.1), xytext=(d2_cx + 3.0, d2_cy + 0.5),
            arrowprops=dict(arrowstyle="-|>", color=C_DAQ2, lw=1.0,
                            connectionstyle="arc3,rad=-0.15"))

# Green box label — to the right
proc_cx, proc_cy = project(proc_x + proc_w/2, proc_y + proc_d/2, proc_z + proc_h/2)
ax.text(proc_cx + 6.5, proc_cy, "Post-acquisition\nprocessing:\ncombining both\ndatastreams",
        ha="center", va="center", fontsize=8.5, fontweight="bold", color="0.15")
ax.annotate("", xy=(proc_cx + 0.5, proc_cy), xytext=(proc_cx + 4.5, proc_cy),
            arrowprops=dict(arrowstyle="-|>", color="0.3", lw=1.0))

# Box label on front face
box_cx, box_cy = project(bw/2, 0, bh * 0.5)
ax.text(box_cx, box_cy, "Behavior arena", ha="center", va="center",
        fontsize=11, color="white", fontweight="bold", zorder=5)

# Set limits with padding
ax.set_xlim(-4, 17)
ax.set_ylim(-1.5, 16)

fig.savefig(f"{OUTPUT_DIR}/publication_dual_daq_schematic.png")
fig.savefig(f"{OUTPUT_DIR}/publication_dual_daq_schematic.pdf")
print("Saved: publication_dual_daq_schematic.png/.pdf")
plt.close(fig)
