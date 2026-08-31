# xiic-fpga-i2c — QEMU emulation of a PCIe FPGA I2C controller

These are **QEMU device models** (they compile *into* QEMU; not kernel code)
that let you exercise the SONiC `multifpgapci` / `i2c-xiic` software stack
**without real switch hardware**: a guest kernel probes a fake PCI card, binds
`i2c-xiic` to each channel, and talks to emulated I2C slaves (EEPROMs,
temperature sensors, muxes …).

## Two devices (the model is split)

| Device | Type | Purpose | Upstreaming |
|--------|------|---------|-------------|
| `xlnx-axi-iic` | SysBus | A generic AMD/Xilinx AXI IIC controller (LogiCORE PG090). Owns one I2C bus, drives a single **level** interrupt line. Driven by the in-tree Linux `i2c-xiic` driver. | Target for upstream — real, documented hardware with an in-tree consumer. |
| `xiic-fpga-i2c` | PCIe | A PCIe function that embeds N `xlnx-axi-iic` cores, maps them into BAR0, and adds the interrupt aggregator that demuxes all channels onto one **MSI** vector (with INTx fallback). | Test/downstream device — its aggregator matches the out-of-tree `multifpgapci` driver, not a datasheet. |

The register map, transfer encoding and interrupt behavior of the core are
documented upstream in QEMU at `docs/specs/xlnx-axi-iic.rst`.

## Interrupt model

Each `xlnx-axi-iic` core asserts a level line while `DGIER` is enabled and
`IISR & IIER` is non-zero. The `xiic-fpga-i2c` wrapper records each channel's
line as a bit in a top-level status register (bit N == channel N), and fires a
single MSI vector (`irq-msi-vector`, default 0) while any unmasked bit is set —
the level-to-edge translation the guest's `regmap-irq` chip expects. When MSI is
disabled it drives INTx to the OR of all channels instead. The guest acks by
writing the status register, which re-arms delivery.

## Layout

```
tools/pddf-qemu-emu/
  xiic_fpga_i2c.c              reference copy of the PCIe wrapper model
  patches/qemu/                RFC patch series (see below)
  test/
    run-selftest.sh            build QEMU from the patches + boot a guest, assert PASS
    fixtures/                  prebuilt SONiC kernel + initramfs + eeprom image
```

In the QEMU tree the split lives in:

```
hw/i2c/xlnx-axi-iic.c              the generic AXI IIC core
include/hw/i2c/xlnx-axi-iic.h
docs/specs/xlnx-axi-iic.rst        register-level spec
tests/qtest/xiic-fpga-i2c-test.c   qtest (drives BAR0 -> core -> tmp105 slave)
hw/misc/xiic_fpga_i2c.c            the PCIe wrapper
```

## Building

```sh
cd <qemu>
# apply the RFC series (core patch, then wrapper patch)
./configure --target-list=x86_64-softmmu
ninja -C build qemu-system-x86_64
```

`CONFIG_XIIC_FPGA_I2C` (`default y if TEST_DEVICES`, `depends on PCI &&
MSI_NONBROKEN`) selects `CONFIG_XLNX_AXI_IIC`.

## Self-test / CI

`test/run-selftest.sh` exercises the change end-to-end **without building a full
SONiC image** — the guest kernel, initramfs and drivers are prebuilt fixtures,
so only QEMU is (re)built:

```sh
tools/pddf-qemu-emu/test/run-selftest.sh
QEMU_BIN=/path/to/qemu-system-x86_64 tools/pddf-qemu-emu/test/run-selftest.sh
```

The guest boots under TCG (no KVM needed). There is also a QEMU qtest
(`tests/qtest/xiic-fpga-i2c-test.c`): `meson test -C build xiic-fpga-i2c-test`.

## Usage

```sh
qemu-system-x86_64 \
  -device xiic-fpga-i2c,num-channels=4 \
  -device at24c-eeprom,bus=xiic-fpga-i2c.0,address=0x50
```

Each channel exposes its own bus named `xiic-fpga-i2c.<N>` (0-based); attach a
slave to a specific channel with `bus=xiic-fpga-i2c.<N>`.

### Device properties (`xiic-fpga-i2c`)

| Property | Default | Meaning |
|----------|---------|---------|
| `num-channels` | 4 | number of embedded AXI-IIC cores / I2C buses (max 32) |
| `ch-base-offset` | 0x0 | where channel 0's register window starts in BAR0 |
| `ch-stride` | 0x1000 | bytes between channel windows |
| `bar-size` | 0x8000 | BAR0 size (auto-grown, rounded up to a power of two) |
| `irq-status-offset` | 0x6000 | BAR offset of the per-channel status register |
| `irq-unmask-offset` | 0x6004 | BAR offset of the unmask register (must be status + 4) |
| `irq-msi-vector` | 0 | MSI vector the aggregator delivers on |

Match these to the platform's device JSON and `multifpgapci` configuration.
