# Hyper Evolution development contract

Preserve the three layers in `src/base/app/companion/`: `aesthetic` owns professional judgment and Policy Packs; `functional` owns capabilities, authorization, Agent/Skill/Workflow and execution; `assets` owns references, versions and provenance. Read `docs/architecture.md` before changes.

All new web, MCP and Agent operations use `LocalRuntime.invoke_capability`. Preserve v1-v11 contracts, runtime role checks, subject-specific physical workspaces and signed peer messages. Enlighter is teacher; Evolver and Self-Evolver are student identities. Experience selection never grants teacher privileges. AI suggestions remain editable suggestions; teacher publication is explicit.

Keep user data, credentials, private teaching materials and internal deployment records out of commits and releases. Include third-party licenses and corresponding source where required. Use original or explicitly redistributable examples.

Run `python -m pytest tests -q`, `node --test tests/*.test.cjs`, `python scripts/check.py --business`, and relevant real web/MCP/peer verification. Tests use fresh synthetic directories. Distinguish source checks, frozen package checks and teaching pilots.

Human guides share `docs/usage/manuals-v0.3.json` and generated `src/growth_local/static/usage-guides.js`. Write approachable instructions: where to click, what to enter and what happens next. Update docs when controls change.
