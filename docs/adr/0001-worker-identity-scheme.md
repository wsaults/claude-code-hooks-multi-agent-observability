# Worker identity is a git-ignored random UUID, omitted on failure

A **Worker** (see `CONTEXT.md`) is identified by a random UUIDv4 generated on first event and persisted to `<worktree>/.claude/worker-id`. The id is **git-ignored** so it never travels between machines, and if it can't be established the `worker` object is omitted from the event entirely rather than synthesized.

## Considered options

- **Random UUIDv4, persisted per worktree (chosen).** Globally unique by construction; survives Session resumes because it's stored on disk, not tied to the ephemeral `session_id`.
- **Derived id (hash of repo + host + path), rejected.** Tempting because it needs no stored state, but two machines with the same repo at the same path would collide, and the dashboard keys cards on the id — a collision silently merges two unrelated Workers into one card. The committed-`.claude/` clone case is the same failure, which is why the persisted file must be git-ignored.

## Consequences

- The id is reproducible across resumes but **machine-local**: cloning a repo to a second machine yields a *different* Worker, which is correct (it's a separate unit of work).
- On total identity failure (e.g. read-only worktree) the event is still delivered but produces no card — a deliberate visible gap, chosen over a fabricated id that could collide. Card absence is a "something's wrong" signal; a silent merge is not.
