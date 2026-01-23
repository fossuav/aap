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

### 4.2. Complete Feature Extraction Checklist (MANDATORY)
**CRITICAL:** The README must document ALL features present in the `hwdef.dat`. Use this checklist to ensure nothing is missed:

#### 4.2.1. Battery Monitoring
*   `HAL_BATT_MONITOR_DEFAULT` -> `BATT_MONITOR`
*   `HAL_BATT_VOLT_PIN` -> `BATT_VOLT_PIN`
*   `HAL_BATT_CURR_PIN` -> `BATT_CURR_PIN`
*   `HAL_BATT_VOLT_SCALE` -> `BATT_VOLT_MULT`
*   `HAL_BATT_CURR_SCALE` -> `BATT_AMP_PERVLT` (Note the name change!)
*   **Second Battery:** If `HAL_BATT2_VOLT_PIN` or `HAL_BATT2_CURR_PIN` exist, document them in a separate subsection.

#### 4.2.2. Analog Inputs (Often Missed!)
*   **RSSI:** If `RSSI_ADC` or `BOARD_RSSI_ANA_PIN` is defined, add an "Analog RSSI and AIRSPEED inputs" section.
*   **Airspeed:** If `PRESSURE_SENS` or `HAL_DEFAULT_AIRSPEED_PIN` is defined, document it.

**Determining Analog Pin Numbers (MANDATORY):**
The actual pin numbers used in ArduPilot parameters (e.g., `RSSI_PIN`, `ARSPD_PIN`) are NOT the MCU pin names. They are assigned during build. To find them:

1.  Run `./waf configure --board <BoardName>`
2.  Look at `build/<BoardName>/hwdef.h` for `HAL_ANALOG_PINS`:
    ```c
    #define HAL_ANALOG_PINS \
    {  4,  4,  2*3.30/4096 }, /* PC4 PRESSURE_SENS */ \
    {  7,  7,    3.30/4096 }, /* PA7 BATT2_CURRENT_SENS */ \
    {  8,  8,    3.30/4096 }, /* PC5 RSSI_ADC */ \
    { 10, 10,    3.30/4096 }, /* PC0 BATT_VOLTAGE_SENS */ \
    { 11, 11,    3.30/4096 }, /* PC1 BATT_CURRENT_SENS */ \
    { 18, 18,    3.30/4096 }, /* PA4 BATT2_VOLTAGE_SENS */ \
    ```
3.  The first number in each entry is the ArduPilot pin number. Map them:
    *   `PRESSURE_SENS` -> `ARSPD_PIN` (e.g., 4)
    *   `RSSI_ADC` -> `RSSI_PIN` (e.g., 8)
    *   `BATT_VOLTAGE_SENS` -> `BATT_VOLT_PIN` (e.g., 10)
    *   `BATT_CURRENT_SENS` -> `BATT_CURR_PIN` (e.g., 11)
    *   `BATT2_VOLTAGE_SENS` -> `BATT2_VOLT_PIN` (e.g., 18)
    *   `BATT2_CURRENT_SENS` -> `BATT2_CURR_PIN` (e.g., 7)

*   Example section:
    ```markdown
    ## Analog RSSI and AIRSPEED inputs

    Analog RSSI uses RSSI_PIN 8
    Analog Airspeed sensor would use ARSPD_PIN 4
    ```

#### 4.2.3. PWM/Motors
*   Analyze `PWM(n)` entries.
*   Group channels sharing the same timer (e.g., `TIM3_CH1`, `TIM3_CH2`).
*   If `BIDIR` is present, note that those channels support bi-directional DShot.
*   Document LED strip output if present (usually `TIM1_CH1` with `# for WS2812 LED` comment).

#### 4.2.4. Sensors (Features List)
*   **Baro:** Look for `BARO` lines (e.g., `BARO DPS310`).
*   **Compass:** Look for `COMPASS` lines. If absent, assume "No builtin compass" unless `HAL_PROBE_EXTERNAL_I2C_COMPASSES` is defined.
*   **IMU:** Look for `IMU` lines (e.g., `ICM42688`). Note if dual IMUs exist.

