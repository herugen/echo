# Echo

A local-first video hub for playback-first bilingual media.

Echo turns local files or online videos into a browsable local media library:
video files, transcripts, translated subtitles, bilingual subtitle files, final
outputs, metadata, and a playback experience that opens directly from each video
card.

Current MVP direction:
- Tauri desktop app for macOS, Linux, and Windows
- Local Python engine for video acquisition, transcription, translation, and output
- Playback-first local video library inspired by familiar video-site browsing patterns
- Import and URL download as supporting actions, not the main screen
- Local-first assets: source media, metadata, thumbnails, transcripts, subtitles, final outputs, and manifests
- Architecture keeps room for a future CLI host without building one now

## Repository layout

- `apps/desktop/` — Tauri desktop app
- `packages/engine/` — local processing engine
- `docs/` — product and architecture notes
