#!/usr/bin/env python3
"""Compare colleague's bit-flipped-buffer detector with our survival metric.

Colleague's script (/Users/mbrosch/Downloads/find_bad_buffers.py) flags any
row whose `frame_num` differs by > 1 from *both* its neighbours (a rolling
window of 3 centred on the middle element). That isolates single-row header
bit-flips in the wireless link — rows where the buffer's frame_num landed far
from the surrounding 8-buffer group.

Our survival metric (scripts/survival_rate.py) counts MCU frames (denominator =
fn_end − fn_start + 1) for which at least one reconstructed frame index has
≥ 8 buffers with the matching majority `frame_num`.

This script reruns the colleague's detector on the same PAIRS the survival
analysis uses, joins per-chunk, and writes:

    output/compare_colleague_method.json
    output/compare_colleague_method.md
    output/compare_colleague_method.png

Units to keep straight:
- colleague `bad_buffers`  — individual rows (buffers) flagged by the flanked
                              difference test
- colleague `actual_frames`— `len(unique frame_num) − bad_buffers` (his own
                              headline denominator, per-file)
- ours `intended`          — MCU frame_num range (fn_end − fn_start + 1)
- ours `lost_ge8`          — MCU frames with no RFI of ≥ 8 matching buffers
"""

import json
import os
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import analyze_frame_num_drops as afd

BASE = "/Users/mbrosch/Documents/9h_long_recording_December2025"
DAQ_DIRS = {"DAQ1": f"{BASE}/neural_DAQ1", "DAQ2": f"{BASE}/neural_DAQ2"}
OUT_DIR = f"{BASE}/output"

SURVIVAL_JSON = f"{OUT_DIR}/survival_rate.json"


def _flanked_by_badness(x):
    x = np.array(x)
    if len(x) != 3:
        return False
    return bool(np.abs(x[0] - x[1]) > 1 and np.abs(x[1] - x[2]) > 1)


def count_bad_buffers(df):
    """Reimplementation of colleague's count_frame_errors, returns (bad_rows_df, n_bad)."""
    bads = df["frame_num"].rolling(window=3, center=True).apply(_flanked_by_badness)
    bads.loc[pd.isna(bads)] = 0
    bads = bads.astype(bool)
    bad_rows = df.loc[bads, ["frame_num", "reconstructed_frame_index"]].copy()
    return bad_rows, int(len(bad_rows))


def run_colleague_on_pairs():
    """Per-chunk colleague numbers for the same PAIRS our survival uses."""
    labels_by_daq = {
        "DAQ1": list(dict.fromkeys(p[0] for p in afd.PAIRS)),
        "DAQ2": list(dict.fromkeys(p[1] for p in afd.PAIRS)),
    }
    out = {"DAQ1": [], "DAQ2": []}
    for daq_key, daq_dir in DAQ_DIRS.items():
        for label in labels_by_daq[daq_key]:
            csv = afd.find_csv(daq_dir, label)
            if csv is None:
                continue
            df = pd.read_csv(csv, usecols=["frame_num", "reconstructed_frame_index"])
            bad_rows, n_bad = count_bad_buffers(df)
            # Colleague's denominator: unique frame_num values minus flagged rows.
            # (This is what his headline print uses.)
            unique_fn = int(df["frame_num"].nunique())
            actual_frames_colleague = unique_fn - n_bad
            out[daq_key].append({
                "label": label,
                "csv": os.path.basename(csv),
                "total_rows": int(len(df)),
                "unique_frame_num": unique_fn,
                "bad_buffers": n_bad,
                "actual_frames_colleague": actual_frames_colleague,
            })
    return out


def load_survival_per_chunk():
    """Flatten survival_rate.json into {daq_key: {label: {trimmed, untrimmed}}}."""
    with open(SURVIVAL_JSON) as f:
        s = json.load(f)
    flat = {"DAQ1": {}, "DAQ2": {}}
    for daq_key, rows in s["per_chunk"].items():
        for r in rows:
            flat[daq_key][r["label"]] = {
                "trimmed": r["trimmed"],
                "untrimmed": r["untrimmed"],
            }
    return flat, s["totals"]