#### 4.2.5. OSD
*   Check for `define OSD_ENABLED 1` and `SPIDEV osd ...` or `SPIDEV icm42688...`.
*   Note the OSD chip (MAX7456/AT7456E - they are compatible).

#### 4.2.6. CAN Bus (Often Missed!)
*   If `CAN1_RX`/`CAN1_TX` are defined, add a "CAN" section to the README.
*   Note if there's a silent pin (`GPIO_CAN1_SILENT`).
*   Example:
    ```markdown
    ## CAN

    The board has a CAN port for DroneCAN peripherals. CAN is active by default.
    ```

#### 4.2.7. GPIOs and Relays
*   Look for `PINIO1`, `PINIO2`, `VTX_PWR`, `CAM_SW` lines.
*   Map these to their `GPIO(n)` number.
*   Document the default state (HIGH/LOW) and function.
*   If `RELAYn_PIN_DEFAULT` is defined, mention which RELAY controls it.

#### 4.2.8. defaults.parm (Minimal Use)
**IMPORTANT:** Board definitions should NOT set user preferences in `defaults.parm`. Most parameters should be left for users to configure.

**Allowed in defaults.parm:**
*   `SERVO13_FUNCTION 120` - NeoPixel LED output (if board has dedicated LED pad)

**NOT allowed in defaults.parm:**
*   `MOT_PWM_TYPE` - User chooses DShot/PWM type
*   `SERVO_DSHOT_ESC` - User chooses ESC protocol
*   `FRAME_CLASS` - User chooses frame type
*   `NTF_LED_LEN` - User configures LED count
*   `RC_OPTIONS`, `FLTMODE_CH`, `RC*_REVERSED` - User preferences
*   Any flight behavior parameters

### 4.3. Refinement and Formatting
You **must** manually enhance the generated content to match the high-quality standards of existing boards (e.g., `TBS_LUCID_H7`, `TBS_LUCID_H7_WING_AIO`). The README should be "full" and meaningful, not just a bare list of pins.

**Standard Structure:**
1.  **Title:** `<Board Name> Flight Controller`
2.  **Introduction:** Brief description and **link to the manufacturer's product page**.
    *   If no manufacturer link is available, use a placeholder: `produced by [Manufacturer Name](URL_HERE)` and note it needs to be filled in.
3.  **Features (Detailed):** Bulleted list of specs. Include:
    *   **MCU:** Type, Speed (MHz), Flash size.
    *   **Sensors:** Specific IMU types (e.g., "Dual ICM42688"), Barometer type.
    *   **Power:** Input voltage range (e.g., "2S-6S"), BEC ratings (Volts/Amps).
    *   **Interfaces:** UART count, PWM count, I2C/CAN/USB support.
    *   **Mechanical:** Mounting holes, dimensions (if known).
4.  **Pinout:** Include images (Top, Bottom, etc.). Use `![Alt Text](Image.png "Title")`. Mention connector types (e.g., "JST-GH").
    *   **CRITICAL - Image Verification:** Before referencing image files, **verify they exist** in the board directory. Do NOT include `![image](Top.png)` references if the files don't exist.
    *   If no images are available, either:
        *   Omit the Pinout section entirely, OR
        *   Add a placeholder: `*Pinout images not yet available.*`
    *   Common image files: `Top.png`, `Bottom.png`, `Pinout.png`, `<BoardName>.png`
5.  **UART Mapping:** Table/List mapping `SERIALx` to physical UARTs and functions.
    *   **Do NOT** list `EMPTY` or missing UARTs in the README.
    *   Include the default protocol from `DEFAULT_SERIALn_PROTOCOL` (e.g., "MAVLink2", "GPS", "RC Input").
    *   Note DMA capabilities if relevant (check `NODMA` in hwdef).
    *   Note physical location if known (e.g., "RX1 in HD VTX connector", "on ESC connector").
    *   Include flow control info if UART has CTS/RTS pins defined.
