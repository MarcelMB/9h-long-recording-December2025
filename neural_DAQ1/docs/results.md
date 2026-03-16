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