def join(colleague_per_daq, survival_flat):
    """Per-chunk join — colleague's bad_buffers alongside our lost/intended."""
    joined = {"DAQ1": [], "DAQ2": []}
    for daq_key, rows in colleague_per_daq.items():
        for r in rows:
            surv = survival_flat[daq_key].get(r["label"])
            if surv is None:
                continue
            tr = surv["trimmed"]
            joined[daq_key].append({
                "label": r["label"],
                "colleague_bad_buffers": r["bad_buffers"],
                "colleague_unique_frame_num": r["unique_frame_num"],
                "colleague_actual_frames": r["actual_frames_colleague"],
                "ours_intended": tr["intended"],
                "ours_surviving_ge8": tr["surviving_ge8"],
                "ours_lost_ge8": tr["lost_ge8"],
                "ours_loss_rate_ge8_pct": tr["loss_rate_ge8_pct"],
                "ours_surviving_ge7": tr["surviving_ge7"],
                "ours_lost_ge7": tr["lost_ge7"],
                "ours_loss_rate_ge7_pct": tr["loss_rate_ge7_pct"],
                "colleague_bad_rate_pct": round(
                    100.0 * r["bad_buffers"] / r["unique_frame_num"], 4
                ) if r["unique_frame_num"] else None,
            })
    return joined


def totals(joined):
    t = {}
    for daq_key, rows in joined.items():
        agg = {
            "n_chunks": len(rows),
            "colleague_bad_buffers": sum(r["colleague_bad_buffers"] for r in rows),
            "colleague_unique_frame_num": sum(r["colleague_unique_frame_num"] for r in rows),
            "ours_intended": sum(r["ours_intended"] for r in rows),
            "ours_surviving_ge8": sum(r["ours_surviving_ge8"] for r in rows),
            "ours_lost_ge8": sum(r["ours_lost_ge8"] for r in rows),
            "ours_surviving_ge7": sum(r["ours_surviving_ge7"] for r in rows),
            "ours_lost_ge7": sum(r["ours_lost_ge7"] for r in rows),
        }
        if agg["colleague_unique_frame_num"]:
            agg["colleague_bad_rate_pct"] = round(
                100.0 * agg["colleague_bad_buffers"] / agg["colleague_unique_frame_num"], 4
            )
        if agg["ours_intended"]:
            agg["ours_loss_rate_ge8_pct"] = round(
                100.0 * agg["ours_lost_ge8"] / agg["ours_intended"], 4
            )
            agg["ours_loss_rate_ge7_pct"] = round(
                100.0 * agg["ours_lost_ge7"] / agg["ours_intended"], 4
            )
        t[daq_key] = agg
    return t


