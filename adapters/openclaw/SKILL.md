---
name: multilogin-cloud-phone
description: >-
  Operate a Multilogin cloud phone over ADB from an OpenClaw agent: start the
  phone and wait for boot, activate ADB via Multilogin, perform the requested
  actions on screen, then always stop the phone. Use for cloud-phone / mobile
  profile automation and disclosed-persona account operation. Transparent
  automation only; refuse impersonation, evasion, or inauthentic engagement.
---

# Multilogin cloud phone (OpenClaw adapter)

A thin wrapper over this repo's `AGENTS.md` — read that for the full contract and
the compliance rules; this only maps it into OpenClaw. No logic is duplicated here.

## Prerequisites
- `pip install -r requirements.txt`, `adb` on PATH, `.env` with Multilogin creds (`MLX_EMAIL`/`MLX_PASSWORD` or `MLX_TOKEN`) and `MOBILE_PROFILE_ID`.

## Lifecycle (deterministic — do not skip the stop)
```bash
python -m mlxphone.session start --phone "$MOBILE_PROFILE_ID" --max-minutes 20   # step 1
python -m mlxphone.session stop  --phone "$MOBILE_PROFILE_ID"                    # step 3, always
```

## Actions (agentic — your loop)
```bash
python -m mlxphone.tools screenshot results/s.png   # look
python -m mlxphone.tools find <keyword>             # exact bounds
python -m mlxphone.tools tap <x> <y>                # act
python -m mlxphone.tools text "..."                 # type
```
Look → find → act → verify. glogin is refreshed automatically before each action.

## Compliance
Per `AGENTS.md`: transparent automation only; no impersonation of real
individuals, no platform manipulation / bulk or fake engagement, no detection
evasion. Decline non-compliant requests and offer a compliant alternative.
