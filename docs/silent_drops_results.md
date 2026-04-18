# Silent Frame Drops — WL27 9-hour Recording

## What we detected

"Silent" drops are frames that never reached the AVI file because all 8 transmission buffers for that frame were lost in flight. They are invisible to the pixel-based broken-frame detectors (black-row / gradient detectors in `scripts/analyze_frames.py`), because those detectors can only flag frames that made it to disk.

## Method

For each CSV log (one per acquisition chunk, per DAQ), we look at `buffer_recv_unix_time` — the host PC's wall-clock time (Unix epoch seconds) at which each buffer arrived over USB. We reduce to one timestamp per frame by taking the minimum host-arrival time across a frame's 8 buffers (i.e. the arrival time of the earliest buffer in the frame).

We then walk the per-frame timestamp sequence and flag any inter-frame gap greater than **75 ms** (1.5× the expected 50 ms period at 20 FPS). For each flagged gap we estimate the number of lost frames as `round(Δt / 50 ms) − 1`.

- Each file is analyzed independently (miniscope restarts between files, so no cross-file timing assumptions).
- DAQ1 files `long-2` and `long-9` have their last 30 s and 155 s trimmed respectively, to match the frame set used in the aligned cross-DAQ drop analysis.
- DAQ2 is not trimmed.

### Why only host timestamps

We initially planned four detectors (device-side `frame_num` gaps, device-side timestamp gaps, host-side timestamp gaps, firmware-reported `dropped_buffer_count` deltas). Inspection of the real CSVs showed that the device-transmitted integer columns (`frame_num`, device `timestamp`, `dropped_buffer_count`, `buffer_count`) are periodically bit-flipped by the wireless link — about 0.01 % of rows carry classic uint32 sentinels such as `0xFFFFFFFF`, `0xFFFE0000`, `0x80000000`, plus harder-to-spot within-range single-bit errors. Those corrupted rows inflated the device-side detectors by 8–11 orders of magnitude and were not usable.

`buffer_recv_unix_time` is written by the host computer itself (not transmitted over the wireless radio), so it is uncorrupted and reliable.

## Results

Rate = silent drops as a percentage of analyzed frames per file.

### DAQ1

| File | Silent drops | Gap events | Analyzed frames | Drop rate |
|------|-------------:|-----------:|----------------:|----------:|
| `long-2`  |   2 |   2 | 79,988 | 0.0025 % |
| `long-4`  |  15 |  15 | 80,639 | 0.0186 % |
| `long-6`  |   3 |   3 | 76,829 | 0.0039 % |
| `long-8`  |   2 |   2 | 87,114 | 0.0023 % |
| `long-9`  |   2 |   2 | 81,466 | 0.0025 % |
| `long-10` |   1 |   1 | 81,110 | 0.0012 % |
| `long-12` |   1 |   1 | 82,697 | 0.0012 % |
| `long-13` |   2 |   2 | 79,660 | 0.0025 % |
| **Total** | **28** | **28** | **649,503** | **0.0043 %** |

### DAQ2

| File | Silent drops | Gap events | Analyzed frames | Drop rate |
|------|-------------:|-----------:|----------------:|----------:|
| `long-2`  |  46 |  40 | 78,550 | 0.0586 % |
| `long-4`  | 126 |  64 | 75,532 | 0.1668 % |
| `long-6`  | 226 | 220 | 86,155 | 0.2623 % |
| `long-7`  |  94 |  87 | 83,168 | 0.1130 % |
| `long-8`  | 106 |  92 | 80,395 | 0.1318 % |
| `long-9`  |  75 |  69 | 81,247 | 0.0923 % |
| `long-10` | 190 | 184 | 77,886 | 0.2439 % |
| **Total** | **863** | **756** | **562,933** | **0.1533 %** |

*Gap events* = number of inter-frame gaps > 75 ms. *Silent drops* = total frames estimated missing across those gaps (one gap can account for multiple missing frames).

### Summary

DAQ2 loses roughly **30×** as many frames as DAQ1 across this recording (0.15 % vs. 0.004 %). Both are low in absolute terms, but the difference between the two DAQs is consistent across every paired chunk — it looks like a per-link property, not an episodic event.

## Inter-frame jitter (host arrival time) and the 75 ms threshold

Looking at the inter-frame gaps that fall *under* the 75 ms drop threshold tells us how tight the normal cadence is and whether 75 ms is a defensible cut-off.

| DAQ | n gaps ≤ 75 ms | mean | std | median | p99 |
|-----|--------------:|-----:|----:|-------:|----:|
| DAQ1 | 649,467 | 48.68 ms | 5.69 ms | 49.20 ms | 54.82 ms |
| DAQ2 | 562,170 | 49.26 ms | 4.76 ms | 47.80 ms | 61.36 ms |

75 ms sits ~4–5 σ above the mean on both DAQs, cleanly separating normal jitter from dropped frames.

### But the two DAQs have structurally different timing distributions

**DAQ1 — tight unimodal peak**

| gap range | % frames |
|----------|---------:|
| 45–50 ms | **88.2 %** |
| 50–55 ms |   8.0 % |
| everything else |   3.8 % |

One peak at 49.2 ms. p90 = 49.8 ms (barely wider than the median). Very clean 20 Hz cadence on the host side.

**DAQ2 — bimodal**

| gap range | % frames |
|----------|---------:|
| 45–50 ms | **56.5 %** |
| 50–55 ms | **34.3 %** |
| 55–65 ms |   3.3 % |
| < 45 ms  |   5.4 % |

Two peaks — one at ~47.8 ms, a secondary at ~52 ms. More than a third of DAQ2 frames land in the 50–55 ms bucket vs DAQ1's 8 %. This is the reason DAQ2's p99 is ~6 ms higher: it's not a rare long tail, it's the *body* of the distribution being wider.

The signature — a "too-early" gap (< 45 ms, 5.4 % of DAQ2 frames vs 1.0 % on DAQ1) immediately followed by a "too-late" gap (50–55 ms) — is characteristic of **host-side USB / OS scheduling batching**. Successive pairs of gaps sum to ~100 ms = two frames, so no data is lost, but the buffers arrive in batches rather than at a steady tempo.

Since the miniscope optical cadence is essentially identical on both DAQs (medians differ by ~1 ms), the difference is in how each host's USB stack hands off buffers — likely a different USB port, hub, or capture-process priority on the DAQ2 side. This is not a silent-drop issue (all these gaps are under the 75 ms threshold), but any downstream analysis that assumes a smooth 20 Hz tempo within a single DAQ (e.g. event timing, peak-fitting) should keep this asymmetry in mind.

## Files

- Script: `scripts/analyze_silent_drops.py`
- Per-file JSON details: `neural_DAQ{1,2}/results/<csv_stem>.silent_drops.json`
- Combined summary: `output/silent_drops_summary.json`
- Plot: `output/silent_drops.png`
