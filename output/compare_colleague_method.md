# Colleague method vs. cleaned survival rate

Per-chunk comparison restricted to the PAIRS used by `scripts/survival_rate.py` (i.e. chunks 01 and other pre-recording chunks excluded).

- **Colleague** (`find_bad_buffers.py`): rolling-3 flanked difference flags a buffer row whose `frame_num` jumps by > 1 from both neighbours — catches single-row header bit-flips. Headline denominator is `len(unique frame_num) − flagged`.
- **Ours** (`scripts/survival_rate.py`): denominator is the MCU `frame_num` range per chunk (`fn_end − fn_start + 1`); numerator is MCU frames that have at least one RFI with ≥ 8 matching buffers. `loss_ge8` = intended − surviving_ge8.

## DAQ1

| chunk | colleague bad buffers | colleague unique `frame_num` | colleague bad rate | ours intended | ours surv(≥8) | ours lost(≥8) | ours loss rate(≥8) | ours lost(≥7) |
|------|----------------------:|-----------------------------:|-------------------:|--------------:|--------------:|--------------:|-------------------:|--------------:|
| `long-2` | 510 | 79,429 | 0.6421% | 79,094 | 76,894 | 2,200 | 2.7815% | 401 |
| `long-4` | 1,076 | 78,759 | 1.3662% | 78,707 | 75,268 | 3,439 | 4.3694% | 856 |
| `long-6` | 833 | 75,347 | 1.1056% | 75,326 | 72,425 | 2,901 | 3.8513% | 684 |
| `long-8` | 674 | 85,923 | 0.7844% | 85,913 | 83,367 | 2,546 | 2.9635% | 535 |
| `long-9` | 726 | 81,791 | 0.8876% | 80,246 | 77,421 | 2,825 | 3.5204% | 531 |
| `long-10` | 413 | 80,339 | 0.5141% | 80,326 | 78,711 | 1,615 | 2.0106% | 378 |
| `long-12` | 811 | 81,306 | 0.9975% | 81,286 | 78,449 | 2,837 | 3.4901% | 616 |
| `long-13` | 1,009 | 77,875 | 1.2957% | 77,854 | 74,303 | 3,551 | 4.5611% | 797 |
| **Total** | **6,052** | **640,769** | **0.9445%** | **638,752** | **616,838** | **21,914** | **3.4308%** | **4,798** |

## DAQ2

| chunk | colleague bad buffers | colleague unique `frame_num` | colleague bad rate | ours intended | ours surv(≥8) | ours lost(≥8) | ours loss rate(≥8) | ours lost(≥7) |
|------|----------------------:|-----------------------------:|-------------------:|--------------:|--------------:|--------------:|-------------------:|--------------:|
| `long-2` | 0 | 78,550 | 0.0000% | 78,550 | 78,549 | 1 | 0.0013% | 0 |
| `long-4` | 64 | 75,437 | 0.0848% | 75,401 | 75,231 | 170 | 0.2255% | 85 |
| `long-6` | 49 | 85,948 | 0.0570% | 85,920 | 85,644 | 276 | 0.3212% | 188 |
| `long-8` | 0 | 80,290 | 0.0000% | 80,290 | 80,168 | 122 | 0.1519% | 113 |
| `long-7` | 0 | 81,654 | 0.0000% | 81,654 | 80,130 | 1,524 | 1.8664% | 1,522 |
| `long-9` | 1 | 81,247 | 0.0012% | 81,246 | 81,244 | 2 | 0.0025% | 0 |
| `long-10` | 1 | 77,884 | 0.0013% | 77,884 | 77,883 | 1 | 0.0013% | 1 |
| **Total** | **115** | **561,010** | **0.0205%** | **560,945** | **558,849** | **2,096** | **0.3737%** | **1,909** |

