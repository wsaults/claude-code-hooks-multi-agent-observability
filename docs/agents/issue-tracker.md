# Issue tracker: Beads (bd)

Issues and PRDs for this repo live in **beads** — a local, Dolt-backed issue tracker in `.beads/`, mirrored to git as `.beads/issues.jsonl` and synced cross-machine via `bd dolt push/pull`. Use the `bd` CLI for all operations. Do NOT use GitHub Issues or markdown task files — the beads workflow in `CLAUDE.md` prohibits it.

Run `bd prime` at the start of a session to load workflow context.

## Conventions

- **Create**: `bd create "Title" --description "..." -t task|bug|feature -p <0-4> -l <labels>`. Pipe multi-line bodies via `--stdin`; add `--silent` to get back just the new ID (handy for scripting dependency wiring).
- **Read**: `bd show <id>` for the detailed view (description, labels, deps, comments); `bd show <id> --json` for structured output.
- **List**: `bd list --status open --json` (filter with `--label`, `--label-any`, `--status`). `bd ready` shows only unblocked issues; `bd blocked` shows what's waiting and why.
- **Comment**: `bd comment <id> "text"` (or pipe via `--stdin`).
- **Apply / remove label**: `bd label add <id> <label>` / `bd label remove <id> <label>` (or `bd update <id> --add-label <l> --remove-label <l>`).
- **Claim work**: `bd update <id> --claim` (sets assignee to you + status `in_progress`).
- **Close**: `bd close <id> --reason "..."` (multiple at once: `bd close <id1> <id2> ...`).
- **Dependencies**: `bd dep add <blocked> <blocker>` — `<blocked>` depends on `<blocker>`; `bd ready` hides `<blocked>` until `<blocker>` closes.

## When a skill says "publish to the issue tracker"

Create beads issues with `bd create`. For a PRD broken into implementation slices, create one issue per slice and wire `bd dep add` so `bd ready` surfaces them in workable order.

## When a skill says "fetch the relevant ticket"

Run `bd show <id>` (add `--json` to parse). The user will normally pass the issue ID (e.g. `dash-xzl`) directly.

## Cross-machine sync

This fork is worked on from more than one machine, so the beads Dolt DB must be kept in sync:

- **New machine:** run `bd bootstrap` (clones the remote Dolt and wires it up). **Never `bd init` on a second machine** — independent inits create divergent Dolt roots that cannot merge.
- **Before working:** `bd dolt pull` (or `just bd-pull`) to receive other machines' changes. The `SessionStart` hook runs this automatically (fail-safe).
- **After beads changes:** push the Dolt DB **explicitly** with `bd dolt push` (or `just bd-push`). Do NOT rely on `git push` — the `pre-push` git hook has been observed to leave `refs/dolt/data` stale, so the issue DB silently diverges from the git `issues.jsonl` mirror unless you push Dolt yourself.
- **Conflicts in `.beads/issues.jsonl`** during a merge/rebase: take `--theirs` and let `bd export` / `bd close` regenerate it — the Dolt DB is the source of truth; the JSONL is just a reviewable mirror.
