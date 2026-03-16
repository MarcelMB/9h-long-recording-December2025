## WL27 Wireless Miniscope -- 9h Recording Frame Quality

Two DAQs received the same wireless signal from a UCLA Miniscope v4. Broken frames are detected via black row runs and gradient (second derivative) analysis on 200x200 grayscale 20fps AVIs. DAQ1 and DAQ2 frames are matched by unix timestamp (25ms threshold), and the best frame from each pair is stitched into 1-hour output chunks.

**DAQ1: 5.96% broken | DAQ2: 1.40% | Combined: 0.84% (1,799 frames lost in 9hrs)**

### Documentation

- [docs/pipeline-overview.md](docs/pipeline-overview.md) — Scripts, run order, segment pairing, trimming
- [docs/detection-algorithms.md](docs/detection-algorithms.md) — Black row and gradient detectors, rejected brightness approach
- [docs/results.md](docs/results.md) — Error rates, output files, debug video inventory
- [docs/changelog.md](docs/changelog.md) — Evolution from v1 (simple thresholds) through v2 (brightness, rejected) to v3 (mio-style)

### Quick Reference

| Script | Purpose |
|--------|---------|
| `run_full_pipeline.py` | Orchestrates all phases end-to-end |
| `analyze_frames.py` | Detect broken frames in a single AVI |
| `combine_daqs.py` | Match DAQ1/DAQ2 and compute combined error rate |
| `create_stitched_video.py` | Build stitched chunks + debug AVIs |
| `analyze_drops.py` | Temporal analysis of dropped frames |

Run with: `conda run -n minian-env python run_full_pipeline.py`
