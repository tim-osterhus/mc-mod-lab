# Development-only recording target label

Status: candidate11 passed a bounded live developer PID/OBS and GUI/dimension
title gate; its source is included in the current public bridge build. This is independent of Survival actor
capability and Aura gameplay acceptance. No Aura product mod or parent private
OBS helper is changed.
The fresh ignored candidate is
`.lab-fixtures/capture-label-bridge-offline-09.jar`, SHA-256
`54a9023a523ec55c08a038e62304e3ad65f14e0c0daa1333d6a658593754e11a`.
Frozen 06/07 bridge JARs and the separate chunk-presence 08 JAR were not
replaced. Candidate09 rebuilds the current WIP source, so it also contains
candidate07 visible-input and candidate08 chunk-presence code; it is not a
label-only release artifact. It is compile/static-validated only and is not
approved for live or public acceptance without the parent review and lease.

The parent corrected its private `WaitFor` title-variable shadowing and ran
two bridge06 MP preflights (bridge SHA-256 `c371bd90262792f2b9d03bb12f34aaf4156fd5c0d695b7f2e46a96a33647fbeb`).
Ignored `recorded-mp-five-labelscope-20260928-140420/capture-label-11572.json`
and `recorded-mp-five-framed-20260928-140810/capture-label-13552.json` each
record one exact PID-derived OS title with a nonzero window handle. The parent
also reports successful exact OBS selection and saved a preview; one MP-F01
clip finalized before a later public request-envelope failure. These are
bridge06 identity/preflight positives only, not candidate09 GUI/dimension
persistence or MP gameplay acceptance.

Two concurrent clients can expose the same default Minecraft window title to
OBS Game Capture. The authenticated Mod Lab bridge now accepts one trusted
`capture_window_label` action with **no parameters**. On the selected client's
render thread it calls the pinned 1.21.1 `Window.setTitle(String)`
(`class_1041.method_24286`) with exactly `MC Mod Lab Minecraft PID <process PID>`.
The Python helper verifies that the returned label matches the PID whose
loopback socket was selected. It is not an actor action or a scripted
scenario-v2 step. A caller cannot supply arbitrary title text.

The new client-only mixin changes `Window.setTitle`'s single title argument
only for the exact `Window` instance on which a successful label action opted
in. Before opt-in, and for any other window, vanilla title updates are
unchanged. After opt-in, all later calls on that instance retain the same
PID-derived label, including vanilla GUI (`setScreen`) and level/dimension
(`setLevel`) title resets. The opt-in survives control-mode release and lasts
for that window instance until the client process exits; there is no remote
unlabel or arbitrary-title method. An unexpected replacement `Window` instance
must be labeled and verified again. Repeating the action is idempotent. This
is developer recording identity only, not player knowledge or Survival input.
The parent later found a definite five-second MP preflight bug in its private
PowerShell helper: `WaitFor` shadowed the expected-title variable. That timeout
is not bridge06 evidence against label dispatch. The first immediate mismatch
may still have been a startup race. Persistence addresses the independent
GUI/dimension reset risk, not that helper bug.

The method does not prove which HWND OBS selected. The recording owner must
independently associate the exact labeled OS window with the selected PID,
verify OBS's selected `title:class:exe` item is unique, inspect a preview frame
from the intended client, and fail closed on mismatch or ambiguity. No native
focus, click, or keyboard input is necessary. The existing three-client/one-
server cap and exclusive recording owner still apply.

Before treating a clip as QA evidence, use a short action-only recording window
with a fresh stop/ready pair, explicit deadline, normal stop and finalized
output. Preserve raw MKV files under
`F:/_animations/video-pipeline/inbox-footage/aura-cascade-mod-port/`; do not
edit or dispatch them to an editor until QA, patches, and recorded validation
are complete. A clip's sidecar may name the pinned artifact, but the evaluator
must independently verify the loaded artifact and gameplay assertion. Probe
video stream codec, dimensions, duration, and nonzero size, then visually
review the intended action. Media validity is not gameplay success.

Read-only review initially found an unconfirmed `StartRecord` reply could
leave recording active and `assert`-based safety checks could vanish under
optimized Python. The parent has since repaired its **private** `obs_record.py`:
explicit checks, start-attempt reconciliation through a fresh OBS connection,
expected-PID/duplicate-title rejection, a 1280x720 stream and duration probe,
and lock retention when stop is unconfirmed. The parent reports six mock
control tests passing under `python -O`. These are private-helper controls,
not a live Mod Lab label/OBS acceptance or gameplay evidence. The private
helper is frozen until the current recording batch ends; Mod Lab neither
copies nor edits it. Recorder-process loss still needs parent supervision.

Offline controls: reject parameters/unknown names, require bridge control mode
and client thread, verify exact PID-derived acknowledgement, confirm the mixin
is packaged and targets only the selected window after opt-in, and keep this
action out of actor and scenario schemas. A denied label action must leave
vanilla titles unchanged. Live controls (parent lease needed): retain
the corrected MP helper's observed-title/handle and OBS window inventory;
then label two simultaneous clients, verify unique OS PID/title and OBS targets,
open/close a GUI and change dimension while checking the label before/during/
after recording, test denied calls, review each preview, and stop both clients
normally. Any mismatch remains a fail-closed capture gate. Compile/static
checks alone are not live B11 acceptance.

Candidate11's single-client profile05 recorded exact PID title 29224 before,
during, and after the chest GUI transition, with normal exit 0. The separate
two-client/dedicated-server private QA run
`recorded-mp-views-label11-20260928-152020` retained exact PID 19092 title
after F01 GUI close and F02 Nether transfer and PID 24728 after F04 GUI close;
the transition log explicitly records no relabel after each event. F02 OBS
selected the exact PID title and finalized a 1280x720 clip. All four owned
Java processes exited 0 without force. Astra independently reviewed all five
matching-hash MP clips as gameplay-acceptable, noting black opening frames in
F03/F04. This is a bounded live development-capture title-transition pass.
The Nether transition used the reviewed dedicated-server console teleport
fixture, not a natural portal, actor input, or newly exposed public command.
The candidate11 local JAR remains an ignored test artifact; the current source
build retains this title feature. It is not a natural portal or B01 input gate.

Primary API references: [GLFW window title and main-thread requirement](https://www.glfw.org/docs/3.3/group__window.html),
[Fabric Window.setTitle mapping](https://maven.fabricmc.net/docs/yarn-1.21%2Bbuild.1/net/minecraft/client/util/Window.html#setTitle(java.lang.String)).
The exact local 1.21.1 Tiny mapping SHA-256 is
`6dfd4ab0691e96bf5dbaf75f0900786bdb534b144c8438e4c2a765145f1e524a`.
