# Direct USB data connection

The Raspberry Pi Zero W can appear to Windows 11 as a USB Ethernet adapter. This is a
point-to-point cable connection: it does not use Wi-Fi, a router, Internet Connection Sharing,
DHCP, or cloud services. WebSockets continue to run over TCP with fixed addresses:

- Windows host: `192.168.7.1/24`
- Raspberry Pi: `192.168.7.2/24`
- WebSocket endpoint: `ws://192.168.7.1:8765`

After the one-time setup, connecting the cable creates `usb0`, NetworkManager assigns the Pi
address automatically, Windows reuses the adapter address, and the application reconnects.

## Safety and prerequisites

1. Keep Wi-Fi enabled until the USB link and SSH access are verified.
2. Use the Pi Zero micro-USB port closest to HDMI, labelled **USB**, not **PWR IN**.
3. Use a known data-capable cable.
4. Gadget mode makes that port a USB device; it can no longer host keyboards or storage.
5. Do not parallel two unrelated 5 V supplies. Either power the complete Pi/display from a
   sufficiently capable PC USB port, or use an intentionally data-only USB cable while a
   regulated supply powers `PWR IN`. Watch for undervoltage.

The setup replaces the existing `dtoverlay=dwc2,dr_mode=host` line with
`dtoverlay=dwc2,dr_mode=peripheral`. It also loads `g_ether`, gives the gadget stable,
locally-administered MAC addresses, and creates a NetworkManager profile for `usb0`.

## 1. Configure Raspberry Pi OS Bookworm

From the repository on the Pi:

```console
cd ~/displays
git pull --ff-only
source .venv/bin/activate
python scripts/setup_usb_gadget_bookworm.py --check
sudo python scripts/setup_usb_gadget_bookworm.py --apply
sudo reboot
```

The first application stores untouched boot-file backups under:

```text
/var/lib/desktop-display/usb-gadget-backup/
```

After reboot, connect the data cable to Windows and verify from the Pi (Wi-Fi SSH is still
acceptable during initial setup):

```console
python scripts/setup_usb_gadget_bookworm.py --check
ip -4 address show usb0
ping -c 3 192.168.7.1
```

## 2. Install the Windows driver if required

Windows should show **Raspberry Pi USB Remote NDIS Network Device** under Network adapters.
If it appears as an unknown device, install the official Raspberry Pi USB gadget driver from:

<https://github.com/raspberrypi/rpi-usb-gadget/releases>

Do not install an unrelated third-party RNDIS driver.

## 3. Configure Windows once

Open PowerShell **as Administrator**, change to the repository, and run:

```powershell
cd D:\display
powershell -ExecutionPolicy Bypass -File .\scripts\setup_usb_host_windows.ps1
ping 192.168.7.2
ssh pi@192.168.7.2
```

The script disables DHCP only on the detected Raspberry Pi USB adapter, assigns
`192.168.7.1/24`, marks the link Private when Windows has created its network profile, and
opens inbound TCP port 8765 only on Private networks and the USB address.

If more than one matching USB adapter exists:

```powershell
Get-NetAdapter
powershell -ExecutionPolicy Bypass -File .\scripts\setup_usb_host_windows.ps1 `
  -InterfaceAlias "Raspberry Pi USB"
```

## 4. Application configuration

The committed examples are Wi-Fi-first. Override the ignored local configuration files for
USB operation:

```toml
# config/host.toml
[server]
bind_host = "192.168.7.1"
port = 8765
```

```toml
# config/pi.toml
[host]
url = "ws://192.168.7.1:8765"
```

Start the implemented host and Pi network test as described in `docs/deployment.md`.

## Rollback

While Wi-Fi access is still available:

```console
cd ~/displays
sudo python scripts/setup_usb_gadget_bookworm.py --restore
sudo reboot
```

This restores the original `config.txt` and `cmdline.txt` and removes the dedicated
NetworkManager profile.

## References

- Raspberry Pi USB gadget project: <https://github.com/raspberrypi/rpi-usb-gadget>
- Raspberry Pi gadget-mode guidance:
  <https://www.raspberrypi.com/news/usb-gadget-mode-in-raspberry-pi-os-ssh-over-usb/>
