[CmdletBinding()]
param(
    [string]$InterfaceAlias
)

$ErrorActionPreference = "Stop"
$HostAddress = "192.168.7.1"
$PrefixLength = 24
$FirewallRuleName = "Desktop Companion Display WebSocket (USB)"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run PowerShell as Administrator."
}

if ($InterfaceAlias) {
    $adapter = Get-NetAdapter -Name $InterfaceAlias
} else {
    $candidates = @(
        Get-NetAdapter | Where-Object {
            $_.InterfaceDescription -match "RNDIS|Raspberry Pi USB|USB Ethernet"
        }
    )
    if ($candidates.Count -eq 0) {
        throw @"
Raspberry Pi USB Ethernet adapter not found.
Connect the Pi Zero's USB port (not PWR IN). If Device Manager shows an unknown
RNDIS device, install Raspberry Pi's official USB gadget driver and rerun.
"@
    }
    if ($candidates.Count -gt 1) {
        $names = ($candidates | ForEach-Object Name) -join ", "
        throw "Multiple USB adapters found ($names). Rerun with -InterfaceAlias '<name>'."
    }
    $adapter = $candidates[0]
}

Write-Host "Configuring '$($adapter.Name)' as $HostAddress/$PrefixLength"

Set-NetIPInterface `
    -InterfaceIndex $adapter.ifIndex `
    -AddressFamily IPv4 `
    -Dhcp Disabled

Get-NetIPAddress `
    -InterfaceIndex $adapter.ifIndex `
    -AddressFamily IPv4 `
    -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -ne $HostAddress } |
    Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue

$existingAddress = Get-NetIPAddress `
    -InterfaceIndex $adapter.ifIndex `
    -AddressFamily IPv4 `
    -IPAddress $HostAddress `
    -ErrorAction SilentlyContinue

if (-not $existingAddress) {
    New-NetIPAddress `
        -InterfaceIndex $adapter.ifIndex `
        -IPAddress $HostAddress `
        -PrefixLength $PrefixLength | Out-Null
}

try {
    Set-NetConnectionProfile `
        -InterfaceIndex $adapter.ifIndex `
        -NetworkCategory Private
} catch {
    Write-Warning "Windows has not created a network profile yet; reconnect the cable and rerun."
}

$existingRule = Get-NetFirewallRule -DisplayName $FirewallRuleName -ErrorAction SilentlyContinue
if ($existingRule) {
    Set-NetFirewallRule `
        -DisplayName $FirewallRuleName `
        -Enabled True `
        -Profile Private `
        -Direction Inbound `
        -Action Allow | Out-Null
} else {
    New-NetFirewallRule `
        -DisplayName $FirewallRuleName `
        -Direction Inbound `
        -Action Allow `
        -Protocol TCP `
        -LocalPort 8765 `
        -LocalAddress $HostAddress `
        -Profile Private | Out-Null
}

Write-Host "USB host configuration complete."
Write-Host "Windows: $HostAddress"
Write-Host "Raspberry Pi: 192.168.7.2"
Write-Host "Test after the Pi reboots: ping 192.168.7.2"
