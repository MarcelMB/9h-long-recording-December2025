# Photobleaching Claim — For Publication Text

## Key claim

Over 8 hours of continuous recording at 20 fps (561,790 frames), no net fluorescence decline was observed in the GCaMP6f signal from dCA1 hippocampus using the wireless Miniscope Zero. This places an upper bound on any photobleaching effect at the excitation power used.

## Two complementary analyses

### 1. Raw fluorescence — baseline stability

Linear fit on all 561,790 per-frame spatial medians (center 50×50 ROI, no binning or smoothing). This is the most direct photobleaching test because it makes no assumptions about signal direction — if bleaching existed, it would appear as a negative slope.

- Slope: +0.65 AU/h (+2.8% over 8 h, R² = 0.004, N = 561,790)
- Note: this is raw fluorescence, not specifically baseline — it includes calcium transients, wireless noise, and everything else. It's the honest, unprocessed view.

### 2. Peak fluorescence dynamics — indicator health

The 95th percentile of ΔF/F₀ (computed in 10-min sliding windows) tracks whether the brightest frames decline over time. Photobleaching degrades GCaMP molecules, which reduces peak transient amplitudes — this is often a more sensitive indicator than baseline decline alone.

- ΔF/F₀ computed as (F − F₀_ALS) / F₀_global, where F₀_ALS is the per-frame ALS baseline and F₀_global is the mean ALS baseline across the entire recording (149.2 AU)
- 95th percentile slope: +0.0013 h⁻¹ (+2.1% over 8 h) — no decline

**Important caveat:** The 95th percentile captures the brightest frames regardless of cause — it does not distinguish calcium transients from wireless noise spikes (thermal artifacts that also push intensity up). Therefore this analysis shows that **peak fluorescence dynamics** are stable, not specifically that **calcium transient amplitudes** are stable. Proving the latter would require extracted single-cell traces (e.g., from CaImAn/MiniAn). However, photobleaching would still pull the 95th percentile down even in the presence of noise, because the GCaMP component within those bright frames would shrink.

## Supporting evidence

- No early downward dip in the raw trace, which would be expected if exponential photobleaching were occurring (bleaching is strongest at the start)
- Multiple baseline estimation methods (rolling percentile, robust regression, ALS) all confirm the absence of a downward trend
- ALS baseline on per-frame data shows +5.6% upward drift — but ALS cannot detect photobleaching by design (its asymmetric penalty tracks the floor, so it would follow any real bleaching downward)

## What we can say

- No net fluorescence decline was detected over 8 hours of continuous imaging
- Peak fluorescence dynamics (95th percentile ΔF/F₀) are stable, showing no decline consistent with indicator degradation
- Any photobleaching effect, if present, is smaller than the ~3% upward thermal drift and therefore negligible for practical calcium imaging analysis
- The low excitation power of the Miniscope Zero is sufficient to avoid detectable photobleaching even during very long recordings

## What we cannot say

- We cannot prove zero photobleaching — only that it is undetectable at this timescale and excitation power
- We cannot determine whether the +2.8% upward drift is thermal, LED-related, or some other artifact
- We cannot rule out that a small bleaching effect is masked by a larger upward drift from other sources — however, the absence of an early exponential decay argues against this
- We cannot claim calcium transient amplitudes specifically are stable — only peak fluorescence dynamics broadly, since the 95th percentile may include wireless noise artifacts

## Suggested phrasing

> "Over 8 hours of continuous GCaMP6f imaging at 20 fps (561,790 frames), no net decline in fluorescence intensity was observed (linear fit slope: +0.65 AU/h, R² = 0.004), and peak fluorescence dynamics (95th percentile of ΔF/F₀ in 10-min windows) remained stable (+2.1%), indicating that photobleaching is negligible at the excitation power used by the Miniscope Zero."

## Publication figures

| File | Description |
|---|---|
| `output/publication_photobleaching_combined.png/.pdf` | Two-panel: (A) raw fluorescence + linear fit, (B) 95th pct ΔF/F₀ + linear fit |
| `output/publication_photobleaching_perframe.png/.pdf` | Standalone: raw fluorescence + linear fit |
| `output/publication_peak_dynamics.png/.pdf` | Standalone: 95th pct ΔF/F₀ + linear fit |
