# Five-proof first slice

The five bounded real-client harness cases in spec milestones 1-3 are accepted.
This is not completion of the Aura mechanic matrix, legacy parity, autonomous
Survival, general Minecraft support or automatic visual approval. No target-mod
source, build configuration or release was changed for this tooling checkpoint.

| Case | Accepted scope and evidence |
| --- | --- |
| Core pump | [Atomic 1,000-aura accounting, earned fuel/time and blocked/unfueled controls](2026-09-27-core-and-black-hole.md). |
| Black Hole | [Passive real pickup, 102 cobblestone removed, exact unrelated inventory preserved and no duplicate output across slots](2026-09-27-core-and-black-hole.md). Ground-entity absence is not claimed. |
| Shared storage | [Real deposit, normal close/reopen, component-exact 7+3 withdrawal and power accounting](2026-09-27-storage-reload.md), with unpowered and component-mismatch negatives. |
| HUD | [1,018 rendered numeric ROI records, complete numeric/RGB keyframe coverage, independent review and distinct zero/look-away/other-node controls](2026-09-27-hud-capture.md). |
| Pusher | Real B-screen equip/removal, exact attachment/cursor components, outward impulse versus untouched no-ring controls at measured two-block distance; details below. |

All target runs use Aura 0.2.1+1.21.1 SHA-256
`2290a1a344fa8e1e43d631729b5f88d422923d573db90d1a592945fecc1aacc8`.
Source expectations remain pinned to `44cc057`, not the target repo's moving
HEAD. Each paired positive/negative uses the same measured public bridge.
Raw profiles, captures, tokens, launcher arguments and diagnostic setup scripts
remain local and ignored, not part of the public plugin.

## Pusher equip and removal

The initial accepted pair uses public bridge SHA-256
`69108498c26dcef697e2db7b2fde5c28bc7fa963fec511c64703fc8715316b76`:

- `.lab-fixtures/pusher-positive-02/scenario-evidence/report.json`.
- `.lab-fixtures/pusher-control-02/scenario-evidence/report.json`.

That pair supplies one pre-bound Pusher ring as a disclosed raw fixture input;
it does not itself prove charm binding. All four accessory slots and the cursor
start empty. Ordinary B-screen clicks move the exact ring from hotbar 8 to
cursor to ring1, and later back through cursor to inventory. Canonical component
digest `307438420020c48c04ce39a57909cc665fcddab58ab88fdc1d9d5f4a8abe24bd`
and count one are preserved; unrelated slots remain empty. No attachment setter
is exposed by the bridge.

The controlled NoAI/NoGravity hostile remains stationary but acquires outward
velocity magnitude 0.72451455 from zero while equipped, at exactly two blocks
from the player. This is a measured knockback impulse, not travel distance.
After actual removal, ordinary forward-key input walks the player to a second
untouched matched target 20 blocks away. The ring is not equipped while walking.
Player and target positions are observed; distance is again two blocks, and
zero-to-zero velocity passes across another normal 60-tick minimum window.
No target velocity is reset after an action. The separate fresh no-ring lane
also remains zero and deliberately fails the positive impulse predicate; its
report stays `fail`, not relabeled successful gameplay.

Both clients close normally with exit 0. Sampled private peaks are 1,675.3 and
1,638.2 MiB under the 3,800 MiB per-workload guard. Astra-low independently
reviewed the four actual open/equipped/returned/removal-context screenshots for
UI consistency. Parent independently checked authoritative reports, artifact
and bridge hashes, exact slots/counts, measured geometry and lifecycle records.
The sibling Aura audit is `docs/audits/2026-09-27-pusher-public-review.md`.

### Actual charm binding rerun

The stronger final pair uses bridge SHA-256
`195cda6e1aa53951292d2f8c6d8376bb7c7ba4279ad78acfc8a5f521f24f1b71`,
with evidence in `.lab-fixtures/pusher-positive-03/scenario-evidence/report.json`
and `.lab-fixtures/pusher-control-03/scenario-evidence/report.json`.
An initially unbound ring is actually equipped through B-screen clicks. Verified
main-hand use of the supplied raw Pusher charm consumes exactly one charm and
changes the ring to the expected supported component digest above. The bound
role/effect is not seeded in this rerun.

