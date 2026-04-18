# Baseline Separation Methods — Comparison & Conclusions

## Context

We have a ~8h GCaMP6f recording from dCA1 hippocampus (wireless Miniscope Zero).
The pipeline computes a spatial median per frame across a center 50×50 ROI (2500 pixels),
yielding 561,790 per-frame values at 20 fps. These are also averaged into 1-min bins (469 points).

## Methods tested

### 1. Rolling 10th percentile (30-min window)
Temporal percentile on 1-min binned trace, smoothed with 15-min moving average.

### 2. Robust regression (Huber, degree 3)
`sklearn.linear_model.HuberRegressor` with polynomial features on 1-min binned trace.
Downweights upward outliers automatically.

### 3. Asymmetric least squares (ALS)
Whittaker smoother with asymmetric weights (Eilers & Boelens, 2005).
Field-standard method used by CaImAn and Suite2p for F₀ estimation.
Tested on both 1-min bins and raw per-frame data.

### 4. Simple linear fit on per-frame data
Direct least-squares fit on all 561,790 per-frame spatial medians.
No binning, no smoothing — the most direct photobleaching test.

## Results (2026-04-07)

### Baseline methods on 1-min binned data

| Method | Drift % | Slope (AU/hr) | Mean residual | Std residual |
|---|---|---|---|---|
| Rolling 10th pct (30-min window) | −0.5% | −0.103 | 8.19 | 8.79 |
| Robust regression (Huber, deg 3) | +2.2% | +0.510 | 1.40 | 8.95 |
| Asymmetric least squares (ALS) | −0.3% | −0.056 | 10.14 | 9.08 |

### Direct photobleaching test (per-frame)

| Method | Drift % | Slope (AU/hr) | Start | End |
|---|---|---|---|---|
| Linear fit on 561k per-frame medians | +2.8% | +0.651 | 181.0 AU | 186.1 AU |
| ALS on 561k per-frame medians (λ=10¹⁰) | +5.6% | +1.046 | F₀ range: 136.5–183.5 AU | Mean F₀: 149.2 AU |

## Conclusions

1. **No photobleaching detected.** All methods show flat or slightly *upward* drift.
   Photobleaching would appear as a downward trend (declining pixel values over time).
   The +2.8% upward drift is likely thermal (wireless image sensor warming).

2. **ALS is best for F₀ estimation** (for future ΔF/F₀ computation in CaImAn/MiniAn),
   but it **cannot detect photobleaching** — its asymmetric penalty tracks the floor
   by design, so it would follow any real bleaching downward and call it "baseline."

3. **Simple linear fit is the proper photobleaching test** — no assumptions about
   signal direction. The per-frame fit (+2.8%) and 1-min binned fit (+2.8%) give
   identical results, confirming binning doesn't affect the drift estimate.

4. **Huber regression** splits the data rather than hugging the floor (mean residual
   1.4 AU vs ~8–10 for percentile/ALS), making it less suited for one-sided baseline.

5. **ALS is robust to parameters** on this data: λ from 10⁴ to 10⁸ and p from 0.001
   to 0.1 all produce similar baselines.

## Peak fluorescence dynamics analysis

In addition to baseline stability, photobleaching can be detected by declining peak
transient amplitudes (indicator molecules degrade → smaller ΔF/F₀ peaks).

Pipeline:
1. ALS baseline on all 561k per-frame medians (λ=10¹⁰, p=0.01)
2. ΔF/F₀ = (F − F₀_ALS) / F₀_global, where F₀_global = mean ALS baseline (149.2 AU)
3. 95th percentile of ΔF/F₀ in 10-min sliding windows (5-min step)
4. Linear fit on the 95th percentile trace

Result: 95th percentile slope = +0.0013 h⁻¹ (+2.1%) — no decline in peak dynamics.

**Caveat:** The 95th percentile tracks the brightest frames regardless of cause — it
does not distinguish calcium transients from wireless noise spikes. So this shows
"peak fluorescence dynamics" are stable, not specifically "calcium transient amplitudes."
The calcium-specific claim would require single-cell traces from CaImAn/MiniAn.
However, photobleaching would still pull the 95th percentile down because the GCaMP
component within those bright frames would shrink.

**Why global mean F₀:** Using the ALS baseline as a time-varying denominator introduces
drift artifacts (the +5.6% upward ALS drift compresses ΔF/F₀ over time). A fixed
denominator (global mean of ALS baseline) avoids this. Global mean is preferred over
first-N-minutes because it's not anchored to an arbitrary time window.

## Output files

| File | Description |
|---|---|
| `output/publication_photobleaching_combined.png/.pdf` | **Publication:** two-panel (A) raw fluorescence + linear fit, (B) 95th pct ΔF/F₀ |
| `output/publication_photobleaching_perframe.png/.pdf` | **Publication:** standalone raw fluorescence + linear fit |
| `output/publication_peak_dynamics.png/.pdf` | **Publication:** standalone 95th pct ΔF/F₀ + linear fit |
| `output/peak_dynamics_over_time.png/.pdf` | Peak dynamics exploratory figure |
| `output/photobleaching_perframe.png` | Linear fit on all 561k per-frame medians |
| `output/baseline_als_summary.png` | ALS F₀ on per-frame data |
| `output/baseline_separation_comparison.png` | 4-panel: all 3 methods overlaid + individual panels (1-min binned) |
| `output/baseline_separation_als_sensitivity.png` | ALS parameter sensitivity (λ and p) |

## Scripts

All in `scripts/`. Run with `conda run -n minian-env python scripts/<script>.py`.

| Script | Purpose |
|---|---|
| `plot_publication_photobleaching_combined.py` | **Publication:** combined baseline + peak dynamics figure |
| `plot_publication_photobleaching.py` | **Publication:** standalone baseline figure |
| `plot_peak_dynamics.py` | Peak dynamics (95th pct ΔF/F₀ over time) |
| `plot_photobleaching_perframe.py` | Linear fit on 561k per-frame medians |
| `plot_baseline_als_summary.py` | ALS F₀ on per-frame data |
| `plot_baseline_separation.py` | 3-method comparison + ALS sensitivity (1-min binned) |
| `plot_photobleaching_summary.py` | Rolling percentile summary (1-min binned) |
| `plot_photobleaching_simple.py` | Simple binned trace + linear fit |

## Publication figures

The combined figure `output/publication_photobleaching_combined.png/.pdf` tells the complete story:
- **Panel A** — raw fluorescence (no processing assumptions, most honest baseline test)
- **Panel B** — peak fluorescence dynamics (95th pct ΔF/F₀, indicator health test)

Neither shows a downward trend. This is relevant for Miniscope Zero publications:
the system uses less excitation light for improved fluorescence detection, so
demonstrating stable fluorescence and peak dynamics over an 8-hour continuous
recording validates that the lower excitation power avoids photobleaching.

See `docs/photobleaching-claim.md` for full claim language, caveats, and suggested phrasing.

## Data files

| File | Contents |
|---|---|
| `output/perframe_center_median.npz` | Per-frame spatial median + mean (561,790 frames), keys: `median`, `mean`, `fps` |
| `output/fluorescence_percentiles.npz` | 1-min binned data, keys: `time_hours`, `center_p50`, `center_mean`, `center_bin_min`, `center_bin_max` |
