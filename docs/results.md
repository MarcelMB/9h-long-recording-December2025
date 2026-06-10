# Results

## Error Rates

All three numbers share ONE session-end boundary: per chunk pair, the analysable
span is the first→last frame either DAQ delivered (excludes the terminal
MCU-reboot collapse). Source of truth: `output/survival_summary.json`.

| Source | MCU survival (new, headline) | AVI broken-frame (old) |
|--------|-----------------------------:|-----------------------:|
| DAQ1 alone | **3.50 %** (22,359 / 639,197 lost) | 5.33 % (v1) / 5.96 % (v3) |
| DAQ2 alone | **0.14 %** (901 / 639,197 lost)    | 0.75 % (v1) / 1.40 % (v3) |
| Dual-DAQ stitched | **0.007 %** (45 / 639,197 both-lost) | 0.20 % (v1, both-broken) / 0.84 % (v3) |

**Headline (use in the manuscript):** DAQ1 3.50 %, DAQ2 0.14 %, Stitched 0.007 %
(MCU-level survival, ≥8-buffer RFI required per MCU frame; shared session-end cut.)

> **Correction (2026-06-09b): consistent session-end cut; DAQ2 0.39 % → 0.14 %.**
> The old trim was a hand-tuned, DAQ1-only constant (`TRIM_SECONDS_DAQ1`,
> long-2/long-9 only) that DAQ2 never had. But the end-of-session degradation is
> the **MCU rebooting** (the device errors out after ~1 h, hence `frame_num`
> restarts each chunk) — a source-side fault identical on both DAQs, not wireless
> loss. So the same collapse was trimmed out of DAQ1 (long-9) but counted against
> DAQ2 (long-7), inflating DAQ2 ~2.7×: ~1,524 of its 2,475 "lost" frames were
> that one MCU tail. Replaced with one data-driven cut applied to both DAQs (the
> union span already used for stitched). New: DAQ1 3.50 %, DAQ2 **0.14 %**,
> stitched 0.007 %. All three computed in `compute_stitched_survival.py` →
> `survival_summary.json`. See `memory/stitched-both-lost-reality.md`.

> **Correction (2026-06-09): stitched 0.00 % was a denominator artifact; the
> honest dual-DAQ loss is 0.007 % (45 frames).**
> The old stitched calc joined the stitcher's `daq1_frame`/`daq2_frame` columns
> to per-RFI survival. Those columns only reference frames that *were*
> reconstructed, so frames lost on a DAQ have no RFI and were simply **absent
> from the denominator** rather than counted lost (the join found only 162 DAQ2
> failures vs the true 2,475). The stitched track was recomputed by aligning
> DAQ1↔DAQ2 directly on the device MCU `frame_num` (union coverage; alignment
> verified — surviving sets overlap 77,315/77,317 and the same frame_num arrives
> within ~4 ms on both DAQs). Result: **45 frames (0.007 %)** are lost on *both*
> DAQs mid-recording. The large apparent both-loss blocks at chunk ends
> (long-2/8/9/10) are **acquisition-stop tails** — both links collapse to
> half-buffer delivery in the final seconds of each recording session — and are
> excluded by analysing only the span between the first and last frame either
> DAQ delivered. See `memory/stitched-both-lost-reality.md`.

> **Correction (2026-06-08): DAQ2 chunk-pairing bug fixed.**
> The canonical `analyze_frame_num_drops.py` `PAIRS` had the DAQ2 labels
> shifted by one for the first four pairs (DAQ2's first chunk is the
> un-numbered base file `...long.csv`). This **skipped DAQ2's entire first
> hour** and double-counted `long-8`, and it also made the stitched-survival
> join look up the wrong DAQ2 chunk for the first ~4 h — which is what created
> the spurious "~9,500 unknown tail rows" and the 660 "lost" stitched frames.
> After fixing the mapping (and verifying it against both unix-time windows and
> `frame_num` ranges, matching `combine_daqs.py`):
> DAQ2 now covers the full **640,771** intended frames (0.39 %), and the
> stitched track joins cleanly over the **full 645,790** frames with **0
> unknown** and **0 lost**. DAQ1 is unaffected. See
> `memory/afd-pairs-daq2-misalignment.md`.

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
| DAQ2 alone | 640,771 | 638,296 | **0.39 %** |

These come from `survival_rate.py` (per-DAQ, no session-end cut) and include the
MCU-reboot tails — they are diagnostics, not the headline. The headline uses the
shared session-end cut in `survival_summary.json` (DAQ1 3.50 %, DAQ2 0.14 %).

### Stitched both-lost — direct frame_num union (headline method)

The stitched number *is* the both-lost count: MCU frames where **neither** DAQ
delivered an ≥8-buffer RFI, aligned directly by `frame_num` (not via the
stitcher's frame-index columns). Within the analysable span of each chunk pair
(first→last frame either DAQ delivered, which excludes the terminal
acquisition-stop collapse), this is **45 frames / 639,197 = 0.007 %**. They are
scattered short interior gaps (the largest cluster, 31 frames, is in
`long-6↔long-4`); genuine simultaneous mid-recording loss is rare. The earlier
"0.000 %" was a denominator artifact (see the 2026-06-09 correction above).
Per-pair breakdown (all three metrics): `output/survival_summary.json`;
per-frame both-lost list with timestamps: `output/stitched_both_lost.csv`.

### Independent cross-check — colleague's bit-flipped-buffer detector

An independent script from a collaborator
(`/Users/mbrosch/Downloads/find_bad_buffers.py`) detects bit-flipped
buffer headers at the row level by flagging any `frame_num` that differs
by > 1 from both neighbours in a rolling-3 window. It doesn't measure
frame survival; it measures *isolated* wireless-link bit-flip events.

Running it on the same PAIRS our survival analysis uses:

> ⚠️ **Stale — pending regeneration.** The DAQ2 row below was computed with the
> old (misaligned) `PAIRS` chunk set, so it misses DAQ2's first hour. DAQ2
> "Ours lost(≥8)" is now **2,475 (0.39 %)** (see corrected table above).
> Re-run `scripts/compare_colleague_method.py` to refresh both DAQ2 columns
> here and `output/compare_colleague_method.*`. DAQ1 figures are unaffected.

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

- `output/survival_summary.json` — **headline source of truth**: DAQ1/DAQ2/stitched
  totals + per-pair spans, all on the shared session-end cut
- `output/survival_rate.json` — per-chunk per-DAQ diagnostics (no shared cut; not headline)
- `output/rfi_survival_all.csv` — per-RFI join table (1.22 M rows)
- `output/stitched_both_lost.csv` — one row per frame lost on BOTH DAQs
  mid-recording (frame_num, segments, timestamp)
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

DAQ2 has a much lower loss rate (0.14 %) than DAQ1 (3.50 %). When both DAQs
are available, the stitched loss drops to **0.007 %** (45 of 639,197 frames) —
the dual-DAQ setup rescues nearly every frame that would otherwise be lost from
DAQ1 alone, because the two links almost never fail on the same MCU frame; only
~45 scattered frames are lost simultaneously across the whole recording.
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
