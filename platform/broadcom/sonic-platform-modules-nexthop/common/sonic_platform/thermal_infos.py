#!/usr/bin/env python

# Copyright 2025 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Thermal policy info types for this platform.

These are the shared implementations; importing this module is what registers them. Add a
platform-specific type here only when the shared one cannot describe the hardware.
"""

from sonic_platform_base.sonic_thermal_control.common_infos import (  # noqa: F401
    ChassisInfo,
    FanDrawerInfo,
    FanInfo,
    PsuInfo,
    ThermalInfo,
)
