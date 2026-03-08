---
name: hwdef-info
description: Show hardware definition details for an ArduPilot board. Use when the user asks about board pinouts, peripherals, MCU type, UART mappings, or hwdef.dat contents.
argument-hint: "<board_name>"
allowed-tools: Glob, Grep, Read, Bash(ls *)
---

# ArduPilot Hardware Definition Info

Show hardware definition details for board `$ARGUMENTS`.

## Workflow

### Step 1: Find the board's hwdef directory

```bash
ls libraries/AP_HAL_ChibiOS/hwdef/ | grep -i "$ARGUMENTS"
```

Board directories are at `libraries/AP_HAL_ChibiOS/hwdef/<board_name>/`.

### Step 2: Read the hwdef.dat

Read the main hardware definition file:

```
Read: libraries/AP_HAL_ChibiOS/hwdef/<board_name>/hwdef.dat
```

### Step 3: Extract key information

Report:
- **MCU:** type and variant (e.g., STM32H743)
- **Flash:** size in KB
- **Board ID:** APJ_BOARD_ID value
- **UARTs:** SERIAL_ORDER mapping (which SERIALn = which UART)
- **I2C:** bus ordering
- **SPI:** devices and bus assignments
- **ADC pins:** battery voltage/current sensing
- **PWM outputs:** timer channels and GPIO mappings
- **CAN:** interfaces available
- **LEDs:** onboard LED pins
- **IMU/Baro/Mag:** onboard sensor defines
- **Included files:** any `include` directives (for boards that inherit from others)
- **Default parameters:** read `defaults.parm` if it exists

### Step 4: Check for variants

Look for related boards:
- `<board_name>-periph` (AP_Periph variant)
- Bootloader definition (`hwdef-bl.dat`)

## hwdef.dat key directives

| Directive | Purpose |
|-----------|---------|
| `MCU` | MCU family and specific type |
| `FLASH_SIZE_KB` | Flash memory |
| `APJ_BOARD_ID` | Unique board ID for firmware loading |
| `SERIAL_ORDER` | Maps SERIALn to physical UART |
| `I2C_ORDER` | Maps I2C bus numbers |
| `Pxx FUNC PERIPH` | Pin assignment (e.g., `PA0 UART4_TX UART4`) |
| `define` | Compile-time defines |
| `include` | Inherit from another hwdef |
| `env` | Set build environment (e.g., `env AP_PERIPH 1`) |
| `IOMCU_UART` | IOMCU connection UART |
| `STORAGE_FLASH_PAGE` | Flash page for parameter storage |

## Special board types

- **Periph boards** (`-periph` suffix): Include parent hwdef + set `env AP_PERIPH 1`
- **Linux boards**: Defined in `libraries/AP_HAL_Linux/hwdef/`
- **ESP32 boards**: Defined in `libraries/AP_HAL_ESP32/hwdef/`
- **SITL**: No hwdef.dat — virtual board
