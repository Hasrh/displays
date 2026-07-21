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

## Future Pi service

After controller and backend verification, deployment will use a dedicated unprivileged
service account and a foreground `systemd` unit with restart backoff. Configuration and
authentication material will live outside the source tree with restrictive permissions.
The service will receive only the supplementary groups needed for the verified DRM,
framebuffer, SPI, or input devices.

Production installation, service units, firewall rules, TLS/authentication, and dependencies
are deferred until their implementation milestones. Never expose a future unauthenticated
listener or commit a pre-shared token.
