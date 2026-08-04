# Optional recipe: social persona avatar (X / Twitter)

A more involved example: driving a **clearly disclosed, fictional/managed persona**
account in the X Android app on a Multilogin cloud phone. This is a recipe on top
of the same lifecycle + tools — nothing here is special-cased in the code.

> ⚠️ **Read this first.** Automating social platforms has real Terms-of-Service and
> legal implications. Only run a persona you are authorized to operate, keep it
> **transparently labeled** (e.g. `Satire`, `Fan`, `Commentary`, `Fictional`,
> `Avatar`, `Managed account`), and stay within [`AGENTS.md`](../../AGENTS.md#compliance-read-before-acting).
> Do **not** impersonate a real person, run inauthentic/bulk engagement, or try to
> evade detection. If in doubt, don't.

No credentials, handles, or persona details ship in this repo — fill your own.

## Setup inputs (you provide)

- Persona brief: display name, handle, bio **with a transparent non-impersonation label**, location, voice, topics to cover / avoid.
- Proxy/geo coherent with the persona (set before the first post, not after).
- Any image assets you want to post (host file paths).

## App reference (X Android)

- Launcher activity: `com.twitter.android/.StartActivity`
- Edit profile: `menu_edit_profile`
- Compose: FAB `composer_write` → post button `button_tweet`; attach media via the `Photos` button
- Timeline actions: `inline_reply`, `inline_retweet`, `inline_like` (the action row at the bottom of a card belongs to that card — match by y-position)

## Flow (using the standard tools)

```bash
python -m mlxphone.session start --phone "$MOBILE_PROFILE_ID" --max-minutes 25

# open X, then run the look → find → act → verify loop:
python -m mlxphone.tools shell monkey -p com.twitter.android -c android.intent.category.LAUNCHER 1
python -m mlxphone.tools screenshot results/x-home.png
python -m mlxphone.tools find composer_write
python -m mlxphone.tools tap <x> <y>
python -m mlxphone.tools text "a short in-voice post"
python -m mlxphone.tools find button_tweet
python -m mlxphone.tools tap <x> <y>

python -m mlxphone.session stop --phone "$MOBILE_PROFILE_ID"
```

## Verification discipline

A post is **not** verified until a fresh detail/profile view shows the exact text
(and media, if attached). A just-sent composer card, a bumped post count, or a
local timeline card can be cached/pending — if you see a `continue sending` /
`saved to drafts` / retry / spinner state, treat the publish as **failed**, clear
the pending send to avoid duplicates, and report it as blocked rather than success.

## Engagement (if in scope)

Only genuine, in-voice, normal-volume interaction with clearly relevant content.
No bulk/coordinated actions, no follow-back farming, no metric inflation. Prefer
no action over an off-voice one.
