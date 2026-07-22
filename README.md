# Flud Shell

A standalone Tauri v2 desktop application, built for fun.

## Development

```bash
cd flud-app
npm install
npm run tauri:dev
```

## Build

```bash
cd flud-app
npm run tauri:build
```

## Architecture

- `src/` — React frontend
- `src-tauri/` — Rust backend
- `migrations/` — Database schema

For detailed project rules, see `.claude/CLAUDE.md`.
