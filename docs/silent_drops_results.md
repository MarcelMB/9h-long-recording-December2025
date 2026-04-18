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

## Files

- Script: `scripts/analyze_silent_drops.py`
- Per-file JSON details: `neural_DAQ{1,2}/results/<csv_stem>.silent_drops.json`
- Combined summary: `output/silent_drops_summary.json`
- Plot: `output/silent_drops.png`
