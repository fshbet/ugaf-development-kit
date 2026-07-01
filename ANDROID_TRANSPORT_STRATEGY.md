# Android Transport Strategy

Research conducted for Milestone 3 (Device Manager) / Milestone 4 (Android Transport),
per the directive to evaluate alternatives before defaulting to ADB. This document
compares the candidate transports, recommends an architecture, and states clearly what
Milestone 3 actually implements versus what is deferred.

## Candidates evaluated

### 1. Android Debug Bridge (ADB)

The foundational client-server protocol every other tool on this list is built on top
of, including UIAutomator2 (openatx/uiautomator2 uses `adbutils` — i.e. ADB — for all
device communication) and scrcpy (pushes its server and streams video "over adb").
There is no way to avoid depending on ADB at some layer; the real question is how much
automation logic should sit directly on top of raw ADB shell commands versus behind a
richer on-device agent.

- **Strengths:** Universal (every Android dev workflow already has it), no APK
  installation required for basic use, supports device enumeration, shell execution,
  file push/pull, port forwarding, and (Android 11+) wireless pairing over TLS with a
  2048-bit RSA keypair — a real security improvement over the old cleartext/USB-only
  model. No licensing concerns (Apache-2.0, part of the Android SDK platform-tools).
- **Weaknesses:** `adb shell input tap/swipe` calls into the Java input-dispatch layer
  and is documented as "very slow and unreliable" for anything beyond simple taps;
  chaining multiple `adb shell` invocations for a gesture adds real latency because
  each is a separate process spawn + round trip. Device state reporting is coarse — our
  own `AdbInputProvider._parse_devices()` (pre-existing code) only recognizes the
  literal `"device"` state and silently treats `offline`/`unauthorized` as "not
  present," which the audit already flagged as a real gap.
- **Security:** Wireless debugging's TLS pairing is sound *if not exposed on a public
  network* — Android's own docs warn that a connection with TLS disabled may be
  unencrypted. USB debugging requires physical access + an on-device Allow tap, which
  is an acceptable trust model for a desktop-controlled automation framework.

### 2. UIAutomator2 (openatx/uiautomator2 Python wrapper)

A Python wrapper around Google's official UI Automator test framework, communicating
with a small JSON-RPC server (`atx-agent`) it pushes to the device — itself using ADB
underneath, not a replacement for it.

- **Strengths:** Real UI-hierarchy introspection (element bounds, text, class names —
  exactly what our `AccessibilityNode` shape from Milestone 2 anticipates), more
  reliable gesture injection than raw `adb shell input`, works without root.
- **Weaknesses:** Requires pushing and keeping alive an on-device HTTP/JSON-RPC agent —
  one more moving part, one more thing that can crash or need reinstalling after an
  app/OS update, and a larger attack surface (an HTTP server listening on the device).
  Adds a third-party dependency (`uiautomator2` PyPI package) with its own maintenance
  and licensing (MIT) to track.
- **Verdict:** The right upgrade path for *input reliability and UI-tree reading* once
  raw ADB input proves insufficient for a specific game's timing requirements — not
  needed to stand up Milestone 3's device orchestration.

### 3. Android Accessibility Service

Read-and-act access to on-screen content and UI events at the OS level — the most
powerful and most policy-sensitive option.

- **Strengths:** Can read arbitrary screen content and inject actions without ADB at
  all, in real time, from an on-device component.
- **Weaknesses / risk:** Google Play policy is explicitly tightening around this API —
  as of the Android 17 rollout, apps can no longer freely enable accessibility services
  by flag; only apps whose *core purpose* is accessibility are permitted, and "Advanced
  Protection Mode" now actively blocks automation apps from (ab)using it. Malware
  abuse of this exact API (credential theft, overlay attacks, autonomous action) is
  well documented, which is precisely why enforcement tightened. Google Play policy
  explicitly permits *deterministic, rule-based automation where behavior follows a
  static, human-defined script*, and prohibits autonomous decision-making via this API
  — a distinction UGAF must respect if it ever ships an on-device accessibility
  component.
- **Verdict:** Legitimate as an **optional, explicitly opt-in** transport a user
  sideloads for their own device, never as a default or silently-enabled path. Deferred
  to Milestone 4's evaluation, not adopted now.

### 4. scrcpy protocol (screen capture)

Not an input mechanism — a screen-mirroring protocol. Pushes a ~2MB Java server to
`/data/local/tmp` over ADB, which captures the screen via `MediaCodec`, encodes to
H.264, and streams the result back over the existing ADB connection; the desktop side
decodes with FFmpeg.

- **Strengths:** 35–70ms latency, 30–120fps depending on device, ~1s startup, no root
  required, works over the same ADB transport we already depend on (no new pairing
  model). This is dramatically better than the current fallback of `adb exec-out
  screencap -p`, which re-encodes a full PNG and transfers it over an ADB pipe on
  *every single call* — fine for occasional screenshots, unworkable for a continuous
  vision loop driving real-time game automation.
