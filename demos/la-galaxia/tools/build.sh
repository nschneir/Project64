#!/bin/sh
# build.sh -- assemble La Galaxia and load it into a session.
#
# `c64 run` does not accept --area, and this program needs it (the engine is
# linked at $4000 and the fill from $080D up is what blanks the charset and
# sprite areas before startup writes the art).  So the cycle is two commands:
# build with the area, then load the .prg with its label file.
#
#   tools/build.sh              build + load into session "dbg"
#   tools/build.sh lg           build + load into session "lg"
#   tools/build.sh --build-only just assemble
set -e

root=$(cd "$(dirname "$0")/../../.." && pwd)
dir="$root/demos/la-galaxia"
c64="$root/.venv/bin/c64"

"$c64" build "$dir/la-galaxia.s" --area 'ENGINE=$4000:$6000'

if [ "$1" = "--build-only" ]; then
    exit 0
fi

sess=${1:-dbg}
"$c64" load "$dir/la-galaxia.prg" --symbols "$dir/la-galaxia.lbl" -s "$sess"