6.  **RC Input:** Explain how to connect RC (SBUS, CRSF, etc.) and any necessary parameters.
7.  **OSD Support:** Mention Analog (MAX7456) and Digital (DisplayPort/MSP) support.
8.  **PWM Output:** Detail channel groups and DShot compatibility.
    *   Mention specific physical locations if relevant (e.g., "M1-M4 on 4-in-1 connector").
    *   Note default functions (e.g., "PWM 13 is Serial LED by default").
9.  **Battery Monitoring:** **CRITICAL**. List exact parameter settings:
    *   `:ref:BATT_MONITOR<BATT_MONITOR>`
    *   `:ref:BATT_VOLT_PIN<BATT_VOLT_PIN__AP_BattMonitor_Analog>`, `:ref:BATT_CURR_PIN<BATT_CURR_PIN__AP_BattMonitor_Analog>`
    *   `:ref:BATT_VOLT_MULT<BATT_VOLT_MULT__AP_BattMonitor_Analog>`, `:ref:BATT_AMP_PERVLT<BATT_AMP_PERVLT__AP_BattMonitor_Analog>`
    *   **If second battery pads exist** (check for `HAL_BATT2_VOLT_PIN`), add a subsection:
        ```markdown
        Pads for a second analog battery monitor are provided. To use:

        - Set BATT2_MONITOR 4
        - BATT2_VOLT_PIN 18
        - BATT2_CURR_PIN 7
        - BATT2_VOLT_MULT 11.0
        - BATT2_AMP_PERVLT as required
        ```
10. **Analog RSSI and Airspeed:** If defined in hwdef, document the pin numbers.
11. **CAN:** If CAN port exists, document it (even briefly).
12. **Compass:** State if internal exists or if external is required (I2C).
13. **GPIO/Relay Control:** Document VTX power, camera switch, or other user-controllable GPIOs with their default states and RELAY assignments.
14. **Loading Firmware:** Standard blurb about DFU and `apj` loading.

## 5. Examples

**Reference Commit:** `a3262271` (TBS Lucid H7 Wing AIO)
**Reference READMEs:**
*   `libraries/AP_HAL_ChibiOS/hwdef/TBS_LUCID_H7/README.md`
*   `libraries/AP_HAL_ChibiOS/hwdef/TBS_LUCID_H7_WING_AIO/README.md`

## 6. Verification and Completion

### 6.1. Board ID Registration (MANDATORY for new boards)
Every new board requires a unique `APJ_BOARD_ID`. This ID is used by the bootloader and ground stations.

**Process:**
1.  **Check existing IDs:** Review `Tools/AP_Bootloader/board_types.txt` for existing entries.
2.  **Find an available ID:**
    *   Look for gaps in existing ranges (IDs 1000-7199 for regular boards).
    *   Do NOT use IDs above 7199 for regular boards.
    *   IDs 10000+ are reserved for OpenDroneID variants (base_id + 10000).
3.  **Add your board ID:**
    ```
    AP_HW_<BoardName>                    <unique_id>
    ```
4.  **Verify no duplicates:**
    ```bash
    grep <your_id> Tools/AP_Bootloader/board_types.txt
    ```

**Example gaps to fill:** Check ranges like 1213-1221, 1224-1226, etc.

**In hwdef.dat:** Reference the board ID:
```
APJ_BOARD_ID AP_HW_<BoardName>
```

### 6.2. Build Verification
Before finalizing:
*   Run `./waf configure --board <BoardName>` to ensure `hwdef.dat` parses correctly.
*   Run `./waf copter` (or appropriate vehicle) to ensure it compiles.
*   Check the README rendering to ensure images and tables look correct.

