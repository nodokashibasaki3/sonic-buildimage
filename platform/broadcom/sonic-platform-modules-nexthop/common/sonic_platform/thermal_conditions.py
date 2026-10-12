#!/usr/bin/env python

# Copyright 2025 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Thermal policy conditions for this platform.

The shared presence condition takes its count and comparison from the policy file, so the
per-count classes this module used to define are expressed there instead.
"""

from sonic_platform_base.sonic_thermal_control.common_conditions import (  # noqa: F401
    DefaultCondition,
    FanDrawerPresenceCondition,
    FanPresenceCondition,
    PsuPresenceCondition,
    ThermalOverThresholdCondition,
)
