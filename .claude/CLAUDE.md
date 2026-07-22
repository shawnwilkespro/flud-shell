# Flud Shell — Container Routing

**This is a container-level routing file.** The actual git repo lives at `flud-app/` (submodule).

Cascade position:
```
~/.claude/CLAUDE.md
  └─ Documents/.claude/CLAUDE.md
     └─ GitHub/.claude/CLAUDE.md
        └─ flud-shell/.claude/CLAUDE.md    ← you are here
           └─ flud-shell/flud-app/.claude/CLAUDE.md  ← project rules
```

---

## Structure

```
flud-shell/                 ← superproject (tracks submodule pointer)
└── flud-app/              ← submodule → github.com/shawnwilkespro/flud.git
    ├── src/               ← React frontend
    └── src-tauri/         ← Rust backend
```

## Branch

- `main` — production branch only.

## Tech Stack

- **Frontend:** React 19, TypeScript, Tailwind CSS
- **Desktop:** Tauri v2
- **Backend:** Rust (src-tauri/)
- **Database:** Migrations tracked in `flud-app/migrations/`

## Rules

- Always `cd` into `flud-app/` before making changes
- `flud-app/` is a **submodule** — commit there first, then update the superproject pointer
- `src-tauri/target/` is in `.gitignore` — never commit build artifacts
- `node_modules/` is ignored — install locally
- Read `flud-app/.claude/CLAUDE.md` for project-specific rules before any work
