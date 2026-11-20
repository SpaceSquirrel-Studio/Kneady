#!/usr/bin/env bash
# Kneady's checks on this computer - Linux (x86-64) or a Mac. No 3D
# knowledge needed: run it, wait, send the file it names at the end.
#
#     bash tests/platform_check.sh
#
# For each Blender version (4.2, 4.5, 5.2 and 5.3 unless KNEADY_VERSIONS says
# otherwise) it downloads the portable Blender from download.blender.org into
# ~/kneady-check (nothing is installed), runs Kneady's tests, then opens
# Blender windows for the checks that need a screen - a real mouse drag, undo,
# the Adjust Last Operation panel, screenshots. Those windows open and close by
# themselves; your own mouse and keyboard don't affect them. Leave them be.
#
#     KNEADY_VERSIONS="5.3" bash tests/platform_check.sh       just one version
#     BLENDER=/path/to/blender bash tests/platform_check.sh    a Blender you have
#     KNEADY_EXTRA="/path/to/addon" bash tests/platform_check.sh
#         also an add-on built on Kneady: its tests/run.py and window probes
#         (tests/probe_*.py); several folders go on separate lines, so a
#         folder's path may have spaces in it
#
# Downloads are kept in ~/kneady-check/blender for the next run; delete
# ~/kneady-check when done to free about 2 GB.

set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"
VERSIONS="${KNEADY_VERSIONS:-4.2 4.5 5.2 5.3}"
WORK="${KNEADY_WORK:-$HOME/kneady-check}"
STAMP="$(date +%Y%m%d-%H%M)"
HOST="$(hostname 2>/dev/null | tr -cd 'A-Za-z0-9_-')"
NAME="results-${HOST:-computer}-$STAMP"
OUT="$WORK/$NAME"
mkdir -p "$WORK/blender" "$OUT"
SUMMARY="$OUT/summary.txt"

say() { echo "$*" | tee -a "$SUMMARY"; }

# Kneady's tests import it by its folder's name; a download or a clone may
# have named the folder anything, so they reach it through a link called
# Kneady
PKG="$WORK/package"
mkdir -p "$PKG"
ln -sfn "$REPO" "$PKG/Kneady"
# the suites to run: Kneady, then each add-on built on it, under its folder's
# name. One folder per line: a folder's path may have spaces in it (a tester's
# "Kneady Tests" folder split in two, and nothing ran - 6 November 2026)
SUITES=("Kneady")
while IFS= read -r folder; do
    [ -n "$folder" ] || continue
    if [ ! -d "$folder" ]; then
        echo "Can't find the folder \"$folder\" (KNEADY_EXTRA)." >&2
        exit 1
    fi
    extra_name="$(basename "$folder")"
    ln -sfn "$(cd "$folder" && pwd)" "$PKG/$extra_name"
    SUITES+=("$extra_name")
done <<< "${KNEADY_EXTRA:-}"
# every suite's tests where they should be, before downloading anything
for suite in "${SUITES[@]}"; do
    if [ ! -f "$PKG/$suite/tests/run.py" ]; then
        echo "Can't find $suite's tests ($PKG/$suite/tests/run.py)." >&2
        echo "Please send Greg a screenshot of this window." >&2
        exit 1
    fi
done

# Runs a command for at most $1 seconds (macOS has no `timeout`)
run_for() {
    local secs="$1"; shift
    "$@" &
    local pid=$!
    ( sleep "$secs"; kill -9 "$pid" 2>/dev/null ) &
    local watch=$!
    wait "$pid"
    local rc=$?
    kill "$watch" 2>/dev/null
    wait "$watch" 2>/dev/null
    return $rc
}

OS="$(uname -s)"
ARCH="$(uname -m)"
PLAT=""
EXT=""
HAS_SCREEN=1
case "$OS" in
    Linux)
        if [ "$ARCH" = "x86_64" ]; then PLAT="linux-x64"; EXT="tar.xz"; fi
        HAS_SCREEN=""
        [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && HAS_SCREEN=1
        ;;
    Darwin)
        if [ "$ARCH" = "arm64" ]; then PLAT="macos-arm64"; else PLAT="macos-x64"; fi
        EXT="dmg"
        HAS_SCREEN=1
        ;;
esac

say "Kneady platform check, $(date)"
say "Kneady: $(cd "$REPO" && (git rev-parse --short HEAD 2>/dev/null || echo 'not a git checkout'))"
# a testers' bundle says which versions it holds
if [ -f "$(dirname "$REPO")/BUNDLE.txt" ]; then
    say "$(cat "$(dirname "$REPO")/BUNDLE.txt")"
fi
say "System: $(uname -a)"
if [ "$OS" = "Linux" ]; then
    say "Distribution: $( (. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME") || echo unknown)"
    say "Session: ${XDG_SESSION_TYPE:-unknown}, desktop: ${XDG_CURRENT_DESKTOP:-unknown}"
