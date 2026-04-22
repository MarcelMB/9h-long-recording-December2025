#!/usr/bin/env python3
"""Per-chunk figure of the four frame-count layers, from device to disk.

For each raw CSV chunk (DAQ1 + DAQ2, same PAIRS as the silent-drop scripts),
we have four nested "frame count" signals:

  1. MCU intended       = fn_end − fn_start + 1                (from frame_num)
     frames the device's counter says it tried to transmit
  2. Link delivered     = unique valid frame_num in range      (from frame_num)
     MCU frames for which at least one of the 8 buffers arrived
  3. Host reconstructed = unique reconstructed_frame_index     (from CSV)
     frames the host reassembled from the buffers that arrived
  4. AVI frames         = cv2 CAP_PROP_FRAME_COUNT             (from .avi)
     frames written to disk by the capture pipeline

Each comparison measures a different loss surface:
  - intended → delivered:  wireless link (silent drops)
  - delivered → reconstructed: host-side reconstruction (partial frames, etc.)
  - reconstructed → AVI:   any write-side loss

Output:
  output/frame_count_layers.png   — grouped bars per chunk, one panel per DAQ
  output/frame_count_layers.json  — per-chunk numbers for both DAQs
"""

import glob
import json
import os
import sys

import cv2
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(__file__))
import analyze_frame_num_drops as afd


BASE_DIR = "/Users/mbrosch/Documents/9h_long_recording_December2025"
DAQ1_DIR = os.path.join(BASE_DIR, "neural_DAQ1")
DAQ2_DIR = os.path.join(BASE_DIR, "neural_DAQ2")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")


def find_avi(daq_dir, label):
    """AVI filename can have a segment suffix like '-012'; match both forms."""
    for pattern in (f"*_{label}.avi", f"*_{label}-*.avi"):
        matches = glob.glob(os.path.join(daq_dir, pattern))
        if matches:
            return sorted(matches)[0]
    return None


def count_avi_frames(path):
    cap = cv2.VideoCapture(path)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    return n


def per_chunk_counts(csv_path, avi_path):
    df = pd.read_csv(csv_path, usecols=["frame_num", "reconstructed_frame_index"])

    fn_start, fn_end, _, _ = afd.pick_start_end(df["frame_num"])
    mask = afd.valid_mask(df["frame_num"])
    vfn = df["frame_num"][mask]

    intended = fn_end - fn_start + 1
    delivered = int(vfn[(vfn >= fn_start) & (vfn <= fn_end)].nunique())
    reconstructed = int(df["reconstructed_frame_index"].nunique())
    avi = count_avi_frames(avi_path) if avi_path and os.path.exists(avi_path) else None

    return {
        "intended": int(intended),
        "delivered": delivered,
        "reconstructed": reconstructed,
        "avi": avi,
    }


def collect():
    per_daq = {"DAQ1": {}, "DAQ2": {}}
    labels_by_daq = {
        "DAQ1": list(dict.fromkeys(p[0] for p in afd.PAIRS)),
        "DAQ2": list(dict.fromkeys(p[1] for p in afd.PAIRS)),
    }
    for daq_key, daq_dir in [("DAQ1", DAQ1_DIR), ("DAQ2", DAQ2_DIR)]:
        for label in labels_by_daq[daq_key]:
            csv = afd.find_csv(daq_dir, label)
            avi = find_avi(daq_dir, label)
            if csv is None:
                print(f"SKIP {daq_key} {label}: no CSV")
                continue
            counts = per_chunk_counts(csv, avi)
            counts["label"] = label
            counts["avi_file"] = os.path.basename(avi) if avi else None
            per_daq[daq_key][label] = counts
            print(
                f"{daq_key} {label}: intended={counts['intended']} "
                f"delivered={counts['delivered']} "
                f"reconstructed={counts['reconstructed']} "
                f"avi={counts['avi']}"
            )
    return per_daq


def plot(per_daq, out_path):
    fig, axes = plt.subplots(2, 1, figsize=(15, 10))
    layers = [
        ("intended",       "#4c72b0", "MCU intended (frame_num range)"),
        ("delivered",      "#55a868", "link delivered (unique frame_num)"),
        ("reconstructed",  "#c44e52", "host reconstructed (unique RFI)"),
        ("avi",            "#8172b2", "AVI frames on disk"),
    ]
    for ax, daq_key in zip(axes, ("DAQ1", "DAQ2")):
        rows = list(per_daq[daq_key].values())
        if not rows:
            ax.set_title(f"{daq_key}: no data")
            continue
        labels = [r["label"] for r in rows]
        x = np.arange(len(labels))
        bar_w = 0.2
        for i, (key, color, name) in enumerate(layers):
            vals = [r[key] if r[key] is not None else 0 for r in rows]
            offset = (i - 1.5) * bar_w
            ax.bar(x + offset, vals, width=bar_w, color=color, label=name)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=9)
        ax.set_ylabel("frames per chunk")
        intended_tot = sum(r["intended"] for r in rows)
        delivered_tot = sum(r["delivered"] for r in rows)
        recon_tot = sum(r["reconstructed"] for r in rows)
        avi_tot = sum(r["avi"] or 0 for r in rows)
        ax.set_title(
            f"{daq_key} — totals: intended {intended_tot:,}  "
            f"delivered {delivered_tot:,}  "
            f"reconstructed {recon_tot:,}  "
            f"AVI {avi_tot:,}"
        )
        ax.legend(loc="lower right", fontsize=8)
        ax.grid(axis="y", alpha=0.3)
        ax.set_ylim(0, max(r["intended"] for r in rows) * 1.15)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def plot_deltas(per_daq, out_path):
    """Companion figure: the per-chunk losses between layers (usually tiny)."""
    fig, axes = plt.subplots(2, 1, figsize=(15, 8))
    for ax, daq_key in zip(axes, ("DAQ1", "DAQ2")):
        rows = list(per_daq[daq_key].values())
        if not rows:
            continue
        labels = [r["label"] for r in rows]
        x = np.arange(len(labels))
        link_loss = [r["intended"] - r["delivered"] for r in rows]
        recon_gain = [r["reconstructed"] - r["delivered"] for r in rows]
        avi_vs_recon = [
            (r["avi"] - r["reconstructed"]) if r["avi"] is not None else 0
            for r in rows
        ]
        bar_w = 0.27
        ax.bar(x - bar_w, link_loss, width=bar_w, color="#55a868", label="link loss (intended − delivered)")
        ax.bar(x,         recon_gain, width=bar_w, color="#c44e52", label="reconstruction surplus (RFI − delivered)")
        ax.bar(x + bar_w, avi_vs_recon, width=bar_w, color="#8172b2", label="AVI − reconstructed")
        ax.axhline(0, color="black", linewidth=0.5)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=9)
        ax.set_ylabel("frame delta")
        ax.set_title(f"{daq_key} — per-chunk differences between frame-count layers")
        ax.legend(loc="upper left", fontsize=8)
        ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def run():
    per_daq = collect()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    json_path = os.path.join(OUTPUT_DIR, "frame_count_layers.json")
    with open(json_path, "w") as f:
        json.dump(per_daq, f, indent=2)
    plot_path = os.path.join(OUTPUT_DIR, "frame_count_layers.png")
    plot(per_daq, plot_path)
    delta_path = os.path.join(OUTPUT_DIR, "frame_count_layers_deltas.png")
    plot_deltas(per_daq, delta_path)
    print(f"\nWritten: {json_path}")
    print(f"Written: {plot_path}")
    print(f"Written: {delta_path}")


if __name__ == "__main__":
    run()
