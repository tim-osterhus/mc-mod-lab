# Reviewed Aura proof fixtures

These scenarios target the exact Aura 0.2.1+1.21.1 artifact in their `runtime`
fields. Use a fresh isolated packaged profile per case. The examples do not
create or mutate fixtures through privileged commands. Prepare raw inputs in a
separate reviewed setup phase, record that phase, close normally, and retain
the intact source `session.lock`. `runtime prepare` copies and hashes that
closed seed while holding its lock. Never seed the expected gameplay result.

## Core pump

Use a stone floor at y=160 and Survival player at (0.5,161,2.5), yaw 180.
Place an empty burning pump at (0,161,0) and empty ordinary node at (0,164,0).
Remove other nearby nodes, item entities, mobs, and redstone sources. Keep
all involved chunks loaded. Supply exactly one White aura crystal in hotbar
slot 0 and one coal in slot 1. No aura or fuel is preloaded. For the blocked
seed only, place an opaque stone block at (0,162,0). Otherwise leave the upward
route empty. Disable mob spawning and daylight cycling for the fixed fixture.

- `aura-core-pump-flow.json`: actual crystal use, real coal drop, and exact
  same-server-tick accounting. Both node totals sum to 1,000 throughout;
  final pump/target totals are 0/1,000. Coal is absent from inventory and the
  pump's pickup bounds. Speed is 300; power spends once per target-attempt
  pulse at world-time modulo 20 equal to 2.
- `aura-core-pump-blocked.json`: the same coal input earns 320 fuel power,
  but the stone route preserves 1,000/0 aura and all 320 fuel power. The last
  positive transfer predicate intentionally fails.
- `aura-core-pump-unfueled.json`: coal remains held, power/speed stay zero,
  and aura stays 1,000/0. The last positive predicate intentionally fails.

The atomic observer refuses intermediate block entities, unsupported node
kinds, unavailable chunks, more than 64 nearby dropped items, or incomplete
inventory components. It examines only this vertical pair and local pickup
bounds, not every block in a general network. Fixture review must exclude
additional feeding/receiving nodes. Fuel consumption is inferred from the
actual drop, authoritative inventory/local-item accounting, newly earned fuel,
and matched controls; the item entity's entire lifetime is not traced.

## Black Hole

Use the same floor/player position with no aura machinery nearby. Survival
inventory starts with cobblestone in three slots: 64, 21, and 17. Other slots
hold 3 diamonds with custom data `{lab:"alpha",value:7}`, 23 stone, and 11
mossy cobblestone. Other inventory/armor/offhand slots are empty.

For the positive seed, place one real dropped Portable Black Hole at the
player's feet with a 2,400-tick vanilla pickup delay. This is a raw item input,
not an inventory injection during the test. Close the preparation client
before the delay expires. The control seed omits only that item. Preserve
setup provenance; no deletion, component mutation, or count outcome is seeded.

The runner first verifies a no-deletion window, then waits normal server ticks
for actual ground pickup and subsequent accessory processing. It requires
102 cobblestone to become zero, exactly one new Black Hole, and identical
counts/component digests for all unrelated stacks. A later window verifies
unchanged subsequent inventory across its slots. It does not prove that no
duplicate item entity remains on the ground; no ground-item observer is used
by this case. These scenarios have no action steps: the stationary player
receives the supplied ground item naturally when its vanilla pickup delay
expires. This is passive inventory-mechanic evidence, not a typed action or
player-controlled movement proof. The no-hole control requires all 102 to remain, then
intentionally fails the positive deletion predicate. Aggregate lifecycle
`fail` is expected for these deliberately failing final predicates; inspect
the preceding successful control assertions and normal cleanup separately.

Snapshots include registry IDs, counts, and supported component digests,
never raw custom-data values. Unknown/truncated component patches refuse
exact conservation. A matching aggregate digest is not a substitute for the
declared exact counts and reviewed causal input/control sequence.

## Still incomplete

Pusher equipment/entity observations, shared storage save/reopen continuation,
and per-render HUD continuity are not provided by these fixtures. Separate
alpha/beta storage components and unsupported-component live controls remain
part of the storage acceptance work. Do not promote these examples to a claim
that all five acceptance cases or all Aura mechanics are complete.