### 6.3. README Completeness Checklist
**MANDATORY:** Before considering the README complete, verify ALL of these items:

| Feature | hwdef.dat Pattern | README Section Required? |
|---------|-------------------|--------------------------|
| Second Battery | `HAL_BATT2_VOLT_PIN` | Yes - add BATT2 subsection |
| Analog RSSI | `RSSI_ADC` or `BOARD_RSSI_ANA_PIN` | Yes - "Analog RSSI and AIRSPEED" |
| Analog Airspeed | `PRESSURE_SENS` or `HAL_DEFAULT_AIRSPEED_PIN` | Yes - "Analog RSSI and AIRSPEED" |
| CAN Port | `CAN1_RX`/`CAN1_TX` | Yes - "CAN" section |
| VTX Power GPIO | `PINIO1` with `VTX` comment or `GPIO(81)` | Yes - "VTX Power Control" |
| Camera Switch | `CAM_SW` or `PINIO` with camera comment | Yes - "Camera Control" |
| LED Strip | `PWM(13)` with LED comment, `SERVO13_FUNCTION 120` | Yes - mention in PWM Output |
| Flow Control | `UARTx_CTS`/`UARTx_RTS` pins | Yes - note in UART Mapping |
| Pinout Images | Files exist in board directory | Only if files exist! |

### 6.4. Cross-Reference Verification
Ensure consistency between `hwdef.dat` and `README.md`:
*   OSD chip name matches (MAX7456/AT7456E are compatible)
*   UART count matches `SERIAL_ORDER` (excluding EMPTY entries)
*   PWM count matches number of `PWM(n)` entries
*   IMU names match `IMU` lines exactly
*   Battery scale values match `HAL_BATT_VOLT_SCALE` and `HAL_BATT_CURR_SCALE`

### 6.5. Bootloader Build (MANDATORY for new boards)
**Every new board MUST have bootloader binaries built and committed.**

```bash
# Build the bootloader
python3 Tools/scripts/build_bootloaders.py <BoardName>
```

**Output files (all three are created):**
*   `Tools/bootloaders/<BoardName>_bl.bin` - Binary file (MUST be committed)
*   `Tools/bootloaders/<BoardName>_bl.hex` - Hex file (MUST be committed)
*   `Tools/bootloaders/<BoardName>_bl.elf` - ELF file (do NOT commit)

**Verify the bootloader was created:**
```bash
ls -la Tools/bootloaders/<BoardName>_bl.*
```

The bootloader binary is embedded in the main firmware build, so this step must be completed before the board can be used by others.

### 6.6. Commit and Pull Request Creation
When submitting a new board definition:

**Required files for PR (all must be committed):**
1.  `libraries/AP_HAL_ChibiOS/hwdef/<BoardName>/hwdef.dat` - Main hardware definition
2.  `libraries/AP_HAL_ChibiOS/hwdef/<BoardName>/hwdef-bl.dat` - Bootloader hardware definition
3.  `libraries/AP_HAL_ChibiOS/hwdef/<BoardName>/README.md` - Documentation
4.  `libraries/AP_HAL_ChibiOS/hwdef/<BoardName>/defaults.parm` - Default parameters (if needed)
5.  `Tools/AP_Bootloader/board_types.txt` - Add new unique board ID
6.  `Tools/bootloaders/<BoardName>_bl.bin` - Bootloader binary
7.  `Tools/bootloaders/<BoardName>_bl.hex` - Bootloader hex file

