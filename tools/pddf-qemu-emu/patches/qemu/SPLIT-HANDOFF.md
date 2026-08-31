# Hand-off: split + review fixes (uncommitted in the qemu11 tree)

The code changes are applied and verified in the QEMU working tree
(`~/qemu11`, branch `xiic-fpga-i2c-rfc`) but **not committed** — commit and
regenerate the patch series yourself.

`0001-hw-misc-add-xiic-fpga-i2c.patch` and `0002-enable-test-i2c-slaves.patch`
here are the **old monolithic** device and are superseded by the two commits
below. `0000-cover-letter.patch` has been rewritten for the split series.

## Changed / new files in the QEMU tree

New:
- `hw/i2c/xlnx-axi-iic.c`, `include/hw/i2c/xlnx-axi-iic.h`
- `docs/specs/xlnx-axi-iic.rst`
- `tests/qtest/xiic-fpga-i2c-test.c`

Modified:
- `hw/misc/xiic_fpga_i2c.c` (now the PCIe wrapper)
- `hw/i2c/meson.build`, `hw/i2c/Kconfig`
- `hw/misc/Kconfig`
- `docs/specs/index.rst`
- `tests/qtest/meson.build`
- `configs/devices/x86_64-softmmu/default.mak` (test slaves: AT24C/TMP105/TMP421)

## Suggested two commits

### Commit 1 — the generic controller (upstream target)
Files: `hw/i2c/xlnx-axi-iic.c`, `include/hw/i2c/xlnx-axi-iic.h`,
`hw/i2c/meson.build`, `hw/i2c/Kconfig`, `docs/specs/xlnx-axi-iic.rst`,
`docs/specs/index.rst`.

```
hw/i2c: add xlnx-axi-iic, a Xilinx AXI IIC controller

Add a model of the AMD/Xilinx AXI IIC controller (LogiCORE IP, PG090),
an I2C bus controller. QEMU has no AXI IIC model today; this lets a guest
driver for it, and the I2C slaves behind it, be exercised without real
hardware.

The device is a SysBus device: it owns one I2C bus, decodes the AXI IIC
register map, implements the controller's dynamic transfer mode, and
drives a single level-triggered interrupt line while DGIER is enabled and
IISR & IIER is set. It has a reset handler and migration state, and a
register-level specification in docs/specs/xlnx-axi-iic.rst.

Signed-off-by: Nodoka Shibasaki <nodokaorganized@gmail.com>
```

### Commit 2 — the PCIe carrier (TEST_DEVICES)
Files: `hw/misc/xiic_fpga_i2c.c`, `hw/misc/Kconfig`, `tests/qtest/xiic-fpga-i2c-test.c`,
`tests/qtest/meson.build`, `configs/devices/x86_64-softmmu/default.mak`.

```
hw/misc: add xiic-fpga-i2c, a PCIe FPGA embedding xlnx-axi-iic cores

Add a PCIe function that embeds N xlnx-axi-iic controllers, maps each
core's register window into BAR0, and adds a top-level interrupt block
that aggregates the per-channel level lines into a bit-per-channel status
register delivered on a single MSI vector (with a legacy INTx fallback),
performing the level-to-edge translation a guest driver expects.

The aggregator's register layout models a specific FPGA carrier rather
than a standardized controller, so the device is gated behind
CONFIG_XIIC_FPGA_I2C (default y if TEST_DEVICES). A qtest drives a
transfer through BAR0 to a tmp105 slave and checks register, transfer and
NACK behavior; the test slaves it needs are enabled in the x86_64-softmmu
test config.

Signed-off-by: Nodoka Shibasaki <nodokaorganized@gmail.com>
```

## Regenerate the series

```sh
cd ~/qemu11
git add -A && git commit    # commit 1 (stage only its files), then commit 2
git format-patch -2 --cover-letter -o /path/to/out
# then refresh 0000-cover-letter.patch from this dir's rewritten copy
```

## Verified before hand-off
- `ninja -C build qemu-system-x86_64` — clean.
- `tests/qtest/xiic-fpga-i2c-test.c` — passes.
- End-to-end `run-selftest.sh` / `run-demo.sh` — RESULT: PASS (EEPROM + tmp421).
- Migration stream of the device round-trips.
