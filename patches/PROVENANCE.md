# Bridge hardening provenance

- Upstream: [langyo/minecraft-mod-mcp](https://github.com/langyo/minecraft-mod-mcp), tag `v0.3.0`, commit `50e059dccb09a9e23b91833ffdbf42efd97fa6e6`.
- Original 1.21.1 Fabric release asset: `minecraft-mcp-1.21.1-fabric-v0.3.0.jar`, SHA-256 `55aab04b1d7ac9203817e071cb83b6d6cf3da7164636867da33877750de64636`.
- Upstream `McpHttpServer.java` at that commit: SHA-256 `aa77bf3da9829a2e550d9a8e87118b3faa0c2145fffabe5561cd646b2cc442f5`.
- Upstream `ReflectedInputHandler.java`: SHA-256 `0b661f61021315b478a9f756d387b82a64296f96947d46696129d881c37a186c`.
- Upstream `ScreenshotHelper.java`: SHA-256 `90382b6bb0153c7461aa9799f7edf647771d14c3afbb48dc1a08a1668b901063`.
- Auth patch: binds both listener branches to loopback, requires a per-session bearer token of at least 32 characters, compares the authorization bytes with `MessageDigest.isEqual`, rejects Origin-bearing requests, and wraps every registered route.
- Framebuffer patch: reads the active GL viewport in the render-thread capture, avoids the normal screenshot cache, and preserves the caller's measured dimensions instead of guessing them from RenderTarget field order.
- Dev-click patch: maps framebuffer-pixel coordinates to GUI coordinates and dispatches actual `Screen.mouseClicked`/`mouseReleased` calls. Verified only in the Minecraft 1.21.1 Fabric Mojmap dev runtime; intermediary production-JAR behavior is not established.
- First authenticated local derivative: SHA-256 `bd36066631849a0eed5cf31718fda241e7e27d400f9cebfa5991cf0e77d68ba1`. The JAR is not included here. ZIP timestamps make rebuilt JAR hashes non-reproducible; record the hash of each artifact under test.
- Verified full-frame local `lab2.jar`: SHA-256 `e7ab46a2aea2057112be0e4249ed2fa8a9ce2e695b2302cc83c8a0a07e1a11a3`. Its 1280x720 title screenshot was independently inspected; world and feature scenarios remain untested.
- Local `lab3.jar`: SHA-256 `0bda1e57a1d5c68711536f6a9c1b6462628d2a2bc097d609ddd480a1aa948ad0`. Full-frame capture and title-to-disposable-world GUI navigation were observed in the dev runtime. Its world/player getters returned incorrect placeholder fields; this is **not** an in-world toolkit pass.

Rebuild on Windows with a `javac` supporting `--release 8`, Git, the verified upstream release JAR, and a compatible Gson JAR already available locally:

```powershell
./scripts/harden-bridge.ps1 -UpstreamJar C:\path\to\minecraft-mcp-1.21.1-fabric-v0.3.0.jar -GsonJar C:\path\to\gson.jar -OutputJar C:\path\to\hardened.jar -WorkDirectory C:\path\to\new-empty-build-dir -JdkBin C:\path\to\jdk\bin
```

This is a narrow patch, not a fork. It does not distribute upstream code or binaries. Preserve and review the upstream repository's `LICENSE-MIT`, `LICENSE-APACHE`, and `LICENSE-CC0` notices when distributing a derivative. The stock npm stdio MCP bridge has no token configuration for this patch and is not a compatible transport. The toolkit uses authenticated direct HTTP on the selected loopback socket.

The source patches are limited to three upstream classes. They do not include the newer, unverified local key, command, or world getter experiments. They do not imply verified in-world behavior or production-JAR compatibility. The full-frame and menu-navigation observations are bridge proofs, not mod parity results.
