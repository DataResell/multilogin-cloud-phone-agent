# Multilogin cloud-phone API — status codes & response shapes

One place to look up the fields the toolkit reads, so nothing is a guessed magic
number. Constants live in `mlxphone/mlx_client.py`. All calls are `POST` to
`https://api.multilogin.com` with `Authorization: Bearer <token>`.

## Phone status codes

From `POST /mobile_profiles/phone/statuses` → `data.success_details[].status`.
Constants: `STATUS_READY`, `STATUS_STARTING`, `STATUS_SHUTDOWN`, `STATUS_EXPIRED`.

| Value | Constant | Meaning |
|------:|----------|---------|
| `0` | `STATUS_READY` | Running / booted / ready for ADB |
| `1` | `STATUS_STARTING` | Booting / proxy session initializing — normal, can take ~20–120s |
| `2` | `STATUS_SHUTDOWN` | Shut down |
| `3` | `STATUS_EXPIRED` | Expired |

`statuses` response shape:

```json
{ "status": {"http_code": 200, "message": "success"},
  "data": { "success_details": [
      { "id": "<id>", "status": 0, "serial_name": "<name>",
        "running_time_secs": 123, "auto_stopped_at": null, "adb_status": "disabled" }
  ], "fail_details": [] } }
```

- `serial_name` — the profile's device/serial label.
- `running_time_secs` — seconds since this run started.
- `auto_stopped_at` — when the server will auto-stop it, if set.
- `adb_status` — `active` | `disabled` | `error` (see below).

## ADB info

`POST /mobile_profiles/phone/adb/set {ids, enabled}` then
`POST /mobile_profiles/phone/adb/info {ids}` → `data.items[]`.
Item `status` constants: `ADB_ACTIVE`, `ADB_DISABLED`, `ADB_ERROR`.

Active item (connection data present):

```json
{ "code": 0, "id": "<id>", "status": "active",
  "ip": "<ADB_IP>", "port": "<ADB_PORT>", "pwd": "<GLOGIN_CODE>" }
```

Disabled item (not yet enabled/running):

```json
{ "code": 49001, "id": "<id>", "status": "disabled" }
```

- `ip` / `port` → `adb connect <ip>:<port>`; `pwd` → `adb -s <ip>:<port> shell glogin <pwd>` (glogin expires in ~30–60s).
- Disabled codes observed: `49001`, `42002` — both mean "ADB not enabled yet"; call `adb/set {enabled:true}` then re-check.

## Start outcomes

`POST /mobile_profiles/phone/start {ids}` can return **HTTP 200 with a refusal**
in `data.fail_details[]` — the harness treats this as a first-class outcome, not a
timeout:

```json
{ "status": {"http_code": 200}, "data": {
    "success_details": [], "fail_details": [
      { "code": 47002, "msg": "Too many requests for your selected phone version, Please try again later or choose another version." } ] } }
```

| Code | Meaning | Handling |
|-----:|---------|----------|
| `47002` | Intermittent **server-side capacity** for the selected phone version (not a client error) | Back off and retry; if it persists, try again later or change the phone version in the Multilogin desktop app |
| other | Non-transient refusal | Fail fast with the server message |

## Mobile-minutes limit

`POST /mobile_profiles/limit` → `data.remaining_limit` (`LimitStat`:
`metric_code, current_used_value, metric_limit, remaining_limit`).

This endpoint is **not implemented on every account tier** — it can return
HTTP `501` / a non-JSON HTML page. In that case `remaining_minutes()` returns
`None` ("unknown") and the run proceeds, with the always-stop guarantee + the
`--max-minutes` watchdog acting as the billing cap. The run only hard-stops when
minutes are *known* and `<= 0`.

## Errors

`MlxHTTPError` (subclass of `MlxError`) carries `status_code`, `path`, `body`,
and two derived flags used across the harness:

- `endpoint_unavailable` — HTTP 501 or a non-JSON body on a known route.
- `credentials_rejected` — HTTP 400 or 401 (drives the plaintext→MD5 sign-in retry).
