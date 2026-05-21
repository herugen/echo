# Echo

A local-first bilingual video learning workbench.

Echo turns local files or online videos into durable learning assets: source media,
transcripts, translated subtitles, bilingual subtitle files, final videos, and a
focused playback session for reviewing the result sentence by sentence.

Current MVP direction:
- Tauri desktop app for macOS, Linux, and Windows
- Local Python engine for video acquisition, transcription, translation, and output
- Study playback for processed tasks, not a general media library or media center
- Local-first assets: source media, transcripts, subtitles, final outputs, and manifests
- Architecture keeps room for a future CLI host without building one now

## Repository layout

- `apps/desktop/` — Tauri desktop app
- `packages/engine/` — local processing engine
- `docs/` — product and architecture notes
