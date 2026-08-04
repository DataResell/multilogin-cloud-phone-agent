# Example task: hello-phone (neutral)

A minimal first task to confirm the full loop works end to end. No accounts, no
logins — just prove you can start a phone, see the screen, act, and stop.

Give your agent this task (with `AGENTS.md` loaded):

> Start the cloud phone `$MOBILE_PROFILE_ID`. Once connected: take a screenshot,
> open the device **Settings** app, confirm you're on the Settings screen by
> taking another screenshot, then stop the phone. Report what you saw.

A correct run looks like:

```bash
python -m mlxphone.session start --phone "$MOBILE_PROFILE_ID" --max-minutes 10

python -m mlxphone.tools screenshot results/01-home.png
# open Settings (package launch is simplest and robust):
python -m mlxphone.tools shell monkey -p com.android.settings -c android.intent.category.LAUNCHER 1
python -m mlxphone.tools screenshot results/02-settings.png
# verify by reading the UI:
python -m mlxphone.tools find settings

python -m mlxphone.session stop --phone "$MOBILE_PROFILE_ID"
```

What this demonstrates:

- The deterministic lifecycle (start → boot → ADB → **always stop**) is fully handled by `mlxphone.session`.
- The agent's part is the loop: **look** (screenshot) → **act** (open app / tap) → **verify** (screenshot + `find`).
- Swap the middle for any ADB-driven task. That is the entire idea.
