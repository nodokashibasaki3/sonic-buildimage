#!/usr/bin/env bash
#
# run-selftest.sh - boot a prebuilt SONiC bring-up guest under QEMU with the
# emulated xiic-fpga-i2c device attached, and assert that the real SONiC
# multifpgapci / i2c-xiic driver stack reads an emulated I2C EEPROM + temp
# sensor through it. Prints the guest self-test summary and exits 0 on PASS.
#
# This exercises the QEMU device change (patches/qemu/) WITHOUT building or
# running a full SONiC image: the guest kernel + initramfs + drivers are
# prebuilt fixtures (test/fixtures/), so CI only needs to (re)build QEMU.
#
# Usage:
#   run-selftest.sh                 # build QEMU from $QEMU_SRC, then test
#   QEMU_BIN=/path/qemu-system-x86_64 run-selftest.sh    # use an existing build
#
# Environment overrides:
#   QEMU_BIN   prebuilt qemu-system-x86_64 to use (skips the build step)
#   QEMU_SRC   QEMU git checkout to patch + build (default: ./qemu, else clone)
#   QEMU_REF   git ref to check out before patching (default: v11.1.0-rc1)
#   KERNEL     guest kernel   (default: test/fixtures/vmlinuz-sonic-amd64)
#   INITRD     guest initramfs(default: test/fixtures/initramfs.cpio.gz)
#   EEPROM     eeprom image   (default: test/fixtures/eeprom0.bin)
#   TIMEOUT    guest boot timeout seconds (default: 150)
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLDIR="$(cd "$HERE/.." && pwd)"
FIX="$HERE/fixtures"
PATCHDIR="$TOOLDIR/patches/qemu"

QEMU_BIN="${QEMU_BIN:-}"
QEMU_SRC="${QEMU_SRC:-$HERE/qemu}"
QEMU_REF="${QEMU_REF:-v11.1.0-rc1}"
KERNEL="${KERNEL:-$FIX/vmlinuz-sonic-amd64}"
INITRD="${INITRD:-$FIX/initramfs.cpio.gz}"
EEPROM="${EEPROM:-$FIX/eeprom0.bin}"
TIMEOUT="${TIMEOUT:-150}"

log() { printf '>>> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 2; }

# --- obtain a QEMU binary that has the xiic-fpga-i2c device -----------------
build_qemu() {
  command -v git >/dev/null    || die "git required to build QEMU"
  command -v ninja >/dev/null  || die "ninja required to build QEMU"
  [ -d "$PATCHDIR" ]          || die "missing patch dir: $PATCHDIR"

  if [ ! -e "$QEMU_SRC/.git" ]; then
    log "cloning QEMU ($QEMU_REF) into $QEMU_SRC"
    git clone --depth 1 --branch "$QEMU_REF" \
      https://gitlab.com/qemu-project/qemu.git "$QEMU_SRC"
  fi

  log "applying QEMU patches from $PATCHDIR"
  shopt -s nullglob
  for p in "$PATCHDIR"/*.patch; do
    if git -C "$QEMU_SRC" apply --check "$p" 2>/dev/null; then
      git -C "$QEMU_SRC" apply --3way "$p" || git -C "$QEMU_SRC" apply "$p"
      log "applied $(basename "$p")"
    elif git -C "$QEMU_SRC" apply --check -R "$p" 2>/dev/null; then
      log "$(basename "$p") already applied - skipping"
    else
      # context drift vs $QEMU_REF: fall back to a 3-way merge
      git -C "$QEMU_SRC" apply --3way "$p"
      log "applied (3-way) $(basename "$p")"
    fi
  done

  if [ ! -d "$QEMU_SRC/build" ]; then
    log "configuring QEMU (x86_64-softmmu)"
    ( cd "$QEMU_SRC" && ./configure --target-list=x86_64-softmmu \
        --disable-docs --disable-werror )
  fi
  log "building qemu-system-x86_64 (this is the slow step)"
  ninja -C "$QEMU_SRC/build" qemu-system-x86_64
  QEMU_BIN="$QEMU_SRC/build/qemu-system-x86_64"
}

if [ -z "$QEMU_BIN" ]; then
  build_qemu
fi
[ -x "$QEMU_BIN" ] || die "qemu binary not found/executable: $QEMU_BIN"
"$QEMU_BIN" -device help 2>/dev/null | grep -q '"xiic-fpga-i2c"' \
  || die "$QEMU_BIN does not include the xiic-fpga-i2c device (patch not applied?)"

for f in "$KERNEL" "$INITRD" "$EEPROM"; do
  [ -f "$f" ] || die "missing fixture: $f"
done

# --- boot the guest ----------------------------------------------------------
# Writable scratch copy of the EEPROM so the committed fixture stays pristine.
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cp "$EEPROM" "$WORK/eeprom.bin"
LOG="$WORK/console.log"
QMP="$WORK/qmp.sock"

log "booting bring-up guest under $QEMU_BIN (timeout ${TIMEOUT}s)"
echo "----------------------------------------------------------------------"

# Best-effort: once QMP is up, set a known live temperature on the emulated
# tmp421 (its reset() zeroes the value). Safe to fail - the guest still reads a
# valid default otherwise.
(
  for _ in $(seq 1 "$((TIMEOUT * 5))"); do [ -S "$QMP" ] && break; sleep 0.2; done
  python3 - "$QMP" <<'PY' 2>/dev/null || true
import socket, sys, json
s = socket.socket(socket.AF_UNIX)
try: s.connect(sys.argv[1])
except OSError: sys.exit(0)
f = s.makefile('rwb', buffering=0); f.readline()
def cmd(o): f.write((json.dumps(o)+"\n").encode()); f.readline()
cmd({"execute": "qmp_capabilities"})
cmd({"execute": "qom-set", "arguments": {
     "path": "/machine/peripheral/temp0",
     "property": "temperature0", "value": 42000}})
PY
) &

timeout "$TIMEOUT" "$QEMU_BIN" -M pc -cpu max -m 512 \
  -kernel "$KERNEL" -initrd "$INITRD" \
  -append "console=ttyS0 rdinit=/init panic=1 loglevel=3" \
  -device xiic-fpga-i2c,num-channels=4 \
  -drive if=none,id=ee,file="$WORK/eeprom.bin",format=raw \
  -device at24c-eeprom,bus=xiic-fpga-i2c.0,address=0x50,rom-size=8192,address-size=2,drive=ee \
  -device tmp421,bus=xiic-fpga-i2c.0,address=0x4c,id=temp0 \
  -display none -serial stdio -monitor none \
  -qmp "unix:$QMP,server,nowait" \
  < /dev/null 2>/dev/null | tee "$LOG" || true

echo "----------------------------------------------------------------------"

# --- verdict -----------------------------------------------------------------
if grep -q "RESULT: PASS" "$LOG"; then
  log "SELF-TEST PASSED"
  exit 0
fi
log "SELF-TEST FAILED (no 'RESULT: PASS' in guest console)"
exit 1
