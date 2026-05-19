# Echo

A cross-platform local video processing desktop app.

Current MVP direction:
- Tauri desktop app for macOS, Linux, and Windows
- Local Python engine for video processing
- Local-first assets: source media, transcripts, subtitles, and final outputs
- Architecture keeps room for a future CLI host without building one now

## Repository layout

- `apps/desktop/` — Tauri desktop app
- `packages/engine/` — local processing engine
- `docs/` — product and architecture notes
