# Multi-Agent Observability

The domain language for the observability dashboard: hooks emit events from running agents, the server turns those events into a live picture of who is working and who needs attention.

## Language

### Identity

**Worker**:
A stable unit of work running in a single git worktree — the entity the dashboard renders cards for. One Worker spans many **Sessions** over its lifetime (resumes, restarts) without losing its identity.
_Avoid_: agent, instance (too generic); session (a Worker is not a Session — see below).

**Session**:
A single Claude Code run, identified by an ephemeral `session_id` that changes on resume. Many Sessions, over time, belong to one **Worker**.
_Avoid_: run.

**Worker ID**:
The stable, globally-unique identifier for a **Worker** — a random UUIDv4 persisted in the worktree (`.claude/worker-id`), git-ignored so it never travels between machines. The dashboard keys its cards on this, so two distinct Workers must never share one.
_Avoid_: agent id; session id (that's the ephemeral one).

**Source App**:
A human-assigned application/deployment label carried on every event (the `--source-app` argument). Groups events by application; orthogonal to **Worker** identity — one Source App can have many Workers.
_Avoid_: app name (ambiguous), project (project is *derived* from the git repo, not the Source App label).

## Flagged ambiguities

Three identifiers travel on every event and are easy to conflate. They are distinct:

- **Source App** — _which application_ (human label, stable, coarse).
- **Worker / Worker ID** — _which unit of work_ (stable across resumes, the card key).
- **Session ID** — _which run_ (ephemeral, changes on resume).

When a field says "identify the agent", it almost always means the **Worker**, not the Session.

## Example dialogue

> **Dev:** A card showed up twice after I restarted Claude in the same folder.
> **Expert:** Then the **Worker ID** wasn't stable — a restart is a new **Session**, but the same **Worker**. The persisted `.claude/worker-id` should have kept it as one card.
> **Dev:** And if I clone the repo to my laptop and run it there?
> **Expert:** Different machine, different worktree → a *different* **Worker**, with its own Worker ID. That's correct — it's a separate unit of work. The danger is the id file getting committed and cloned; then both machines would claim the same Worker ID and the dashboard would merge them. That's why it's git-ignored.
> **Dev:** Where does `--source-app` fit?
> **Expert:** That's the **Source App** — the application label. One Source App can run many Workers across many worktrees and machines. It answers "which app", not "which unit of work".
