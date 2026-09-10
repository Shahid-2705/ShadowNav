# ADR-003: Publish the fair baselines and the PS 10 % target on the deck, including where the project loses

## Context

The committed deck compares ShadowNav only to unaided double integration ("1.7×–43× closer than plain sensor maths") and never mentions the PS's own numeric target (audit §0, §3, §25). Today the fair baselines were run through the same harness on the same 991 outages, seed 20260905, and the scoring protocol was corrected so the scored instant is never aided. The results (`eval/results/*.json`, medians at 10/30/60/120/180 s):

| Method | CRSE (m) | Drift % of distance | Share under 10 % |
|---|---|---|---|
| Naive strapdown (`baseline_naive.json`) | 310 / 1725 / 6856 / 26688 / 63408 | 229 / 444 / 918 / 1844 / 2553 | 0 / 0.4 / 0 / 0 / 0 |
| Freeze last fix (`baseline_freeze.json`) | 222 / 436 / 754 / 1153 / 1577 | 194 / 123 / 106 / 97 / 93 | 0 / 0 / 0 / 0.7 / 1.6 |
| Straight line at last GNSS speed, no IMU (`baseline_cv.json`) | 182 / 346 / 612 / 979 / 1326 | 154 / 97 / 84 / 76 / 68 | 0 / 0 / 0 / 0.7 / 0.8 |
| Speed hold + gyro heading (`baseline_gyro.json`) | 182 / 357 / 627 / 995 / 1341 | 155 / 99 / 86 / 79 / 71 | 0 / 0 / 0 / 0 / 0.8 |
| **ShadowNav kinematic MVP** (`kinematic.json`) | 194 / 378 / 658 / 1086 / 1480 | 155 / 103 / 88 / 84 / 80 | 0 / 0 / 0.5 / 0 / 3.1 |

Paired per outage (`summarise_results.py`), the MVP beats the frozen dot in 59/72/69/65/51 % of outages and beats the straight line in 49/36/34/29/27 %. The PS target of drift below 10 % of distance (audit §5, line 102) is met by essentially nothing, including every baseline: at a 9 s fix period the frozen dot itself drifts 93–194 %.

Three facts make hiding this worse than showing it: the harness is public and seeded, so anyone can run the baselines; the PS owner wrote the 10 % figure and will check it first (audit §0); and a judge who finds an omitted baseline stops trusting the rest of the deck, including the parts that are strong (ADR-001).

## Decision

The deck publishes, on the feasibility slide, one chart with five bars per horizon — naive floor, freeze, straight line, gyro hold, ShadowNav — and a dashed line at 10 % of distance; the caption states in plain words that on this dataset a straight line at the last GNSS speed matches or beats the filter at every horizon, and why (speed held from a fix up to 9 s stale; 10 Hz IMU cannot observe speed; heading integration currently adds cross-track error). The comparison matrix on slide 6 carries a row "Drift < 10 % of distance (PS target)" with ✗ for ShadowNav and the remedy and date beneath it. The idea-description field carries the same sentence. The "1.7×–43×" figure appears nowhere as a headline; the naive floor appears only as the bottom bar of that chart.

Every number on the deck is the median from the named result file under the corrected protocol; the deck never quotes a pre-correction figure (README.md's table is updated in the same pass, plan A10).

## Alternatives considered

1. **Show only the naive comparison** (status quo). Rejected: strawman; falsifiable by anyone with the repo in under an hour (`run_baseline.py`); the audit's §10 attack table names it as the first destroying question.
2. **Show the fair baselines but omit the 10 % target.** Rejected: the target is the PS's only numeric criterion and the omission is itself a signal; the audit's §29 item 5 and mentor guidance (§23) both say judges reward the team that states the gap first.
3. **Show the target with the 8-sequence control numbers** (2.8–20.8 % of outages under target, `kinematic_ctrl8.json`), which look better. Rejected: 8 sequences vs 79, and `summarise_results.py` already refuses to compute the ratio across mismatched sets; quoting them without the full-set number would be exactly the selective reporting this decision exists to prevent.
4. **Wait for the device drive and show only its number.** Rejected: the drive may not happen before 15 Sep (plan R4); a device number, if it exists, is *added* with "one drive, n = k blackouts", never substituted for the mandated-dataset result.
5. **Report the paired win share against the frozen dot only** (59–72 %), which reads as a win. Rejected: it is true and stays on the chart, but the straight-line comparison is the one a navigation scientist asks about, and showing one without the other is selection.

## Consequences

- The deck contains a chart where the project's bar is not the shortest. The narrative around it — the dataset's fix period, the observability argument, the phone's 401 Hz / 1 Hz path, the components in flight — becomes the feasibility story, which is what the audit's §25 fix for slide 4 asks for ("It runs, it is measured, and it is not yet at the target").
- Competitor self-reports (PathPulse 10 %, Agastya 1.4 m ATE) are addressed by definition, not dispute: our metric is named on the slide (CRSE at the first real fix at or after the horizon, unaided), and the harness is offered.
- Any future improvement is shown against the same five bars, so a real gain is visible as a gain rather than as a re-baselined headline.
- The internal college jury may find the honesty unusual; the general-audience script leads with the app and the problem and reaches the chart second (plan §1 A5, R6).
- `eval/results/summary.md` (plan A11) becomes the single file the deck's numbers are read from, so the chart can be regenerated and checked mechanically before every export.

## Status

Accepted, 2026-09-10.

## Date

2026-09-10
