# Passive Chunk Presence: Separate Developer Gate

Status: public source has a bounded live technical probe and independent
raw/source review. This follow-up is
separate from the candidate07 visible-input bridge and its prepared profile04.
It is not an Aura product change, an action, or part of the B01 Survival actor.
The distinct candidate08 JAR is
`.lab-fixtures/chunk-presence-bridge-offline-08.jar`, SHA-256
`a4e0f28a84b3f514a72615c56af38a8a83f0737fbabcbd4dbd9e6490d740edfa`.

## Need and contract

The seven B02-K route replacements cannot infer Aura's `Level.hasChunkAt`
guard from `/execute if loaded`: the latter requires entity-ticking and loaded
entities, while the former accepts a visible FULL chunk holder in the pinned
Minecraft 1.21.1 runtime. `block_entity_inventory` is not reusable: it guards
on `hasChunkAt`, then reads a nearby block entity, and returns unsupported
when that guard fails. Target block-data reads can load/promote a chunk.

The existing authenticated `/api/scenario/v2` endpoint gains only
`observe/chunk_presence` with exactly `x`, `y`, and `z` (existing world-border
and build-height bounds). It executes on the integrated server thread for the
selected player's current dimension and echoes that dimension, coordinates,
server tick, `serverAuthoritative: true`, and
`stateSource: integrated_server_chunk_presence`. The two independent flags are
`hasChunkAt = level.hasChunkAt(pos)` and
`entityTicking = level.isPositionEntityTicking(pos)`. The endpoint uses no
`getChunk`, `getBlockState`, `getBlockEntity`, or data command, and returns no
block or entity contents. The implementation must remain read-only even when
both flags are false.

The mapping pinned by the build is Minecraft 1.21.1 Tiny SHA-256
`6dfd4ab0691e96bf5dbaf75f0900786bdb534b144c8438e4c2a765145f1e524a`.
The inspected intermediary chain is `LevelReader.method_22340` ->
`LevelAccessor.method_8393` -> `ServerChunkCache.method_12123`, which reads a
visible holder at FULL status without requesting a chunk. ServerLevel
`method_37118` reads entity visibility and ticking-tracker maps without a
chunk request. This is source/bytecode evidence, not a live behavioral pass.

## Acceptance and negative controls

- Offline: reject unknown fields, booleans/floats/out-of-range coordinates,
  malformed result flags/source/dimension, missing or inconsistent server
  ticks, and mismatched coordinates. Compile against pinned 1.21.1 inputs;
  inspect the compiled probe for absence of loading or block-content calls.
- Live, only after an explicit client lease: record a local position with
  `hasChunkAt=true` and preserve the independently observed `entityTicking`
  value; do not require both flags to be true at that coordinate. Probe the
  same local position after settling to seek an `entityTicking=true` positive
  control, but withhold that flag's live-positive claim if it stays false.
  Then record a remote non-forceloaded position with `hasChunkAt=false` and
  repeat passive probes without changing that result. A local `true/false`
  pair is valid evidence that loaded and entity-ticking differ, not an
  observer failure. Do not infer either flag from `/execute if loaded`.
- Route gate: at each controlled measurement tick of B02-K01-R1/K03-R1 through
  K08-R1, record the exact target `hasChunkAt` flag alongside source state.
  Match tick IDs; withhold route conclusions on missing/mismatched samples.
  Keep target block-data queries out of the measured window. A true flag on
  any tick cannot support an unloaded-guard claim for that tick. Preserve the
  prior diagnostic-only rows and assess new proof separately.

The observer is for trusted developer/evaluator use only. The pixel-only
Survival broker must not expose it to an actor, and this feature does not
constitute an autonomous driver or B01 no-cheat readiness.

