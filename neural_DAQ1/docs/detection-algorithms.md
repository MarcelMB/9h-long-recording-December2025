# Noise Detection Algorithms

## Current Detectors (mio-style)

Two artifact types are detected, both caused by wireless transmission errors in the UCLA Miniscope v4 system.

### 1. Black Row Detector

Identifies frames where large horizontal bands of pixels are zeroed out — a signature of dropped or corrupted wireless packets.

- **Method:** Per-row, find runs of consecutive pixels with value == 0 using a cumulative sum sliding window
- **Thresholds:**
  - Run length >= 30 consecutive zero pixels in a row
  - Frame must have >= 10 such rows to be flagged
- **Rationale:** Short zero runs can occur naturally in dark regions of calcium imaging. Requiring 30 consecutive zeros and 10+ affected rows prevents false positives while catching genuine transmission dropouts.
- **Known issue:** The black row detector still produces some false positives — flagging valid frames that happen to have dark regions with long zero runs. This is acceptable for now since the dual-DAQ stitching rescues most of these, but the detector needs improvement in a future iteration (e.g. requiring additional spatial context, or combining with temporal neighbors to distinguish genuine dropouts from naturally dark frames).

### 2. Gradient (Checkerboard) Detector

Identifies frames with high-frequency spatial noise — rapid pixel-to-pixel intensity oscillations that produce a "checkerboard" or "salt-and-pepper" pattern.

- **Method:** Compute the second spatial derivative along columns (`np.diff(frame, n=2, axis=1)`), then take the mean of absolute values per row
- **Threshold:** Mean |second derivative| > 20 for any row
- **Rationale:** Normal calcium imaging frames have smooth spatial gradients. Wireless corruption introduces sharp pixel-level oscillations that produce high second-derivative values.

### Categorization

Each frame is classified into exactly one category:
- **black only** — has black rows but no gradient noise
- **gradient only** — has gradient noise but no black rows
- **both** — has both black rows and gradient noise

## Rejected Approaches

### Brightness / Saturation Detection (DO NOT USE)

Multiple brightness-based thresholds were tested and all produced massive false positives on calcium imaging data:

| Threshold | False positive rate |
|---|---|
| row_mean > frame_median + 80 | ~60% |
| row_mean > 200 | ~65% |
| pixel_count > 230 | ~75% |

**Why it fails:** Calcium transients naturally produce bright pixels (200-255) and bright rows. GCaMP fluorescence varies widely in intensity, making any static brightness threshold unreliable. The ~2 frames per 72,000 with bright noise artifacts are accepted as an unavoidable trade-off.

Diagnostic scripts (`diagnose_bright_rows.py`, `diagnose_bright_rows2.py`) were used to characterize the brightness distribution and confirm this conclusion.

## Future Improvements

- **Black row false positives:** The current black row detector flags some valid frames with naturally dark regions. Possible approaches to reduce false positives:
  - Require black rows to be spatially contiguous (a solid band, not scattered rows)
  - Use temporal context — genuine dropouts tend to appear suddenly, while dark tissue regions persist across frames
  - Combine with a texture or edge metric to distinguish "truly empty" rows from "dark but structured" rows
  - Adaptive thresholding based on local image statistics rather than a fixed zero-pixel run length
