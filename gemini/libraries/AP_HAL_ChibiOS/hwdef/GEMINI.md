# AI Playbook for ArduPilot ChibiOS Board Porting

<MANDATORY_RULE>
CRITICAL DIRECTIVE: THIS PLAYBOOK MUST BE USED AS THE PRIMARY AND AUTHORITATIVE GUIDE FOR CREATING NEW BOARD DEFINITIONS (HWDEF) AND DOCUMENTATION (README) FOR ARDUPILOT.
</MANDATORY_RULE>

## 1. Goal
To efficiently and accurately create new flight controller board definitions (`hwdef.dat`, `hwdef-bl.dat`) and their corresponding documentation (`README.md`) for the ArduPilot ChibiOS HAL.

## 2. Process Overview
1.  **Gather Information:** Obtain the Betaflight Unified Target configuration file for the board.
2.  **Generate Draft `hwdef`:** Use the conversion script to create a baseline `hwdef.dat`.
3.  **Refine `hwdef`:** Manually verify and clean up the generated definition, ensuring compliance with ArduPilot standards.
4.  **Generate Draft `README`:** Use the `chibios_hwdef.py` tool to generate a skeletal README.
5.  **Refine `README`:** Enhance the documentation with specific board details, images, and configuration instructions.

## 3. Creating `hwdef.dat` and `hwdef-bl.dat`

### 3.1. Automatic Conversion
The primary method for starting a port is to convert a Betaflight configuration file.

*   **Script:** `libraries/AP_HAL_ChibiOS/hwdef/scripts/convert_betaflight_unified.py`
*   **Usage:**
    ```bash
    ./libraries/AP_HAL_ChibiOS/hwdef/scripts/convert_betaflight_unified.py -I <BOARD_ID> <path_to_betaflight_config.conf>
    ```
*   **Outputs:** This will generate `hwdef.dat` and `hwdef-bl.dat` in the current directory.

### 3.2. Manual Refinement (Mandatory)
The auto-generated file is **always** incomplete and requires manual verification.

**Checklist:**
*   **MCU Definition:** Verify `MCU STM32...` matches the actual hardware.
*   **Flash Size:** Ensure `FLASH_SIZE_KB` and `FLASH_RESERVE_START_KB` are correct for the MCU and bootloader.
*   **SPI Table:**
    *   Verify `SPIDEV` entries map to the correct SPI bus and Chip Select (CS) pins.
    *   Ensure IMU, Baro, OSD, and Flash devices are correctly defined.
*   **UART Order:**
    *   `SERIAL_ORDER` determines the mapping to ArduPilot `SERIALx` parameters.
    *   Standard convention: `SERIAL0`=USB, `SERIAL1`=Telem1, `SERIAL2`=Telem2, `SERIAL3`=GPS1, `SERIAL4`=GPS2.
    *   Ensure `OTG1` (USB) is usually `SERIAL0`.
*   **Timers & PWM:**
    *   Betaflight uses different timer allocations. Verify `PWM(...)` assignments.
    *   Group channels sharing the same timer for DShot compatibility.
*   **ADC:**
    *   Verify `BATT_VOLTAGE_SENS`, `BATT_CURRENT_SENS` pins and scales (`HAL_BATT_VOLT_SCALE`, `HAL_BATT_CURR_SCALE`).
    *   Betaflight scales often need conversion.
*   **GPIOs:**
    *   Identify GPIOs for VTX power, Camera switching, etc., and map them to `GPIO(n)` or `RELAY`.

### 3.3. Schematic-Driven Generation
When a vendor schematic (PDF or Image) is provided, the AI must perform a structured extraction:

1.  **MCU Pin Tracing:** Systematically list MCU pins (e.g., `PA9`, `PB12`) and their Net Labels.
2.  **Net Matching:**
    *   **Comms:** Match `TX/RX` labels to UARTs. Trace `SCL/SDA` to I2C buses.
    *   **Sensors:** Identify chips connected to SPI/I2C buses (e.g., "ICM42688 on SPI1", "DPS310 on I2C2").
    *   **Actuators:** Trace `M1`, `M2`... to their Timer/Channel pins.
