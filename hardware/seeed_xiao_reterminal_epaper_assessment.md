# Seeed XIAO / reTerminal E ePaper Reference Assessment

Date: 2026-06-10

## Question

Check whether Seeed XIAO eInk boards or reTerminal E can be used as a reference for the MF-1750 / M009F-T 1024x600 six-color panel.

## Current MF-1750 Requirement

- Panel: MF-1750 / M009F-T, 1024x600, six-color.
- Connector: 50-pin FPC, 0.5 mm pitch.
- Critical interface finding from our tests: full-screen refresh needs two chip-select lines.
- Required control pins:
  - `CSB`: MF-1750 pin 31, main controller / left half.
  - `SL_CSB`: MF-1750 pin 4, second controller / right half.
- Current DESPI-C73 issue: only one CS is exposed, so only half of the panel is actually addressed.

## Seeed XIAO eInk Expansion Board V2

Source:
- Official wiki: https://wiki.seeedstudio.com/xiao_eink_expansion_board_v2/
- Local mirror: `hardware/reference_seeed_wiki_documents/sites/en/docs/Sensor/ePaper_Displays/Expansion_Board_Series/for_XIAO_Design/xiao_eink_expansion_board_v2.md`

Findings:
- Uses 24-pin FPC connector.
- Single SPI chip select only.
- Wiki pinout maps `CS` to XIAO `D1`, `RST` to `D0`, `DC` to `D3`, `BUSY` to `D2`, `SCK` to `D8`, `MOSI` to `D10`.
- Supported panels are Seeed 24-pin SPI ePaper modules, including 7.5 inch 800x480 mono/tri-color and 5.65 inch seven-color 600x480.

Assessment:
- Not directly usable for MF-1750.
- Useful only as a reference for XIAO socket, battery connector, charging/switching style, and basic SPI firmware conventions.

## Older XIAO eInk Expansion Board

Source:
- Official wiki: https://wiki.seeedstudio.com/XIAO-eInk-Expansion-Board/
- Local mirror: `hardware/reference_seeed_wiki_documents/sites/en/docs/Sensor/ePaper_Displays/Expansion_Board_Series/for_XIAO_Design/ePaper_Breakout_Board_For_XIAO/XIAO-eInk-Expansion-Board.md`

Findings:
- Uses 24-pin FPC connector.
- Single SPI chip select only.
- Has a downloadable Eagle PCB/SCH zip.

Assessment:
- Not directly usable for MF-1750.
- May be useful as a simple Eagle/KiCad style reference for small XIAO ePaper boards, but not for the MF-1750 50-pin dual-CS interface.

## XIAO 7.5 inch ePaper Panel

Source:
- Official wiki: https://wiki.seeedstudio.com/xiao_075inch_epaper_panel/
- ESPHome page: https://wiki.seeedstudio.com/xiao_075inch_epaper_panel_esphome/
- Local mirror: `hardware/reference_seeed_wiki_documents/sites/en/docs/Sensor/ePaper_Displays/xiao_075inch_epaper_panel/getting_started_with_xiao_075_epaper_panel.md`

Findings:
- MCU: XIAO ESP32-C3.
- Display: 7.5 inch monochrome, 800x480.
- ESPHome example uses Waveshare `7.50inv2`, with one `cs_pin`.
- Resources include an `ePaper_Driver_Board.pdf`.

Assessment:
- Not directly usable for MF-1750.
- It is a finished 800x480 monochrome product, not a 1024x600 six-color dual-controller raw panel driver.
- Useful mainly for enclosure, battery, sleep-mode, and dashboard software ideas.

## reTerminal E Series

Source:
- Official wiki: https://wiki.seeedstudio.com/reterminal_e10xx_main_page/
- Local mirror: `hardware/reference_seeed_wiki_documents/sites/en/docs/Sensor/ePaper_Displays/reTerminal_E10xx/reterminal_e10xx_main_page.md`

