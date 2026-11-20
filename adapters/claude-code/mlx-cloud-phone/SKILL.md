---
name: mlx-cloud-phone
description: >-
  Automate a Multilogin cloud phone over ADB — start the phone and wait for boot,
  activate ADB, perform actions on screen, and always stop it afterwards. Use when
  asked to run a task on a Multilogin cloud phone / mobile profile, drive an Android
  app on it, or operate a disclosed persona account. Transparent automation only.
---

# Multilogin cloud phone (Claude Code adapter)

This is a thin wrapper. The full contract is in the repo's `AGENTS.md`; read it,
then follow it. Nothing here reimplements the lifecycle.

## Prerequisites
- Repo installed: `pip install -r requirements.txt`, `adb` on PATH, `.env` filled in (`MLX_EMAIL`/`MLX_PASSWORD` or `MLX_TOKEN`, `MOBILE_PROFILE_ID`).

## Do this
1. **Start (deterministic):** `python -m mlxphone.session start --phone "$MOBILE_PROFILE_ID" --max-minutes 20`
2. **Act (your loop):** open the app with `tools launch <package>`, then for each step — `tools screenshot` → read it → `tools find <keyword>` for exact bounds → `tools tap <x> <y>` / `tools text "..."` → screenshot to verify. Re-find bounds after navigation.
3. **Always stop:** `python -m mlxphone.session stop --phone "$MOBILE_PROFILE_ID"` — on success or failure. (`--max-minutes` is a backstop, not a substitute.)

## Rules
Follow the Compliance section of `AGENTS.md`: transparent automation only; no
impersonation of real people, no inauthentic/bulk engagement, no detection
evasion. Decline and offer a compliant alternative if asked to break these.

Start with `examples/hello-phone/task.md`.
