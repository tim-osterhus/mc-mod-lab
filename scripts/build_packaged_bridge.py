"""Build the reviewed Minecraft 1.21.1 Fabric bridge from pinned inputs."""

import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = Path("packages/common/src/main/java/xyz/langyo/minecraft/mcp/common")
MAPPINGS_SHA256 = "6dfd4ab0691e96bf5dbaf75f0900786bdb534b144c8438e4c2a765145f1e524a"
SOURCE_SHA256 = {
    "McpHttpServer.java": "c0b54fe0461368d87aba0b754cce54d216054a2d5d72192c5c63d2800787c038",
    "ReflectedInputHandler.java": "32c8e98345a0a7fcd16dd7f2b25c61734e02baf898d827cd08994f641cd614e5",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError("pinned bridge source changed at a required edit site")
    return source.replace(old, new)


class Tiny:
    def __init__(self, path):
        if digest(path) != MAPPINGS_SHA256:
            raise ValueError("1.21.1 mapping bytes differ from the reviewed fixture")
        self.classes = {}
        self.members = {}
        owner = None
        with path.open(encoding="utf-8") as stream:
            if stream.readline().rstrip("\n") != "tiny\t2\t0\tofficial\tintermediary\tnamed":
                raise ValueError("unsupported Tiny mapping namespaces")
            for line in stream:
                fields = line.rstrip("\n").split("\t")
                if fields[0] == "c" and len(fields) >= 4:
                    owner = fields[3]
                    self.classes[owner] = fields[2]
                elif fields[0] == "" and len(fields) >= 6 and fields[1] in {"m", "f"}:
                    self.members.setdefault((owner, fields[5]), set()).add(fields[4])

    def member(self, owner, name):
        values = self.members.get((owner, name), set())
        if len(values) != 1:
            raise ValueError("missing or ambiguous reviewed mapping: " + owner + "." + name)
        return next(iter(values))

    def cls(self, name):
        if name not in self.classes:
            raise ValueError("missing reviewed class mapping: " + name)
        return self.classes[name].replace("/", ".")


def mapped_input(source, mappings):
    mc = "net/minecraft/client/Minecraft"
    window = "com/mojang/blaze3d/platform/Window"
    source = replace_once(source, 'mc.getClass().getMethod("getWindow")',
                          'mc.getClass().getMethod("' + mappings.member(mc, "getWindow") + '")')
    groups = {
        mc: ("player", "gameMode", "hitResult", "options", "screen", "keyboardHandler",
             "getSingleplayerServer", "startAttack", "startUseItem"),
        "net/minecraft/client/Options": ("keyAttack", "keyUse"),
        "net/minecraft/client/KeyMapping": ("setDown",),
        "net/minecraft/client/KeyboardHandler": ("keyPress",),
        window: ("getWindow", "getWidth", "getHeight"),
        "net/minecraft/client/gui/screens/Screen": ("width", "height"),
        "net/minecraft/client/gui/components/events/GuiEventListener": ("mouseClicked", "mouseReleased"),
        "net/minecraft/world/entity/player/Player": ("getGameProfile",),
        "net/minecraft/client/multiplayer/MultiPlayerGameMode": ("getPlayerMode",),
        "net/minecraft/server/MinecraftServer": ("getWorldData", "getWorldPath"),
        "net/minecraft/world/level/storage/LevelResource": ("ROOT",),
        "net/minecraft/world/level/storage/WorldData": ("getLevelName", "getDifficulty", "getGameType"),
    }
    for owner, names in groups.items():
        for name in names:
            old = '"' + name + '"'
            if old not in source:
                continue
            source = source.replace(old, '"' + mappings.member(owner, name) + '"')
    source = replace_once(source, "net.minecraft.world.level.storage.LevelResource",
                          mappings.cls("net/minecraft/world/level/storage/LevelResource"))
    screenshot = mappings.cls("net/minecraft/client/Screenshot")
    target = mappings.cls("com/mojang/blaze3d/pipeline/RenderTarget")
    capture = (
        'Object target = mc.getClass().getMethod("' + mappings.member(mc, "getMainRenderTarget") + '").invoke(mc);\n'
        '            Object image = Class.forName("' + screenshot + '").getMethod("'
        + mappings.member("net/minecraft/client/Screenshot", "takeScreenshot")
        + '", Class.forName("' + target + '")).invoke(null, target);\n'
        '            byte[] result;\n'
        '            try { result = (byte[]) image.getClass().getMethod("'
        + mappings.member("com/mojang/blaze3d/platform/NativeImage", "asByteArray")
        + '").invoke(image); }\n'
        '            finally { ((AutoCloseable) image).close(); }'
    )
    source = replace_once(source, "byte[] result = ReflectionHelper.takeScreenshot(mc, w, h);", capture)
    start = source.index("    @Override\n    public String executeCommand(String command) {")
    end = source.index("    @Override\n    public String getPlayerInfo()", start)
    source = source[:start] + (
        '    @Override\n    public String executeCommand(String command) {\n'
        '        return "{\\"error\\":\\"execute_command disabled in public bridge\\"}";\n'
        '    }\n\n'
    ) + source[end:]
    return source


def hardened_http(source):
    for route, handler in (("events", "EventHandler"), ("calls", "CallsHandler"),
                           ("debug", "StaticHandler")):
        source = replace_once(source,
                              '        addAuthenticatedContext("/api/' + route + '", new '
                              + handler + '());\n' if route != "debug" else
                              '        addAuthenticatedContext("/debug", new StaticHandler());\n', "")
    source = replace_once(source, '        addAuthenticatedContext("/", new RootHandler());\n', "")
    anchor = '                ev.method = cmd;\n'
    check = (
        '                if (!java.util.Arrays.asList("get_world_info", "get_player_info",\n'
        '                        "get_screen_buttons", "press_key", "click",\n'
        '                        "click_button_index", "use_item", "enter_control_mode",\n'
        '                        "exit_control_mode").contains(cmd)) {\n'
        '                    return "{\\"error\\":\\"command is not in public allowlist\\"}";\n'
        '                }\n'
    )
    source = replace_once(source, anchor, anchor + check)
    source = replace_once(source, '                ev.params = body;\n',
                          '                validatePublicRequest(jo, cmd);\n'
                          '                ev.params = body;\n')
    validator = r'''        private void validatePublicRequest(com.google.gson.JsonObject jo, String cmd) {
            if (jo == null || !jo.has("cmd") || jo.has("method") || jo.size() > 2
                    || (jo.has("params") && !jo.get("params").isJsonObject())) {
                throw new IllegalArgumentException("invalid public request envelope");
            }
            com.google.gson.JsonObject params = jo.has("params")
                    ? jo.getAsJsonObject("params") : new com.google.gson.JsonObject();
            for (java.util.Map.Entry<String, com.google.gson.JsonElement> entry : params.entrySet()) {
                if (!entry.getValue().isJsonPrimitive()) {
                    throw new IllegalArgumentException("public parameter must be scalar");
                }
            }
            if (java.util.Arrays.asList("get_world_info", "get_player_info",
                    "get_screen_buttons", "use_item", "enter_control_mode",
                    "exit_control_mode").contains(cmd)) {
                if (params.size() != 0) throw new IllegalArgumentException("unexpected public parameter");
            } else if ("press_key".equals(cmd)) {
                if (params.size() != 1 || !params.has("key")
                        || !java.util.Arrays.asList("Enter", "Escape", "E", "Tab")
                            .contains(params.get("key").getAsString())) {
                    throw new IllegalArgumentException("key is outside public allowlist");
                }
            } else if ("click_button_index".equals(cmd)) {
                if (params.size() != 1 || !params.has("index")) {
                    throw new IllegalArgumentException("invalid button index");
                }
                requireBoundedInteger(params.get("index"), 0, 20);
            } else if ("click".equals(cmd)) {
                if (params.size() != 2 || !params.has("x") || !params.has("y")) {
                    throw new IllegalArgumentException("invalid click coordinates");
                }
                requireBoundedInteger(params.get("x"), 0, 8191);
                requireBoundedInteger(params.get("y"), 0, 8191);
            }
        }

        private void requireBoundedInteger(com.google.gson.JsonElement value, int minimum, int maximum) {
            if (!value.getAsJsonPrimitive().isNumber()
                    || !value.getAsString().matches("[0-9]{1,4}")) {
                throw new IllegalArgumentException("numeric parameter is invalid");
            }
            int number = Integer.parseInt(value.getAsString());
            if (number < minimum || number > maximum) {
                throw new IllegalArgumentException("numeric parameter is out of bounds");
            }
        }

'''.replace('\\"', '"')
    source = replace_once(source, '        private String dispatchCmd(String body, CallEvent ev) {\n',
                          validator + '        private String dispatchCmd(String body, CallEvent ev) {\n')
    source = replace_once(source,
                          '    private static String readBody(HttpExchange exchange) throws IOException {\n'
                          '        InputStream is = exchange.getRequestBody();\n'
                          '        ByteArrayOutputStream baos = new ByteArrayOutputStream();\n'
                          '        byte[] buf = new byte[4096];\n'
                          '        int n;\n'
                          '        while ((n = is.read(buf)) != -1) baos.write(buf, 0, n);',
                          '    private static String readBody(HttpExchange exchange) throws IOException {\n'
                          '        InputStream is = exchange.getRequestBody();\n'
                          '        ByteArrayOutputStream baos = new ByteArrayOutputStream();\n'
                          '        byte[] buf = new byte[4096];\n'
                          '        int n;\n'
                          '        while ((n = is.read(buf)) != -1) {\n'
                          '            if (baos.size() + n > 16384) throw new IOException("request too large");\n'
                          '            baos.write(buf, 0, n);\n'
                          '        }')
    return source


def build(args):
    upstream = Path(args.upstream).resolve(strict=True)
    gson = Path(args.gson).resolve(strict=True)
    mapping_file = Path(args.mappings).resolve(strict=True)
    jdk_bin = Path(args.jdk_bin).resolve(strict=True)
    output = Path(args.output).absolute()
    work = Path(args.work).absolute()
    if work.exists() or output.exists():
        raise ValueError("build work and output must be fresh paths")
    if output.is_relative_to(work) or work.is_relative_to(output):
        raise ValueError("output and work must be separate")
    mappings = Tiny(mapping_file)
    alpha = output.with_name(output.stem + ".alpha.jar")
    if alpha.exists():
        raise ValueError("alpha output already exists")
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        raise ValueError("PowerShell is required to run the pinned upstream hardening stage")
    subprocess.run([shell, "-NoProfile", "-File", str(ROOT / "scripts/harden-bridge.ps1"),
                    "-UpstreamJar", str(upstream), "-GsonJar", str(gson),
                    "-OutputJar", str(alpha), "-WorkDirectory", str(work),
                    "-JdkBin", str(jdk_bin)], check=True, stdout=subprocess.DEVNULL)
    source_root = work / SOURCE_DIR
    sources = []
    for name, expected in SOURCE_SHA256.items():
        path = source_root / name
        if digest(path) != expected:
            raise ValueError("pinned hardened source changed: " + name)
        text = path.read_text(encoding="utf-8")
        transformed = hardened_http(text) if name == "McpHttpServer.java" else mapped_input(text, mappings)
        path.write_text(transformed, encoding="utf-8")
        sources.append(path)
    classes = work / "packaged-classes"
    classes.mkdir()
    javac = jdk_bin / "javac.exe"
    jar = jdk_bin / "jar.exe"
    subprocess.run([str(javac), "-J-Xmx256m", "--release", "8", "-proc:none", "-cp",
                    str(alpha) + ";" + str(gson), "-d", str(classes), *map(str, sources)], check=True)
    shutil.copy2(alpha, output)
    subprocess.run([str(jar), "uf", str(output), "-C", str(classes),
                    "xyz/langyo/minecraft/mcp/common"], check=True)
    with zipfile.ZipFile(output) as archive:
        for name in ("McpHttpServer", "ReflectedInputHandler"):
            if not archive.read("xyz/langyo/minecraft/mcp/common/" + name + ".class"):
                raise ValueError("packaged class missing from derivative")
    return digest(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("upstream", "gson", "mappings", "jdk-bin", "output", "work"):
        parser.add_argument("--" + name, required=True)
    try:
        print("Public packaged bridge SHA-256: " + build(parser.parse_args()))
    except (OSError, ValueError, subprocess.CalledProcessError, zipfile.BadZipFile) as exc:
        print("Packaged bridge build failed: " + str(exc), file=sys.stderr)
        sys.exit(1)
