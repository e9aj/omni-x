# OMNI-X Desktop

The Windows-first desktop shell uses Tauri 2, React, TypeScript and Vite. It
starts the existing Python runtime as an owned local process and checks it via
an authenticated loopback health endpoint. Credentials never enter the
frontend. Chat, tasks, models and settings are being connected incrementally
to the existing SQLite-backed OMNI-X services.

Development prerequisites: Node.js/npm and Rust/Tauri tooling. From this
directory run `npm install`, `npm run typecheck`, `npm run build`, or
`npm run tauri dev`. The current environment has Node/npm, but Cargo execution
is blocked by Windows Application Control; Tauri compilation therefore remains
an explicit validation prerequisite on an unrestricted Windows build machine.
