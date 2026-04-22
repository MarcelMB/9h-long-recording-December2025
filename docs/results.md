# Results

## Error Rates

Two metrics, reported with trimming that matches the publication figure
(DAQ1 `long-2` −30 s, `long-9` −155 s; DAQ2 untrimmed).

| Source | MCU survival (new, headline) | AVI broken-frame (old) |
|--------|-----------------------------:|-----------------------:|
| DAQ1 alone | **3.43 %** (21,914 / 638,752 lost) | 5.33 % (v1) / 5.96 % (v3) |
| DAQ2 alone | **0.37 %** (2,096 / 560,945 lost)  | 0.75 % (v1) / 1.40 % (v3) |
| Dual-DAQ stitched † | **0.10 %** (660 / 636,244 lost)   | 0.20 % (v1, both-broken) / 0.84 % (v3) |

**Headline (use in the manuscript):** DAQ1 3.43 %, DAQ2 0.37 %, Stitched 0.10 %
(MCU-level survival, ≥8-buffer RFI required per MCU frame; trimmed.)

> **† Stitched denominator caveat — read before quoting 0.10 %.**
> The stitched denominator is **636,244**, not the full 645,790 stitched
> frames. The missing **~9,500 tail rows** reference DAQ2 RFIs that fall
> **outside the current CSV generation** our survival analysis sees: the
> stitcher was run on a slightly different AVI/CSV export than the current
> survival pipeline, and those tail RFIs have no entry in
> `rfi_survival_all.csv`, so we can't assign a survived/lost verdict to
> them. They are **excluded from the headline** rather than counted as lost
> (counting them as lost would be pessimistic; counting them as survived
> would be optimistic). See `output/survival_rate_stitched.json` field
> `total_unknown_rows`. If you need a loss rate for the full 645,790-frame
> stitched output, it has to wait on re-running the stitcher and the
> survival analysis on the same CSV/AVI generation.

The old AVI-broken-frame rate (`scripts/analyze_frames.py` + black-row / gradient
detectors) **double-counts** the wireless-link events. A single bit-flip in a
buffer's `frame_num` header makes mio's `_buffer_to_frame` emit 2–3 separate
AVI frames from one real MCU frame; each of those fragments is flagged broken.
Per-MCU-frame survival collapses those fragments back to one event, which is
the honest question ("did this frame make it across the wireless link?").
See `docs/frame_num_bitflip_example.md` and miniscope/mio issue #163.

### Untrimmed (for completeness)

| Source | Intended MCU frames | Surviving (≥8 buf) | Loss |
|--------|--------------------:|-------------------:|-----:|
| DAQ1 alone | 640,571 | 616,838 | **3.70 %** |
| DAQ2 alone | 560,945 | 558,849 | **0.37 %** |

(Stitched has no "untrimmed" counterpart — the stitched output was produced
with the same trim applied.)

### Alternative stitched number — `neither_survived`

The direct analog of the old "both broken" 0.20 %: stitched frames where
*neither* DAQ had an ≥ 8-buffer RFI. Only **24 frames (0.004 %)**. The rest
of the 0.10 % headline comes from the stitcher picking DAQ2 at a moment when
only DAQ1 had survived — a picker issue, not a capture failure. A
survival-aware picker would collapse the stitched rate toward 0.004 %.

### Independent cross-check — colleague's bit-flipped-buffer detector

An independent script from a collaborator
(`/Users/mbrosch/Downloads/find_bad_buffers.py`) detects bit-flipped
buffer headers at the row level by flagging any `frame_num` that differs
by > 1 from both neighbours in a rolling-3 window. It doesn't measure
frame survival; it measures *isolated* wireless-link bit-flip events.

Running it on the same PAIRS our survival analysis uses:

| DAQ | Colleague bad buffers | Ours lost(≥8) | Ours lost(≥7) |
|-----|----------------------:|--------------:|--------------:|
| DAQ1 |  6,052 (0.944 %) | 21,914 (3.431 %) | 4,798 (0.751 %) |
| DAQ2 |    115 (0.021 %) |  2,096 (0.374 %) | 1,909 (0.340 %) |

Each isolated bit-flip takes exactly 1 buffer off its true MCU frame, so
the affected frame fails ≥ 8 but passes ≥ 7. That means bit-flips should
account for the *delta* between ≥ 8 and ≥ 7 loss:

- **DAQ1**: `lost(≥8) − lost(≥7) = 17,116`; colleague catches 6,052 of those
  as isolated flips (~35 %); the rest is clustered flips + multi-buffer loss.
