# Lifecycle sequence

The deterministic harness owns start/ADB/stop; the agent owns the actions in the
middle. The phone is **always** stopped in a `finally`, and a detached watchdog
force-stops it on a deadline as a backstop.

```mermaid
sequenceDiagram
    participant A as AI agent (any runtime)
    participant S as mlxphone.session
    participant G as Multilogin gateway API
    participant P as Cloud phone (ADB)

    Note over A,S: Step 1 — deterministic
    A->>S: session start --phone <id> --max-minutes N
    S->>G: /mobile_profiles/limit (preflight)
    S->>G: /mobile_profiles/phone/start
    loop until status == 0 (ready)
        S->>G: /mobile_profiles/phone/statuses
    end
    S->>G: /mobile_profiles/phone/adb/set {enabled:true}
    loop until adb status == active
        S->>G: /mobile_profiles/phone/adb/info
    end
    S->>P: adb connect ip:port + glogin
    S-->>A: connected (serial saved) + watchdog armed

    Note over A,P: Step 2 — agentic
    loop look → find → act → verify
        A->>P: tools screenshot / dump-ui / find
        A->>P: tools tap / text (glogin refreshed)
    end

    Note over A,S: Step 3 — deterministic (always)
    A->>S: session stop --phone <id>
    S->>P: adb disconnect
    S->>G: /mobile_profiles/phone/stop
    Note over S,G: watchdog would force-stop on deadline if the agent never returned
```
