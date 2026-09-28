# Offline Minecraft 1.21.1 mapping lookup

The packaged bridge already uses a reviewed Tiny v2 mapping with namespaces
`official`, `intermediary`, and `named`. It must have SHA-256
`6dfd4ab0691e96bf5dbaf75f0900786bdb534b144c8438e4c2a765145f1e524a`.
The build checks the bytes before translating fixed reflection sites. Keep
using that local input and the exact 1.21.1 intermediary Minecraft JAR, Aura
0.2.1 JAR, and Fabric dependencies declared for the local build. Do not infer
compatibility from a newer game's mappings.

For a source maintenance question, locate the named class/member in the
reviewed Tiny file, resolve its intermediary name, and inspect its signature
with local `javap` against the 1.21.1 intermediary JAR. Compare the bridge's
fixed Java call and add a focused test before rebuilding. `Tiny.cls` and
`Tiny.member` in `scripts/build_packaged_bridge.py` provide the same bounded
lookup already used by the builder. A missing or ambiguous member and a
mapping hash mismatch are build failures, not a reason to fetch a replacement
automatically.

This is a developer workflow, not an MCP endpoint. Do not ship decompiled
Minecraft source or Minecraft JARs in the plugin. Upstream source-search tools
such as [use-ai-for-mc/mcdev-mcp](https://github.com/use-ai-for-mc/mcdev-mcp)
may be useful as external references, but their client-source bundle and
paired Groovy bridge do not replace this pinned Fabric 1.21.1 runtime. The
independent [embeddedt/mcdev-mcp](https://github.com/embeddedt/mcdev-mcp)
has useful mapping/source-path ideas under OSL-3.0; no code was copied from it.