elif [ "$OS" = "Darwin" ]; then
    say "macOS: $(sw_vers -productVersion 2>/dev/null)"
fi
say ""

# The newest patch of a version for this computer, e.g. 4.2 -> 23
latest_patch() {
    local v_re
    v_re="$(echo "$1" | sed 's/\./\\./g')"
    curl -fsL --max-time 60 "https://download.blender.org/release/Blender$1/" \
        | grep -oE "blender-$v_re\.[0-9]+-$PLAT\.$EXT" \
        | sed -E "s/blender-$v_re\.([0-9]+)-.*/\1/" \
        | sort -n | tail -1
}

# Downloads a version once; prints the path of its blender program
fetch_blender() {
    local v="$1" patch name dir exe mnt
    patch="$(latest_patch "$v")"
    if [ -z "$patch" ]; then
        return 1
    fi
    name="blender-$v.$patch-$PLAT"
    dir="$WORK/blender/$name"
    if [ "$EXT" = "tar.xz" ]; then
        exe="$dir/blender"
        if [ ! -x "$exe" ]; then
            echo "Downloading $name ..." >&2
            curl -fL --progress-bar -o "$WORK/blender/$name.tar.xz" \
                "https://download.blender.org/release/Blender$v/$name.tar.xz" || return 1
            tar -xJf "$WORK/blender/$name.tar.xz" -C "$WORK/blender" || return 1
            rm -f "$WORK/blender/$name.tar.xz"
        fi
    else
        exe="$dir/Blender.app/Contents/MacOS/Blender"
        if [ ! -x "$exe" ]; then
            echo "Downloading $name ..." >&2
            curl -fL --progress-bar -o "$WORK/blender/$name.dmg" \
                "https://download.blender.org/release/Blender$v/$name.dmg" || return 1
            mnt="$(mktemp -d)"
            hdiutil attach -nobrowse -quiet -mountpoint "$mnt" "$WORK/blender/$name.dmg" || return 1
            mkdir -p "$dir"
            ditto "$mnt/Blender.app" "$dir/Blender.app"
            hdiutil detach -quiet "$mnt"
            rm -f "$WORK/blender/$name.dmg"
        fi
    fi
    echo "$exe"
}

# Python errors a run printed - a panel that failed to draw shows only there
errors_in() {
    local n
    n="$(grep -ac "Traceback (most recent call last)" "$1")"
    if [ "${n:-0}" -gt 0 ]; then
        say "   $n Python error(s) - see $(basename "$1")"
    fi
}

check_blender() {
    local label="$1" exe="$2" suite tests probe name log
    say "== Blender $label"
    for suite in "${SUITES[@]}"; do
        tests="$PKG/$suite/tests"
        say "-- $suite"
        log="$OUT/$label-$suite-tests.log"
        run_for 1800 "$exe" --background --factory-startup --python "$tests/run.py" > "$log" 2>&1
        grep -aE "^(FAIL|CRASH|SKIP)|passed" "$log" | tee -a "$SUMMARY"
        grep -aq "passed" "$log" || say "   the tests did not finish - see $(basename "$log")"
        if [ -z "$HAS_SCREEN" ]; then
            say "   no screen found (DISPLAY / WAYLAND_DISPLAY): window checks skipped"
            continue
        fi
        for probe in "$tests"/probe_*.py; do
            [ -f "$probe" ] || continue
            name="$(basename "$probe" .py)"
            log="$OUT/$label-$suite-$name.log"
            KNEADY_SHOTS="$OUT/screens-$label" run_for 300 "$exe" --factory-startup --enable-event-simulate \
                --window-geometry 120 160 1400 860 --python "$probe" > "$log" 2>&1
            grep -aE "^(PASS|FAIL|CRASH|INFO)" "$log" | tee -a "$SUMMARY"
            grep -aqE "^(PASS|FAIL|CRASH)" "$log" || say "   $name did not finish - see $(basename "$log")"
            errors_in "$log"
        done
    done
}

if [ -n "${BLENDER:-}" ]; then
    check_blender "own" "$BLENDER"
elif [ -z "$PLAT" ]; then
    say "No Blender download for $OS $ARCH: run with BLENDER=/path/to/blender"
else
    for v in $VERSIONS; do
        exe="$(fetch_blender "$v")"
        if [ -z "$exe" ] || [ ! -x "$exe" ]; then
            say "== Blender $v: no $PLAT download (or it failed) - skipped"
            continue
        fi
        check_blender "$v" "$exe"
    done
fi

say ""
say "Done, $(date)"
if (cd "$WORK" && tar -czf "$NAME.tar.gz" "$NAME"); then
    echo
    echo "Please send this file to Greg:"
    echo "    $WORK/$NAME.tar.gz"
else
    echo
    echo "Packing the results failed. Please send Greg the folder instead:"
    echo "    $OUT"
fi
