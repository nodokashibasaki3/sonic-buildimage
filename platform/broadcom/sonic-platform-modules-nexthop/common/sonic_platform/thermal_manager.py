#!/usr/bin/env python

# Copyright 2025 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import logging
import logging.handlers

from sonic_platform_base.sonic_thermal_control.thermal_manager_base import ThermalManagerBase

# Importing these registers the policy types the thermal_policy.json file names.
from . import thermal_actions  # noqa: F401
from . import thermal_conditions  # noqa: F401
from . import thermal_infos  # noqa: F401
from .syslog import SYSLOG_IDENTIFIER_THERMAL

COMMON_LOGGER = 'sonic_platform_base.sonic_thermal_control'


class ThermalManager(ThermalManagerBase):
    @classmethod
    def initialize(cls):
        """
        Initialize thermal manager, including register thermal condition types and thermal action types
        and any other vendor specific initialization.
        """
        cls._route_common_logging_to_syslog()
        return True

    @classmethod
    def deinitialize(cls):
        """
        Destroy thermal manager, including any vendor specific cleanup.
        :return:
        """
        return True

    @classmethod
    def _route_common_logging_to_syslog(cls):
        """
        The shared thermal modules log through the standard library rather than a vendor
        logger, so point that namespace at syslog under this platform's identifier to keep
        fan and PID messages where the rest of the platform's logs go.
        """
        logger = logging.getLogger(COMMON_LOGGER)
        if any(isinstance(h, logging.handlers.SysLogHandler) for h in logger.handlers):
            return
        try:
            handler = logging.handlers.SysLogHandler(address='/dev/log')
        except OSError:
            # No syslog socket, as in a unit test container. Leave the default handlers.
            return
        handler.setFormatter(
            logging.Formatter(SYSLOG_IDENTIFIER_THERMAL + ': %(name)s: %(message)s'))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