**Complete workflow:**
```bash
# 1. Verify board ID is unique
grep <your_id> Tools/AP_Bootloader/board_types.txt

# 2. Configure and build to verify hwdef.dat
./waf configure --board <BoardName>
./waf copter

# 3. Build bootloader (MANDATORY)
python3 Tools/scripts/build_bootloaders.py <BoardName>

# 4. Verify bootloader files exist
ls Tools/bootloaders/<BoardName>_bl.bin Tools/bootloaders/<BoardName>_bl.hex

# 5. Create commits (one per subsystem)
# Commit 1: Board ID
git add Tools/AP_Bootloader/board_types.txt
git commit -m "AP_Bootloader: add <BoardName> board ID"

# Commit 2: Bootloader binaries
git add Tools/bootloaders/<BoardName>_bl.bin Tools/bootloaders/<BoardName>_bl.hex
git commit -m "bootloaders: add <BoardName>"

# Commit 3: hwdef files
git add libraries/AP_HAL_ChibiOS/hwdef/<BoardName>/
git commit -m "AP_HAL_ChibiOS: add <BoardName> board support"
```

**Commit structure (MANDATORY - one commit per subsystem):**
ArduPilot requires separate commits for each subsystem. The commit message prefix must match the subdirectory name:

| Files | Subdirectory | Commit Prefix |
|-------|--------------|---------------|
| `Tools/AP_Bootloader/board_types.txt` | `AP_Bootloader` | `AP_Bootloader:` |
| `Tools/bootloaders/<BoardName>_bl.*` | `bootloaders` | `bootloaders:` |
| `libraries/AP_HAL_ChibiOS/hwdef/<BoardName>/` | `AP_HAL_ChibiOS` | `AP_HAL_ChibiOS:` |

**Example commits for a board named "FooFC":**
1. `AP_Bootloader: add FooFC board ID`
2. `bootloaders: add FooFC`
3. `AP_HAL_ChibiOS: add FooFC board support`

**PR Description should include:**
*   Board manufacturer and product page link
*   Key features (MCU, IMUs, interfaces)
*   Any special notes about the board
*   Confirmation that it builds successfully

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
*   **Purpose:** This file should be used **sparingly** - only for hardware-specific output assignments that cannot be set in `hwdef.dat`.
*   **Allowed:**
    *   `SERVO13_FUNCTION 120` - NeoPixel LED output on dedicated LED pad
*   **NOT Allowed (user preferences - do not set):**
    *   `MOT_PWM_TYPE`, `SERVO_DSHOT_ESC` - Motor/ESC configuration
    *   `FRAME_CLASS`, `FRAME_TYPE` - Vehicle configuration
    *   `NTF_LED_TYPES`, `NTF_LED_LEN` - LED configuration
    *   `OSD_TYPE` - OSD configuration
    *   `BATT_MONITOR` - Use `HAL_BATT_MONITOR_DEFAULT` in hwdef.dat instead
    *   `SERIALn_PROTOCOL` - Use `define DEFAULT_SERIALn_PROTOCOL` in hwdef.dat instead
    *   Any RC, flight mode, or behavior parameters

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

## 9. Standard README Text Blocks (Approved Language)

These templates match the approved language from the `chibios_hwdef.py --generate-readme` script.

### 9.1. Introduction (Template)
```markdown
# <Board Name> Flight Controller

The <Board Name> is a flight controller produced by [Manufacturer](URL), featuring <key highlights>.
```

**Key highlights to mention (pick 2-3 most notable):**
*   Processor type (e.g., "STM32H743 processor")
*   Dual IMUs if present (e.g., "dual ICM42688 IMUs for redundancy")
*   Notable interfaces (e.g., "7 UARTs, CAN bus, and analog OSD")
*   Target application if specific (e.g., "designed for fixed-wing aircraft")

**Example:**
```markdown
The Brahma H7 is a high-performance flight controller produced by [Manufacturer](URL), featuring an STM32H743 processor, dual ICM42688 IMUs for redundancy, and a full suite of interfaces including 7 UARTs, CAN bus, and analog OSD.
```

### 9.2. Features (Template)
```markdown
## Features

 - MCU - <MCU_TYPE> 32-bit processor running at <SPEED> MHz
 - Two <IMU_NAME> IMUs (if same type) OR list separately if different
 - <BARO_NAME> barometer
 - OSD - AT7456E (if present)
 - microSD card slot (or "flash-based logging" if dataflash)
 - <N>x UARTs
 - CAN support (if present)
 - <N>x PWM Outputs (<M> Motor Output, 1 LED)
```
**MCU Speed by series:** H7=480MHz, F7=216MHz, F4=168MHz

