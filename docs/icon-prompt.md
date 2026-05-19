# Echo App Icon Prompt

你可以把这段直接丢给 ChatGPT / 图像生成器：

> Design a premium macOS and Windows desktop app icon for a local video understanding tool named “Echo”. The product transcribes, translates, and generates bilingual subtitles for local videos. Create a clean rounded-square app icon, no text, no letters, no UI mockup. Visual concept: a softly glowing audio waveform emerging from a video frame, forming a subtle echo/ripple shape. Style: modern Apple-like 3D minimalism, tactile depth, dark warm graphite background, amber/gold light accents, elegant and calm, suitable for productivity software. Keep the silhouette readable at 16px and 32px. Centered composition, high contrast, smooth gradients, no photorealistic people, no microphone cliché, no play-button cliché. Output as a 1024×1024 PNG with transparent or rounded-square background.

生成后建议产物：
- `icon.png`: 1024×1024 原图
- 再用 Tauri icon pipeline 生成 `icon.icns`、`icon.ico`、各尺寸 PNG
