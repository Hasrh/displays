# Deployment outline

Deployment is intentionally not active at this milestone.

## Windows development host

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
Copy-Item config\host.example.toml config\host.toml
.\.venv\Scripts\python -m pc.main --config config\host.toml
```

The composition root currently validates configuration, logs that runtime services are not
implemented, and exits successfully. It does not bind a port.

## Raspberry Pi probe

Copy the repository or just `scripts/pi_hardware_probe.py` to the Pi, then run:

```console
python3 --version
python3 scripts/pi_hardware_probe.py
python3 scripts/pi_hardware_probe.py --json > pi-hardware-probe.json
```

The probe needs no third-party packages and makes no configuration changes. Normal-user
output is preferred; if entries show `unavailable`, rerun with `sudo` only to read protected
inventory and review the script first. Do not enable SPI or apply an overlay merely to make
the report look complete.

## Verified framebuffer test

The LCDWiki MPI3501 is exposed as `/dev/fb1` with 480×320 RGB565 geometry. Copy the example
configuration and run the explicit hardware test:

```console
cp config/pi.example.toml config/pi.toml
python3 -m pi.main --config config/pi.toml --display-test
```

This writes static RGB565 color bars and exits. The test does not configure SPI, load a
driver, contact the Windows host, or access touch input. The user running it must belong to
the `video` group or otherwise have write access to `/dev/fb1`.

## Future Pi service

Production deployment will use a dedicated unprivileged service account and a foreground
`systemd` unit with restart backoff. Configuration and authentication material will live
outside the source tree with restrictive permissions. The service will require the `video`
group for the verified framebuffer; input permissions are unnecessary while touch is disabled.

Production installation, service units, firewall rules, TLS/authentication, and dependencies
are deferred until their implementation milestones. Never expose a future unauthenticated
listener or commit a pre-shared token.
