# NEXUS Python 3.12+ Background Daemon Guide

## Target Runtime
- Python `3.12+` on Windows 10/11 64-bit (note: AI Studio Linux sandbox runs Python 3.11.2, so Python 3.12+ runtime verification must be run locally).

## Local Setup
```powershell
.\scripts\setup-python.ps1
pytest tests/python
```

## Package Layout
- `core/nexus_core/config.py` — Loopback bind configuration & SQLite paths
- `core/nexus_core/daemon.py` — Daemon lifecycle coordinator (Stage 2)
- `core/nexus_core/security.py` — Project directory sandboxing & permission gates
- `core/nexus_core/storage.py` — SQLite schema for projects, tasks, checkpoints, audit logs
- `core/nexus_core/orchestrator.py` — 12-step task pipeline definitions
