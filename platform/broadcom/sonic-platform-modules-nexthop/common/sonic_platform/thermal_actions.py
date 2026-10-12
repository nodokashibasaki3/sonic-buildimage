#!/usr/bin/env python

# Copyright 2025 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Thermal policy actions for this platform.

PID gains, fan limits and setpoints come from thermal_config.json in the device directory
rather than from the policy file.
"""

from sonic_platform_base.sonic_thermal_control.common_actions import (  # noqa: F401
    FanControlError,
    SetFanSpeedAction,
    SetMaxFanSpeedAction,
    ThermalControlAlgorithmAction,
    set_all_fan_speeds,
)
