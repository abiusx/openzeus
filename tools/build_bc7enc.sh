#!/bin/sh
# Build bc7enc_rdo's command-line tool with bc7e.ispc (all BC7 modes) for tools/hires_compress.py (BC7 copies of
# the play-mode sheets; docs/play/hires.md "Reproduce from scratch"). Output: .cache/bc7enc/bc7e (git-ignored).
#   sh tools/build_bc7enc.sh
# Needs git, curl, a C++17 compiler (Apple clang 17.0.0 used). Downloads (pinned):
#   bc7enc_rdo  https://github.com/richgel999/bc7enc_rdo  commit b9438627eef73a1157e84201b6fa6eb2ffd6d9f0
#   ISPC 1.32.0 https://github.com/ispc/ispc/releases/download/v1.32.0/ispc-v1.32.0-macOS.arm64.tar.gz
#               sha256 efc5180095554628c01022507329ba7a2141c7ba97cf1bccc2df85dc47874e02
#               (Linux/Windows: the matching archive of the same release, and an x86 --target such as avx2-i32x8)
# No OpenMP: with libomp the encoder spent minutes per sheet spinning on 10 cores; hires_compress.py runs one
# single-threaded process per core instead.
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=$ROOT/.cache/bc7enc
COMMIT=b9438627eef73a1157e84201b6fa6eb2ffd6d9f0
ISPC_URL=https://github.com/ispc/ispc/releases/download/v1.32.0/ispc-v1.32.0-macOS.arm64.tar.gz
ISPC_SHA=efc5180095554628c01022507329ba7a2141c7ba97cf1bccc2df85dc47874e02
TARGET=${ISPC_TARGET:-neon-i32x8}
mkdir -p "$OUT" && cd "$OUT"
[ -d src ] || git clone -q https://github.com/richgel999/bc7enc_rdo.git src
git -C src checkout -q $COMMIT
if [ ! -x ispc/bin/ispc ]; then
  curl -sL -o ispc.tgz "$ISPC_URL"
  echo "$ISPC_SHA  ispc.tgz" | shasum -a 256 -c -
  mkdir -p ispc && tar xzf ispc.tgz -C ispc --strip-components 1 && rm ispc.tgz
fi
ispc/bin/ispc -O2 src/bc7e.ispc -o bc7e.o -h bc7e_ispc.h --target=$TARGET --opt=fast-math --opt=disable-assertions 2>/dev/null
cd src
c++ -O3 -std=c++17 -fno-strict-aliasing -w -DSUPPORT_BC7E=1 -I"$OUT" bc7enc.cpp bc7decomp.cpp bc7decomp_ref.cpp \
    lodepng.cpp test.cpp rgbcx.cpp utils.cpp ert.cpp rdo_bc_encoder.cpp "$OUT/bc7e.o" -o "$OUT/bc7e"
echo "$OUT/bc7e"
