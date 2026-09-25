#!/usr/bin/env bash
# Build the Linux Game Bench GUI AppImage (x86_64) from the COMMITTED client (git HEAD).
#
#   packaging/appimage/build_appimage.sh            -> dist/LinuxGameBench-x86_64.AppImage (+ .sha256)
#
# Layout (same as the AppImage offered since 2026-08-23):
#   AppDir/usr            python-build-standalone CPython 3.12 (relocatable, no system Python needed)
#   AppDir/usr/lib/python3.12/site-packages   client + dependencies + PySide6-Essentials
#   AppDir/AppRun         starts linux_game_benchmark.gui.launch()
#
# Pinned downloads are cached in ~/.cache/lgb-appimage-build and checked against SHA256.
# Uncommitted changes in the work tree are NOT included (git archive HEAD).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
CACHE="${LGB_APPIMAGE_CACHE:-$HOME/.cache/lgb-appimage-build}"
WORK="${WORK:-$REPO/build/appimage}"
OUT="${OUT:-$REPO/dist}"

PBS_TAG="20260924"
PBS_FILE="cpython-3.12.14+${PBS_TAG}-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
PBS_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/${PBS_FILE}"
PBS_SHA256="269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41"   # = official SHA256SUMS

TOOL_FILE="appimagetool-1.9.1-x86_64.AppImage"
TOOL_URL="https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage"
TOOL_SHA256="ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"  # pinned 2026-09-25 (no official sum)

# Same Qt as the 2026-08-23 AppImage (Essentials only: the GUI needs no Qt add-ons)
PYSIDE="PySide6-Essentials==6.7.3"

fetch() {  # url file sha256
    local url="$1" file="$CACHE/$2" sha="$3"
    mkdir -p "$CACHE"
    if [ ! -f "$file" ]; then
        echo "download $2"
        curl -sSfL -o "$file.part" "$url"
        mv "$file.part" "$file"
    fi
    echo "$sha  $file" | sha256sum -c --quiet - || { echo "SHA256 mismatch: $file" >&2; exit 1; }
}

cd "$REPO"
VERSION="$(git show HEAD:pyproject.toml | sed -n 's/^version = "\(.*\)"/\1/p' | head -1)"
SETTINGS_VERSION="$(git show HEAD:src/linux_game_benchmark/config/settings.py | sed -n 's/.*CLIENT_VERSION = "\(.*\)"/\1/p' | head -1)"
[ "$VERSION" = "$SETTINGS_VERSION" ] || { echo "version mismatch: pyproject $VERSION vs settings.py $SETTINGS_VERSION" >&2; exit 1; }
git show HEAD:src/linux_game_benchmark/config/settings.py | grep -q 'return "prod"' || { echo "default stage is not prod" >&2; exit 1; }
COMMIT="$(git rev-parse --short HEAD)"
echo "== Linux Game Bench $VERSION ($COMMIT)"

fetch "$PBS_URL" "$PBS_FILE" "$PBS_SHA256"
fetch "$TOOL_URL" "$TOOL_FILE" "$TOOL_SHA256"
chmod +x "$CACHE/$TOOL_FILE"

rm -rf "$WORK"
mkdir -p "$WORK/src" "$WORK/AppDir/usr" "$OUT"
git archive HEAD | tar -x -C "$WORK/src"

# Relocatable CPython -> AppDir/usr
tar -xzf "$CACHE/$PBS_FILE" -C "$WORK"
cp -a "$WORK/python/." "$WORK/AppDir/usr/"
rm -rf "$WORK/python"
PY="$WORK/AppDir/usr/bin/python3"

# Client + dependencies + Qt
"$PY" -m pip install --no-cache-dir --disable-pip-version-check --no-warn-script-location -q \
    "$WORK/src" "$PYSIDE"

# Slim down: pip itself, bytecode caches, test suites, headers/static libs
"$PY" -m pip uninstall -y -q pip
find "$WORK/AppDir/usr" -name "__pycache__" -type d -prune -exec rm -rf {} +
rm -rf "$WORK/AppDir/usr/lib/python3.12/test" "$WORK/AppDir/usr/lib/python3.12/idlelib/idle_test" \
       "$WORK/AppDir/usr/lib/python3.12/site-packages/pandas/tests" \
       "$WORK/AppDir/usr/lib/python3.12/site-packages/numpy/"*"/tests" \
       "$WORK/AppDir/usr/include" "$WORK/AppDir/usr/lib/"*.a
# Entry scripts written by pip point at the build path; the AppImage only uses AppRun
rm -f "$WORK/AppDir/usr/bin/lgb" "$WORK/AppDir/usr/bin/lgb-gui" "$WORK/AppDir/usr/bin/linux-game-benchmark"

# Sanity check with the bundled interpreter (no system Python involved)
"$PY" - "$VERSION" <<'EOF'
import sys
import linux_game_benchmark.gui  # noqa: F401  (GUI package + PySide6 import)
from linux_game_benchmark.config.settings import settings
from linux_game_benchmark.gui.update_info import update_instructions
assert settings.CLIENT_VERSION == sys.argv[1], (settings.CLIENT_VERSION, sys.argv[1])
assert update_instructions("https://linuxgamebench.com/api/v1", {"APPIMAGE": "/x.AppImage"}).kind == "appimage"
print("bundle ok:", settings.CLIENT_VERSION)
EOF

install -m 755 "$HERE/AppRun" "$WORK/AppDir/AppRun"
install -m 644 "$HERE/linuxgamebench.desktop" "$WORK/AppDir/linuxgamebench.desktop"
install -m 644 "$REPO/src/linux_game_benchmark/gui/icons/lgb.png" "$WORK/AppDir/linuxgamebench.png"
ln -sf linuxgamebench.png "$WORK/AppDir/.DirIcon"

TARGET="$OUT/LinuxGameBench-x86_64.AppImage"
rm -f "$TARGET"
ARCH=x86_64 "$CACHE/$TOOL_FILE" --appimage-extract-and-run --no-appstream "$WORK/AppDir" "$TARGET" >/dev/null
( cd "$OUT" && sha256sum "$(basename "$TARGET")" > "$(basename "$TARGET").sha256" )
echo "== built $TARGET ($(du -h "$TARGET" | cut -f1)), version $VERSION, commit $COMMIT"
cat "$TARGET.sha256"