3.  **Peripheral Identification:** Note specific part numbers for IMUs, Barometers, and Regulators to populate `hwdef.dat` comments and README features.
4.  **Connector Mapping:** Correlate physical connectors (e.g., "J1 - GPS") with the traced MCU pins to generate the README "UART Mapping" table.

### 3.4. Vendor-Provided hwdef Refinement
If a vendor provides a draft `hwdef.dat`, use it as a base but treat it as potentially inaccurate.

1.  **Cross-Verification:** Cross-reference all pin assignments against provided schematics or high-res photos. Vendors often make copy-paste errors from other board definitions.
2.  **Missing Information:** Identify and add missing mandatory defines (e.g., `HAL_STORAGE_SIZE`, `OSCILLATOR_HZ`, `MCU_CLOCKRATE_MHZ`).
3.  **Sanitize Style:** Re-format the file to meet the **Style Guide (Section 11)**. This includes adding section headers and descriptive comments.
4.  **Audit `SERIAL_ORDER`:** **MANDATORY**: Ensure "Natural Order" is followed. Re-order UARTs so `SERIALn` maps to `UARTn`. Use `EMPTY` to skip gaps. Avoid random or vendor-specific ordering.

### 3.5. PWM & Timer Optimization
*   **DShot Priority:** Prioritize bi-directional DShot support for the first 4-8 motor outputs.
*   **Timer Selection:**
    *   Use `TIMx_CH1` through `TIMx_CH4`.
    *   **Avoid** complimentary channels (`TIMx_CH1N`) for DShot motors as they do not support bi-directional communication.
    *   **BIDIR Constraints:**
        *   Only supported on **TIM1 through TIM8**.
        *   **NEVER** apply `BIDIR` to `TIM4_CH4` (DMA conflict).
    *   **BIDIR Tag:** Apply `BIDIR` to at least one channel in a timer pair (CH1/CH2 or CH3/CH4).
        *   *Example:* `PA0 TIM5_CH1 TIM5 PWM(1) GPIO(50) BIDIR`
        *   *Note:* On F4/F7, the channel with the `BIDIR` tag determines which DMA channel is used for input capture. On H7, it is less critical but still good practice.
*   **Alternative Mappings:** If the default assignment is a complimentary channel (e.g., `TIM1_CH1N`), check the MCU definition script (e.g., `libraries/AP_HAL_ChibiOS/hwdef/scripts/STM32H743xx.py`) for alternative functions (e.g., `TIM3_CH2`) on the same pin that support DShot.

## 4. Creating `README.md`

### 4.1. AI-Driven Generation (Preferred)
Do **not** use the `chibios_hwdef.py --generate-readme` script, as it is error-prone. Instead, generate the README directly by analyzing the `hwdef.dat` file and applying the logic below.

### 4.2. Analysis Logic (hwdef.dat -> README)
Map the following `hwdef.dat` definitions to their corresponding README sections:

*   **Battery Monitoring:**
    *   `HAL_BATT_MONITOR_DEFAULT` -> `BATT_MONITOR`
    *   `HAL_BATT_VOLT_PIN` -> `BATT_VOLT_PIN`
    *   `HAL_BATT_CURR_PIN` -> `BATT_CURR_PIN`
    *   `HAL_BATT_VOLT_SCALE` -> `BATT_VOLT_MULT`
    *   `HAL_BATT_CURR_SCALE` -> `BATT_AMP_PERVLT` (Note the name change!)
*   **PWM/Motors:**
    *   Analyze `PWM(n)` entries.
    *   Group channels sharing the same timer (e.g., `TIM3_CH1`, `TIM3_CH2`).
    *   If `BIDIR` is present, note that those channels support DShot.
*   **Sensors (Features List):**
    *   **Baro:** Look for `BARO` lines (e.g., `BARO DPS310`).
    *   **Compass:** Look for `COMPASS` lines. If absent, assume "No builtin compass" unless `HAL_PROBE_EXTERNAL_I2C_COMPASSES` is defined.
    *   **IMU:** Look for `IMU` lines (e.g., `ICM42688`).
*   **OSD:**
    *   Check for `define OSD_ENABLED 1` and `SPIDEV osd ...`.
*   **GPIOs:**
    *   Look for lines labeled `VTX_PWR` or `CAM_SW`.
    *   Map these to the corresponding `GPIO(n)` number and describe their function (VTX Power, Camera Switch).