After binding, measured outward impulse is 0.70257243 from zero at two blocks.
Physical removal returns exactly one component-identical ring, with no extra
inventory output. Ordinary walking to the untouched second target again yields
zero-to-zero impulse at two blocks. The matched no-ring lane attempts the same
charm use, retains it unchanged, keeps all attachments/cursor empty, observes
zero impulse and deliberately fails the positive predicate. Both clients exit
normally, code 0; sampled private peaks are 1,683.4 and 1,658.9 MiB. The independent
four-screen UI review above belongs to the initial `02` pair; this supplemental
`03` run adds authoritative binding evidence, not a separate UI-parity verdict.

## Reusable fixture and scenarios

The portable [positive](../../examples/aura-pusher-positive.json) and
[negative](../../examples/aura-pusher-control.json) scenarios extend the above
comparison to actual raw-charm binding. Prepare a closed, reviewed disposable
Survival seed before the public run:

- Empty all four accessory slots and cursor. Supply an unbound ordinary Ring of
  Binding in hotbar 8 and one Pusher Fairy Charm in hotbar 0. The charm's raw
  supported custom data is `fairyRole: "pusher"`. No bound-ring result or fairy
  entity is seeded in this version.
- Use a stone floor at y179 spanning x118..128 and z118..148 with clear air above.
  Start the player at (123.5,180,123.5), yaw 0, pitch 0, Survival. Use no unrelated
  nearby entities, natural spawning or active status effects.
- Supply two otherwise identical persistent, silent, invulnerable NoAI and
  NoGravity zombies at (125.5,180,123.5) and (125.5,180,143.7). Initial motion is
  zero as raw fixture state only. A stone stop at x122..124, y180..182, z144 makes
  the normal walking endpoint stable. The recorded endpoint is
  (123.5,180,143.69999998807907); the second target remains two blocks away.
- Pin a 1280x720 framebuffer and GUI scale 2. The examples use reviewed screen
  coordinates, not resolution-independent semantic slots. B must open
  `AuraAccessoryScreen`; fixed server attachment/cursor assertions gate clicks.
  Do not reuse the coordinates at another GUI scale.
- Use the same clean seed for both lanes and the exact declared artifact. No
  setup command is allowed once the public sequence begins. The no-ring lane
  attempts charm use without equipping the ring, and must retain the charm.

The server observer reads four named slots and the current menu cursor in one
server-thread task, with complete supported component digests and hashed player
identity. Unknown/truncated components, client-cache authority, missing slots
or mixed ticks refuse an exact claim. `set_forward` uses vanilla key state;
cleanup waits for confirmed forward/crouch release. `use_selected_item` verifies
the held registry ID and invokes vanilla item use; an ACK is never consumption
or effect evidence. `stationary_entity_impulse` binds UUID, health, dimension,
fixed positions, initial motion and optional declared distance. It does not
turn an unrelated ambient velocity into a general fairy proof.

The [HUD changing example](../../examples/aura-hud-changing.json) uses the
previously documented empty burning pump at (0,161,0), upward ordinary node at
(0,164,0), 12 White crystals in hotbar 0 and one coal in hotbar 1. It collects
evidence only; independent review and separate controls remain required.

## Known failures and deferred work

Validation: 179 Python tests pass with two Windows host symlink-permission
skips. The release audit covers 88 tracked files and 70 explicitly packaged
files, including the newly staged helpers, tests and examples; package creation
passes. The final mapped bridge compiles under Java 21, and both final binding
lanes exercised that exact bridge. No owned Minecraft or build process remains
after these runs. The per-workload memory guard samples working set and private
bytes; it is not an OS-enforced cap or proof against unsampled peaks.

The first Pusher copies retained unrelated old accessories. The new observer
correctly failed their empty-slot preconditions before any effect action.
An initial GUI cleanup hit its too-small declared keyframe budget and failed;
a fresh copy with an adequate bounded budget completed normal GUI removal and
normal close. These retained failures are fixture/evidence failures, not Aura
defects and not hidden passes. All final claims refer to the named clean runs.

The Aura coverage ledger remains in the sibling repo at
`docs/specs/aura-playtesting-v2.md`; its full T/B matrix is separate from these
five harness acceptance references. The known juvenile Breeder defect and other
project-specific gaps are not resolved or marked green by this checkpoint.

At this checkpoint, spec milestone 4 (Fabric GameTest importer and deterministic
in-world conservation) was pending next, not canceled. Its subsequent bounded
implementation is recorded in [the GameTest checkpoint](2026-09-27-gametest.md).
Milestone 5 remains
later/deferred: broader matrix, randomized trials,
multiplayer integration, profiling and survival-agent/NPC backend evaluation.
There is no pathfinding, generic NBT/command escape, automatic baseline
promotion, universal component codec or general multi-network proof here.
