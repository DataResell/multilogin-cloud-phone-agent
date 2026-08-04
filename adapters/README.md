# Adapters (optional)

The repo is agent-agnostic: any agent that can run a shell and read a screenshot
drives it via [`AGENTS.md`](../AGENTS.md) and the `mlxphone` tools. These adapters
are thin conveniences that register the same instructions in a specific runtime —
they add no logic. Use one if it helps; skip them otherwise.

- `claude-code/` — a Claude Code skill. Copy `mlx-cloud-phone/` into `.claude/skills/`.
- `openclaw/SKILL.md` — an OpenClaw / ClawHub skill manifest.
