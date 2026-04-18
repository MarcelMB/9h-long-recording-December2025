## Fluorescence Analysis — Photobleaching & Baseline Stability

### Goal
Assess whether the 9-hour GCaMP6f recording from dCA1 hippocampus (wireless Miniscope Zero) shows photobleaching (gradual decline in fluorescence) despite noise from wireless power fluctuations that intermittently brighten the image sensor.

### What we did

1. **Spatial median per frame** — For each frame in stitched chunks 02–09, computed the spatial median pixel intensity within a center ROI (50×50 px, rows 75–125, cols 75–125). Chunk 01 was excluded because the wrong excitation light was used during the first hour.

2. **1-minute binning** — Per-frame spatial medians were averaged into 1-minute bins (1200 frames at 20fps), yielding ~469 data points over ~7.8 hours (first 10 minutes also trimmed due to excitation ramp-up).

3. **Rolling percentile baselines** — To separate resting fluorescence from calcium activity:
   - **Baseline fluorescence (F0):** Rolling 10th temporal percentile (30-min window). GCaMP transients are one-sided (only positive deflections from baseline), so the 10th percentile tracks the true resting fluorescence unbiased by neural activity.
   - **Ca²⁺ event fluorescence:** Rolling 90th temporal percentile (30-min window). Captures bins with elevated activity.
   - Both rolling percentile traces were smoothed with a 15-min moving average to remove staircase artifacts inherent to rank-order statistics.

4. **Linear fits** — Separate linear fits on baseline and event floor to quantify drift over time.

5. **Exponential decay analysis** — Per-hour exponential fits (A·exp(-t/τ) + C) on the raw 1-min bins were tested to check for short-timescale photobleaching within individual hours. No consistent exponential decay was found — fits were dominated by wireless noise (R² < 0.2 for most hours).

### Results — Photobleaching summary (center ROI)

- **Direct test (linear fit on 561k per-frame medians):** +2.8% over 8 h (+0.65 AU/hr) — slight *upward* drift, no photobleaching
- **Rolling 10th percentile baseline:** −0.5% over 8 h (−0.10 AU/hr) — essentially flat
- **Ca²⁺ event floor (90th pct):** +6.0% over 8 h (+1.46 AU/hr) — upward drift, likely thermal (wireless sensor warming)
- **Baseline–event gap:** ~19 AU average

Multiple baseline methods tested (rolling percentile, robust regression, ALS) all confirm the same conclusion: **no detectable photobleaching**. The slight upward drift is consistent with thermal effects on the wireless image sensor. See `docs/next-steps-baseline-separation.md` for full comparison.

Note: ALS (asymmetric least squares) is the field-standard F₀ estimation method (used by CaImAn/Suite2p), but its asymmetric penalty means it cannot independently detect photobleaching — it tracks the floor by design. The simple linear fit on raw per-frame data is the proper photobleaching test.

**Publication figures:** `output/publication_photobleaching_combined.png/.pdf` — two-panel figure:
- **(A) Raw fluorescence** — linear fit on all 561k per-frame medians. No binning, smoothing, or asymmetric weighting. Slope = +0.65 AU/hr (+2.8%). Most direct photobleaching test: if bleaching existed, it would appear as a negative slope.
- **(B) Peak fluorescence dynamics** — 95th percentile of ΔF/F₀ in 10-min windows, using global mean ALS baseline as fixed F₀. Slope = +0.0013 h⁻¹ (+2.1%). Tracks whether peak intensity dynamics decline over time (indicator degradation).

Caveat on panel B: the 95th percentile captures the brightest frames regardless of cause (calcium transients and wireless noise alike). It shows peak *fluorescence* dynamics are stable, not specifically calcium transient amplitudes. The calcium-specific claim requires single-cell traces from CaImAn/MiniAn.

See `docs/photobleaching-claim.md` for full claim language and suggested publication phrasing.

Note: The spatial median aggregates 2500 pixels per frame, so individual cell transients are averaged out and the dynamic range between baseline and Ca²⁺ events is smaller than for single-cell traces.

### Earlier analyses (retained for reference)

#### Full field of view (200×200)

Same rolling median analysis on the full FOV instead of the center ROI. The full FOV includes darker corners outside the GRIN lens, so absolute values are lower (~165 vs ~175). Linear drift on rolling median: +1.8% over 8h — consistent with center ROI result.

#### Multi-percentile consistency check

For each frame, computed 5 spatial percentiles (P10, P25, P50, P75, P90) across all pixels, then applied the same 1-minute binning and rolling 10th temporal percentile to each. All baselines were flat — no meaningful photobleaching at any brightness level.

#### Per-hour pixel intensity histograms

Per-hour pixel brightness histograms overlap tightly across all 8 hours, confirming wireless artifacts are a minor effect. The bimodal histogram shape (peaks at ~100–120 and ~180–200) is characteristic of GRIN lens miniscope optics.

---

### Output files

| File | Description |
|------|-------------|
| `output/photobleaching_perframe.png` | Linear fit on 561k per-frame medians — cleanest photobleaching test |
| `output/baseline_als_summary.png` | ALS F₀ estimation on per-frame data |
| `output/baseline_separation_comparison.png` | 3-method baseline comparison (percentile, Huber, ALS) on 1-min bins |
| `output/baseline_separation_als_sensitivity.png` | ALS parameter sensitivity (λ and p) |
| `output/photobleaching_summary.png` | Rolling percentile baseline + Ca²⁺ event floor + linear fits |
| `output/photobleaching_simple.png` | Simple 1-min binned trace + linear fit |
| `output/fluorescence_percentiles.npz` | Pre-computed data: time_hours, spatial percentiles (full FOV), center_p50, center_mean |
| `output/fluorescence_over_time.png` | Two-panel plot: raw + LPF + rolling baseline (ROI) |
| `output/fluorescence_over_time_fullFOV.png` | Same using full 200×200 FOV |
| `output/fluorescence_percentiles.png` | Multi-percentile baseline plot (P10–P90) |
| `output/fluorescence_histograms.png` | Overlaid per-hour pixel intensity histograms |
| `output/exponential_fit_per_hour.png` | Per-hour exponential decay fits on raw 1-min bins |

### Scripts

| Script | Purpose |
|--------|---------|
| `plot_photobleaching_perframe.py` | Linear fit on 561k per-frame medians |
| `plot_baseline_als_summary.py` | ALS F₀ on per-frame data |
| `plot_baseline_separation.py` | 3-method baseline comparison + ALS sensitivity |
| `analyze_fluorescence.py` | ROI mean fluorescence + LPF + rolling percentile baseline |
| `analyze_fluorescence_fullFOV.py` | Same as above but full 200×200 field of view |
| `analyze_fluorescence_percentiles.py` | Multi-percentile spatial analysis (P10–P90, full FOV) |
| `analyze_fluorescence_histograms.py` | Per-hour pixel brightness histograms |
| `compute_center_roi_fluorescence.py` | Compute center 50×50 ROI median + mean, add to NPZ |
| `plot_photobleaching_summary.py` | Photobleaching summary figure (uses pre-computed NPZ data) |
| `fit_exponential_per_hour.py` | Per-hour exponential decay fits |

Run with: `conda run -n minian-env python scripts/<script>.py`