Findings:
- reTerminal E1001: 7.5 inch monochrome, 800x480.
- reTerminal E1002: 7.3 inch full-color Spectra 6, 800x480.
- reTerminal E1003: 10.3 inch monochrome, 1404x1872.
- reTerminal E1004: 13.3 inch full-color Spectra 6, 1200x1600.
- These are finished ESP32-S3 ePaper terminals, not generic 1024x600 MF-1750 driver boards.

Assessment:
- Not directly usable for MF-1750.
- Useful as a software/product architecture reference: SenseCraft HMI, Home Assistant, TRMNL, Arduino workflows, sleep and battery behavior.

## XIAO ePaper Display Board EE04

Source:
- Official wiki: https://wiki.seeedstudio.com/epaper_ee04/
- Official SCH PDF: https://files.seeedstudio.com/wiki/Epaper/EE04/XIAO_ePaper_Display_Board_EE04_SCH_V1.2.pdf
- Official SCH&PCB zip downloaded locally:
  - `hardware/seeed_ee04_sch_pcb.zip`
  - `hardware/reference_seeed_ee04/202004537_XIAO ePaper Display Board EE04_V1.2_SCH & PCB/`

Findings:
- Board is based on XIAO ESP32-S3 Plus.
- It supports both 24-pin and 50-pin 0.5 mm ePaper connectors.
- 50-pin connector footprint in KiCad:
  - `J1`
  - value `CHW05200-501TAPE-2W`
  - footprint `Connector:FPC50-0.5-28.6X4.9X2MM`
- KiCad source has no `SL_CSB` or `CS2` net.
- KiCad PCB shows:
  - `J1 pad 4 = unconnected-(J1-Pad4)`
  - `J1 pad 20 = SPI0_CS`
  - `J1 pad 18 = SPI0_MOSI`
  - `J1 pad 19 = SPI0_CLK`
  - `J1 pad 21 = EDP_DC`
  - `J1 pad 22 = EDP_BUSY`
  - `J1 pad 23 = EDP_RES`
- This 50-pin mapping appears targeted to Seeed's 7.3 inch Spectra 6 800x480 panel, not MF-1750.

Assessment:
- EE04 is the most useful Seeed hardware reference, but it still cannot be copied directly for MF-1750.
- The exact conflict is critical: MF-1750 needs pin 4 as `SL_CSB`, while EE04 leaves J1 pad 4 unconnected.
- If adapting EE04 to MF-1750, add a second CS net:
  - Route `J1 pin 4 / SL_CSB` to a spare ESP32-S3 GPIO.
  - Keep `J1 pin 31 / CSB` mapped according to the MF-1750 datasheet, not the EE04 50-pin mapping.
  - Verify all MF-1750 power rails and charge-pump pins against the MF-1750 pin table; do not assume Seeed 7.3 inch Spectra 6 pinout equals MF-1750.

## Practical Conclusion

Use Seeed EE04 as a layout and board-architecture reference, not as a pin-compatible base.

Recommended reuse:
- XIAO ESP32-S3 Plus placement and surrounding decoupling.
- Battery connector, switch, charger/PMIC structure.
- 50-pin FPC footprint style and pin-1 marking practice.
- Jumper/silkscreen warning style for 24-pin vs 50-pin modes.
- PlatformIO / Seeed_GFX workflow ideas.

Do not reuse directly:
- EE04 J1 50-pin net mapping.
- Single `SPI0_CS` architecture.
- Seeed 7.3 inch 800x480 Spectra 6 driver constants.
- XIAO 7.5 inch 800x480 monochrome ESPHome config.

## Next Design Action

For the MF-1750 board, continue from our own 50-pin MF-1750 pin map and use EE04 only to improve:

- PCB mechanical layout around the FPC connector.
- XIAO ESP32-S3 Plus module/socket option.
- Battery and power-switch circuit.
- Silkscreen labels, pin-1 marking, and orientation warnings.

The MF-1750 design must explicitly include `SL_CSB` on FPC pin 4 and expose it to the MCU.
