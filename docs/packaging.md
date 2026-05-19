# Echo Desktop Packaging

Echo MVP targets macOS and Windows 11 installers. End users should be able to install and run Echo without manually installing Python, WhisperX, yt-dlp, FFmpeg, or Python packages. The only expected first-run download is the WhisperX model cache when the selected model is not already present.

## What is bundled

Tauri bundles the React desktop app plus an `engine` resource directory:

```text
Echo.app / Echo.exe
└─ resources/engine
   ├─ src/echo_engine/        # Python engine source
   ├─ pyproject.toml
   ├─ python/                 # redistributable standalone Python runtime
   └─ bin/                    # optional extra native tools
```

At runtime:

- development builds use `packages/engine` directly;
- release builds use the bundled `resources/engine`;
- the app prepends the bundled Python bin directory and `resources/engine/bin` to `PATH`;
- `PYTHONPATH` points at `resources/engine/src`.

## Build-time runtime creation

The installer build creates a platform-native Python runtime automatically:

```bash
cd apps/desktop
npm run prepare:engine:runtime
```

This script:

1. copies the engine source into `apps/desktop/bundle-resources/engine`;
2. downloads/extracts a redistributable standalone Python runtime;
3. installs the engine dependencies into that bundled runtime;
4. leaves the prepared runtime for Tauri to bundle into the installer.

This is a **build-machine concern only**. Target users do not run this command.

By default this uses `python-build-standalone` release `20260510`, Python `3.10.20`. Override when needed:

```bash
ECHO_PYTHON_STANDALONE_URL=https://... npm run prepare:engine:runtime
# or
ECHO_PYTHON_STANDALONE_RELEASE=20260510 ECHO_PYTHON_STANDALONE_VERSION=3.10.20 npm run prepare:engine:runtime
```

## FFmpeg / media probing

The installer includes `imageio-ffmpeg`, so audio extraction does not require users to install FFmpeg separately. Media probing uses `ffprobe` when available and falls back to PyAV from the bundled Python runtime. If we later want a specific FFmpeg/FFprobe build, platform-specific binaries can still be placed under `packages/engine/bin/` and will be bundled first on `PATH`.

## macOS build

Build on macOS:

```bash
cd apps/desktop
npm run package:mac
```

Output is under:

```text
apps/desktop/src-tauri/target/release/bundle/dmg/
```

## Windows 11 build

Build on Windows 11:

```powershell
cd apps\desktop
npm run package:win
```

Output is under:

```text
apps\desktop\src-tauri\target\release\bundle\
```

## GitHub Actions Windows build

The repository includes a Windows packaging workflow at `.github/workflows/windows-installer.yml`. It runs on pushes to `main` and can also be started manually from the GitHub Actions tab.

The workflow builds on `windows-latest`, runs:

```powershell
cd apps\desktop
npm ci
npm run package:win
```

and uploads the `.msi` and NSIS `.exe` files as a workflow artifact named `echo-windows-installers`.

## Notes

- macOS and Windows installers should be built on their respective OSes because the bundled runtime and Python wheels are platform-specific.
- CUDA support is detected at runtime by WhisperX/PyTorch. If CUDA is unavailable or fails, the engine falls back to CPU.
- The installer should include Python packages and yt-dlp. WhisperX model files remain runtime cache artifacts and may download on first use.