- **Weaknesses:** Adds an H.264 decode step on the desktop side (an FFmpeg dependency,
  or a pure-Python decoder) — real but bounded complexity. Apache-2.0 licensed
  (Genymobile/scrcpy), no licensing blocker.
- **Verdict:** The clear right answer for Milestone 5's Screenshot Provider on Android
  — not implemented in Milestone 3 (out of scope; Device Manager doesn't do screen
  capture), but the choice is recorded here so Milestone 5 doesn't re-litigate it.

### 5. Custom on-device agent (gRPC or similar)

Considered and rejected for now: this would mean designing, signing, and distributing
our own APK, plus a build/release pipeline for it — a substantial new maintenance
surface with no capability gain over UIAutomator2 (which already solves "richer
on-device agent" via ADB-based deployment) at this stage of the project. Revisit only
if a concrete capability gap emerges that none of the above cover.

## Recommended architecture: multiple transports, one Device Manager

No single transport covers every need, and the directive's own example ("ADB for
deployment/shell, UIAutomator2 for UI interaction, Accessibility where appropriate,
scrcpy for low-latency screenshots") matches what the research above supports. UGAF
adopts a **multi-transport** architecture:

| Concern | Transport | Milestone |
|---|---|---|
| Device discovery, enumeration, shell exec, authorization/health | ADB | **3 (this milestone)** |
| Screen capture for the vision loop | scrcpy protocol | 5 (Vision Pipeline) |
| Reliable gesture/tap injection, UI-tree reading | UIAutomator2 | 4 (Android Transport), evaluated further before adoption |
| Opt-in UI-tree reading / action injection without ADB | Accessibility Service | 4, explicitly opt-in only, policy-documented |

Every transport is consumed through the interfaces already established in Milestone 2
(`ugaf.platform.device.DeviceProvider`) and Milestone 1's SDK boundary — the Core
Engine and game plugins never call ADB, UIAutomator2, or Accessibility APIs directly.
Swapping the input-injection transport from raw ADB `input` commands to UIAutomator2
in a later milestone should require changing only the Android adapter registered under
`ugaf.input.registry`, not `ugaf.core` or any plugin.

## What Milestone 3 actually builds

Device Manager orchestration needs a working transport to orchestrate *now* — that
transport is ADB, per the table above, not because "it already exists" but because it
is the only one of the four that requires no new third-party dependency and no new
distributed on-device component, and because Milestones 4/5 explicitly build the richer
transports on top of the device inventory this milestone establishes. Concretely:

- `ugaf.device.adb_provider.AdbDeviceProvider` — implements
  `ugaf.platform.device.DeviceProvider`, using `adb devices -l` (not the narrower
  `adb devices`) so `offline`/`unauthorized`/`no permissions` states are captured
  correctly instead of silently treated as "no device" (fixing the exact gap identified
  in the original repository audit).
- `ugaf.device.manager.DeviceManager` — the central orchestrator the Core Engine talks
  to instead of touching ADB directly: multi-provider registration, periodic
  discovery/health polling with event publication (`device.discovered`,
  `device.online`, `device.offline`, `device.unauthorized`, `device.lost`), retrying
  shell command execution with ADB-server-restart recovery informed directly by the
  research above ("a stuck ADB daemon" is the most common cause of a device going
  `offline`; `adb kill-server` + `adb start-server` is the documented fix).

## Sources

- [uiautomator2 · PyPI](https://pypi.org/project/uiautomator2/)
- [GitHub - openatx/uiautomator2](https://github.com/openatx/uiautomator2)
- [Write automated tests with UI Automator | Android Developers](https://developer.android.com/training/testing/other-components/ui-automator)
- [GitHub - Genymobile/scrcpy](https://github.com/Genymobile/scrcpy)
- [SCRCPY – Android Screen Mirroring Software](https://scrcpy.org/)
- [Use of the AccessibilityService API - Play Console Help](https://support.google.com/googleplay/android-developer/answer/10964491?hl=en)
- [Google cracks down on Android apps abusing accessibility | Malwarebytes](https://www.malwarebytes.com/blog/mobile/2026/03/google-cracks-down-on-android-apps-abusing-accessibility)
- [Advanced Protection Mode in Android 17 prevents apps from misusing Accessibility Services](https://securityaffairs.com/189497/security/advanced-protection-mode-in-android-17-prevents-apps-from-misusing-accessibility-services.html)
- [Android's AccessibilityService: A Single Toggle to Total Device Control](https://chocapikk.com/posts/2026/android-a11y-god-mode/)
- [Android ADB device offline, can't issue commands | Codemia](https://codemia.io/knowledge-hub/path/android_adb_device_offline_cant_issue_commands)
- [Resolving Android ADB Device Offline Issues - Repeato](https://www.repeato.app/resolving-android-adb-device-offline-issues/)
- [Android Debug Bridge (adb) | Android Developers](https://developer.android.com/tools/adb)
- [Understanding ADB Shell Input Events - Repeato](https://www.repeato.app/understanding-adb-shell-input-events/)
- [GitHub - hansalemaos/getevent_sendevent](https://github.com/hansalemaos/getevent_sendevent)