def write_markdown(joined, tots, path):
    lines = []
    lines.append("# Colleague method vs. cleaned survival rate")
    lines.append("")
    lines.append("Per-chunk comparison restricted to the PAIRS used by "
                 "`scripts/survival_rate.py` (i.e. chunks 01 and other "
                 "pre-recording chunks excluded).")
    lines.append("")
    lines.append("- **Colleague** (`find_bad_buffers.py`): rolling-3 flanked "
                 "difference flags a buffer row whose `frame_num` jumps by > 1 "
                 "from both neighbours — catches single-row header bit-flips. "
                 "Headline denominator is `len(unique frame_num) − flagged`.")
    lines.append("- **Ours** (`scripts/survival_rate.py`): denominator is the "
                 "MCU `frame_num` range per chunk (`fn_end − fn_start + 1`); "
                 "numerator is MCU frames that have at least one RFI with ≥ 8 "
                 "matching buffers. `loss_ge8` = intended − surviving_ge8.")
    lines.append("")
    for daq_key in ("DAQ1", "DAQ2"):
        rows = joined[daq_key]
        if not rows:
            continue
        lines.append(f"## {daq_key}")
        lines.append("")
        lines.append("| chunk | colleague bad buffers | colleague unique `frame_num` | colleague bad rate | ours intended | ours surv(≥8) | ours lost(≥8) | ours loss rate(≥8) | ours lost(≥7) |")
        lines.append("|------|----------------------:|-----------------------------:|-------------------:|--------------:|--------------:|--------------:|-------------------:|--------------:|")
        for r in rows:
            lines.append(
                f"| `{r['label']}` | {r['colleague_bad_buffers']:,} | "
                f"{r['colleague_unique_frame_num']:,} | "
                f"{r['colleague_bad_rate_pct']:.4f}% | "
                f"{r['ours_intended']:,} | {r['ours_surviving_ge8']:,} | "
                f"{r['ours_lost_ge8']:,} | {r['ours_loss_rate_ge8_pct']:.4f}% | "
                f"{r['ours_lost_ge7']:,} |"
            )
        t = tots[daq_key]
        lines.append(
            f"| **Total** | **{t['colleague_bad_buffers']:,}** | "
            f"**{t['colleague_unique_frame_num']:,}** | "
            f"**{t['colleague_bad_rate_pct']:.4f}%** | "
            f"**{t['ours_intended']:,}** | **{t['ours_surviving_ge8']:,}** | "
            f"**{t['ours_lost_ge8']:,}** | **{t['ours_loss_rate_ge8_pct']:.4f}%** | "
            f"**{t['ours_lost_ge7']:,}** |"
        )
        lines.append("")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def plot(joined, path):
    fig, axes = plt.subplots(2, 1, figsize=(14, 9))
    for ax, daq_key in zip(axes, ("DAQ1", "DAQ2")):
        rows = joined[daq_key]
        if not rows:
            continue
        labels = [r["label"] for r in rows]
        x = np.arange(len(labels))
        w = 0.4
        bad = np.array([r["colleague_bad_buffers"] for r in rows])
        lost_ge8 = np.array([r["ours_lost_ge8"] for r in rows])
        lost_ge7 = np.array([r["ours_lost_ge7"] for r in rows])
        ax.bar(x - w / 2, bad, width=w, color="#1f77b4",
               label="colleague: bit-flipped buffers")
        ax.bar(x + w / 2, lost_ge8, width=w, color="#d62728",
               label="ours: MCU frames lost (≥8-buffer RFI missing)")
        ax.bar(x + w / 2, lost_ge7, width=w, color="#d62728", alpha=0.35,
               label="ours: lost (≥7-buffer)", zorder=0)
        for i, r in enumerate(rows):
            ax.text(x[i] - w / 2, bad[i], f"{bad[i]:,}",
                    ha="center", va="bottom", fontsize=8)
            ax.text(x[i] + w / 2, lost_ge8[i], f"{lost_ge8[i]:,}",
                    ha="center", va="bottom", fontsize=8)
        ax.set_title(f"{daq_key} — colleague bad buffers vs. our MCU-frame loss per chunk")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=9)
        ax.set_ylabel("count per chunk")
        ax.grid(axis="y", alpha=0.3)
        ax.legend(loc="upper right", fontsize=9)
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def main():
    colleague = run_colleague_on_pairs()
    survival_flat, survival_totals = load_survival_per_chunk()
    joined = join(colleague, survival_flat)
    tots = totals(joined)

    summary = {
        "description": "per-chunk join of colleague's bit-flipped-buffer "
                       "detector and our MCU-frame survival metric",
        "pairs_source": "scripts/analyze_frame_num_drops.py PAIRS",
        "colleague_script": "/Users/mbrosch/Downloads/find_bad_buffers.py",
        "our_script": "scripts/survival_rate.py",
        "per_chunk": joined,
        "totals": tots,
    }
    json_path = f"{OUT_DIR}/compare_colleague_method.json"
    md_path = f"{OUT_DIR}/compare_colleague_method.md"
    png_path = f"{OUT_DIR}/compare_colleague_method.png"
    with open(json_path, "w") as f:
        json.dump(summary, f, indent=2)
    write_markdown(joined, tots, md_path)
    plot(joined, png_path)

    print("Totals (PAIRS only):")
    for daq_key, t in tots.items():
        print(
            f"  {daq_key}: colleague bad={t['colleague_bad_buffers']:,} "
            f"({t['colleague_bad_rate_pct']}% of unique fn)  |  "
            f"ours lost(≥8)={t['ours_lost_ge8']:,} "
            f"({t['ours_loss_rate_ge8_pct']}%)  "
            f"lost(≥7)={t['ours_lost_ge7']:,} "
            f"({t['ours_loss_rate_ge7_pct']}%)"
        )
    print(f"\nWrote: {json_path}\n       {md_path}\n       {png_path}")


if __name__ == "__main__":
    main()
