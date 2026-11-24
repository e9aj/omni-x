# OMNI-X Windows alpha installation

## Requirements

- Windows 10 or Windows 11 x64.
- WebView2 runtime, normally present on supported Windows installations.
- An OmniRoute gateway or an explicitly configured compatible provider for AI
  inference. FREE mode is enabled by default.

## Install

1. Download the NSIS installer from the alpha workflow artifact supplied by the
   project owner.
2. Verify the published SHA-256 checksum before running it.
3. Run the installer and launch OMNI-X from the Start menu or installation
   directory.
4. Complete onboarding. Provider credentials are entered through OMNI-X's
   secure credential flow and are never stored in frontend state.

The development alpha installer is unsigned. Do not disable Smart App Control,
AppLocker or other Windows security features to run it. Use an authorised
allowlist or test VM if Windows blocks the package.

## Free mode

FREE mode and zero spending are the default policy. OMNI-X reports the selected
provider and model and does not invent credentials. If no eligible route is
available, configure a legitimate free-tier provider or a local model; do not
enter fabricated keys.

## Data and uninstall

SQLite sessions and settings are stored in the user's OMNI-X application-data
directory. Back up that directory before uninstalling if conversations must be
preserved. Uninstallation removes application files; user data handling is
reported by the installer workflow and should be reviewed before deletion.

## Troubleshooting

- A blocked installer means Windows policy rejected an unsigned development
  package; use an authorised test environment.
- A healthy desktop with no model response usually means the gateway/provider
  is unavailable or requires credentials.
- Attach only sanitised logs to issues. Never include tokens, credentials or
  private conversation data.
