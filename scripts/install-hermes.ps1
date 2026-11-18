[CmdletBinding()]
param(
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"
$HermesCommit = "4ae451d4126327c871fd084e60c045dec0c85911"
$InstallerUrl = "https://raw.githubusercontent.com/NousResearch/hermes-agent/$HermesCommit/scripts/install.ps1"
$temp = Join-Path ([System.IO.Path]::GetTempPath()) ("omnix-hermes-install-" + [guid]::NewGuid().ToString("N") + ".ps1")
try {
    Invoke-WebRequest -Uri $InstallerUrl -OutFile $temp -UseBasicParsing
    $args = @("-Commit", $HermesCommit)
    if ($NonInteractive) { $args += "-NonInteractive" }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $temp @args
    if ($LASTEXITCODE -ne 0) { throw "Hermes installer failed with exit code $LASTEXITCODE" }
    Write-Output "Hermes backend installed at $env:LOCALAPPDATA\hermes"
    Write-Output "OMNI-X will discover the installed backend automatically."
}
finally {
    Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue
}