**Combining duplicate sensors:** If two devices are the same type, summarize on a single line:
*   "Two ICM42688-P IMUs" (not "IMU1 - ICM42688-P" + "IMU2 - ICM42688-P")
*   "Two DPS310 barometers" (if dual baro of same type)

### 9.3. UART Mapping (Template)
```markdown
## UART Mapping

The UARTs are marked Rn and Tn in the above pinouts. The Rn pin is the
receive pin for UARTn. The Tn pin is the transmit pin for UARTn.

 - SERIAL0 -> USB (MAVLink2)
 - SERIAL1 -> USART1 (<Protocol>, DMA-enabled)
 - SERIAL2 -> USART2 (<Protocol>)
```
**Protocol names:** Use human-readable names from `DEFAULT_SERIALn_PROTOCOL`:
- `SerialProtocol_MAVLink2` -> "MAVLink2"
- `SerialProtocol_GPS` -> "GPS"
- `SerialProtocol_RCIN` -> "RC Input"
- `SerialProtocol_ESCTelemetry` -> "ESC Telemetry"
- `SerialProtocol_MSP_DisplayPort` -> "DisplayPort"
- No protocol or `SerialProtocol_None` -> "Spare"

### 9.4. RC Input (Template - Detailed)
```markdown
## RC Input

The default RC input is configured on <UARTx>. RC could be applied instead to a different UART port such as <spare UARTs> and set
the protocol to receive RC data :ref:`SERIALn_PROTOCOL<SERIALn_PROTOCOL>` = 23 and change :ref:`SERIALx_PROTOCOL<SERIALx_PROTOCOL>`
to something other than '23'. For RC protocols other than unidirectional, the <UARTx>_TX pin will need to be used:

 - :ref:`SERIALx_PROTOCOL<SERIALx_PROTOCOL>` should be set to "23".
 - FPort would require :ref:`SERIALx_OPTIONS<SERIALx_OPTIONS>` be set to "15".
 - CRSF would require :ref:`SERIALx_OPTIONS<SERIALx_OPTIONS>` be set to "0".
 - SRXL2 would require :ref:`SERIALx_OPTIONS<SERIALx_OPTIONS>` be set to "4" and connects only the TX pin.
```

### 9.5. OSD Support (Template)
```markdown
## OSD Support

The <Board Name> supports OSD using OSD_TYPE 1 (MAX7456 driver)
```
If DisplayPort is available on a specific UART, add:
```markdown
and simultaneously DisplayPort using <UARTx> on the HD VTX connector.

## VTX Support

The SH1.0-6P connector supports a DJI Air Unit / HD VTX connection. Protocol defaults to DisplayPort. Pin 1 of the connector is 9v so
be careful not to connect this to a peripheral that can not tolerate this voltage.
```

### 9.6. PWM Output (Template)
```markdown
## PWM Output

The <Board Name> supports up to <N> PWM or DShot outputs. The pads for motor output
M1 to M<N> are provided on both the motor connectors and on separate pads, plus
separate pads for LED strip and other PWM outputs.

The PWM is in <N> groups:

 - PWM 1-2   in group1
 - PWM 3-4   in group2
 - PWM 5-6   in group3
 - PWM 7-10  in group4
 - PWM 11-12 in group5
 - PWM 13    in group6

Channels within the same group need to use the same output rate. If
any channel in a group uses DShot then all channels in the group need
to use DShot. Channels 1-10 support bi-directional dshot.
```

