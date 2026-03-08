---
name: boards
description: List and search ArduPilot board targets. Use when the user asks about available boards, board names, or what targets they can build for.
argument-hint: "[search term]"
allowed-tools: Bash(./waf *), Grep, Glob, Read
---

# List ArduPilot Boards

## Usage

List all available boards or search for specific ones.

### List all boards

```bash
./waf list_boards
```

### Search for a board

If the user provides a search term via `$ARGUMENTS`, filter the board list:

```bash
./waf list_boards | tr ' ' '\n' | grep -i "$ARGUMENTS"
```

### Show board details

To show details about a specific board, read its hwdef.dat:

```bash
# Find the board's hwdef directory
ls libraries/AP_HAL_ChibiOS/hwdef/ | grep -i <board_name>

# Read the hwdef.dat for pin mappings, MCU, peripherals
cat libraries/AP_HAL_ChibiOS/hwdef/<board_name>/hwdef.dat
```

## Board naming conventions

- Standard boards: `CubeOrange`, `MatekH743`, `Pixhawk6X`
- Peripheral variants: `CubeOrange-periph`, `MatekH743-periph`
- SITL variants: `sitl`, `SITL_x86_64_linux_gnu`
- Linux boards: `navigator`, `bebop`, `erlebrain2`

## Key hwdef.dat fields

| Directive | Example | Purpose |
|-----------|---------|---------|
| `MCU` | `STM32H7xx STM32H743xx` | MCU family and variant |
| `FLASH_SIZE_KB` | `2048` | Flash memory size |
| `APJ_BOARD_ID` | `AP_HW_CUBEORANGE` | Unique board identifier |
| `SERIAL_ORDER` | `OTG1 USART2 USART3` | UART mapping to SERIALn |
| `I2C_ORDER` | `I2C2 I2C1` | I2C bus ordering |
| `define` | `HAL_STORAGE_SIZE 32768` | Compile-time defines |
