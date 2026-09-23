param(
    [Parameter(Mandatory = $true)][string]$UpstreamJar,
    [Parameter(Mandatory = $true)][string]$GsonJar,
    [Parameter(Mandatory = $true)][string]$OutputJar,
    [Parameter(Mandatory = $true)][string]$WorkDirectory,
    [Parameter(Mandatory = $true)][string]$JdkBin
)

$ErrorActionPreference = "Stop"
$sourceCommit = "50e059dccb09a9e23b91833ffdbf42efd97fa6e6"
$sourceHashes = @{
    "McpHttpServer.java" = "aa77bf3da9829a2e550d9a8e87118b3faa0c2145fffabe5561cd646b2cc442f5"
    "ReflectedInputHandler.java" = "0b661f61021315b478a9f756d387b82a64296f96947d46696129d881c37a186c"
    "ScreenshotHelper.java" = "90382b6bb0153c7461aa9799f7edf647771d14c3afbb48dc1a08a1668b901063"
}
$upstreamSha256 = "55aab04b1d7ac9203817e071cb83b6d6cf3da7164636867da33877750de64636"
$sourceRoot = "packages/common/src/main/java/xyz/langyo/minecraft/mcp/common"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$patches = @(
    (Join-Path $repoRoot "patches/minecraft-mod-mcp-v0.3.0-loopback-auth.patch"),
    (Join-Path $repoRoot "patches/minecraft-mod-mcp-v0.3.0-framebuffer.patch"),
    (Join-Path $repoRoot "patches/minecraft-mod-mcp-v0.3.0-dev-click.patch"),
    (Join-Path $repoRoot "patches/minecraft-mod-mcp-v0.3.0-dev-integration.patch")
)
$upstream = (Resolve-Path -LiteralPath $UpstreamJar).Path
$gson = (Resolve-Path -LiteralPath $GsonJar).Path
$work = [IO.Path]::GetFullPath($WorkDirectory)
$output = [IO.Path]::GetFullPath($OutputJar)

if ((Get-FileHash -Algorithm SHA256 -LiteralPath $upstream).Hash.ToLowerInvariant() -ne $upstreamSha256) {
    throw "Upstream JAR does not match pinned v0.3.0 release asset"
}
if (Test-Path -LiteralPath $work) { throw "WorkDirectory already exists; choose a new empty path" }
if (Test-Path -LiteralPath $output) { throw "OutputJar already exists; refusing overwrite" }
if ($output.StartsWith($work + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw "OutputJar must be outside WorkDirectory"
}

$jdk = (Resolve-Path -LiteralPath $JdkBin).Path
$javac = Join-Path $jdk "javac.exe"
$jar = Join-Path $jdk "jar.exe"
if (-not (Test-Path -LiteralPath $javac) -or -not (Test-Path -LiteralPath $jar)) {
    throw "JdkBin must contain both javac.exe and jar.exe"
}
$javaVersion = & $javac -version 2>&1
if ($LASTEXITCODE -ne 0) { throw "javac is unavailable" }
Write-Output "Compiler: $javaVersion (--release 8)"

New-Item -ItemType Directory -Path $work | Out-Null
$sourceDir = Join-Path $work $sourceRoot
New-Item -ItemType Directory -Path $sourceDir -Force | Out-Null
$sources = @()
foreach ($name in @("McpHttpServer.java", "ReflectedInputHandler.java", "ScreenshotHelper.java")) {
    $source = Join-Path $sourceDir $name
    $url = "https://raw.githubusercontent.com/langyo/minecraft-mod-mcp/$sourceCommit/$sourceRoot/$name"
    Invoke-WebRequest -Uri $url -OutFile $source
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash.ToLowerInvariant() -ne $sourceHashes[$name]) {
        throw "Pinned upstream source hash mismatch: $name"
    }
    $sources += $source
}

$env:GIT_CEILING_DIRECTORIES = $repoRoot
$insideRepo = & git -C $work rev-parse --is-inside-work-tree 2>$null
if ($LASTEXITCODE -eq 0 -and $insideRepo -eq "true") {
    throw "WorkDirectory must not be inside another Git working tree"
}
foreach ($patch in $patches) {
    & git -C $work apply --check $patch
    if ($LASTEXITCODE -ne 0) { throw "Patch does not apply to pinned source: $patch" }
    & git -C $work apply $patch
    if ($LASTEXITCODE -ne 0) { throw "Patch application failed: $patch" }
}

$classes = Join-Path $work "classes"
New-Item -ItemType Directory -Path $classes | Out-Null
& $javac --release 8 -cp "$upstream;$gson" -d $classes $sources
if ($LASTEXITCODE -ne 0) { throw "Patched source did not compile" }
Copy-Item -LiteralPath $upstream -Destination $output
& $jar uf $output -C $classes xyz/langyo/minecraft/mcp/common
if ($LASTEXITCODE -ne 0) { throw "JAR update failed" }

$digest = (Get-FileHash -Algorithm SHA256 -LiteralPath $output).Hash.ToLowerInvariant()
Write-Output "Upstream SHA-256: $upstreamSha256"
Write-Output "Hardened SHA-256: $digest"
Write-Output "Hardened JAR: $output"
Write-Output "Build files retained at: $work"
