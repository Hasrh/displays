# Hardware discovery

## Current status

The board specifications supplied by the owner identify:

- LCD controller: **ILI9486**
- Resistive-touch controller: **XPT2046** (ADS7846-compatible Linux driver family)

The controller-identification gate is complete. The SPI wiring, chip selects, GPIO pins,
kernel overlay, framebuffer/DRM device, input event device, rotation, and calibration matrix
remain unverified. Similar-looking boards use different wiring, so controller names alone
are not enough to select a boot overlay. Supply probe output and the board pinout before
concrete display integration.

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

## Evidence required before concrete backend implementation

Record:

1. Exact board model/revision, front/back photos, and PCB markings.
2. Full probe output, Pi model, Raspberry Pi OS release, and kernel version.
3. Physical SPI bus, chip selects, reset/data-command/backlight/interrupt pins.
4. Verified ILI9486 overlay/driver and resulting `/dev/fb*` or `/dev/dri/*` device.
5. Verified XPT2046 `/dev/input/event*`, native orientation, and calibration matrix.
6. Measured full-frame throughput after a safe driver setup.

Until these are supplied, the correct KMSDRM/framebuffer path and hardware-specific
configuration remain blocked by design even though both controller models are identified.
