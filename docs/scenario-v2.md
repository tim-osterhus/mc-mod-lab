# Bounded scenario v2 (partial implementation)

`scenario run` tests a prepared, isolated, already-running Windows Fabric
1.21.1 packaged client. `runtime prepare` and `runtime launch` add an opt-in
owned packaged-client lifecycle, including normal save/exit and a continuously
sampled memory guard. The five Aura proof cases in the design spec remain
unimplemented. The private diagnostic bridge used in Aura QA is not a public
Mod Lab backend.

The runtime manifest and Java argument template are **trusted, reviewed local
executable inputs**. Matching SHA-256 hashes proves bytes did not change; it
does not sandbox Java, prove every classpath JAR is safe, or verify the full
classloader. The launcher requires a single Fabric KnotClient main class,
packaged absolute JAR classpath with Fabric Loader, and rejects common dev
output paths and remapping flags. Review the entire template and all classpath
JARs before marking a profile public. The exact target JAR is separately
copied to the fresh profile and checked against scenario, metadata, and log.

The runner shares the alpha's marked disposable world, exact process/game
directory check, authenticated loopback and 3,800 MiB working-set guard.
`fixture create` holds a nonblocking source `session.lock` when present and
omits that lock from the new world copy; a held lock refuses the copy.
It additionally verifies an exact artifact hash, `fabric.mod.json` ID/version,
unique matching JAR in that profile's `mods` directory and matching fresh
Fabric launch-log entry. These checks are strong identity evidence, but the
Fabric log alone is not a cryptographic classloader attestation. A profile
with ambiguous mod identity is `unsupported`.

Use a **separate profile, save, port and token for each workload**. Parallel
isolated sessions are allowed. Never point this command at another task's
profile. The 4.5 GB ceiling applies to each Minecraft/build/helper workload,
not to the Codex desktop app. The CLI samples working set and private bytes
for declared tracked PIDs at scenario steps; this is not a continuous or
OS-enforced memory cap. Include every workload child PID in local identity.

After preparing a real packaged instance and identity file, replace the
all-zero example artifact hash with the reviewed JAR's SHA-256. Run:

```text
python lab.py validate scenario-v2 examples/scenario-v2.json
python lab.py scenario run --identity identity.json --scenario examples/scenario-v2.json --artifact PATH_TO_JAR_IN_PROFILE_MODS --out reports/inventory-v2
python lab.py validate scenario-report-v2 reports/inventory-v2/report.json --portable
```

The example is a contract, not runnable as committed. Never put a private
token in the scenario, identity, or report. `MC_MOD_LAB_TOKEN` stays only in
the current process environment. Every run needs a fresh output directory.

Supported now: read-only world/player/screen/full-frame observations; bounded
`press_key`, `click`, `click_button_index`, and `use_item`; exact screen-class
and world-name assertions. A result of `pass` means **only** these declared
steps and required assertions passed on the verified prepared instance.
Action acknowledgements alone do not establish gameplay semantics. PNGs stay
`not_reviewed` until an independent visual review.

Unsupported now: actual inventory contents, nearby entities, Aura state,
semantic movement/aim/drop/equip, server game-tick/event waits, per-render HUD
metrics, normal save/reopen, automated packaged launch, and the five Aura
mechanics. The runner stops at the first unavailable capability and leaves
later steps `not_run`; it never fabricates positive evidence. The v2 schema
reserves bounded names for those future capabilities but does not expose
arbitrary commands, reflection, or NBT paths.

Control mode uses an exclusive lock in the selected profile. Successful exit
removes the lock. If exit is not confirmed, the report fails and leaves the
lock in place for manual inspection; never delete it automatically or take
control of that profile from another session. `save-exit` reports
`unsupported` until a verified lifecycle adapter exists.
