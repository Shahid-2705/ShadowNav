# ShadowNav

**Smart India Hackathon 2026 — Problem Statement SIH26168 (ISRO)**

A smartphone-only (accelerometer + gyroscope, no external speed sensor) vehicle dead-reckoning system that holds position through GNSS blackouts — tunnels, multi-level parking, urban canyons — and blends back cleanly on GPS re-acquisition. The name refers to **GPS shadow**, the standard term for zones where satellite signal is blocked or degraded.

## The problem

Every commercial GNSS-denied dead-reckoning system (Baidu VDR, Amap's tunnel mode) is gated behind a vendor SDK, a hardware exclusive, or assumes a car's wheel-tick/CAN bus. India has no sovereign equivalent, no product targets the two-wheelers that make up ~75% of India's fleet, and NavIC currently has only 3 operational satellites — below the 4 needed for a fix. ShadowNav corrects IMU drift/bias, detects outage entry and re-acquisition, and dead-reckons through the gap using only sensors already in every phone.

## Repo layout

- **[PLAN.md](PLAN.md)** — the buildable project plan: positioning, full architecture with data contracts, phased build order, validation targets, risk register. Start here.
- **[research/SIH26168-dead-reckoning-research.md](research/SIH26168-dead-reckoning-research.md)** — technical dossier: paper deep-reads (DMDVDR/AVNet, GNIO, FDIO, WiCHINS, PiDR), dataset survey, competitor landscape, cross-domain technique transfer.
- **[research/SIH26168-open-track-findings.md](research/SIH26168-open-track-findings.md)** — verification pass on nine proposed features, with buildable/not-buildable verdicts. Read before claiming anything is novel.
- **[demo/](demo/)** — single-file WebGL presentation demo (`gnss-demo.html`) simulating the GNSS-blackout → dead-reckoning → re-acquisition cycle for live pitching.

## Status

Planning complete as of 2026-09-05. Implementation not yet started.