### 4.3. Refinement and Formatting
You **must** manually enhance the generated content to match the high-quality standards of existing boards (e.g., `TBS_LUCID_H7`, `TBS_LUCID_H7_WING_AIO`). The README should be "full" and meaningful, not just a bare list of pins.

**Standard Structure:**
1.  **Title:** `<Board Name> Flight Controller`
2.  **Introduction:** Brief description and **link to the manufacturer's product page**.
3.  **Features (Detailed):** Bulleted list of specs. Include:
    *   **MCU:** Type, Speed (MHz), Flash size.
    *   **Sensors:** Specific IMU types (e.g., "Dual ICM42688"), Barometer type.
    *   **Power:** Input voltage range (e.g., "2S-6S"), BEC ratings (Volts/Amps).
    *   **Interfaces:** UART count, PWM count, I2C/CAN/USB support.
    *   **Mechanical:** Mounting holes, dimensions (if known).
4.  **Pinout:** Include images (Top, Bottom, etc.). Use `![Alt Text](Image.png "Title")`. Mention connector types (e.g., "JST-GH").
5.  **UART Mapping:** Table/List mapping `SERIALx` to physical UARTs and functions.
    *   **Do NOT** list `EMPTY` or missing UARTs.
    *   Note DMA capabilities and physical location (e.g., "RX1 in HD VTX connector").
6.  **RC Input:** Explain how to connect RC (SBUS, CRSF, etc.) and any necessary parameters.
7.  **OSD Support:** Mention Analog (MAX7456) and Digital (DisplayPort/MSP) support.
8.  **PWM Output:** Detail channel groups and DShot compatibility.
    *   Mention specific physical locations if relevant (e.g., "M1-M4 on 4-in-1 connector").
    *   Note default functions (e.g., "PWM 13 is Serial LED by default").
9.  Battery Monitoring: **CRITICAL**. List exact parameter settings:
    *   `:ref:BATT_MONITOR<BATT_MONITOR>`
    *   `:ref:BATT_VOLT_PIN<BATT_VOLT_PIN__AP_BattMonitor_Analog>`, `:ref:BATT_CURR_PIN<BATT_CURR_PIN__AP_BattMonitor_Analog>`
    *   `:ref:BATT_VOLT_MULT<BATT_VOLT_MULT__AP_BattMonitor_Analog>`, `:ref:BATT_AMP_PERVLT<BATT_AMP_PERVLT__AP_BattMonitor_Analog>`

10. **Compass:** State if internal exists or if external is required (I2C).
11. **Loading Firmware:** Standard blurb about DFU and `apj` loading.

## 5. Examples

**Reference Commit:** `a3262271` (TBS Lucid H7 Wing AIO)
**Reference READMEs:**
*   `libraries/AP_HAL_ChibiOS/hwdef/TBS_LUCID_H7/README.md`
*   `libraries/AP_HAL_ChibiOS/hwdef/TBS_LUCID_H7_WING_AIO/README.md`

## 6. Verification
Before finalizing:
*   Run `./waf configure --board <BoardName>` to ensure `hwdef.dat` parses correctly.
*   Run `./waf <BoardName>` to ensure it compiles.
*   Check the README rendering to ensure images and tables look correct.

## 7. Best Practices & Reference

### 7.1. Header & ID
*   **Header:** Always start with `# hw definition file for processing by chibios_hwdef.py` and `# for <Board Name> hardware`.
*   **Board ID:** Use `APJ_BOARD_ID AP_HW_<BoardName>`.

### 7.2. MCU & System
*   **H7:** `MCU STM32H7xx STM32H743xx`, `FLASH_RESERVE_START_KB 128`, `STM32_ST_USE_TIMER 12`.
*   **F7:** `MCU STM32F7xx STM32F745xx`, `FLASH_RESERVE_START_KB 96`, `STM32_ST_USE_TIMER 5`.
*   **F4:** `MCU STM32F4xx STM32F405xx`, `FLASH_RESERVE_START_KB 48`, `STM32_ST_USE_TIMER 5`.
*   **Clock:** Explicitly set `MCU_CLOCKRATE_MHZ` (e.g., 480 for H7).
*   **LEDs:** If using standard notifications + external/onboard LEDs, ensure `define DEFAULT_NTF_LED_TYPES 455` is set if needed (sets bits 0,1,2,6,7,8).

