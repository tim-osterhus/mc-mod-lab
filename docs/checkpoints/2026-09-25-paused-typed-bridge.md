# Paused typed bridge checkpoint

Historical pause record; implementation resumed afterward. See the current
packaged-bridge documentation for supported capabilities and newer evidence.

Status: saved, uncommitted work in `mc-mod-lab`. Do not claim the five Aura
gameplay proofs or milestones 1-3 complete.

The last public commit remains `c19e752`. Current local edits add a fixed
authenticated typed bridge route, read-only client/integrated-server tick and
inventory observers, an optional Aura client-cache adapter, bounded item
component digests including `minecraft:custom_data`, four client actions,
and partial v2 runner/schema support. The authoritative Aura server observer
was not written. Aura client-cache snapshots explicitly do not claim server
authority. No typed Aura mechanic has passed a public scenario.

Checks at pause: 93 Python tests passed with 2 skipped; the current Java bridge
source compiled with Java 21 into an ignored derivative. An earlier derivative
passed an isolated packaged 1.21.1 client run with server-tick and inventory
reads, unsupported non-Aura coordinate, rejected wrong-item action, fixed-route
security denials, and normal save/exit. Those live checks predate the final
`custom_data`/timeout edits; they do not validate the newest derivative.

Local ignored evidence: `.lab-fixtures/prepared-021-j/` (typed read/action
probe) and `.lab-fixtures/prepared-021-k/` (typed route denial probes). The
security run used runner code mid-edit and its GUI scenario was unsupported;
an earlier stable GUI run is `.lab-fixtures/prepared-021-h/`.

Resume by reviewing the dirty diff and updating `package-files.json`; add
focused tests for the typed endpoint, tick waits, assertions, and component
digests. Rebuild the derivative, then use a new disposable profile and a
sealed, non-result-seeded Aura fixture to validate server-authoritative
observations and each positive/control pair. Do not reuse a parent's live
profile or treat action acknowledgement as a state transition.
