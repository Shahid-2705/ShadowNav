# ShadowNav: spoken scripts

Two versions of the same story. Every number below is from `eval/results/*.json` or a device measurement recorded in the repo; nothing is projected or aspirational unless the sentence says so. Time markers assume a relaxed speaking pace of about 130 words per minute.

---

## 1. For a general audience (about 2 min 45 s)

**[0:00] The problem.**
Every phone knows where it is, until it doesn't. Drive into a tunnel, an underground car park, or a street between tall buildings, and the little blue dot freezes, jumps, or wanders off the road. That is because the phone was listening to satellites, and now it can't hear them.

**[0:25] Why it matters here.**
In India that gap is not rare. New highway tunnels are kilometres long, city parking goes several floors underground, and about three out of four vehicles are two-wheelers, which have none of the extra sensors a modern car uses to cover for lost GPS. Delivery riders, cab drivers, ambulances: all of them lose their position exactly where it matters most.

**[0:55] What ShadowNav does.**
ShadowNav is an Android app that keeps the blue dot moving when the satellites go quiet, using only two sensors every phone already has: the one that feels acceleration and the one that feels turning. Think of it as a passenger with their eyes closed who still knows "we've been going straight for forty seconds, then turned right." When the satellites come back, the app slides back onto the real position smoothly instead of jumping.

**[1:25] The honest part.**
Sensors like these drift. Left alone, the guess gets worse every second. So ShadowNav does three things: it learns the phone's own quirks while GPS is still available, it uses the physics of a vehicle (cars don't slide sideways), and it tells you how sure it is with a circle on the map that is sized to be right nine times out of ten. We tested that claim, not assumed it.

**[1:55] The proof.**
We took 79 real drives from a public dataset, cut the GPS artificially 991 times, and measured how far off we were when it returned. Compared with simply adding up the sensor readings, ShadowNav is between 1.7 and 43 times closer to the truth, and the longer the blackout, the bigger the gap. After a one-minute tunnel we are typically about 640 metres off, where the naive method is nearly 7 kilometres off.

**[2:25] Where we are.**
The app runs today on a low-cost phone, is 2.2 megabytes, needs no internet, no extra hardware, and no permission from any map company. It is not finished: over a long straight tunnel we still drift more than we want, and we say so on the slides. The next step is to use the phone's much faster sensor rate, which is forty times what our test data had, to close that gap.

**[2:45] Close.**
ShadowNav: the blue dot that doesn't give up when the sky disappears.

---

## 2. For a technical audience (about 3 min 15 s)

**[0:00] Problem statement.**
SIH26168 from ISRO asks for smartphone dead reckoning through GNSS outages using only the accelerometer and gyroscope: correct drift and bias, detect outage entry and re-acquisition, and blend back without a jump. No wheel ticks, no CAN bus, no magnetometer.

**[0:20] Why the obvious approach fails.**
Strapdown integration of a consumer IMU diverges in seconds. On our benchmark the naive method is 310 metres off after 10 seconds and 63 kilometres off after three minutes. Heading error from gyro bias is the dominant term, and at 10 Hz logging even a well-formed 21-state error-state filter is unusable; we built one, verified its Jacobians numerically, and it diverged on the data. That result is recorded, not hidden.

**[0:50] What we built instead.**
A 5-state planar kinematic EKF: east, north, heading, speed, gyro bias. Speed is held through the blackout rather than integrated from the accelerometer, because integrating accelerometer noise was measurably worse. Around the filter sit four pieces. First, self-calibration: device-to-vehicle alignment estimated from horizontal specific force against GNSS-derived longitudinal acceleration during the aided phase, plus a stationary detector with an IMU-bootstrapped gravity check. Second, vehicle constraints: a non-holonomic pseudo-measurement and Ackermann curvature and friction bounds, the friction bound unconditional, the curvature bound slip-gated. Third, GNSS handling: a chi-square innovation gate at 11.6 for two degrees of freedom, per-satellite C/N0 de-weighting, gate escape after three consecutive rejections so the filter can never trap itself in dead reckoning, and a four-state machine, aided, degraded, dead-reckoning, reacquiring, with a critically damped blend at 2.3 rad/s on re-acquisition. Fourth, calibrated confidence: the filter's own 90 percent ellipse covered only 17 percent of true positions on held-out routes, so we fit a scalar conformal inflation on the validation fold; on the test fold coverage is 97 percent. We report that as empirically calibrated coverage, never as a guarantee, because trajectory errors are not exchangeable.

**[1:55] Learned component.**
A CNN plus GRU forward-speed front end, 128 thousand parameters, 0.13 megabytes, 2.4 milliseconds per window on one CPU core, with a GNIO-style motion bank and gated head. It is opt-in. Ablations show it helps at 30 to 120 seconds and hurts at 180 seconds on this 10 Hz data, and its bias flips sign between validation and test folds, so it is not in the default path. We would rather show a negative result than ship it blind.

**[2:25] Evaluation.**
IO-VNBD, CC BY 4.0, 79 drives, 29.7 hours. GPS is cut with seeded windows at 10, 30, 60, 120 and 180 seconds, 991 informative outages in total. Median error at the first fix back: 180, 368, 640, 1071 and 1474 metres against 310 metres to 63 kilometres for naive strapdown, a 1.7 to 43 times improvement. Every number reproduces from a committed seed; 161 Python tests and 21 Kotlin tests pass, and the Kotlin estimator matches the Python reference to one part in a billion on golden vectors.

**[2:55] Deployment and limits.**
Pure Kotlin, minSdk 29, 2.2 megabyte APK, foreground service, NavIC constellation visibility read through GnssStatus. Measured 401 Hz IMU on a moto g64. Limits we state on the slides: drift is still 77 to 108 percent of distance travelled at 60 to 180 seconds, against a 0.64 percent field reference from AVNet; long straight tunnels give the gyro bias nothing to correct against; NavIC has three operational satellites today. The next phase re-runs the strapdown and speed-net ablations at 401 Hz on the device, and adds a heading-only OpenStreetMap constraint that can never pull the track laterally.

**[3:15] Close.**
A phone-only dead-reckoning stack with measured error, calibrated confidence, and its failures written down.

---

## Likely questions and short answers

- **Why not use the magnetometer?** Outside the problem statement's scope, and inside a vehicle it is dominated by the chassis and electronics.
- **Why hold speed instead of integrating acceleration?** Measured: integrating forward acceleration from a 10 Hz consumer IMU made position worse at every horizon in our ablation.
- **Is 640 metres after a minute good?** No, and we say so. It is 10.7 times better than the floor, and the dataset's 10 Hz rate is the binding constraint; the phone gives 401 Hz.
- **How do you know the confidence circle is honest?** Coverage measured on routes the calibration never saw: 97 percent at a 90 percent target. Calibrated, not guaranteed.
- **Does it need the internet?** No. No cloud, no vendor SDK, no map tiles in the current build.
- **Where is the code?** Repository link on slide 6; build, tests and evaluation JSON are committed; the deck's figures are generated from those files by scripts in the repo.
