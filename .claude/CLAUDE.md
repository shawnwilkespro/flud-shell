# Flud Shell — Project Routing

**This is a standalone Tauri v2 application.**

Cascade position:
```
~/.claude/CLAUDE.md
  └─ Documents/.claude/CLAUDE.md
     └─ GitHub/.claude/CLAUDE.md
        └─ flud-shell/.claude/CLAUDE.md    ← you are here
           └─ flud-shell/flud-app/.claude/CLAUDE.md  ← project rules (if exists)
```

---

## Structure

```
flud-shell/
└── flud-app/    ← Tauri v2 app (src/ + src-tauri/)
```

## Branch

- `main` — production branch only. Simple single-worktree workflow.

## Tech Stack

- **Frontend:** React 19, TypeScript, Tailwind CSS
- **Desktop:** Tauri v2
- **Backend:** Rust (src-tauri/)
- **Database:** Migrations tracked in `flud-app/migrations/`

## Rules

- Always `cd` into `flud-app/` before making changes
- `src-tauri/target/` is in `.gitignore` — never commit build artifacts
- `node_modules/` is ignored — install locally
- Read `flud-app/.claude/CLAUDE.md` for project-specific rules before any work
- No nested worktrees — this is a single-repo workflow