### 7.3. Peripherals
*   **UARTs (Natural Ordering):**
    *   **MANDATORY for Non-IOMCU boards:** UARTs must be listed in "natural order" in `SERIAL_ORDER`.
    *   `SERIAL0` is usually `OTG1` (USB).
    *   `SERIAL1` should map to `UART1`, `SERIAL2` to `UART2`, and so on.
    *   **Use `EMPTY`** to skip missing physical UARTs to maintain the index (e.g., if `UART5` is missing: `SERIAL_ORDER OTG1 USART1 USART2 USART3 UART4 EMPTY USART6`).
    *   Set default protocols: `define DEFAULT_SERIALn_PROTOCOL SerialProtocol_MAVLink2`.
    *   Use `NODMA` for low-bandwidth ports (e.g., GPS, generic UARTs) if DMA channels are scarce.
    *   **RC Input:** Typically `SerialProtocol_RCIN`.
    *   **ESC Telemetry:** `SerialProtocol_ESCTelemetry`.
*   **SPI:**
    *   Define `SPIDEV` for all devices.
    *   Use `CS` keyword for Chip Select pins.
    *   Example: `SPIDEV osd SPI2 DEVID1 OSD1_CS MODE0 10*MHZ 10*MHZ`.
*   **I2C:**
    *   Order matters: `I2C_ORDER I2C2 I2C1`.
    *   Internal barometers often on a specific bus.
*   **ADC:**
    *   Use `ADC1` for battery.
    *   Standard scaling: `SCALE(1)`.
    *   Define `HAL_BATT_VOLT_PIN`, `HAL_BATT_CURR_PIN`, `HAL_BATT_VOLT_SCALE` (e.g., 11.0), `HAL_BATT_CURR_SCALE`.
*   **PWM/Motors:**
    *   Use `BIDIR` for DShot capability.
    *   Group timers carefully (comments like `# Motors` vs `# LEDs` help).
    *   Disable DMA (`NODMA`) on LED strips or aux outputs if needed.

### 7.4. Sensors
*   **Baro:** `BARO DPS310 I2C:0:0x76` (Driver Bus:Instance:Addr).
*   **Compass:**
    *   If none internal: `define ALLOW_ARM_NO_COMPASS`, `define HAL_PROBE_EXTERNAL_I2C_COMPASSES`.
    *   `define HAL_I2C_INTERNAL_MASK 0`.
*   **IMU:**
    *   `IMU <Driver> SPI:<name> <Rotation>`
    *   Example: `IMU Invensensev3 SPI:imu1 ROTATION_YAW_270`.

### 7.5. OSD & Flash
*   **OSD:** `define OSD_ENABLED 1`, `ROMFS_WILDCARD libraries/AP_OSD/fonts/font*.bin`.
*   **Logging:** `define HAL_LOGGING_DATAFLASH_ENABLED 1` (requires `SPIDEV dataflash ...`).

### 7.6. defaults.parm
*   **Purpose:** Use this file for ArduPilot parameters that should be set by default for this specific board, but aren't strictly hardware definitions.
*   **Common Defaults:**
    *   `NTF_LED_TYPES 455` (Enables internal and external LEDs: bits 0,1,2,6,7,8). Use this if the board has standard LED indicators.
    *   `OSD_TYPE 1` (MAX7456) or `OSD_TYPE 5` (MSP DisplayPort).
    *   `BATT_MONITOR 4`.
    *   `SERIALn_PROTOCOL` settings if they differ from the `hwdef.dat` defaults (though `hwdef.dat` `define DEFAULT_SERIALn_PROTOCOL` is preferred).

## 8. Documentation Standards (Reviewer Preferences)

### 8.1. Parameter Naming
*   **Battery:** **MANDATORY**: Use `BATT_AMP_PERVLT` instead of `BATT_CURR_SCALE` in the `README.md`.
    *   *Correct:* `BATT_AMP_PERVLT 40`
    *   *Incorrect:* `BATT_CURR_SCALE 40`
    *   *Note:* The `hwdef.dat` file still uses `HAL_BATT_CURR_SCALE`.
