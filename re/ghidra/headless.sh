#!/bin/sh
# Headless Ghidra on our Zeus.exe project. Usage: re/ghidra/headless.sh [analyzeHeadless args...]
set -eu
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home}"
export XDG_CONFIG_HOME="$ROOT/re/ghidra/.config" XDG_CACHE_HOME="$ROOT/re/ghidra/.cache"
exec /opt/homebrew/opt/ghidra/libexec/support/analyzeHeadless "$ROOT/re/ghidra/projects" zeus \
  -scriptPath "$ROOT/re/ghidra/scripts" "$@"
