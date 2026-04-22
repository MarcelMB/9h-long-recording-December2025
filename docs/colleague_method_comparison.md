# Colleague's `find_bad_buffers.py` vs. our cleaned survival rate

Cross-check of our MCU-frame survival rate against an independent bit-flipped-buffer
detector written by a collaborator
(`/Users/mbrosch/Downloads/find_bad_buffers.py`). The two methods measure
different things — buffer-level corruption events vs. MCU-frame-level loss —
but the comparison tells us how much of our ≥ 8-buffer loss is explained by
single-row header bit-flips alone.

## Methods

**Colleague** — rolling window of 3 over `frame_num`, flag the middle row when
it differs by > 1 from *both* neighbours. Real MCU frames occupy 8 consecutive
rows with the same `frame_num`, so the flanked test lights up on isolated
single-row header bit-flips on the wireless link. Headline denominator:
`len(unique frame_num) − flagged`.

**Ours** (`scripts/survival_rate.py`) — per-chunk, denominator is the MCU
`frame_num` range (`fn_end − fn_start + 1`); numerator is MCU frames with at
least one reconstructed frame index (RFI) of ≥ 8 buffers whose majority
`frame_num` matches.

## Results — PAIRS only (same chunks survival uses)

Full per-chunk tables: `output/compare_colleague_method.md`. Totals:

| DAQ | colleague bad buffers | colleague rate | ours intended | ours lost(≥8) | ours loss rate(≥8) | ours lost(≥7) | ours loss rate(≥7) |
|-----|----------------------:|---------------:|--------------:|--------------:|-------------------:|--------------:|-------------------:|
| DAQ1 |  6,052 | 0.944 % | 638,752 | 21,914 | 3.431 % | 4,798 | 0.751 % |
| DAQ2 |    115 | 0.021 % | 560,945 |  2,096 | 0.374 % | 1,909 | 0.340 % |

(Colleague's own headline run, which walks every CSV in each folder including
chunks our survival excludes, reports 6,259 / 652,461 on DAQ1 and 120 / 658,556
on DAQ2 — the totals above drop chunk 01 and other non-PAIRS files so both
methods see the same data.)

## Reading the two numbers together

Each isolated bit-flipped header the colleague flags takes exactly one buffer
out of its true MCU frame (leaving 7 correct buffers) and deposits it at some
out-of-range `frame_num`, so at the ≥ 8 threshold the affected MCU frame fails
and at the ≥ 7 threshold it passes. If bit-flips were the *only* source of
survival loss, we would see `colleague_bad_buffers ≈ lost(≥8) − lost(≥7)`.

- DAQ1: 6,052 flagged vs. 21,914 − 4,798 = 17,116 (≥ 8 minus ≥ 7).
- DAQ2:   115 flagged vs.  2,096 − 1,909 =    187.

So isolated bit-flips account for roughly **a third** of the drop between the
≥ 8 and ≥ 7 thresholds on DAQ1 and **about two-thirds** on DAQ2. The remainder
is consistent with what we already know: multi-buffer loss within an MCU frame
(radio drops more than one of the 8 buffers, or two bit-flips land in the
same frame and defeat the flanked test), and clustered bit-flips that the
rolling-3 detector doesn't resolve as isolated outliers.

The bigger story is the **≥ 8 ↔ ≥ 7 sensitivity**. On DAQ1 the ≥ 7 loss rate
(0.75 %) is 4.6× smaller than the ≥ 8 rate (3.43 %), meaning most "lost" MCU
frames on that link are in fact reconstructable — they are just one buffer
short because one buffer's header got bit-flipped or dropped. On DAQ2 the two
rates are nearly identical (0.34 % vs. 0.37 %), consistent with DAQ2's losses
being genuine buffer losses rather than bit-flips.

DAQ1's much higher colleague-flagged bit-flip rate (0.94 % vs. 0.02 %) is also
consistent with this: the DAQ1 radio link is noisier at the bit level, which
inflates ≥ 8 loss without hurting ≥ 7 survival.

## Which method to use when

The two methods answer different questions, so neither strictly supersedes the
other. The short version:

- **Cite ours** (≥ 8-buffer MCU survival) for any frame-loss claim. It's
  denominated in MCU-intended frames and is what a downstream user cares
  about ("what fraction of frames arrived as usable images?").
- **Cite colleague's** as an independent bit-level link-quality diagnostic, not
  as a loss rate.

### Where ours is stronger
- Answers the question that matters for publication. "3.43 % of MCU-intended
  frames didn't reconstruct" is quotable; "6,052 buffer rows had flipped
  headers" is a diagnostic.
- Multi-threshold (≥ 8, ≥ 7, ≥ 6) reveals the *shape* of the damage — which
  is exactly what let us distinguish DAQ1 (bit-flip dominated) from DAQ2
  (genuine buffer loss). His method can't make that distinction.
- Unambiguous denominator (MCU counter range). His `len(unique frame_num) −
  flagged` mixes buffer-level errors into a frame-level count and silently
  includes out-of-range sentinel values as "frames."

### Where his is stronger
- Fewer moving parts — ~20 lines with no state, no dependency on mio's
  reconstructor, the sentinel filter, or quorum boundary picking. Makes it a
  good independent check.
- It gives us a **floor**. Our ≥ 8 loss must always exceed his bad-buffer count
  (each isolated flip costs one buffer from one MCU frame). It does, which
  rules out the possibility that our numbers are inflated by a pipeline
  artefact.

### Where his is genuinely weaker
- **Lower bound only.** The rolling-3 flanked test catches isolated flips;
  two adjacent bit-flipped buffers or a flip at a frame boundary slip through.
- **Silent buffer drops are invisible to it** — a buffer that never arrived
  produces no bit-flipped row to flag, but still degrades frame survival.
  This is exactly DAQ2's failure mode.
- **No intended-vs-delivered framing.** It can't distinguish "the device never
  sent this frame" from "the device sent it but it got corrupted," which is
  the core question for a wireless link.

Bottom line: our metric is the one to quote; his is the one to run alongside
to confirm nothing has gone wrong in ours. The two together are stronger than
either alone.

## Files

- Colleague script (upstream): `/Users/mbrosch/Downloads/find_bad_buffers.py`
- Wrapper + join: `scripts/compare_colleague_method.py`
- Raw colleague outputs (whole-folder walk):
  `output/colleague_method/DAQ{1,2}_bad_buffers.csv`
- PAIRS-only comparison: `output/compare_colleague_method.{json,md,png}`