*   **ArduPilot Links:** Use ReStructuredText-style links for parameters to ensure they hyperlink correctly in the docs:
    *   `:ref:BATT_MONITOR<BATT_MONITOR>`
    *   `:ref:SERIAL1_PROTOCOL<SERIAL1_PROTOCOL>`

### 8.2. Structure & Specifications
*   **Specs List:** Use a detailed bulleted list for specifications:
    *   **Processor** (MCU, Flash)
    *   **Sensors** (IMU, Baro, Voltage/Current)
    *   **Power** (Input voltage, BECs)
    *   **Interfaces** (UARTs, PWM, I2C, USB, OSD, Camera inputs)
*   **Pinouts:**
    *   Include `## Pinout` and `## Wiring Diagram` (if applicable).
    *   Image format: `![Alt Text](filename.png)` or `[Board Name](filename.png)`.
*   **UART Mapping:**
    *   List `SERIALx` -> `UARTy` (Function).
    *   Note DMA capabilities if relevant.

### 8.3. RC Input
*   Explicitly list supported protocols (SBUS, DSM, CRSF).
*   Mention if specific parameters are needed (e.g., `SERIALn_OPTIONS` for FPort or half-duplex).

### 8.4. OSD
*   State "Built-in OSD" or "Analog OSD" using MAX7456.
*   Mention HD/Digital support (DisplayPort/MSP) on specific UARTs.

## 9. Standard README Text Blocks

### 9.1. Loading Firmware
```markdown
## Loading Firmware

The <Board Name> does not come with ArduPilot firmware pre-installed. Use the instructions here to load ArduPilot the first time :ref:`common-loading-firmware-onto-chibios-only-boards`.
Firmware for the <Board Name> can be found `here <https://firmware.ardupilot.org>`_ in sub-folders labeled "<Board Directory Name>".

Initial firmware load can be done with DFU by plugging in USB with the
bootloader button pressed. Then you should load the "with_bl.hex"
firmware, using your favourite DFU loading tool.

Once the initial firmware is loaded you can update the firmware using
any ArduPilot ground station software. Updates should be done with the
*.apj firmware files.
```

### 9.2. RC Input (Template)
```markdown
## RC Input

RC input is configured by default via the <UARTx> RX input (SERIALx). It supports all serial RC protocols.

* For FPort the receiver must be tied to the <UARTx> TX pin, and :ref:`SERIALx_OPTIONS<SERIALx_OPTIONS>` set to "7" (invert TX/RX, half duplex).
* For full duplex CRSF/ELRS use both TX and RX on <UARTx>, and set :ref:`SERIALx_PROTOCOL<SERIALx_PROTOCOL>` to 23.
```

### 9.3. FrSky Telemetry (Template)
```markdown
## FrSky Telemetry

FrSky Telemetry is supported using an unused UART, such as the Tx pin of <UARTy>.
You need to set the following parameters to enable support for FrSky S.PORT:

 - :ref:`SERIALy_PROTOCOL<SERIALy_PROTOCOL>` 10
 - :ref:`SERIALy_OPTIONS<SERIALy_OPTIONS>` 7
```

### 9.4. OSD Support (Template)
```markdown
## OSD Support

The <Board Name> supports analog OSD using its onboard MAX7456.
External MSP DisplayPort OSDs (like DJI or Walksnail) are supported on <UARTz> (SERIALz).
```

## 10. hwdef.dat Formatting & Style Guide

To ensure maintainability and human-readability, `hwdef.dat` files must adhere to the following structural and commenting standards.

### 10.1. Sectioning
Use distinct separator comments to divide the file into logical blocks.
```bash
# ---------------- MCU & System ----------------
...
# ----------------- SPI Bus --------------------
...
# ----------------- I2C Bus --------------------
...
# ----------------- UARTs ----------------------
...
# ----------------- PWM & GPIO -----------------
```

### 10.2. Commenting Rules
*   **Inline Comments:** Use `#` to explain specific assignments, especially for non-obvious pins.
    *   `PC4 PRESSURE_SENS ADC1 SCALE(2) # External Airspeed`
