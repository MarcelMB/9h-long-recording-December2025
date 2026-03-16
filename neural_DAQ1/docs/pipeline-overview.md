# Pipeline Overview

## Recording Setup

- **Subject:** WL27 wireless miniscope, ~9 hours continuous recording (Dec 10, 2025)
- **Two DAQs** received the same wireless signal simultaneously as redundancy
- **Format:** 200x200 grayscale, 20 fps, raw AVI (fourcc=0)
- **Segments:** 8 paired recording segments per DAQ (DAQ numbering is offset, not matched by name)

## Pipeline Scripts

Run order is managed by `run_full_pipeline.py`:

### Phase 1–2: `analyze_frames.py`

Scans each AVI independently for broken frames. Writes:
- `results/<label>.json` — per-frame broken status with category (black/gradient/both)
- `debug_detectors/<stem>_black.avi` — all black-flagged frames
- `debug_detectors/<stem>_gradient.avi` — all gradient-flagged frames
- `debug_detectors/<stem>_both.avi` — frames with both artifacts

Shared by both DAQ1 and DAQ2 (same script, different directories).

### Phase 3: `combine_daqs.py`

Matches DAQ1 and DAQ2 frames by unix timestamp (25ms threshold from buffer-level CSVs). Reports:
- Per-segment and total error rates for each DAQ alone
- Combined error rate (both DAQs broken simultaneously)
- Number of rescued frames (broken in one DAQ, good in the other)

### Phase 4: `create_stitched_video.py`

Builds the final clean video from matched frame pairs:
- For each matched pair, picks the best frame (prefers DAQ2 when both are good)
- Skips frames where both DAQs are broken
- Outputs 1-hour chunks: `output/WL27_stitched_chunk_XX.avi`
- Saves max projection PNGs per chunk
- Writes aggregate debug AVIs (broken from each DAQ + per-type black/gradient)

**Trimming:** `long-2` (last 30s) and `long-9` (last 155s) are trimmed where the miniscope was off.

### Phase 5: `analyze_drops.py`

Analyzes the temporal distribution of dropped frames (both DAQs broken) in the stitched stream:
- Consecutive run statistics (min/max/mean/median)
- Run length distribution
- Timeline and density plots (`output/drop_analysis.png`)
- Raw data export (`output/drop_analysis.json`)

## Segment Pairing

DAQ1 and DAQ2 segment labels don't match — they are paired by timestamp:

| DAQ1 | DAQ2 |
|------|------|
| long-2 | long |
| long-4 | long-2 |
| long-6 | long-4 |
| long-8 | long-6 |
| long-9 | long-7 |
| long-10 | long-8 |
| long-12 | long-9 |
| long-13 | long-10 |