- **DAQ2**: `lost(≥8) − lost(≥7) = 187`; the two thresholds are nearly equal,
  so DAQ2 loss is *genuine buffer loss*, not header corruption.

This confirms the DAQ1 vs DAQ2 story: DAQ1's link is noisy at the bit level
(high isolated-flip rate; large ≥ 8 vs ≥ 7 gap), while DAQ2 drops whole buffers
less noisily. The colleague's count also gives a floor — our ≥ 8 loss always
exceeds it, as it must, which rules out the possibility that our survival
numbers are inflated by a pipeline artefact. Which method to cite:

- **Survival rate** (ours) for any "how many frames were lost" claim — it's
  denominated in MCU-intended frames and directly maps to downstream usability.
- **Colleague's count** as an independent link-quality diagnostic, not a loss
  rate: it catches isolated bit-flips only (a lower bound) and its denominator
  mixes buffer-level and frame-level quantities.

Full per-chunk comparison: `docs/colleague_method_comparison.md`,
`output/compare_colleague_method.{json,md,png}`.

### Source files

- `output/survival_rate.json` — per-chunk + trimmed/untrimmed totals
- `output/survival_rate_stitched.json` — stitched-track summary
- `output/rfi_survival_all.csv` — per-RFI join table (1.22 M rows)
- `output/WL27_stitched_survival.csv` — one row per stitched frame, with
  survival flags for both DAQs and the picked source
- `output/publication_survival_timeline.{png,pdf}` — new timeline (headline)
- `output/publication_survival_bar.{png,pdf}` — old vs new metric side by side
- `output/publication_drop_timeline.{png,pdf}` — **old** timeline, kept for reference
- `output/compare_colleague_method.{json,md,png}` — cross-check vs colleague's
  bit-flip detector

## Stitched Output

- **645,790 stitched frames** (32,290s = 8.97 hours)
- **9 hourly chunks** (`WL27_stitched_chunk_01.avi` through `_09.avi`)
- Each chunk has an accompanying max projection PNG

## Debug Videos

### Aggregate (across all segments, in `output/`)

| File | Frames | Duration |
|------|--------|----------|
| `debug_broken_daq1.avi` | 34,703 | 28.9 min |
| `debug_broken_daq2.avi` | 4,807 | 4.0 min |
| `debug_both_broken.avi` | 1,799 | 1.5 min |
| `debug_broken_daq1_black.avi` | black-only subset of DAQ1 | — |
| `debug_broken_daq1_gradient.avi` | gradient-only subset of DAQ1 | — |
| `debug_broken_daq2_black.avi` | black-only subset of DAQ2 | — |
| `debug_broken_daq2_gradient.avi` | gradient-only subset of DAQ2 | — |

### Per-file (in `debug_detectors/`)

Each input AVI produces three debug AVIs:
- `<stem>_black.avi` — frames with black row artifacts
- `<stem>_gradient.avi` — frames with gradient/checkerboard artifacts
- `<stem>_both.avi` — frames with both artifact types

## Key Observation

DAQ2 has a much lower loss rate (0.37 %) than DAQ1 (3.43 %). When both DAQs
are available, the stitched loss drops to 0.10 % — meaning the dual-DAQ setup
rescues ~97 % of the frames that would otherwise be lost from DAQ1 alone.
(The old AVI-broken-frame numbers — 1.40 % / 5.96 % / 0.84 % — doubled the
apparent loss because of mio bit-flip amplification; see "Error Rates" above.)

## Photobleaching & Baseline Stability

**No detectable photobleaching over 8 hours.** Linear fit on all 561,790 per-frame spatial medians (center 50×50 ROI) shows +2.8% upward drift (+0.65 AU/hr), consistent with thermal warming of the wireless image sensor. Multiple baseline estimation methods (rolling percentile, robust regression, ALS) all confirm the same result.

Key figure: `output/photobleaching_perframe.png` — linear fit directly on per-frame data, no binning or smoothing.

Two complementary analyses:
- **(A) Raw fluorescence:** Linear fit on 561k per-frame medians shows +2.8% upward drift — no downward trend.
- **(B) Peak dynamics:** 95th percentile of ΔF/F₀ (10-min windows, global mean F₀) shows +2.1% — peak fluorescence dynamics stable.

Caveat: the 95th percentile tracks brightest frames regardless of cause (calcium + wireless noise). Confirming calcium transient stability specifically requires single-cell extraction.

Publication figure: `output/publication_photobleaching_combined.png/.pdf`

See `docs/photobleaching-claim.md` for full claim language and caveats, `docs/next-steps-baseline-separation.md` for method comparison, and `docs/fluorescence-analysis.md` for detailed analysis.