Profile13 exercised the public candidate12 bridge in a fresh owned client
without OBS or fixture commands. The raw report is
`.lab-fixtures/survival-visible-smoke-profile-13/public-chunk-presence-report.json`.
The known local `(1,161,2)` cell returned `true/true` at server ticks 123 and
197; remote `(1000000,64,1000000)` returned `false/false` at ticks 150, 226
and 458 after all negative controls. Each envelope had exact coordinates,
dimension `minecraft:overworld`, server-authoritative source and one-tick
coherence. Missing/wrong bearer returned 401, Origin 403, GET 405, and
boolean/float/extra/out-of-range coordinates 400. The client exited normally
with code 0, and no OBS was used. This is strong bounded positive/far/security
evidence, independently reviewed for this bounded public capability, but not evidence for Banach's seven
private a8 route cases. Absence of a changed far result supports non-promotion
in this fixture; source review still anchors the non-loading mechanism.

## Private Aura QA compatibility

Banach's game4 fixture/tick scripts use trusted `execute_command` on a
**private** a8 bridge (`bridge-intermediary.jar`, SHA-256
`a8fad2ea5e6f68ebab0900a5bd67f268368cdaa72c7a7641320fd58ffd6be5b0`).
That JAR has no `/api/scenario/v2`; its `McpHttpServer.class` is byte-identical
to the private lab7 base class (class SHA-256
`4f8bd8bf6d645b821ccdf1f63de63f8a702c169031b4fae09ee1162b5045c0a5`).
The public candidate08/09 bridges deny generic commands, so substituting
either would invalidate the existing fixture runner. There is no trusted
structured fixture path in that runner that replaces its commands.

The minimal follow-up is an ignored, separately hashed **private QA-only**
overlay on that exact a8 JAR: rebuild only its existing HTTP server class to
register one `/api/chunk_presence` handler through the existing loopback,
bearer-token, and Origin-rejecting context wrapper; add one read-only handler
that validates an exact bounded `x/y/z` JSON request and schedules the two
non-loading predicates on the integrated-server thread. Keep `/api/cmd` and
the private command behavior unchanged for trusted fixture setup, and do not
copy this route or command policy into the public package. The offline overlay
was `.lab-fixtures/private-chunk-overlay-02.jar`, SHA-256
`36eca78d8766c5a22add319555fa99e17cb93ff26a4150226b9fe8f673294ec5`.
`scripts/build_private_chunk_overlay.py` pins the a8 JAR, private HTTP source,
and original HTTP class hashes. It compiles `private-qa/ChunkPresenceHandler.java`,
runs the parser's 12 negative controls, and replaces only the outer HTTP class
while preserving the private command and input handler class bytes. Overlay02
is **invalid**: its Java 21 outer class omitted synthetic `access$` methods
still called by retained a8 Java 8 handlers; a leased `/api/cmd get_world_info`
preflight failed with `NoSuchMethodError access$600` before any chunk probe.
Do not reuse overlay02 or count it as live observer evidence.

Offline overlay03, `.lab-fixtures/private-chunk-overlay-03.jar` (SHA-256
`012a1bfdfac3f38b01bd23bc5f13f9259f3e274669d1a2b4513d087647ab47b8`),
compiles the replacement outer at Java 8 compatibility and the added handler
at Java 21. Against the exact a8 base, all 39 retained class entries remain
byte-identical; all ten retained `McpHttpServer.access$` call targets resolve
with matching descriptors and accessor instruction bodies. The builder now
checks this complete bytecode linkage before packaging. Parser negatives
passed, but the private `/api/cmd`, auth/Origin, loaded/far and non-loading
runtime controls remain unrun for overlay03. The JAR contains a
`private_qa_only` marker; neither builder nor handler is in the public package
or isolated actor surface.
Negative controls: malformed/extra/float/boolean coordinates, wrong method,
missing token, Origin, missing integrated server, duplicate/incorrect PID,
and repeated far-cell probes that must not promote loading. Banach's seven
cases remain diagnostic-only until that separate private artifact and live
predicate/tick evidence pass under a parent client lease.