### 9.7. Battery Monitoring (Template)
```markdown
## Battery Monitoring

The board has a internal voltage sensor and connections on the ESC connector for an external current sensor input.
The voltage sensor can handle up to 6S LiPo batteries.

The default battery parameters are:

 - :ref:`BATT_MONITOR<BATT_MONITOR>` = <value>
 - :ref:`BATT_VOLT_PIN<BATT_VOLT_PIN__AP_BattMonitor_Analog>` = <pin>
 - :ref:`BATT_CURR_PIN<BATT_CURR_PIN__AP_BattMonitor_Analog>` = <pin> (CURR pin)
 - :ref:`BATT_VOLT_MULT<BATT_VOLT_MULT__AP_BattMonitor_Analog>` = <scale>
 - :ref:`BATT_AMP_PERVLT<BATT_AMP_PERVLT__AP_BattMonitor_Analog>` = <scale>
```

### 9.8. Second Battery Monitoring (Template)
```markdown
Pads for a second analog battery monitor are provided. To use:

 - :ref:`BATT2_MONITOR<BATT2_MONITOR>` 4
 - :ref:`BATT2_VOLT_PIN<BATT2_VOLT_PIN__AP_BattMonitor_Analog>` <pin>
 - :ref:`BATT2_CURR_PIN<BATT2_CURR_PIN__AP_BattMonitor_Analog>` <pin>
 - :ref:`BATT2_VOLT_MULT<BATT2_VOLT_MULT__AP_BattMonitor_Analog>` <scale>
 - :ref:`BATT2_AMP_PERVLT<BATT2_AMP_PERVLT__AP_BattMonitor_Analog>` as required
```

### 9.9. Analog RSSI Input (Template)
```markdown
## Analog RSSI input

Analog RSSI uses :ref:`RSSI_PIN<RSSI_PIN>` <pin>
```

### 9.10. Analog Airspeed Input (Template)
```markdown
## Analog AIRSPEED inputs

Analog Airspeed sensor would use ARSPD_PIN <pin>
```

### 9.11. Compass (Templates)
**Without builtin compass:**
```markdown
## Compass

The <Board Name> does not have a builtin compass, but you can attach an external compass using I2C on the SDA and SCL pads.
```

**With builtin compass:**
```markdown
## Compass

The <Board Name> has builtin compass. You can also attach an external compass using I2C on the SDA and SCL pads.
```

### 9.12. VTX Power Control (Template)
```markdown
## VTX power control

GPIO <N> controls the VTX BEC output to pins marked "9V" and is included on the HD VTX connector. Setting this GPIO low removes
voltage supply to this pin/pad. By default <RELAYn> is configured to control this pin and sets the GPIO high.
```

### 9.13. Camera Control (Template)
```markdown
## Camera control

GPIO <N> controls the camera output to the connectors marked "CAM1" and "CAM2". Setting this GPIO low switches the video output
from CAM1 to CAM2. By default <RELAYn> is configured to control this pin and sets the GPIO high.
```

### 9.14. Loading Firmware (Template)
```markdown
## Loading Firmware

Firmware for these boards can be found `here <https://firmware.ardupilot.org>`__ in sub-folders labeled "<Board Name>".

Initial firmware load can be done with DFU by plugging in USB with the
bootloader button pressed. Then you should load the "with_bl.hex"
firmware, using your favourite DFU loading tool.

Once the initial firmware is loaded you can update the firmware using
any ArduPilot ground station software. Updates should be done with the
*.apj firmware files.
```

### 9.15. FrSky Telemetry (Template)
```markdown
## FrSky Telemetry

FrSky Telemetry is supported using an unused UART, such as the Tx pin of <UARTy>.
You need to set the following parameters to enable support for FrSky S.PORT:

 - :ref:`SERIALy_PROTOCOL<SERIALy_PROTOCOL>` 10
 - :ref:`SERIALy_OPTIONS<SERIALy_OPTIONS>` 7
```

### 9.16. CAN Port (Template)
```markdown
## CAN

The <Board Name> has a CAN port for DroneCAN peripherals such as GPS, compass, airspeed, and rangefinder.
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
