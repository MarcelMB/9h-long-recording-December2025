# Concrete example: one `frame_num` bit-flip → three AVI frames from one MCU frame

**Source:** `neural_DAQ1/WL27_DAQ1_25_12_10_long-4.csv`, rows 155,489–155,504
(raw rows also extracted to `output/frame_num_bitflip_example.csv`).

## What each row is

Each row in the CSV is **one 4-byte buffer** sent over the wireless radio.
A real MCU frame is **8 consecutive buffers** that all carry the same
`frame_num` in their header, and a `frame_buffer_count` running 0 → 7. The
host-side mio library watches the `frame_num` field: every time it sees
`frame_num` change, it declares "new frame" and increments
`reconstructed_frame_index` (RFI) — which is also the index of the frame in
the output `.avi` file.

Below: MCU frame **20189** was sent intact as 8 buffers, but one of them
(`frame_buffer_count = 1`) arrived with a bit-flipped header. That single
corrupt buffer causes mio to emit **three separate AVI frames** from this one
real MCU frame.

## The raw rows (with annotations)

| RFI | frame_num | buffer_count | fbc | what's happening |
|----:|----------:|-------------:|----:|-------------------|
| 19768 | 20188 | 161,507 | 4 | previous MCU frame (20188), buffers 4–7 complete |
| 19768 | 20188 | 161,508 | 5 | |
| 19768 | 20188 | 161,509 | 6 | |
| 19768 | 20188 | 161,510 | 7 | end of previous MCU frame |
| **19769** | **20189** | **161,511** | **0** | MCU frame **20189** starts (buffer 0) — mio sees `frame_num` change 20188→20189, emits previous, opens RFI 19769 |
| **19770** | **20173** ⚠️ | **145,128** ⚠️ | **1** | ⚠️ same MCU frame 20189, but this buffer's header is **bit-flipped**: `frame_num` reads 20173, `buffer_count` reads 145,128. mio sees `frame_num` change 20189→20173, emits RFI 19769 (just 1 buffer), opens RFI 19770 |
| **19771** | **20189** | **161,513** | **2** | back to real `frame_num = 20189` (buffer 2). mio sees change 20173→20189, emits RFI 19770 (just 1 buffer — the junk frame), opens RFI 19771 |
| 19771 | 20189 | 161,514 | 3 | remainder of MCU frame 20189 accumulates in RFI 19771 |
| 19771 | 20189 | 161,515 | 4 | |
| 19771 | 20189 | 161,516 | 5 | |
| 19771 | 20189 | 161,517 | 6 | |
| 19771 | 20189 | 161,518 | 7 | end of MCU frame 20189 |
| 19772 | 20190 | 161,519 | 0 | next MCU frame (20190) starts normally |
| 19772 | 20190 | 161,520 | 1 | |
| 19772 | 20190 | 161,521 | 2 | |
| 19772 | 20190 | 161,522 | 3 | |

Note the clean counters that tell us the bit-flipped buffer really *is* buffer
1 of MCU frame 20189:

- `frame_buffer_count` reads 1 (correct — it didn't get flipped)
- `buffer_count` reads 145,128, but the sequence on either side is
  161,511 / 161,513 / 161,514… — the true value should be 161,512.
- The exact flips are both **single-bit**:
  - `frame_num`:    20,189 XOR 20,173 = 16    = 0x00000010  (1 bit flipped)
  - `buffer_count`: 161,512 XOR 145,128 = 16,384 = 0x00004000  (1 bit flipped)
- `buffer_recv_unix_time` is monotonic across the three RFIs — host-side
  time confirms these buffers arrived continuously, not as separate frames.

## What ends up in the AVI

| RFI | buffers | AVI frame content |
|----:|--------:|-------------------|
| 19769 | **1** | head of MCU frame 20189 — 1 of 8 buffers present → **bottom 7/8 of image is black** |
| 19770 | **1** | the bit-flipped buffer on its own — **7/8 of image is black** (spurious "frame") |
| 19771 | **6** | tail of MCU frame 20189 — 6 of 8 buffers present → **bottom 2/8 of image is black** |

Three AVI frames where the MCU sent one. All three get flagged as broken by
the pixel-based detectors in `scripts/analyze_frames.py`.

## The causal chain, one picture

```
MCU sent MCU frame 20189 as 8 buffers (fbc 0..7):
  [20189 20189 20189 20189 20189 20189 20189 20189] [20190 20190 ...]

Wireless link flips two bits in one header (buffer fbc=1):
  [20189 20173 20189 20189 20189 20189 20189 20189] [20190 20190 ...]
         ^^^^^
         corrupted

mio sees THREE frame_num transitions instead of one:
  1)  20188 → 20189   → emit previous frame (RFI 19768), open RFI 19769
  2)  20189 → 20173   → emit 1-buffer RFI 19769, open RFI 19770
  3)  20173 → 20189   → emit 1-buffer RFI 19770  ← the "junk" AVI frame
  4)  20189 → 20190   → emit 6-buffer RFI 19771

Result: 3 AVI frames produced from 1 real MCU frame, all visibly broken.
```

## Why this explains the error rates

This pattern repeats throughout the recording. From
`scripts/diagnose_rfi_surplus.py`:

- DAQ1 long-4 alone: **1,857** real MCU frame_nums got split across
  multiple RFIs, producing **1,932 surplus AVI frames** and **1,691 "tiny"**
  (1–2 buffer) AVI frames — all visibly broken.
- Across all 15 chunks / 7 hours: **~14,600 surplus AVI frames** on top of
  the **1,201,516 frames the MCU actually sent**.
- Every surplus frame plus its "partner" (the truncated real frame next to
  it) contributes to the visible-broken-frame rate — DAQ1 **5.96 %** / DAQ2
  **1.40 %** under the AVI-broken-frame detector (v3). Collapsing these
  back to one event per real MCU frame — the MCU-survival metric used in
  `docs/results.md` — gives **DAQ1 3.43 %, DAQ2 0.37 %, Dual-DAQ stitched
  0.10 %** (trimmed, ≥8-buffer survival). The asymmetry tracks directly with
  header-corruption rate: DAQ1 has ~6× more bit-flipped headers than DAQ2,
  and ~9× the MCU-level loss rate.

**Important:** the MCU-counter analysis (`scripts/analyze_frame_num_drops.py`)
separately shows **zero silent drops** across the same data — every frame
the device counted off arrived with at least one buffer. So the wireless
link isn't losing whole frames; it's corrupting a tiny fraction of buffer
headers, and the *host-side reconstruction logic* amplifies each single-bit
header flip into multiple broken output frames.

## Where in mio this happens

Single code location: `miniscope-io/mio/stream_daq.py` (commit `94c737b2`,
branch `feat-stitch-video`).

- `_buffer_to_frame` (around line 385) — emits a frame whenever the incoming
  buffer's `frame_num` differs from the previous buffer's `frame_num`. No
  validation that the change is monotonic (+1) or that the new value is
  plausible given recent history.
- `_format_frame` (lines 493 + 504) — assigns the current
  `frame_index_counter` to every buffer of the emitted group and then
  increments the counter.

A sanity check at `_buffer_to_frame` — for example, "ignore a single
buffer's `frame_num` excursion if the next buffer reverts to the previous
value" — would eliminate the large majority of the ~14,600 surplus frames
on this recording.

## Files referenced

- `output/frame_num_bitflip_example.csv` — the 16-row extract used above
- `output/frame_num_drops_summary.json` — per-chunk silent-drop numbers (all 0)
- `output/frame_count_layers.json` — the four frame-count layers per chunk
- `output/frame_count_layers.png`, `output/drop_method_comparison.png` — plots
- `scripts/analyze_frame_num_drops.py`, `scripts/diagnose_rfi_surplus.py`,
  `scripts/extract_bitflip_example.py` — analysis pipeline
