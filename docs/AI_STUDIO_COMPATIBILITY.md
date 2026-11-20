# Google AI Studio vs. Windows Desktop Compatibility

Google AI Studio provides a Linux cloud preview running a Node.js + Vite server on port `3000` inside an HTTPS iframe.

- **Node.js Preview Backend (`server.ts`)**: Runs actively in AI Studio to serve the React frontend and `/api/*` diagnostic/protocol endpoints without exposing secrets to the browser.
- **Tauri 2 / Rust Shell (`apps/desktop/src-tauri/`)**: Scaffolding only inside AI Studio; `window.__TAURI_INTERNALS__` is absent in browser preview.
- **Python 3.12+ Daemon (`core/`)**: Cannot run as a persistent local Windows background service inside the browser iframe; loopback probes return honest `Disconnected` status unless a local bridge is reachable.
- **Unity & Godot Adapters (`adapters/`)**: Cannot execute inside AI Studio; live tool count remains `0`.
