param(
    [switch]$Release = $true
)

$ErrorActionPreference = "Stop"

$manifest = Join-Path $PSScriptRoot "Cargo.toml"
$cargoArgs = @("build", "--manifest-path", $manifest)
$maturinArgs = @("-m", $manifest)

if ($Release) {
    $cargoArgs += "--release"
    $maturinArgs += "--release"
}

Write-Host "Building memory_bridge_rs..."
cargo @cargoArgs

Write-Host "Installing Python extension via maturin..."
python -m maturin develop @maturinArgs

Write-Host "Done."
