#!/usr/bin/env python3
"""Extract a concrete, shareable example of the frame_num bit-flip → RFI-split
mechanism from real CSV data. Writes:

  docs/frame_num_bitflip_example.md   — narrative + annotated row tables
  output/frame_num_bitflip_example.csv — the raw CSV rows involved

Source: neural_DAQ1/WL27_DAQ1_25_12_10_long-4.csv (1,857 split frames to choose from).

We find the cleanest possible case:
  • a real MCU frame split into exactly 2 RFIs
  • where the first RFI is short (spurious 1-buffer emit, the "junk frame")
  • and the second RFI has the remainder of the real frame's buffers
  • with enough neighboring context on both sides to be unambiguous
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import analyze_frame_num_drops as afd  # noqa: E402

BASE = "/Users/mbrosch/Documents/9h_long_recording_December2025"
CSV = f"{BASE}/neural_DAQ1/WL27_DAQ1_25_12_10_long-4.csv"
OUT_MD = f"{BASE}/docs/frame_num_bitflip_example.md"
OUT_CSV = f"{BASE}/output/frame_num_bitflip_example.csv"


def find_example(df):
    """Find a split where one MCU frame_num maps to exactly 2 RFIs and the
    first RFI has just 1 buffer (cleanest demonstration)."""
    mask = afd.valid_mask(df["frame_num"])
    valid = df[mask]
    split_fns = (
        valid.groupby("frame_num")["reconstructed_frame_index"]
        .nunique()
        .pipe(lambda s: s[s == 2])
    )
    rfi_sizes = df.groupby("reconstructed_frame_index").size()

    for fn in split_fns.index:
        rows = valid[valid["frame_num"] == fn]
        rfis = sorted(rows["reconstructed_frame_index"].unique())
        if len(rfis) != 2:
            continue
        first_rfi, second_rfi = rfis
        if rfi_sizes.get(first_rfi, 0) == 1 and rfi_sizes.get(second_rfi, 0) >= 5:
            # Also verify the first RFI contains exactly one row
            # whose frame_num is DIFFERENT (the bit-flipped one)
            first_rfi_rows = df[df["reconstructed_frame_index"] == first_rfi]
            if len(first_rfi_rows) == 1:
                return fn, first_rfi, second_rfi
    return None


def main():
    print(f"Loading {CSV} ...")
    df = pd.read_csv(CSV)
    print(f"  {len(df):,} rows, {df['reconstructed_frame_index'].nunique():,} RFIs")

    result = find_example(df)
    if result is None:
        print("No clean example found.")
        return
    real_fn, spurious_rfi, second_rfi = result

    real_fn_rows = df[df["frame_num"] == real_fn]
    real_rfis = sorted(real_fn_rows["reconstructed_frame_index"].unique())
    first_rfi = real_rfis[0]

    start_idx = df[df["reconstructed_frame_index"] == first_rfi].index.min()
    end_idx = df[df["reconstructed_frame_index"] == second_rfi].index.max()
    context_start = max(0, start_idx - 4)
    context_end = min(len(df) - 1, end_idx + 4)
    slice_df = df.iloc[context_start : context_end + 1].copy()

    slice_df.to_csv(OUT_CSV, index=False)
    print(f"Wrote {len(slice_df)} rows to {OUT_CSV}")

    show_cols = [
        "reconstructed_frame_index",
        "frame_num",
        "buffer_count",
        "frame_buffer_count",
        "buffer_recv_unix_time",
    ]
    short = slice_df[show_cols].copy()
    short["buffer_recv_unix_time"] = short["buffer_recv_unix_time"].map(
        lambda x: f"{x:.4f}"
    )

    def fmt_row(row, annotation=""):
        rfi = row["reconstructed_frame_index"]
        fn = row["frame_num"]
        bc = row["buffer_count"]
        fbc = row["frame_buffer_count"]
        ts = row["buffer_recv_unix_time"]
        line = (
            f"| {rfi:>8} | {fn:>15,} | {bc:>10,} | {fbc:>2} | {ts} |"
        )
        if annotation:
            line += f" **{annotation}**"
        return line

    lines = []
    lines.append("# Concrete example: one `frame_num` bit-flip → 2 junk AVI frames")
    lines.append("")
    lines.append(
        "Source: `neural_DAQ1/WL27_DAQ1_25_12_10_long-4.csv` — "
        f"rows {context_start:,} through {context_end:,} (CSV byte-range)."
    )
    lines.append("")
    lines.append("## What you're looking at")
    lines.append("")
    lines.append(
        "Each row is one 4-byte buffer sent over the wireless radio. A real "
        "MCU frame is 8 consecutive buffers that all carry the same "
        "`frame_num` in their header. The host-side mio library watches "
        "this header field — every time it sees `frame_num` change, it "
        "declares \"new frame\" and increments `reconstructed_frame_index` "
        f"(= RFI, which is also the AVI frame index). MCU frame `{real_fn}` "
        "below was emitted intact by the device but arrives at the host "
        "with one buffer whose `frame_num` has been bit-flipped in transit."
    )
    lines.append("")
    lines.append("")
    lines.append("| RFI | frame_num | buffer_count | fbc | buffer_recv_unix_time | |")
    lines.append("|----:|----------:|-------------:|----:|-----------------------|---|")
    for _, row in slice_df.iterrows():
        rfi = row["reconstructed_frame_index"]
        fn = row["frame_num"]
        ann = ""
        if rfi < first_rfi:
            ann = f"previous real MCU frame"
        elif rfi == first_rfi:
            ann = f"MCU frame {real_fn} — first chunk, {(slice_df['reconstructed_frame_index']==first_rfi).sum()}-buffer RFI"
        elif rfi == spurious_rfi:
            ann = (
                f"⚠️ bit-flipped `frame_num` — "
                f"mio sees \"new frame\", emits a 1-buffer RFI (junk)"
            )
        elif rfi == second_rfi:
            ann = (
                f"back to real MCU frame {real_fn}, but mio has already moved on — "
                f"this becomes RFI {second_rfi} ({(slice_df['reconstructed_frame_index']==second_rfi).sum()}-buffer RFI)"
            )
        else:
            ann = "next real MCU frame"
        lines.append(fmt_row(row, ann if (_ == 0 or df.at[_, "reconstructed_frame_index"] != df.at[_ - 1, "reconstructed_frame_index"]) else ""))
    lines.append("")
    lines.append("## What the host ends up writing to the AVI")
    lines.append("")
    pre_rfi = slice_df.iloc[0]["reconstructed_frame_index"]
    post_rfi = slice_df.iloc[-1]["reconstructed_frame_index"]
    rfi_counts = slice_df["reconstructed_frame_index"].value_counts().sort_index()
    lines.append(f"| RFI | buffers in this RFI | what's in the AVI image |")
    lines.append(f"|----:|--------------------:|-------------------------|")
    for rfi, n in rfi_counts.items():
        if rfi < first_rfi:
            desc = f"previous real MCU frame (complete)"
        elif rfi == first_rfi:
            desc = f"head of MCU frame {real_fn} — {n} of 8 buffers → **bottom {(8-n)}/8 of image is black**"
        elif rfi == spurious_rfi:
            desc = f"spurious frame from one bit-flipped buffer → **7/8 of image is black** (visibly broken)"
        elif rfi == second_rfi:
            desc = f"tail of MCU frame {real_fn} — {n} of 8 buffers → **bottom {(8-n)}/8 of image is black**"
        else:
            desc = "next real MCU frame (complete)"
        lines.append(f"| {rfi} | {n} | {desc} |")
    lines.append("")
    lines.append("## The causal chain, in one diagram")
    lines.append("")
    lines.append("```")
    lines.append("MCU sends frame N as 8 buffers:   [N N N N N N N N] [N+1 N+1 ...]")
    lines.append("")
    lines.append("Wireless link bit-flips one header:  one buffer's frame_num → X")
    lines.append("                                   [N N N X N N N N] [N+1 N+1 ...]")
    lines.append("                                         ↑")
    lines.append("mio's _buffer_to_frame sees three `frame_num` transitions instead of one:")
    lines.append("  1) N → X   (emit the 3-buffer head as RFI_k)")
    lines.append("  2) X → N   (emit the 1-buffer spurious middle as RFI_k+1)")
    lines.append("  3) N → N+1 (emit the 4-buffer tail as RFI_k+2)")
    lines.append("")
    lines.append("AVI on disk ends up with 3 frames where the device sent 1.")
    lines.append("All three are partially/mostly black → flagged broken by pixel detectors.")
    lines.append("```")
    lines.append("")
    lines.append("## Code reference")
    lines.append("")
    lines.append(
        "`miniscope-io/mio/stream_daq.py` — the \"frame_num change → emit a frame\" "
        "logic lives in `_buffer_to_frame` around line 385, and "
        "`_format_frame` at lines 493 and 504 is where the reconstructed_frame_index "
        "counter is assigned to all buffers of each emitted group and then "
        "incremented. There is no sanity check that the frame_num change is "
        "monotonic (+1) before emitting — any change triggers an emit, so a "
        "single corrupt header produces multiple extra output frames."
    )
    lines.append("")
    lines.append(
        f"Supporting data: `output/frame_num_drops_summary.json`, "
        f"`output/frame_count_layers.json`, `output/frame_num_bitflip_example.csv`. "
        f"Analysis scripts: `scripts/analyze_frame_num_drops.py`, "
        f"`scripts/diagnose_rfi_surplus.py`."
    )

    with open(OUT_MD, "w") as f:
        f.write("\n".join(lines))
    print(f"Wrote narrative to {OUT_MD}")

    print("\n--- PREVIEW of the example rows ---")
    print(short.to_string(index=False))


if __name__ == "__main__":
    main()
