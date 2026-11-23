#!/bin/sh
# Migration-only (ADR 0017, Task 2.5): raw copy of one retained volume between two block devices.
# Rendered into ConfigMap migrate-<id> by migrate_volume.py; deleted in Task 5.9.
#   copy_volume.sh forward|reverse <inventory size bytes>
#   copy_volume.sh gate <id>   (reverse source gate: read-only e2fsck of the source)
set -eu
SRC=${MIGRATE_SRC:-/dev/migrate-src} # the env override exists for the loop-device test only
DST=${MIGRATE_DST:-/dev/migrate-dst}
CHUNK=4194304

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }
die() {
  log "refused: $*"
  exit 1
}

mode=${1:-}
case $mode in
  gate)
    id=${2:?usage: copy_volume.sh gate <id>}
    log "gate: e2fsck -fn $SRC"
    rc=0
    e2fsck -fn "$SRC" || rc=$?
    [ "$rc" -eq 0 ] || die "e2fsck -fn exit $rc"
    echo "gate-fsck-ok $id"
    exit 0
    ;;
  held)
    # Internal: runs as the child of the exclusive-open holder below, so both devices stay O_EXCL throughout.
    [ "${MIGRATE_HELD:-}" = 1 ] || die "held is internal to the holder below"
    S=$2
    log "dd $SRC -> $DST, $((S / CHUNK)) x 4M"
    dd if="$SRC" of="$DST" bs=4M count=$((S / CHUNK)) iflag=direct oflag=direct conv=fsync
    log "cmp -n $S"
    cmp -n "$S" "$SRC" "$DST"
    exit 0
    ;;
  forward | reverse) want=${2:?usage: copy_volume.sh forward|reverse <bytes>} ;;
  *) die "usage: copy_volume.sh forward|reverse <bytes> | gate <id>" ;;
esac

S=$(blockdev --getsize64 "$SRC")
T=$(blockdev --getsize64 "$DST")
log "$mode: source $S bytes, target $T bytes, inventory $want bytes"
[ "$T" -ge "$S" ] || die "T < S ($T < $S)"
[ $((S % CHUNK)) -eq 0 ] || die "source size $S is not a multiple of 4MiB"
if [ "$mode" = reverse ] && [ "$T" -ne "$S" ]; then
  die "reverse needs T == S ($T != $S)"
fi

log "holding O_EXCL on $SRC and $DST for dd and cmp"
python3 -c '
import os, subprocess, sys
os.environ["MIGRATE_HELD"] = "1"
fds = [os.open(p, os.O_RDONLY | os.O_EXCL) for p in sys.argv[1:3]]
sys.exit(subprocess.call(sys.argv[3:]))
' "$SRC" "$DST" sh "$0" held "$S"
log "hold released"

if [ "$mode" = forward ]; then
  log "e2fsck -fp $DST"
  rc=0
  e2fsck -fp "$DST" || rc=$?
  [ "$rc" -eq 0 ] || die "e2fsck -fp exit $rc (1 means the copy differs from a clean filesystem: Ben's call)"
  log "tune2fs -O mmp -E mmp_update_interval=5 -e remount-ro $DST"
  tune2fs -O mmp -E mmp_update_interval=5 -e remount-ro "$DST"
  log "dumpe2fs -h $DST"
  info=$(dumpe2fs -h "$DST" 2>/dev/null)
  echo "$info" | grep -Eq '^Filesystem features:.*\bmmp\b' || die "mmp feature not set"
  echo "$info" | grep -Eq '^Errors behavior:[[:space:]]+Remount read-only$' || die "errors behaviour not remount-ro"
  echo "$info" | grep -Eq '^MMP update interval:[[:space:]]+5$' || die "MMP update interval not 5"
  if [ "$want" -gt "$S" ]; then
    log "resize2fs $DST"
    resize2fs "$DST"
    info=$(dumpe2fs -h "$DST" 2>/dev/null)
    count=$(echo "$info" | sed -n 's/^Block count:[[:space:]]*//p')
    bsize=$(echo "$info" | sed -n 's/^Block size:[[:space:]]*//p')
    [ $((count * bsize)) -eq "$T" ] || die "filesystem is $((count * bsize)) bytes after resize2fs, device is $T"
  fi
fi

echo "copy-ok $mode $S $T"
