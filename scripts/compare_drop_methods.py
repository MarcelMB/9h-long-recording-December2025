#!/usr/bin/env python3
"""Side-by-side comparison of the two silent-drop methods.

Method A (host timestamps):
  scripts/analyze_silent_drops.py  -> output/silent_drops_summary.json
Method B (MCU frame_num counter):
  scripts/analyze_frame_num_drops.py -> output/frame_num_drops_summary.json

Emits:
  output/drop_method_comparison.json  — per-chunk table, per-DAQ totals
  output/drop_method_comparison.png   — grouped bars, both methods per chunk
"""

import json
import os

import numpy as np
import matplotlib.pyplot as plt


BASE_DIR = "/Users/mbrosch/Documents/9h_long_recording_December2025"
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

TS_JSON = os.path.join(OUTPUT_DIR, "silent_drops_summary.json")
FN_JSON = os.path.join(OUTPUT_DIR, "frame_num_drops_summary.json")


def load(path):
    with open(path) as f:
        return json.load(f)


def build_comparison():
    ts = load(TS_JSON)
    fn = load(FN_JSON)

    out = {
        "methods": {
            "timestamp": {
                "source": "host buffer_recv_unix_time, gap > 75 ms",
                "fps": ts["fps"],
                "gap_threshold_ms": ts["gap_threshold_ms"],
            },
            "frame_num": {
                "source": "MCU frame_num counter, intended - delivered",
                "fps": fn["fps"],
                "head_window": fn["head_window"],
                "tail_window": fn["tail_window"],
            },
        },
    }

    for daq_key in ("DAQ1", "DAQ2"):
        ts_rows = {r["file"]: r for r in ts[daq_key]["per_file"]}
        fn_rows = {r["file"]: r for r in fn[daq_key]["per_file"]}
        files = list(ts_rows.keys())
        # Preserve ordering from fn (which processes chunks in PAIRS order);
        # add any timestamp-only files at the end.
        ordered = [r["file"] for r in fn[daq_key]["per_file"]]
        for f in files:
            if f not in ordered:
                ordered.append(f)

        rows = []
        ts_total = 0
        fn_total = 0
        intended_total = 0
        for f in ordered:
            ts_row = ts_rows.get(f)
            fn_row = fn_rows.get(f)
            row = {
                "file": f,
                "ts_drops": ts_row["host_ts_drops"] if ts_row else None,
                "ts_gap_events": ts_row["host_ts_gap_events"] if ts_row else None,
                "ts_analyzed_frames": ts_row["analyzed_frames"] if ts_row else None,
                "fn_drops": fn_row["silent_drops"] if fn_row else None,
                "fn_intended": fn_row["intended"] if fn_row else None,
                "fn_delivered": fn_row["delivered"] if fn_row else None,
                "fn_flags": fn_row["flags"] if fn_row else None,
                "delta": (
                    (fn_row["silent_drops"] - ts_row["host_ts_drops"])
                    if (fn_row and ts_row and fn_row["silent_drops"] is not None)
                    else None
                ),
            }
            rows.append(row)
            if row["ts_drops"] is not None:
                ts_total += row["ts_drops"]
            if row["fn_drops"] is not None:
                fn_total += row["fn_drops"]
            if row["fn_intended"] is not None:
                intended_total += row["fn_intended"]

        out[daq_key] = {
            "per_file": rows,
            "totals": {
                "timestamp_drops": ts_total,
                "frame_num_drops": fn_total,
                "frame_num_intended": intended_total,
                "delta_fn_minus_ts": fn_total - ts_total,
                "timestamp_rate_pct": (
                    round(100.0 * ts_total / intended_total, 4) if intended_total else None
                ),
                "frame_num_rate_pct": (
                    round(100.0 * fn_total / intended_total, 4) if intended_total else None
                ),
            },
        }

    return out


def plot_comparison(comparison, out_path):
    fig, axes = plt.subplots(2, 1, figsize=(15, 9))
    for ax, daq_key in zip(axes, ("DAQ1", "DAQ2")):
        rows = comparison[daq_key]["per_file"]
        if not rows:
            ax.set_title(f"{daq_key}: no files")
            continue
        labels = [r["file"].replace(".csv", "").replace("WL27_", "") for r in rows]
        x = np.arange(len(labels))
        ts_drops = [r["ts_drops"] or 0 for r in rows]
        fn_drops = [r["fn_drops"] or 0 for r in rows]
        bar_w = 0.4
        ax.bar(x - bar_w / 2, ts_drops, width=bar_w, color="#1f77b4", label="method A: host timestamps")
        ax.bar(x + bar_w / 2, fn_drops, width=bar_w, color="#d62728", label="method B: MCU frame_num")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)
        ax.set_ylabel("silent drops per chunk")
        t = comparison[daq_key]["totals"]
        ax.set_title(
            f"{daq_key} — method A total: {t['timestamp_drops']}  "
            f"method B total: {t['frame_num_drops']}  "
            f"(MCU intended {t['frame_num_intended']})"
        )
        ax.legend(loc="upper right", fontsize=9)
        ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def print_tables(comparison):
    for daq_key in ("DAQ1", "DAQ2"):
        print(f"\n=== {daq_key} ===")
        print(f"{'chunk':<40} {'ts_drops':>9} {'fn_drops':>9} {'intended':>9} {'delivered':>10} {'delta':>7}")
        for r in comparison[daq_key]["per_file"]:
            print(
                f"{r['file']:<40} "
                f"{str(r['ts_drops']):>9} "
                f"{str(r['fn_drops']):>9} "
                f"{str(r['fn_intended']):>9} "
                f"{str(r['fn_delivered']):>10} "
                f"{str(r['delta']):>7}"
            )
        t = comparison[daq_key]["totals"]
        print(
            f"  totals: ts={t['timestamp_drops']} fn={t['frame_num_drops']} "
            f"intended={t['frame_num_intended']} delta={t['delta_fn_minus_ts']} "
            f"ts_rate={t['timestamp_rate_pct']}% fn_rate={t['frame_num_rate_pct']}%"
        )


def run():
    comparison = build_comparison()
    out_json = os.path.join(OUTPUT_DIR, "drop_method_comparison.json")
    with open(out_json, "w") as f:
        json.dump(comparison, f, indent=2)
    out_png = os.path.join(OUTPUT_DIR, "drop_method_comparison.png")
    plot_comparison(comparison, out_png)
    print_tables(comparison)
    print(f"\nWritten: {out_json}")
    print(f"Written: {out_png}")


if __name__ == "__main__":
    run()
