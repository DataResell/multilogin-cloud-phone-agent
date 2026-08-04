# Multilogin cloud-phone agent

An open, **agent-agnostic** example of AI-driven automation on a
[Multilogin](https://multilogin.com) cloud phone. It does exactly this:

1. **Starts** the selected phone, waits for it to boot, and automatically activates ADB via Multilogin.
2. **Connects** to the phone and lets an AI agent perform the requested actions over ADB.
3. **Always stops** the phone and saves results/logs when finished — on success or failure.

It works with **any agent** that can run a shell and look at a screenshot —
Claude Code, OpenClaw, Cursor, or your own — because the agent-facing surface is
plain CLI tools plus [`AGENTS.md`](AGENTS.md), not a single vendor's plugin format.

> This is a reference example, not a product. You are responsible for complying
> with the terms of service of any app or platform you automate. See
> [Compliance](AGENTS.md#compliance-read-before-acting).

## Why the split matters

The lifecycle (**start → boot → ADB → always-stop**) is **deterministic code**,
never the agent's discretion — mobile minutes are billed, so the phone *must*
always be stopped. The **actions** in the middle are **agentic**: the model looks
at the screen, decides what to do, acts, and verifies. So the design is:

```
  Any agent  ──reads──▶  AGENTS.md        (step 2: the perception→act→verify loop)
      │
      │ calls over its shell
      ▼
  mlxphone/  ──▶ session ──▶ start_wait ──▶ adb ──▶ [hand device to agent] ──┐
             (deterministic lifecycle harness)                               │
                                                    FINALLY: always stop + logs ┘
```

See [`docs/sequence.md`](docs/sequence.md) for the full sequence diagram.

## Prerequisites

- A Multilogin account with the **API-token** plan feature, a cloud phone (mobile profile), and remaining mobile minutes
- The **[Multilogin desktop app](https://multilogin.com/download/) installed and running** — it's how you create and manage the cloud phone, and it keeps the Multilogin launcher available in the background. This example drives the phone over the API; having the desktop app running makes sure your account, workspace, and mobile profile are ready.
- Python 3.9+ and `pip install -r requirements.txt`
- The `adb` binary on your PATH ([Android platform-tools](https://developer.android.com/tools/releases/platform-tools))
- Credentials in `.env` (copy from [`.env.example`](.env.example))

## Quickstart

```bash
git clone <repo-url> && cd multilogin-cloud-phone-agent
make setup                 # 1. create .venv + install deps (Python 3.9+, 3.11+ recommended)
cp .env.example .env       # 2. fill in real values: email/password (or MLX_TOKEN) + MOBILE_PROFILE_ID
make doctor                # 3. validate environment + credentials — spends no mobile minutes
make dry-run               # 4. walk the whole flow with no network/device
make demo                  # 5. real end-to-end demo: start → boot → ADB → screenshot → ALWAYS stop
```

No virtualenv or `pip` fiddling — `make setup` creates `.venv` and installs deps
(via `python -m pip`, the portable form). Always run **`make doctor` before
`make demo`**: it checks deps, `adb`, your `.env` (catching leftover placeholders),
sign-in, and that your phone is visible — so you catch problems before any minutes
are spent. `make demo` saves `results/demo_screenshot.png` and stops the phone at
the end (including on Ctrl-C).

Without `make`: run `./scripts/setup.sh`, then
`.venv/bin/python -m mlxphone.session {doctor,demo,start,stop}`.

## How an agent uses it

Point your agent at [`AGENTS.md`](AGENTS.md). The flow it follows:

```bash
python -m mlxphone.session start --phone "$MOBILE_PROFILE_ID" --max-minutes 20
python -m mlxphone.tools screenshot results/s1.png
python -m mlxphone.tools find compose
python -m mlxphone.tools tap 540 1780
python -m mlxphone.tools text "hello from an AI agent"
# ... look / find / act / verify ...
python -m mlxphone.session stop --phone "$MOBILE_PROFILE_ID"
```

`--max-minutes` arms a detached watchdog that force-stops the phone on a deadline,
so it still stops if the agent crashes between calls.

Per-agent convenience wrappers live in [`adapters/`](adapters/) (Claude Code,
OpenClaw) — thin pointers to `AGENTS.md`, entirely optional.

## Layout

```
Makefile             make setup / doctor / dry-run / demo / clean
scripts/setup.sh     bootstrap: create .venv + install deps (python -m pip)
AGENTS.md            portable agent instructions (any runtime)
mlxphone/            the toolkit
  mlx_client.py      /user/signin (auto-hash) -> token + gateway API calls
  start_wait.py      minutes preflight + start (+ fail_details) + wait until booted
  adb.py             enable ADB + connect + glogin
  session.py         orchestrator + ALWAYS-stop guarantee + CLI (doctor/demo/start/stop)
  watchdog.py        detached force-stop safety net
  tools.py           agent-facing device tools (screenshot/find/tap/text/…)
  doctor.py          preflight: deps, adb, .env, sign-in, profile visibility
  checks.py          adb / placeholder / env helpers
adapters/            optional per-agent wrappers (claude-code, openclaw)
examples/            hello-phone (neutral), x-avatar (optional recipe)
docs/sequence.md     sequence diagram
docs/api-responses.md  status codes & response shapes (no magic numbers)
```

## Troubleshooting

Run `make doctor` first — it names the specific failing check with a fix hint.
Beyond that the tool self-diagnoses: a missing `adb` gives a per-OS install
command; the wrong password form is auto-retried (plaintext → MD5) and logged; a
`/mobile_profiles/limit` `501` on your tier is treated as "minutes unknown,
proceed" (always-stop + watchdog are the billing cap); and a start refused with
capacity code `47002` backs off and reports the real reason instead of a bare
timeout. Field/status shapes: [`docs/api-responses.md`](docs/api-responses.md).

## Security & privacy

No secrets are committed. All credentials come from a git-ignored `.env`;
`.env.example` contains placeholders only. Runtime artifacts (`results/`,
`logs/`, `.mlxphone/`) are git-ignored. The token is obtained cleanly via
`/user/signin`; no credential interception is used or needed.

## License

[MIT](LICENSE).
