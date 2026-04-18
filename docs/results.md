# Results

## Error Rates

| Source | Broken frames | Total frames | Error rate |
|--------|--------------|-------------|------------|
| DAQ1 alone | ~34,703 | ~647,589 | 5.96% |
| DAQ2 alone | ~4,807 | ~647,589 | 1.40% |
| Combined (both broken) | 1,799 | 647,589 | 0.84% |

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

DAQ2 has a much lower error rate (1.40%) than DAQ1 (5.96%). When both DAQs are available, the combined loss drops to 0.84% — meaning the dual-DAQ setup rescues ~85% of frames that would otherwise be lost from DAQ1 alone.

## Photobleaching & Baseline Stability

**No detectable photobleaching over 8 hours.** Linear fit on all 561,790 per-frame spatial medians (center 50×50 ROI) shows +2.8% upward drift (+0.65 AU/hr), consistent with thermal warming of the wireless image sensor. Multiple baseline estimation methods (rolling percentile, robust regression, ALS) all confirm the same result.

Key figure: `output/photobleaching_perframe.png` — linear fit directly on per-frame data, no binning or smoothing.

Two complementary analyses:
- **(A) Raw fluorescence:** Linear fit on 561k per-frame medians shows +2.8% upward drift — no downward trend.
- **(B) Peak dynamics:** 95th percentile of ΔF/F₀ (10-min windows, global mean F₀) shows +2.1% — peak fluorescence dynamics stable.

Caveat: the 95th percentile tracks brightest frames regardless of cause (calcium + wireless noise). Confirming calcium transient stability specifically requires single-cell extraction.

Publication figure: `output/publication_photobleaching_combined.png/.pdf`

See `docs/photobleaching-claim.md` for full claim language and caveats, `docs/next-steps-baseline-separation.md` for method comparison, and `docs/fluorescence-analysis.md` for detailed analysis.
