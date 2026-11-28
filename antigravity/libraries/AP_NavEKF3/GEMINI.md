# AP_NavEKF3 — GEMINI.md

Reference guide for working with the EKF3 navigation filter in ArduPilot.

> **Read `.agents/references/AP_NavEKF3.md` before modifying or analyzing EKF3.**
> Antigravity caps `GEMINI.md` files at 24,000 bytes, so the full 77 KB EKF3 playbook
> (ground effect, accel bias inhibition, hover Z-bias, gyro bias without yaw, known
> issues, mag cal, lane switching, DCM fallback, GPS-denied flight, and log tools)
> lives in `.agents/references/AP_NavEKF3.md`. Use `read_file` on the relevant
> sections before writing code or forming a diagnosis.

## State Vector (24 states)

From `AP_NavEKF3_core.h`:
- `0-3`: `quat` (NED -> body quaternion)
- `4-6`: `velocity` (NED, m/s)
- `7-9`: `position` (NED, m)
- `10-12`: `gyro_bias` (body, rad)
- `13-15`: `accel_bias` (body, m/s)
- `16-18`: `earth_magfield` (NED, Gauss)
- `19-21`: `body_magfield` (body, Gauss)
- `22-23`: `wind_vel` (NE, m/s)

## Filter & Replay Rules

- **ARCH-21 (Masked filter state keeps covariance consistent):** `P = P - K*H*P` is only right for optimal gain. Update a masked state in Joseph form, or decorrelate it before computing gain.
- **ARCH-26 (Filter outputs are not independent measurements):** Fuse correlated outputs from another filter only at the rate new information enters, or inflate noise.
- **REPLAY-1:** Append new DAL replay fields at the end of existing messages with explicit `unused` alignment bytes; zero must preserve old behaviour.
- **REPLAY-2:** Keep retired DAL fields in place renamed `unused`; never reuse a retired field's meaning.
- **REPLAY-3:** Everything EKF reads at runtime (sensor data, properties, vehicle flags, cached config) must come through `AP_DAL`.
- **REPLAY-4:** Infrequently changing config gets its own DAL message, written on change and at log start.

## Flight-State Flags Warning

`onGround`, `inFlight`, `takeOffDetected`, `land_complete`, and `is_flying()` have vehicle-specific meanings and recorded in-flight false positives (e.g., on Copter `onGround` is `!armed`, and `takeOffDetected` latches/lags across disarms or vehicle classes). Read the **Flight-State Flags** section of `.agents/references/AP_NavEKF3.md` before gating anything on them.
