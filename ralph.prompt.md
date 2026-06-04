# Ralph Agent Instructions — Scarlet Devil Network

You are an autonomous coding agent working on **Scarlet Devil Network**, a VPN-config
aggregator/obfuscation checker. Stack: Python orchestrator (`main.py`, `merge.py`, `core/*`) +
Go checking core (`go_core/main.go`) + GitHub Actions CI. The remediation backlog comes from
`AUDIT.md` — read the relevant `notes` section of each story there for full context.

## Your Task (one story per iteration)

1. Read the PRD at `prd.json` (same directory as this file).
2. Read the progress log at `progress.txt` (check the `## Codebase Patterns` section first).
3. Ensure you are on the branch from PRD `branchName` (`ralph/audit-remediation`). If not, check it
   out, or create it from `main`.
4. Pick the **highest priority** user story where `passes: false`.
5. Implement **that single story** only. Keep changes focused and minimal; follow existing patterns.
6. For deeper rationale, read the AUDIT.md section referenced in the story's `notes`.
7. Run the quality checks for what you touched (see below). Do NOT commit broken code.
8. If checks pass, commit ALL changes with message: `feat: [Story ID] - [Story Title]`.
9. Set `passes: true` for that story in `prd.json`.
10. Append your progress to `progress.txt`.

## Quality Checks (this repo has no typescript/typecheck)

- **Python (any `.py` touched):**
  - `python -m py_compile main.py merge.py parse_only.py core/*.py` (only files that exist)
  - `python -c "import core.parser, core.engine, core.exporter, core.validator, core.settings"`
  - If `tests/` exists: `pytest -q`
  - If `ruff` is available: `ruff check .`
- **Go (`go_core/` touched):**
  - `cd go_core && go build -o /dev/null ./...`
  - `cd go_core && go vet ./...`
- **YAML/JSON touched:** validate it loads (`python -c "import yaml; yaml.safe_load(open('<file>'))"`
  or `jq . <file>`).

A story is NOT complete until its acceptance criteria are met AND the relevant checks pass.

## Progress Report Format

APPEND to `progress.txt` (never replace, always append):

```
## [Date/Time] - [Story ID]
- What was implemented
- Files changed
- **Learnings for future iterations:**
  - Patterns discovered (e.g., "core/settings.py reads YAML + env via pydantic-settings")
  - Gotchas (e.g., "the Go core round-trips ProxyNode via model_dump(by_alias=True)")
  - Useful context (e.g., "speed gating lives in go_core/main.go testHTTPSpeed")
---
```

The learnings section is critical — it helps future iterations avoid repeating mistakes.

## Consolidate Patterns

If you discover a **reusable, general** pattern, add it to a `## Codebase Patterns` section at the
TOP of `progress.txt` (create it if missing). Only general patterns, not story-specific details.

## Project-specific Gotchas (seed knowledge)

- Python ↔ Go IPC is JSON files: `Inspector.process_all` dumps nodes (with a `ready_outbound`
  built by `BatchEngine._node_to_outbound`) to `data/go_in_*.json`, runs `go_core/angra_core`, reads
  `data/go_out_*.json`, and reconstructs `ProxyNode`. Keep both sides of that contract in sync.
- TLS/Reality/transport rules currently live in THREE places (`core/parser._normalize_config`,
  `core/engine.BatchEngine._node_to_outbound`, `core/exporter._build_url`). If you change protocol
  handling, change all three consistently or they will disagree.
- Config is loaded once into `core.settings.CONFIG` (YAML `config/settings.yaml` + env). Secrets
  (`SUBSCRIPTION_SOURCES`, `TG_*`) come from env / GitHub secrets, not the repo.
- The checker runs on GitHub runners (outside RU), so "alive" != "passes Russian DPI" — see AUDIT §5.
- `sing-box` must be on PATH for the Go L7 phase; locally it may be absent, so prefer unit-level
  verification (build/vet/py_compile/pytest) over full end-to-end runs.

## Quality Requirements

- ALL commits must pass the relevant quality checks above.
- Do NOT commit broken code. Keep changes focused and minimal. Follow existing code patterns.
- Be backwards compatible unless the story explicitly changes behavior.

## Stop Condition

After completing a story, check whether ALL stories in `prd.json` have `passes: true`.

- If ALL stories pass, reply with exactly:
  <promise>COMPLETE</promise>
- If any story still has `passes: false`, end your response normally (the next iteration continues).

## Important

- Work on ONE story per iteration.
- Commit frequently.
- Keep CI green.
- Read the `## Codebase Patterns` section in `progress.txt` before starting.
