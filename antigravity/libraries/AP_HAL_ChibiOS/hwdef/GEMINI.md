# ArduPilot ChibiOS Board Porting — GEMINI.md

Reference guide for ChibiOS board definitions (`hwdef.dat`, `hwdef-bl.dat`, bootloaders, and board READMEs).

> **Read `.agents/references/hwdef.md` before creating or reviewing an hwdef.**
> Antigravity caps `GEMINI.md` files at 24,000 bytes, so the full 63 KB board porting
> playbook (pin mapping, DMA verification, BIDIR/bdshot rules, SPI/IMU conventions,
> standard README text blocks, and hardware review checklist) lives in
> `.agents/references/hwdef.md`. Use `read_file` on it before starting.

## Quick Rules

- Use `/hwdef-check` (`.agents/skills/hwdef-check/hwdef_check.py`) to automate DMA sharing, board ID uniqueness, file presence, BIDIR/bdshot, and commit-structure checks.
- Keep `hwdef.dat` and `hwdef-bl.dat` consistent (board ID, flash size, USB, SDMMC/SPI pins).
- Always rebuild and commit the bootloader binaries (`AP_Bootloader:` for `board_types.txt`, `bootloaders:` for binaries, `hwdef:` for board files — separate commits).
- `defaults.parm` and `@include` files must use valid parameter names within the 16-character limit.
- Avoid `DMA_NOSHARE` conflicts on shared buses (SPI, I2C, DShot/BIDIR timers).
