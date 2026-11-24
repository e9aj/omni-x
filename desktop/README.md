# OMNI-X Desktop

The Windows-first desktop shell uses Tauri 2, React, TypeScript and Vite. It
starts the existing Python runtime as an owned local process and checks it via
an authenticated loopback health endpoint. Credentials never enter the
frontend. Chat, tasks, models and settings are being connected incrementally
to the existing SQLite-backed OMNI-X services.

The Windows alpha packages the Python backend as a managed sidecar. Hosted
Windows validation covers installation, launch, authenticated health, owned
process crash recovery, clean shutdown and silent uninstall. The installer is
currently unsigned; Windows security policy may require an authorised test
environment.

Development prerequisites: Node.js/npm and Rust/Tauri tooling. From this
directory run `npm ci`, `npm run typecheck`, `npm run build`, or
`npm run tauri dev`. For local Windows packaging when the repository is under
OneDrive, set `CARGO_TARGET_DIR` to a writable path outside OneDrive and create
the target-specific PyInstaller sidecar described in `.github/workflows/desktop.yml`.
