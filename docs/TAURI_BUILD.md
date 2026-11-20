# Building NEXUS Desktop Shell (Windows 10/11 64-bit)

See [`WINDOWS_PACKAGING_AND_INSTALL.md`](./WINDOWS_PACKAGING_AND_INSTALL.md) for full architecture, version management, clean VM verification, and uninstallation procedures.

## Prerequisites (Local Windows Machine)
1. Node.js 22+ and npm
2. Python 3.12+ (64-bit)
3. Rust toolchain (`rustup toolchain install stable-x86_64-pc-windows-msvc`)
4. Microsoft Visual Studio 2022 C++ Build Tools, Windows SDK & WebView2 Runtime
5. Tauri CLI v2 (`cargo install tauri-cli --version "^2.0.0"`)

## Automated Packaging Command (Windows PowerShell)
```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-desktop.ps1
```

## Manual Steps
```powershell
npm install
npm run sync:godot-addon
npm run stage:adapters
powershell -ExecutionPolicy Bypass -File scripts\build-python-sidecar.ps1
npm run build
cd apps\desktop\src-tauri
cargo tauri build
```

> Note: Google AI Studio runs in a Linux web container without `cargo`, `rustc`, `pyinstaller`, `makensis`, or Windows SDK toolchains. Native Windows installer compilation (`cargo tauri build`) and clean Windows VM install/uninstall checks have **not** been executed in the container and must be verified locally on Windows 10/11.
