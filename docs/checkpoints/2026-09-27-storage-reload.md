# Storage reload checkpoint

The third of the five shared bounded gameplay proofs now has real packaged
evidence. Pusher and per-render HUD acceptance are still incomplete.

## Exact runtime

- Minecraft 1.21.1, Aura 0.2.1 artifact SHA-256
  `2290a1a344fa8e1e43d631729b5f88d422923d573db90d1a592945fecc1aacc8`.
- Source expectations use Aura commit `44cc057`, not its moving HEAD.
- First positive and negative use bridge SHA-256
  `43d0d738071595bb5a794ed290bf1f0a3f6b67ca85927423f9368ea8c037594d`.
- Local ignored evidence: `.lab-fixtures/storage-01/scenario-evidence/report.json`,
  continuation `runs/7ac9767b899244fc93ba45cd10bf7bb2/scenario-evidence/report.json`,
  and `.lab-fixtures/storage-unpowered-01/scenario-evidence/report.json`.
  These local traces, profiles and launcher credentials are not distributed.
- Matched reruns `.lab-fixtures/storage-02` and
  `.lab-fixtures/storage-unpowered-02` repeat the same results on bridge
  `50e277c03ad7a65a47920335f566787df2c49c00468b15723e7d03b5c211eaad`.

## Observed behavior

The fixed Survival fixture has a coordinator at (0,161,0), a storage shelf
east of it with an empty Basic Storage Book, and one power node west of it.
It supplies 1,000 stored power as initial test input, not earned-power evidence.
Inventory contains two diamond stacks with distinct supported custom-data
components: alpha-7 and beta-3. No deposit, withdrawal or resulting item state
is injected during the public run.

Actual held-item USE on the coordinator deposits each whole stack. One
server-thread observation atomically captures shelf entries, inventory,
power node and cost. Exact component/count conservation passes, with power
1,000 to 990. The client saves and exits normally, code 0. A hash-bound
receipt permits reopening the same save, without reseeding or copying it.

After reopen the stored component digests and counts are identical, inventory
is still empty and power is still 990. Real crouch-key input, normal ticks,
server-confirmed crouch and two empty-hand coordinator USE actions withdraw
the original stacks exactly. Final shelf contents are empty and power is 980.
The second client also exits normally, code 0. This is the ordinary coordinator
interaction path, not a full browser-GUI test.

The unpowered fixture uses the same actions and raw items with zero power.
All inventory components/counts remain unchanged, storage stays empty and
power remains zero. Its unchanged-state assertion passes; the positive
deposit assertion intentionally fails. The report remains `fail`, with normal
cleanup. Sampled private peaks for the first three clients are 1,687.4,
1,699.0 and 1,638.9 MiB, below the 3,800 MiB per-workload guard.

## Runtime and safety additions

- `runtime resume` consumes a receipt binding a prior successful public run,
  exact artifact, report hashes and closed-world bytes. Missing/contended
  locks, changed saves, failed cleanup and uncertain profiles refuse reuse.
  Resume preserves separate logs/reports under `runs/<id>`.
- Storage resume reobserves the prior final fixed storage snapshot before
  new scenario actions; changed inventory, components, contents or power fail.
  A third launch of `storage-02` passed this automatic check and a live ground
  entity observer smoke, then exited normally. Its evidence is in that profile's
  additional `runs/<id>` directory, including `storage-continuity.json`.
- `set_crouch` changes the real vanilla key mapping. Its ACK does not prove
  server state. Tests wait normal ticks and assert server crouch separately.
- Exit-control waits at most two seconds for client-thread crouch-key release.
  Unconfirmed cleanup retains the lease and quarantines the profile. A fresh
  live run ending crouched and same-save reopen passed on bridge
  `58f63751808b5e32283aeef567d23abaf6023d22c65fa58bbb796f6b7b3baa70`,
  under `.lab-fixtures/crouch-smoke-02`; both exits were 0.
- Ground-entity helper/endpoint integration is preparatory for Pusher. It
  is server-authoritative and bounded to loaded chunks, radius 1..16 and 64
  entities. This does not yet establish a Pusher effect.

Tests include refusal of client-cached/mixed-tick/incomplete storage snapshots,
component substitution, duplicate inventory output and incorrect power cost.
No unsupported component or truncated snapshot can pass exact conservation.
The full Python suite passes 140 tests with two host symlink-permission skips.
Java 21 compilation passes for the mapped packaged bridge including the new
bounded entity observer. Runtime evidence, not compilation, gates gameplay claims.

Next: public Pusher equip/control evidence and bounded per-render HUD evidence.
The five-case slice is not complete.
