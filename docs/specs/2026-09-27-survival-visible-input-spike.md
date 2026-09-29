# Milestone 5a: bounded visible-input Survival spike

Status: published bounded developer technical evidence plus an offline-tested
isolated-actor follow-up candidate, not B01 Survival acceptance. This is a
separate follow-on to public checkpoint `16ba207`. It does not change Aura or
make B01 guide-led fresh-world Survival complete. The broader five-seed task
driver gate remains in [autonomous-playtesting-v2.md](autonomous-playtesting-v2.md#survival-agent-research-spike-separate-milestone).

## Boundary and decision

Use the existing reviewed Minecraft 1.21.1 Fabric client, exact Aura
`0.2.1+1.21.1` artifact, authenticated loopback bridge, disposable profile,
runtime guard, and exclusive `ControlLease`. The actor must run in a separate
process with no access to Mod Lab files, source, environment token, save,
network, mappings, or evaluator telemetry. The parent orchestrator holds the
bridge token and offers the actor only the interface below. OS/process
isolation is an external prerequisite, not something a Python class can grant.
The guide is shown through the game UI; no hidden guide answer or fixture
coordinate is supplied after the run begins.

### Actor process gate

`PolicySession` is the trusted broker half only. The feasible B01 wiring is a
parent-owned broker process that holds the token and selected client identity,
serializes the fixed requests below, and sends only PNG bytes and generic
acknowledgements to an actor. Use an already-approved model endpoint through
that broker with local tools and workspace attachments disabled, or a separate
OS-restricted actor account/container with an explicit allowlist for only the
broker channel and any already-approved model access. Native agents that inherit
the workspace, token, save, or loopback permissions are not isolated actors.
No new paid service, credential discovery, or unrestricted local subprocess is
part of this milestone. If approved model access or verifiable process
restriction is absent, B01 remains blocked at this gate; do not relabel a
trusted scripted runner as a policy.

Before a live B01 attempt, demonstrate negative probes from the actor context:
reading Mod Lab and Aura source/save files, reading the bridge token from the
environment, connecting directly to the bridge port, and requesting typed
inspection or command execution must all fail. The broker's game-control
schema exposes only `frame`, `look`, `pulse`, `press`, `click`, and `cancel`.
An internal `vision` exchange may ask the trusted model to choose from a cached
PNG and generic action history, but must never query the game or expose typed
observations. Malformed or
unknown requests must not dispatch input. The parent records these denials.
The current launcher handles normal errors, wall-time cancellation and
neutral-release failure in process, but a hard trusted-launcher crash can
leave its Minecraft child running. An independently verified parent-owned
process-loss watchdog or Windows Job Object is required before a live B01
actor trial. The actor must never receive evaluator results or
the predeclared guide answer.

The actor sees PNG framebuffer bytes and a generic input acknowledgement,
not screen classes, slots, block/entity inventories, server ticks, game
coordinates, registry IDs, recipe tables, source lookup, or typed HUD data.
Those remain evaluator-only. A server-authoritative probe is still not player
knowledge. Input acknowledgements never establish gameplay success.

### Offline isolated-actor candidate

`scripts/isolated_survival_actor.py` runs under WSL Ubuntu `bubblewrap` with
its own network namespace, dropped capabilities, new session and a minimal
read-only Python/script mount. The
trusted `survival_actor.py` broker retains the token, PID identity, model
connection, input lease and evaluator observations. It transmits only original
PNG frames, one selected fixed action, and generic accepted/denied replies
over stdio. The child cannot mount the Windows workspace, connect to the
bridge, inherit the token, or request typed observations/commands; offline
tests execute those denials from the actual sandbox. The local Ollama model
is part of the trusted inference service, not an actor file/network tool; the
child is transport, while that model makes the pixel-only policy decisions. The
host-side Ollama process is **not** OS-isolated by the child's sandbox; model
tool denial and PNG-only request construction are application controls. A live
B01 claim still requires separately approved model execution, independent
sandbox/process review, and evidence that the policy decision point has no
privileged source or hidden game-state route. The model receives the PNG and
bounded generic action history with no tool list or
privileged telemetry; its JSON output must pass the fixed input validator.
The first actor-visible guide frame is retained as pixel context for later
vision calls, with no OCR, fixture answer, source lookup or privileged state.

`scripts/run_survival_actor.py` is an owned-launch first-trial entry point.
Before Minecraft starts it checks the exact Aura `0.2.1+1.21.1` artifact,
published movement-pulse bridge hash, a closed/copied `level.dat` with
`allowCommands=0`, `GameType=0`, and empty player/ender inventory. It binds
the copied `level.dat` bytes to the closed seed and checks the whole copied
world against the prepared profile hash before launch, then requires an
explicitly named, already-installed local vision model. It never pulls a
model or starts Ollama. After client readiness the evaluator checks a fresh
server-authoritative empty inventory, runs source/save/token/port and broker
denial probes, then starts `PolicySession`. The first PNG and action trace
stay in the evaluator's profile evidence with the first-frame SHA-256,
timestamped trusted action trace, child-source SHA-256, bubblewrap version and neutral-release
status; raw actor status remains
`inconclusive` until independent guide visibility/gameplay review. Any
failed isolation, model, seed, input, cancellation or neutral-release gate
fails closed. A cancellation observed before dispatch denies that action;
an already in-flight authenticated input can complete before neutral release,
so this is not a mathematically exact wall-clock action cutoff. No hidden setup
result is sent to the actor.

The NBT checks are a no-cheat/empty-inventory gate, **not proof of a freshly
generated or unplayed world**. A separate reviewed creation record and clean
copy chain must establish that provenance before B01. Saving `first-frame.png`
does not verify that the in-game guide is visible; an independent reviewer
must inspect that exact frame before accepting a guide-led claim. The current
Java/OBS resource guard does not account for an external model process or GPU
memory. A future local-model trial needs an explicit model allocation and
resource observation in addition to the Minecraft client cap.

Current local model inventory contains only an embedding model, not a vision
model, and the existing technical Survival seed is cheat-enabled and seeded.
Therefore no fresh guide-led run has been made from this candidate. The next
leased gate requires a separately reviewed unseeded no-cheat Survival world
whose guide is visible in the first frame, an explicitly approved installed
vision model, normal client/OBS cleanup, and independent review of the actor
trace. One attempt may fail or be inconclusive; five declared vanilla seeds
and one Aura guide-led action remain the broader acceptance obligation.
Native AstraLight can review actor-visible frames and recordings, but its
normal workspace/tool permissions are not an isolated B01 policy boundary.
No scoped in-app PNG-to-fixed-action endpoint is currently available to this
broker. An OpenAI API model would require separately approved billable access;
the local Ollama adapter is only an optional offline candidate, not an
authorization to download or run a new model.

At a future explicit client lease, prepare a fresh reviewed runtime profile
with the existing `python lab.py runtime prepare` command, then invoke
`python -m scripts.run_survival_actor --manifest <reviewed-manifest> --profile
<fresh-profile> --scenario <identity-matched-scenario> --model
<already-installed-vision-model> --aura-source <existing-Aura-Java-source>`.
The scenario is only the launch identity preflight; the actor does not receive
its steps. The private model endpoint must be independently approved and
preflighted before this command, and the initial guide frame must be reviewed
before interpreting any result. Do not run this against the technical seed,
install/download a model at runtime, or call a scripted replay a B01 trial.

| Actor request | Fixed behavior and limit | Deliberately absent |
| --- | --- | --- |
| `frame` | Original rendered PNG only, exact evaluator-declared full-frame size within 640x360 to 1920x1080, at most 8 MiB and two frames/s | No metadata, crop, OCR, or typed observations |
| `look` | Relative integer yaw/pitch deltas, each -15..15 degrees/call, only in world | No target coordinate or block-ID aim |
| `pulse` | Movement keys: one typed client-side 50..500 ms pulse with tick-driven release in the candidate13 source build. Attack: 50..5000 ms broker request with candidate12's nonrenewable six-second bridge grant and explicit release in `finally`. Use: broker-timed 50..500 ms with explicit release. | No indefinite movement grant; the movement pickup gate passed only on a disclosed technical fixture, and broker-timed use still has RPC-latency uncertainty |
| `press` | One of E, Escape, Q, or hotbar 1..9 through normal key input | No chat/command text, arbitrary key, or server command |
| `click` | Left GUI click at a coordinate inside the last full-frame image; existing bridge rejects no-screen | No widget tree, slot-index action, or outside-frame click |
| `cancel` | Release control and all held keys, mark terminal | No resume of an uncertain profile |

Session caps: 10 wall minutes, 1200 input calls, 600 frames, at least 100 ms
between non-pulse inputs, and an existing 3800 MiB client working-set guard.
The broker refuses a pulse that would pass its deadline; its asynchronous
deadline signal prevents any new action after ten minutes; an already in-flight
model or bridge call may finish on its own fixed timeout before neutral teardown,
so this is not an exact global wall-clock limit. The broker never returns the bridge
endpoint, token, identity, file path, exception detail, or server result to
the actor. It calls the selected PID/loopback verifier before each bridge
request. A failed, timed-out, or unvalidated action terminates the session,
marks the profile uncertain through the existing action path, and attempts
neutral release; a failed release is a failed run, never success. The launcher
owns its in-process timeout and normal client shutdown. Hard broker-process
loss is not yet contained and remains a pre-live gate.

The movement candidate removes the second per-pulse HTTP release request for
`forward`, `back`, `left`, `right`, `jump`, and `sneak`. Its one-shot deadline is
set on the client thread at dispatch, not after the broker's socket-owner
check or response; a later client tick clears the key. A repeated request
while the key is held is rejected. Opening a screen, leaving control mode,
or canceling also releases it. This is a client-tick bound, not an exact
wall-clock duration guarantee if the client tick stalls. The slow-response
profile11 remains a failed diagnostic until a fresh live movement/pickup
gate demonstrates the new path.

## Acceptance and controls

1. Offline: strict request shapes reject booleans as coordinates/deltas,
   floats, NaN, unknown keys/fields, excess duration, excessive rate/count,
   click before a valid frame, stale/cropped/oversized PNG, and actions after
   cancellation. Unit tests prove a pulse releases on failure and close
   invokes the existing lease. Build the fixed bridge against hash-pinned
   1.21.1 mappings; no runtime download or second backend.
2. Live technical smoke (requires parent client lease): fresh disposable
   Survival client with a predeclared chest and two soft mining targets placed
   before the measured run, no cheats or item grants during the run; compare
   framebuffer before/after bounded look, movement, jump, held mining,
   initial attack, use, and GUI open/click/close. `visible_key` sets the
   vanilla keybinding's pressed state; attack also queues one vanilla click
   edge on its first press. Its acknowledgement does not prove the client
   consumed that edge or caused a gameplay effect. Check actual observed behavior, held-key release,
   timeout/cancel, exact artifact and normal exit. A deliberate denied request
   must not dispatch input. Keep actor and evaluator traces separate.
3. B01 trial: the isolated actor reads the in-game guide and acts using only
   this interface. Record completion, deaths, stuck/no-progress, recovery,
   invalid actions and failure trace. One trial is a feasibility smoke, not a
   pass for the broader milestone. If feasible, run the existing five-declared-
   seed vanilla capability gate and one Aura guide-led direct-client action.
   No NPC result can establish real-client GUI, rendering or player-only Aura
   semantics. A failure/inconclusive run is still a valid measured result.

The runner has fixed scenarios, screenshots, ordinary inputs and an offline
sandboxed transport candidate, but no approved live isolated policy actor. It
cannot claim autonomous Survival. No hidden setup assertion may be replaced
by a console command's exit alone: the evaluator must check the loaded world,
Survival/cheat settings, empty-start inventory and intended preconditions
before interpreting an actor outcome. Actor-visible pixels are not an
authoritative setup check.

## External backends and effort

[WorldDriver at `688e43a`](https://github.com/AI-assisted-Minecraft-Developers/worlddriver/commit/688e43ab776b83713807627bfbc3499cadc98685)
supports 1.21.1 Fabric and real-client controls, but its own
[security guide](https://github.com/AI-assisted-Minecraft-Developers/worlddriver/blob/688e43ab776b83713807627bfbc3499cadc98685/docs/guide/transports.md#security)
says its transports have no authentication and reachable Rhino/command
capabilities have full process/operator reach. Its bot and hidden-state API
are not a no-cheat policy boundary; reject direct integration here.
[StageWright at `6b82369`](https://github.com/AI-assisted-Minecraft-Developers/stagewright/commit/6b8236955454b5cf89a043dd594e8761d9f573a1)
is a 1.21.1 Fabric/NeoForge developer scene harness, not a player-perception
driver. Defer it and NPC/protocol backends. No third-party code or mod is
copied, installed or auto-downloaded.

The adapter is a small-to-medium isolated code/test slice using the existing
bridge and lease. Actor sandbox/integration, a reviewed no-cheat seed and
guide presentation, and sequential client time for one smoke then five
declared seeds are separate prerequisites. This is a qualitative work
estimate; Minecraft startup and trial duration dominate wall time.

## Attach-only live technical smoke

`scripts/smoke_survival_input.py` is a trusted developer probe, **not** an
isolated actor or B01 trial. Its `prepare`
verb checks the selected PID, exact packaged Aura artifact and bridge, sets a
PID-derived window label, and aims at one reviewed fixture block before a
recording starts. Its `act` verb arms, waits up to 30 seconds for a matching
recorder-ready file, exercises one action, saves full-frame PNGs, cancels the
lease, and signals recorder stop in `finally`. The OBS clip and PNGs require
independent visual review; pixel difference alone is not mining or attack
proof. `use` additionally checks that the intended screen opens and closes.
The probe can be called attach-only; `scripts/run_survival_smoke.py` now owns
the disposable launch and calls it three times under one in-process token.

Prerequisites for the parent-leased run: one disposable 1280x720 Fabric 1.21.1
Survival client; a reviewed pre-measurement fixture with a reachable chest and
two separate glass or similarly soft blocks; exact Aura
`0.2.1+1.21.1` SHA-256
`2290a1a344fa8e1e43d631729b5f88d422923d573db90d1a592945fecc1aacc8`;
and ignored candidate bridge
`.lab-fixtures/survival-bridge-offline-07.jar` SHA-256
`516a0ff035d68322b60c0e8140d4764406c429034b6bf8835092fcc10348f6f3`.
The runner calls the existing reviewed `runtime_launch.launch` path: one
client with its integrated server, a fresh prepared profile, an ephemeral
in-process token, the memory guard, and normal window-close/save teardown.
It rejects a changed candidate bridge or Aura SHA before launch. The private
OBS recorder subprocess receives no bridge token or port. Parent verifies the
fixture's loaded blocks, Survival/cheat settings, empty/no-grant policy as
applicable, and the client/server cap before starting. The technical fixture
is not reused as a no-cheat B01 seed.

At the explicit parent lease, prepare a fresh profile using the existing
`python lab.py runtime prepare --manifest <reviewed-survival-manifest> --out
<fresh-profile>` path. The manifest must pin both exact JARs above, the
reviewed fixture save, `public_reviewed` bridge and Survival. Supply a
reviewed scenario-v2 file with the same fixture and Aura artifact identity;
this is a launcher preflight contract, not a gameplay script. The three
targets must be reachable, distinct blocks confirmed in the loaded world.
From the Mod Lab repo root, run one trusted command, using the actual absolute
paths and confirmed coordinates (values below are placeholders, not fixture
claims):

```powershell
python -m scripts.run_survival_smoke `
  --manifest <reviewed-survival-manifest.json> --profile <fresh-profile> `
  --scenario <reviewed-preflight-scenario.json> `
  --obs-control <private-obs-control.py> --obs-record <private-obs-record.py> `
  --use-target <chest-x> <chest-y> <chest-z> minecraft:chest `
  --attack-target <block-a-x> <block-a-y> <block-a-z> minecraft:glass `
  --mine-target <block-b-x> <block-b-y> <block-b-z> minecraft:glass
```

The runner reapplies and verifies the PID title, selects that exact enabled OBS
window, then starts the parent's authenticated bounded raw recorder for each
phase. Before the first recording, it verifies all three exact block IDs and
reach with the same fixed `aim_at_block` check; missing/unloaded setup cells
fail before a clip. It checks matching readiness, `test_id`, PID, artifact hash and normal
recorder exit; the action signals stop even on error. Its outer `finally`
verifies recording **and** streaming inactive, attempting `StopRecord` only if
its own recorder had started. A forced or unconfirmed stop fails the supervisor
even if the client lifecycle report says `inconclusive`. No OBS control is
performed by profile preparation or offline tests. If another recording was
already active, the runner refuses launch and does not stop it.

Raw clips remain in the recorder's declared inbox; PNGs, per-phase reports,
recorder output and `lifecycle-report.json` remain in the prepared profile.
The 150 ms initial-block-attack pulse and 500 ms held-mining pulse are still
only probes. A clean run reports `inconclusive` pending independent review of
the clips for an actual initial hit, sustained cracking/breaking, use, release
and normal client exit. A failed/uncertain run discards the profile. This is
not an isolated no-cheat actor or B01 readiness proof.

Candidate06, tested in closed profile03 on 2026-09-28, passed the bounded chest
use/open/close/release phase. Independent clip review found no visible hit,
crack, or break during either attack phase; before/after frames were identical.
Minecraft 1.21.1 bytecode shows that `KeyMapping.setDown` alone does not
increment `clickCount`, while `Minecraft.handleKeybinds` consumes click count
for `startAttack` and held state for continued mining. Candidate07 adds a
single first-press attack click through the current vanilla key binding, and
drains unconsumed attack clicks on release/cancel. The upstream ordinary click
handler is GUI-only, so it cannot supply a world attack. `startAttack` and
continued mining have no explicit window-focus check in the inspected pinned
bytecode, but actual background behavior remains a live gate. Do not claim
entity combat from the block-attack fixture.

Candidate07 profile04 ran the three bounded raw phases on 2026-09-28 with
normal client exit 0, PID/title-matched OBS clips, and inactive recording and
streaming afterward. Independent review passed chest use/open/close/release
and found a transient hand swing in both attack clips. No sustained cracks,
block break, or entity hit were demonstrated; the attack/mining endpoint PNGs
were pixel-identical. Thus the vanilla click edge actuates an initial swing,
but held mining is **not** accepted. Pinned 1.21.1 bytecode shows
`Minecraft.handleKeybinds` calls `continueAttack` only while attack is down
and `MouseHandler.isMouseGrabbed` is true; `grabMouse` itself returns unless
the Minecraft window is active. This is a plausible background-only gate,
not a measured mouse-grab state in profile04. A later leased diagnostic must
establish grab state and exact crosshair hit before changing the input path.
The separate private Aura QA a8 bridge already uses a redirect at the pinned
`Minecraft.handleKeybinds` mouse-grab check, gated by its active attack hold;
this supports the source-level diagnosis but is not evidence that candidate07
mines successfully. A future distinct public candidate may adapt only that
bounded condition for an active `visible_key(attack)` hold, with control-mode,
world/screen and cancel/release checks. It must not manipulate native focus or
silently inherit the private bridge's command surface. Keep candidate07 and
its profile04 evidence frozen until an independently reviewed new build and
leased live cracking/break/release proof.

Offline candidate10, `.lab-fixtures/visible-mining-bridge-offline-10.jar`
(SHA-256 `46543a391ed11f92a6878d8faf9bcb477aea113ace3f534d069dba9760cdae0d`),
implements the narrow redirect. Only a control-mode, screen-closed,
client-thread `visible_key(attack)` hold of at most two seconds may bypass the
vanilla mouse-grab check in `handleKeybinds`; ordinary vanilla behavior remains
for all other states. Explicit release and cancellation clear the grant.
Candidate10 includes the still-unvalidated persistent PID title and public
chunk-presence work from candidate09/08, but its HTTP server, input handler,
and typed endpoint class bytes match candidate09. It does not add private
commands or native focus/input manipulation. Offline compile and source checks
are not evidence of actual sustained mining: a new leased recording must show
crosshair hit, cracking or break, release, and normal teardown. Candidate07,
09 and all existing live evidence remain frozen.

Independent review found candidate10 renewed its two-second grant on every
repeated `visible_key(attack, pressed=true)` request, allowing an indefinite
hold without release. Candidate10 is frozen and unsupported. Offline candidate11,
`.lab-fixtures/visible-mining-bridge-offline-11.jar` (SHA-256
`99beb5e04c5dfb27e1e7cff2d3c614e89f170b3b92b2c180dd1ad4295c5b4e11`),
grants only on a false-to-true attack binding edge. Repeated pressed requests
cannot renew the deadline; release clears it and permits a new grant on a
later press. Focused source-level regression covers those transitions. This
is an unsupported packaged candidate; it is not on public main. Hilbert's
independent source/bytecode review passed the P1 fix. The disclosed profile05
technical smoke then exited normally with the exact PID title retained during
the chest GUI and both glass crosshairs verified. Its held-mining before/after
frames show the targeted glass present then absent, and the action report
records repeated press, explicit release/re-press, and neutral cancel. Astra's
independent raw-clip review confirmed cracking and break on the initial and
held glass targets, then a later renewed swing. This is a bounded background
mining positive. Since the glass was already gone at release, it cannot prove
that release stopped ongoing cracking or that the two-second grant expires.
The separate approved
MP fixture has now bounded-accepted GUI/Nether PID-title persistence for
developer capture, not a natural-portal or B01 input claim. Public
`chunk_presence` live non-loading controls and final release review remain
separate gates before candidate11 can be published.

## Bounded First-Wood Follow-Up

The current isolated-actor input validator allows an `attack` pulse of at most
500 ms, and candidate11's background mouse-grab grant lasts at most two
seconds. Repeated pulses release the key and reset vanilla mining progress;
neither limit can support continuous bare-hand log mining of roughly three
seconds. Candidate11's seeded glass break therefore does not establish B01
resource acquisition or guide-led Survival readiness.

A distinct offline candidate extends **only** `attack` pulse duration to a
strict integer range of 50..5000 ms at the trusted broker boundary. Other
keys remain at 50..500 ms with the existing input/frame budgets and actor
surface. The bridge must grant at most one nonrenewable six-second background
attack window per explicit false-to-true developer input edge, allowing RPC
margin for a five-second broker pulse. Repeated `pressed=true` calls cannot
refresh it, even if vanilla changes key state; only an explicit release and
neutral confirmation may re-arm it. At expiry the bridge must release the
held attack state, not merely stop bypassing mouse-grab, and control-mode
exit, broker cancellation, errors, and normal teardown must likewise verify
neutral release. There is no indefinite lease, raw command, native focus
input, hidden-state actor feed, or general autonomous-planner framework.

Before any B01 claim: static/bytecode and behavioral negative controls for
booleans/floats/out-of-range durations, other keys unchanged, repeated press
nonrenewal, forced deadline release, and cancellation; a leased raw recording
on intact stone showing cracks while held, cessation after release, neutral
tail, and re-press; then a fresh no-cheat, unseeded Survival client with the
isolated pixel/action actor actually breaking and picking up the first log.
The latter must show visible-input and inventory evidence without privileged
setup/observer leakage to the actor. The guide-led policy, isolation boundary,
five declared vanilla seeds, and one Aura guide-led trial remain separate
milestone obligations; no seeded technical fixture can substitute for them.

Candidate12 implements the bounded attack-only broker pulse and six-second
bridge deadline. Unlike candidate11's binding-edge check, its logical
one-shot request flag cannot re-arm when vanilla changes the binding state;
only explicit release/cancel clears it. A client-tick expiry actively clears
the attack key and pending click. Profile08 independently accepted release,
reset and re-press on intact stone. Profile12 independently accepted a bounded
expiry/re-press observation: cracking reset well before its timestamped
explicit release, and the rejected repeated press dispatched no input. This
does not prove an exact global six-second deadline or B01 readiness. The
disclosed profile10 placed-log input broke and was picked up, but OBS hit its
duration limit before the completion tail; fresh profile11's recorder ended
correctly while the player left the collection platform after a nominal
100 ms forward pulse. Neither is a complete technical pickup gate.

The earlier broker movement pulse used separate authenticated press and
release HTTP calls with `time.sleep(milliseconds / 1000)` between their
acknowledgments. Each request independently ran a PowerShell socket-owner
check and could wait on client dispatch; the sleep duration did **not** bound
client-held movement. Profile11 lacks per-request timestamps, so its exact
press/release latency cannot be reconstructed. Profile12's analogous attack
requests took 1.333 seconds for the initial press acknowledgment and 1.440
seconds for release, demonstrating substantial RPC overhead without proving
profile11's exact duration.

Candidate13 changes only movement to one authenticated `visible_pulse` call:
the client sets a 50..500 ms monotonic deadline and releases the ordinary key
on a later client tick. It retains the PID/loopback checks and does not cache
away ownership verification. Fresh profile14 used the same disclosed input
log and two 100 ms client-timed forward pulses; integrated-server inventory
changed `0 -> 1`, ground log `0 -> 1 -> 0`, and the player stayed within the
predeclared collection platform. The exact-PID clip stopped with
`test_finished`, and the client exited normally with OBS inactive. Its raw
visual state remains `not_reviewed` in the raw report; Astra's separate
hash-matched review accepted visible break, pickup, and settled tail for the
bounded technical fixture. Tick stalls can delay an auto-release,
so this does not establish an exact global wall-clock input bound. Natural
unseeded guide-led B01 acquisition with an isolated actor remains outstanding.
