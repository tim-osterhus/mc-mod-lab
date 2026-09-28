# Core pump and passive inventory checkpoint

Two bounded fixture cases now have positive and deliberately failing controls.
The complete five-case milestone remains unfinished: Pusher, shared storage
reload, and per-render HUD continuity are still pending.

All gameplay evidence below uses exact Aura 0.2.1+1.21.1 artifact SHA-256
`2290a1a344fa8e1e43d631729b5f88d422923d573db90d1a592945fecc1aacc8`,
expectations from source `44cc057`, and public bridge JAR SHA-256
`897ad57f4e835a9ba846a47d86edb7269d3064ff650807fb921399b33e997430`.
The bridge hash is not a Git commit. No raw fixture or gameplay outcome was
modified through a public command endpoint.

## Core pump acceptance

Local ignored evidence directories:

- `.lab-fixtures/core-pump-fueled-04/`: exact 1,000-aura same-tick accounting;
  power 299 to 284 over 15 target-attempt pulses, speed 300, coal absent from
  player inventory and local item bounds after actual drop. Positive pass.
- `.lab-fixtures/core-pump-blocked-04/`: real coal earns 320 power; opaque stone
  obstruction preserves all 320 power and pump/target aura 1,000/0. Accounting
  passes; final positive-transfer predicate deliberately fails.
- `.lab-fixtures/core-pump-unfueled-05/`: held coal unchanged, zero power/speed,
  pump/target aura 1,000/0. Accounting passes; positive predicate fails.
- `.lab-fixtures/core-pump-fueled-06/`: fresh positive rerun after the runner's
  HTTP 422 quarantine fix, exact accounting and normal exit pass.

Keep the negative reports' original `fail` statuses. They demonstrate that
the positive predicate rejects known-broken conditions; do not relabel the
entire run `pass`. Every accepted run closed normally with exit code 0.
The earlier unfueled-04 startup attempt was unsupported because simultaneous
startup selected an already-reserved-but-not-yet-listening port. It is retained
as a launcher failure, not gameplay evidence. Port reservation now holds an OS
lock through startup/shutdown; a real contention regression covers that path.

## Black Hole acceptance

`.lab-fixtures/black-hole-positive-02/` and
`.lab-fixtures/black-hole-control-02/` are the final paired evidence. Each has
`scenario-evidence/report.json`, framebuffer capture, and lifecycle report.
Positive: a stable precontrol, then exactly 102 cobblestone across 64/21/17
stacks becomes zero after one actual pickup. All unrelated inventory preserves
exact components/counts: three custom-data diamonds, 23 stone, 11 mossy
cobblestone. The later inventory snapshot is unchanged. Control: no hole,
all 102 cobblestone remains and the final positive deletion predicate fails.

This is passive inventory-mechanic evidence. There are **no typed action
steps**: the player stands still over a supplied ground hole whose vanilla
pickup delay expires. The fixture seeds that raw item, never deletion.
The historical step name `no-duplicate-output` means only unchanged later
inventory across its slots. Ground-entity absence or duplicate ground output
was not observed and is not claimed. Both clients exit normally, code 0.
Peak private bytes: positive 1,648.1 MiB, control 1,634.8 MiB.

## Safety and checks

- Every post-send action failure before a fully validated matching ACK
  quarantines the profile, including HTTP 500/422, malformed JSON/envelopes,
  oversized replies, invalid ticks and malformed 200 acknowledgements.
  Regression coverage checks retry and fixture/runtime seed refusal; pre-send
  and read-only errors do not quarantine.
- Missing source `session.lock` now refuses copying. The existing real child
  process contention test verifies an actively held lock also refuses copying.
- Supported item counts/component digests are recorded without raw custom data.
- 114 Python tests pass, two host symlink-permission skips. Java 21 bridge
  compilation and portable live report validation pass. Earlier slow suite
  runs came from an obsolete test port mock; startup tests now mock reservations
  and the fresh full verbose suite completes in about ten seconds.
- Portable example scenarios and their reviewed raw-input fixture layouts are
  shipped. See [fixture requirements](../aura-proof-fixtures.md).

Next: implement shared storage observation and normal same-save reopen with
exact component/count/power receipts, then Pusher and per-render HUD evidence.
Do not mark these remaining cases supported from offline tests or preparatory
schemas alone.
