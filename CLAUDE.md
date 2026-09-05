# DEAD-RECKONING

This project targets **Smart India Hackathon 2026, problem statement SIH26168** (ISRO): an AI/ML system that uses only a smartphone's accelerometer and gyroscope to dead-reckon a vehicle's position through GPS blackouts (tunnels, multi-level parking, urban canyons), correct sensor drift/bias, detect outage entry/re-acquisition, and blend cleanly back to GPS. Validated by replaying an IO-VNBD sequence with GPS artificially cut through a tunnel-length section.

**Before doing any research on dead-reckoning, inertial odometry, GNIO/DMDVDR/AVNet, competitor teams, or related papers/repos: read [research/SIH26168-dead-reckoning-research.md](research/SIH26168-dead-reckoning-research.md) first.** It's a full technical dossier already covering:
- Deep reads of the DMDVDR/AVNet (2025), GNIO (2026), FDIO (2025), WiCHINS (2026), and PiDR (2026) papers — architectures, equations, results tables, ablations
- The pedestrian-odometry and vehicle-DR lineage (IONet → RIDI → RoNIN → TLIO / AI-IMU-DR → DeepOdo → DMDVDR)
- Datasets (IO-VNBD, GSDC, comma2k19, KITTI, OxIOD, RIDI, RoNIN) with GPS-outage-segment notes
- Code assets with license status (which repos are safe to build on vs. unlicensed)
- A proposed architecture synthesizing the papers, refined by cross-domain research, with a requirement-traceability table against the PS's own wording (§6-§7)
- **§10: ~14 live Indian SIH26168 GitHub competitor repos**, ranked by real technical maturity (not just filenames) — read this before claiming anything is "novel"
- **§11: international prior art** outside the Indian SIH ecosystem (comparatively sparse — verified, not just unsearched)
- **§12: cross-domain technique transfer** from SLAM/drone/marine/AR-VR/AMR/gait fields, including two techniques explicitly checked and rejected (Schuler tuning, gait-HMM) so they aren't re-investigated
- Full source citations (33 entries)

Don't re-run web research to rediscover any of this — the doc has it, with confidence levels marked per claim. Only research further to fill an explicitly-flagged gap, to check whether a new competitor repo has appeared since 2026-09-04, or to verify something before quoting it in a submission.

A rendered version (tables + architecture diagram, research-only, predates the market/plan work below) is published at: https://claude.ai/code/artifact/2a0af494-38e0-4434-8d1a-47c0f46cc0fd

**[research/SIH26168-open-track-findings.md](research/SIH26168-open-track-findings.md)** is a verification pass on nine proposed features/tracks, run after a collaborator caught two factual errors in the dossier. Read it before claiming anything is novel or starting any of: jamming-vs-blockage detection, online self-calibration, map coupling, conformal confidence, Ackermann/MoE/Mamba work, or IO-VNBD pipeline setup. It contains the schema gotchas, the FTO/patent landscape, and a per-feature buildable/not-buildable verdict.

**[PLAN.md](PLAN.md) is the buildable project plan** — positioning, full component-by-component architecture with data contracts, added-features detail, phased build order, validation targets, and a risk register. Read this before starting implementation.

Status as of 2026-09-04: planning complete, no implementation started yet.
