# Public Chunk Presence: Independent Bounded Review

Status: accepted for the public developer-inspection capability only; not a
private a8 route proof, Survival actor observation, or publication decision.
The parent independently reviewed the profile13 raw controls and source after
the owned client exited normally. No OBS recording was used.

- Raw report: `.lab-fixtures/survival-visible-smoke-profile-13/public-chunk-presence-report.json`, SHA-256 `8f88e57c125e3b8b94144c4b80ab557f6f706448c898cfeecc4ce3b2dafe1c1c`.
- Exact client artifact: candidate12 `fa97fbee19beb09c1a1becde8f5a91a7b40d77ae5eb2923dfe6fa6f37f3fa177`; Aura 0.2.1 `2290a1a344fa8e1e43d631729b5f88d422923d573db90d1a592945fecc1aacc8`.
- In `minecraft:overworld`, local `(1,161,2)` gave `hasChunkAt=true/entityTicking=true` at ticks 123 and 197. Far `(1000000,64,1000000)` gave `false/false` at ticks 150, 226, and final tick 458 after repeated probes. Exact coordinates, dimension, and atomic server-tick envelope were retained.
- Missing/wrong bearer returned 401; Origin 403; GET 405; boolean, float, extra and out-of-range coordinates 400. Public generic `execute_command` remained denied.
- Source and compiled probe use the passive `hasChunkAt` and `isPositionEntityTicking` predicates on the integrated-server thread. No chunk fetch, block entity/content read, or load promotion is in this observer path. The far-cell repeat did not promote a loaded result in this run.

This evidence supports the bounded public observer contract. It does not
establish any of Banach's seven route cases, nor does it authorize exposing
developer inspection to an isolated pixel-only actor. The raw report's
review state is unchanged; this document records the separate review.
