# Changelog — Noise Detection Evolution

## v3: mio-style detection (current)

Replaced the original checkerboard detector with a second-derivative gradient detector, and tightened the black row detector.

**Changes:**
- **Black row detector:** switched from `row_mean < 2` to counting runs of >= 30 consecutive zero pixels, requiring >= 10 such rows per frame. More precise — catches partial black bands without flagging dim-but-valid rows.
- **Gradient detector:** replaced even/odd column difference (`abs(even_cols - odd_cols).mean() > 30`) with second spatial derivative (`mean(|diff(frame, n=2)|) > 20` per row). Catches a broader range of high-frequency noise patterns beyond strict checkerboard.
- **JSON schema:** `checker_frames` renamed to `gradient_frames`, `checker_only_count` renamed to `gradient_only_count`
- **Per-type debug AVIs:** `analyze_frames.py` now writes `_black.avi`, `_gradient.avi`, `_both.avi` per input file (when debug_dir is passed)
- **Aggregate per-type debug AVIs:** `create_stitched_video.py` writes `debug_broken_daq1_black.avi`, `debug_broken_daq1_gradient.avi` (and DAQ2 equivalents) across all segments

**Results:** DAQ1 5.96% broken, DAQ2 1.40%, Combined 0.84%

## v2: brightness detection attempt (rejected)

Attempted to add brightness-based detection to catch bright-row artifacts missed by the black+checkerboard detectors.

**Tested thresholds:**
- `row_mean > frame_median + 80`
- `row_mean > 200`
- `pixel_count > 230`

**Outcome:** All produced 60-75% false positive rates. Calcium transients (GCaMP fluorescence) naturally produce bright pixels and rows that are indistinguishable from noise by intensity alone. Approach was abandoned.

**Diagnostic scripts:** `diagnose_bright_rows.py`, `diagnose_bright_rows2.py`

## v1: original detection

Initial implementation with two detectors:
- **Black rows:** `row_mean < 2` (simple threshold)
- **Checkerboard:** `abs(even_columns - odd_columns).mean() > 30`

**Results:** DAQ1 5.33% broken, DAQ2 0.75%, Combined 0.20%

Lower combined rate than v3 because the original detectors were less sensitive — they missed some broken frames that v3 now catches (hence higher individual rates but the same frames are now correctly flagged).