*   **Peripheral Context:** Explicitly state what is connected to buses.
    *   `# SPI1 - Internal ICM42688 IMU`
    *   `# USART1 - RC Input (SBUS/CRSF)`
*   **DMA Explanation:** If disabling DMA, explain why.
    *   `PB9 UART4_TX UART4 NODMA # Shared DMA resource with SPI3`

### 10.3. Grouping
*   **Keep related pins together.** Do not scatter pins for the same UART or Timer across the file.
*   **Logic Flow:** Follow the flow: System -> Comms (SPI/I2C/UART) -> IO (PWM/GPIO) -> ADC.

## 11. Troubleshooting

### 11.1. Compilation Errors
*   **Missing MAVLink Headers (`fatal error: include/mavlink/v2.0/...`):
    *   *Cause:* Submodules are not initialized or out of sync.
    *   *Fix:* Run `git submodule update --init --recursive`. If that fails, manually generate headers: `python3 modules/mavlink/pymavlink/tools/mavgen.py --lang=C --wire-protocol=2.0 --output=build/<Board>/include/mavlink/v2.0 modules/mavlink/message_definitions/v1.0/all.xml`.

### 11.2. Configuration Errors
*   **Missing Board ID (`ValueError: Unable to map ... to a board ID`):
    *   *Cause:* The `APJ_BOARD_ID` in `hwdef.dat` is not listed in the central registry.
    *   *Fix:* Add the new ID to `Tools/AP_Bootloader/board_types.txt`. Ensure no duplicates.

### 11.3. Build Failures
*   **Bootloader Missing (`Error: Bootloader ... does not exist`):
    *   *Cause:* The main firmware build requires the bootloader binary to be present for embedding (if enabled).
    *   *Fix:* Build the bootloader explicitly: `Tools/scripts/build_bootloaders.py <BoardName>`.

## 12. DMA Verification & Optimization

### 12.1. General DMA Requirements (All MCUs)
Certain peripherals have strict or high-priority DMA requirements for reliable operation:
*   **RC Input (CRITICAL):** `USARTn_RX` **MUST** have DMA for high-rate protocols (CRSF/ELRS) or those requiring precision (inverted SBUS).
*   **GPS (HIGH):** Should have DMA for high baud rates. If `NODMA` is unavoidable, set `GPS_DRV_OPTIONS` to 1 (lower baudrate).
*   **HD VTX (HIGH):** MSP DisplayPort and high-rate telemetry require high bandwidth; prioritize DMA.
*   **DShot (HIGH):** Motor timers must have DMA for bi-directional communication.
*   **ESC Telemetry (LOW):** Does **not** require DMA if the board supports bi-directional DShot (as DShot provides the primary telemetry path).

### 12.2. Verification Process
DMA channel allocation is dynamic. To verify all critical peripherals got a DMA channel:
1.  Run `./waf configure --board <BoardName>`.
2.  Open the generated header: `build/<BoardName>/hwdef.h`.
3.  Search for the string `//` (comments) next to line definitions or `HAL_..._DMA_STREAM`.
4.  Look for warnings like `// No DMA stream found` or `// SHARED`.

### 12.3. F4/F7 MCU Specifics
F4 and F7 MCUs have rigid DMA maps compared to the flexible DMAMUX on H7. Conflicts are common.

1.  **Prioritize Fast/Time-Critical:** Ensure Timers, SPI (IMU), and SDIO/SDMMC have DMA.
2.  **Sacrifice Slow Peripherals:**
    *   **I2C:** Often safe to use `NODMA I2C*` or `define STM32_I2C_USE_DMA FALSE`.
    *   **Low-Priority UARTs:** Telemetry (standard MAVLink), Spare ports, and **ESC Telemetry** (if using bi-directional DShot) can run without DMA. Add `NODMA` (e.g., `PA9 USART1_TX USART1 NODMA`).

### 12.4. Resolution
If a critical peripheral is missing DMA:
*   **Conflict Resolution:** Add `NODMA` to *less* critical peripherals in `hwdef.dat` to free up streams.
*   **Prioritization:** Use `DMA_PRIORITY <Peripheral>*` to force allocation.
*   **Sharing:** Use `DMA_NOSHARE <Peripheral>*` to prevent critical devices (like IMU SPI) from sharing with slow ones.
