## WL27 Wireless Miniscope -- 9h Recording Frame Quality

Two DAQs received the same wireless signal from a Miniscope Zero. Broken frames are detected via black row runs and gradient (second derivative) analysis on 200x200 grayscale 20fps AVIs. DAQ1 and DAQ2 frames are matched by unix timestamp (25ms threshold), and the best frame from each pair is stitched into 1-hour output chunks.

**DAQ1: 5.96% broken | DAQ2: 1.40% | Combined: 0.84% (1,799 frames lost in 9hrs)**

### Project Structure

```
9h_long_recording_December2025/
  scripts/          — all Python processing scripts
  docs/             — documentation (this file + analysis docs)
  output/           — stitched videos, plots, analysis results
  neural_DAQ1/      — raw DAQ1 data (.avi/.bin/.csv) + results/ + debug_detectors/
  neural_DAQ2/      — raw DAQ2 data (.avi/.bin/.csv) + results/ + debug_detectors/
```

### Documentation

- [pipeline-overview.md](pipeline-overview.md) — Scripts, run order, segment pairing, trimming
- [detection-algorithms.md](detection-algorithms.md) — Black row and gradient detectors, rejected brightness approach
- [results.md](results.md) — Error rates, output files, debug video inventory
- [changelog.md](changelog.md) — Evolution from v1 (simple thresholds) through v2 (brightness, rejected) to v3 (mio-style)
- [fluorescence-analysis.md](fluorescence-analysis.md) — Photobleaching assessment: baseline & Ca²⁺ event floor stability (center 50×50 ROI, GCaMP6f, dCA1)

### Quick Reference

| Script | Purpose |
|--------|---------|
| `run_full_pipeline.py` | Orchestrates all phases end-to-end |
| `analyze_frames.py` | Detect broken frames in a single AVI |
| `combine_daqs.py` | Match DAQ1/DAQ2 and compute combined error rate |
| `create_stitched_video.py` | Build stitched chunks + debug AVIs |
| `analyze_drops.py` | Temporal analysis of dropped frames |
| `analyze_fluorescence.py` | ROI fluorescence over time + photobleaching check |
| `analyze_fluorescence_fullFOV.py` | Full FOV fluorescence over time |
| `analyze_fluorescence_percentiles.py` | Multi-percentile spatial analysis (P10–P90) |
| `analyze_fluorescence_histograms.py` | Per-hour pixel brightness histograms |
| `compute_center_roi_fluorescence.py` | Center 50×50 ROI median + mean |
| `plot_photobleaching_summary.py` | Photobleaching summary figure |
| `fit_exponential_per_hour.py` | Per-hour exponential decay fits |

Run with: `conda run -n minian-env python scripts/run_full_pipeline.py`
