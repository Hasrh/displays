# Hardware discovery

## Current status

The working Raspberry Pi setup is:

- Board: **Raspberry Pi Zero W Rev 1.1**
- OS: **Raspberry Pi OS Lite (Bookworm)**, Linux 6.12.x
- LCD module: **LCDWiki MPI3501**
- LCD controller: **ILI9486**, driven by `fb_ili9486` through fbtft
- Boot configuration: `dtparam=spi=on` and `dtoverlay=tft35a:rotate=90`
- Framebuffer: **`/dev/fb1`**
- Framebuffer geometry: **480×320**, 16 bits per pixel
- Pixel format: **RGB565** (`rgba 5/11,6/5,5/0,0/0`)
- Resistive-touch controller: **XPT2046** (ADS7846-compatible Linux driver family)

The LCD path is verified by a successful solid-pattern test. The kernel applies the
90-degree overlay rotation and exposes a 480×320 framebuffer. Touch input is intentionally
deferred; its event device and calibration matrix are not required for the current milestone.

## Read-only probe

On the Raspberry Pi, from the repository root:

```console
python3 scripts/pi_hardware_probe.py | tee pi-hardware-probe.txt
python3 scripts/pi_hardware_probe.py --json > pi-hardware-probe.json
```

The utility only reads OS/kernel details, device-tree compatibility and accessible overlay
state, relevant boot config lines, framebuffer/DRM devices, SPI devices and loaded modules,
and Linux input identities/capability bitmaps. It does not open `/dev/input/event*`, write
boot files, load modules, bind drivers, enable SPI, or apply overlays.

Useful independent read-only checks are:

```console
uname -a
tr '\0' '\n' < /proc/device-tree/compatible
ls -l /dev/fb* /dev/dri /dev/spidev* /dev/input/event* 2>/dev/null
cat /proc/bus/input/devices
cat /proc/modules
grep -E '^(dtoverlay|dtparam=spi|display_)' /boot/firmware/config.txt 2>/dev/null
grep -E '^(dtoverlay|dtparam=spi|display_)' /boot/config.txt 2>/dev/null
```

These commands are observational. Avoid `raspi-config`, `modprobe`, edits under `/boot`,
overlay application, GPIO writes, or calibration changes during discovery.

## Interpreting evidence

Evidence consistent with an ILI9486/ILI9488 display may include:

- a readable board/chip marking or vendor schematic explicitly naming `ILI9486` or
  `ILI9488` (strongest evidence);
- device-tree `compatible`, SPI `modalias`, framebuffer name, DRM driver symlink, or loaded
  module containing `ili9486`, `ili9488`, `fb_ili9486`, or a matching panel driver;
- an active `/dev/fbN` or `/dev/dri/cardN` whose sysfs device resolves to that verified SPI
  panel.

Evidence consistent with XPT2046 touch may include:

- a chip/board marking or schematic explicitly naming `XPT2046`;
- `compatible`/modalias/module text containing `xpt2046`, or commonly `ads7846` because the
  XPT2046 is often driven by Linux's ADS7846-compatible driver;
- an input block named `ADS7846 Touchscreen`, `XPT2046`, or similar, with an `eventN`
  handler and absolute-axis (`ABS`) capability bits.

Names are clues, not proof: copied overlays can declare an incorrect compatible string,
and `ads7846` may represent another compatible controller. Conversely, absent devices may
mean SPI/overlays are not configured, not that those chips are absent. A `spidev` node only
proves a generic SPI userspace device exists; it does not identify the connected controller.

## Remaining hardware work

1. Measure sustained full-frame throughput and CPU usage on the Pi Zero W.
2. Confirm the framebuffer device remains `/dev/fb1` across reboots.
3. When touch is enabled later, identify its `/dev/input/event*` device and calibration matrix.
