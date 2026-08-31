#!/usr/bin/env python

# Copyright 2025 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import time
import traceback

from typing import TYPE_CHECKING, Dict, List, Optional, Any, Union

from sonic_platform_base.sonic_thermal_control.thermal_action_base import ThermalPolicyActionBase
from sonic_platform_base.sonic_thermal_control.thermal_json_object import thermal_json_object
from sonic_platform_base.sonic_thermal_control.pid_controller import PIDController

if TYPE_CHECKING:
    from sonic_platform_base.fan_base import Fan

from sonic_platform.thermal_infos import FanDrawerInfo, ThermalInfo
from sonic_platform.syslog import SYSLOG_IDENTIFIER_THERMAL, NhLoggerMixin

# Default range of fan speed (percentage) that PID controller can produce.
FAN_MIN_SPEED: float = 30.0
FAN_MAX_SPEED: float = 100.0


class _PidLogAdapter:
    """Adapts NhLoggerMixin to the logger interface PIDController expects."""

    def __init__(self, owner: NhLoggerMixin, domain: str) -> None:
        self._owner = owner
        self._domain = domain

    def debug(self, msg: str, *args: Any) -> None:
        self._owner.log_debug(f"[{self._domain}] " + (msg % args if args else msg))

class FanException(Exception):
    """Base exception class for fan-related errors."""
    pass

def set_all_fan_speeds(logger: NhLoggerMixin, fans: List['Fan'], speed: float) -> None:
    """
    Set speed for all fans.

    Args:
        logger: Logger instance for logging messages
        fans: List of Fan objects to set speed for
        speed: Target fan speed percentage (0-100)
    """
    if not fans:
        logger.log_error("No fans available to set speed")
        raise FanException("No fans available to set speed")
    success_count = 0
    for i, fan in enumerate(fans):
        try:
            result = fan.set_speed(speed)
            if result:
                success_count += 1
            else:
                logger.log_warning(f"Failed to set speed {speed:.1f}% for fan {i} (fan may not be present)")
        except Exception as e:
            logger.log_error(f"Exception setting speed {speed:.1f}% for fan {i}: {e}")
            logger.log_error(f"Traceback:\n{traceback.format_exc()}")
            raise

    logger.log_info(f"Applied speed {speed:.1f}% to {success_count}/{len(fans)} fans")

@thermal_json_object('fan.set_speed')
class FanSetSpeedAction(ThermalPolicyActionBase, NhLoggerMixin):
    """Thermal action to set fan speed to a specific percentage."""

    JSON_FIELD_SPEED: str = 'speed'

    def __init__(self) -> None:
        """Initialize FanSetSpeedAction."""
        ThermalPolicyActionBase.__init__(self)
        NhLoggerMixin.__init__(self, SYSLOG_IDENTIFIER_THERMAL)
        self._speed: Optional[int] = None
        self.log_debug("Initialized")

    def load_from_json(self, set_speed_json: Dict[str, Any]) -> None:
        """
        Load configuration from JSON.

        Args:
            set_speed_json: JSON object with 'speed' field (0-100)

        Raises:
            KeyError: If 'speed' field is missing
            ValueError: If speed value is invalid
        """
        try:
            self._speed = int(set_speed_json[self.JSON_FIELD_SPEED])
            self.log_info(f"Loaded with speed: {self._speed}%")
        except (KeyError, ValueError, TypeError) as e:
            self.log_error(f"Failed to load from JSON: {e}")
            raise

    def execute(self, thermal_info_dict: Dict[str, Any]) -> None:
        """
        Set speed for all present fans.

        Args:
            thermal_info_dict: Dictionary containing thermal information
        """
        fan_drawer_info = thermal_info_dict.get(FanDrawerInfo.INFO_TYPE)
        set_all_fan_speeds(self, fan_drawer_info.get_fans(), self._speed)

@thermal_json_object('fan.set_max_speed')
class FanSetMaxSpeedAction(ThermalPolicyActionBase, NhLoggerMixin):
    """Thermal action to set fan speed to a specific percentage."""

    JSON_FIELD_MAX_SPEED: str = 'max_speed'

    def __init__(self) -> None:
        """Initialize FanSetSpeedAction."""
        ThermalPolicyActionBase.__init__(self)
        NhLoggerMixin.__init__(self, SYSLOG_IDENTIFIER_THERMAL)
        self._max_speed: Optional[float] = None
        self.log_debug("Initialized")

    def load_from_json(self, set_max_speed_json: Dict[str, Any]) -> None:
        """
        Load configuration from JSON.

        Args:
            set_max_speed_json: JSON object with 'max_speed' field (0-100)

        Raises:
            KeyError: If 'max_speed' field is missing
            ValueError: If max_speed value is invalid
        """
        try:
            self._max_speed = float(set_max_speed_json[self.JSON_FIELD_MAX_SPEED])
            self._validate_json(set_max_speed_json)
            self.log_info(f"Loaded with max_speed: {self._max_speed}%")
        except (KeyError, ValueError, TypeError) as e:
            self.log_error(f"Failed to load from JSON: {e}")
            raise

    def _validate_json(self, set_max_speed_json: Dict[str, Any]) -> None:
        """
        Validate loaded JSON configuration.

        Raises:
            ValueError: If configuration is invalid
        """
        if self._max_speed is None:
            raise ValueError("No max_speed defined in JSON policy file")
        if self._max_speed < FAN_MIN_SPEED or self._max_speed > FAN_MAX_SPEED:
            raise ValueError(f"Max speed {self._max_speed} is out of range [{FAN_MIN_SPEED}, {FAN_MAX_SPEED}]")

    def execute(self, thermal_info_dict: Dict[str, Any]) -> None:
        """
        Set maximum speed for all present fans.

        Args:
            thermal_info_dict: Dictionary containing thermal information
        """
        fan_drawer_info = thermal_info_dict.get(FanDrawerInfo.INFO_TYPE)
        if not fan_drawer_info:
            raise ValueError("No fan drawer info available in thermal_info_dict")

        fans = fan_drawer_info.get_fans()
        if not fans:
            self.log_error("No fans available to set max_speed")
            raise FanException("No fans available to set max_speed")

        for fan in fans:
            fan.set_max_speed(self._max_speed)
        self.log_info(f"Applied max_speed {self._max_speed:.1f}% to {len(fans)} fans")

@thermal_json_object('thermal.control_algo')
class ThermalControlAlgorithmAction(ThermalPolicyActionBase, NhLoggerMixin):
    """PID-based thermal control algorithm using multiple thermal domains."""

    def __init__(self) -> None:
        """Initialize thermal control algorithm action."""
        ThermalPolicyActionBase.__init__(self)
        NhLoggerMixin.__init__(self, SYSLOG_IDENTIFIER_THERMAL)
        self._pidDomains: Optional[Dict[str, Dict[str, float]]] = None
        self._constants: Optional[Dict[str, Any]] = None
        self._fan_limits: Optional[Dict[str, Union[int, float]]] = None
        self._pidControllers: Dict[str, 'PIDController'] = {}
        self._extra_setpoint_margin: Dict[str, float] = {}
        self._last_run_timestamp: Optional[float] = None

        self.log_debug("Initialized")

    def load_from_json(self, algo_json: Dict[str, Any]) -> None:
        """
        Load PID configuration from JSON.

        Args:
            algo_json: JSON object with pid_domains, constants, and fan_limits

        Raises:
            KeyError: If required JSON fields are missing
            ValueError: If JSON validation fails
        """
        try:
            self._pidDomains = algo_json['pid_domains']
            self._constants = algo_json['constants']
            self._fan_limits = algo_json['fan_limits']
        except KeyError as e:
            self.log_error(f"Missing required fields in JSON: {e}")
            raise
        except Exception as e:
            self.log_error(f"Failed to load from JSON: {e}")
            raise

        self.log_info(f"Initialized with {len(self._pidDomains)} PID domains")
        self.log_debug(f"PID domains: {list(self._pidDomains.keys())}")
        self.log_debug(f"Constants: {self._constants}")
        self.log_debug(f"Fan limits: {self._fan_limits}")
        try:
            self.validate_json()
        except ValueError as e:
            self.log_error(f"Invalid thermal control algorithm JSON: {e}")
            raise

    def validate_json(self) -> None:
        """
        Validate loaded JSON configuration.

        Raises:
            ValueError: If configuration is invalid
        """
        if not self._pidDomains:
            raise ValueError("No PID domains defined in JSON policy file")
        if not self._constants:
            raise ValueError("No constants defined in JSON policy file")
        if not self._fan_limits:
            raise ValueError("No fan limits defined in JSON policy file")
        min_limit = self._fan_limits.get('min')
        if min_limit is None:
            raise ValueError("No min fan limits defined in JSON policy file")
        if min_limit < FAN_MIN_SPEED or min_limit > FAN_MAX_SPEED:
            raise ValueError(f"Min fan limit {min_limit} is out of range [{FAN_MIN_SPEED}, {FAN_MAX_SPEED}]")
        if not self._constants.get('interval'):
            raise ValueError("Interval must be defined in JSON policy file")

    def execute(self, thermal_info_dict: Dict[str, Any]) -> None:
        """
        Execute PID thermal control algorithm. Sets fans to maximum on errors.

        Args:
            thermal_info_dict: Dictionary containing thermal information
        """
        try:
            self._execute_raise_on_error(thermal_info_dict)
        except Exception as e:
            self.log_error(f"Exception executing thermal control algorithm: {e}")
            self.log_error(f"Traceback:\n{traceback.format_exc()}")
            self.log_error(f"Setting fan speed to {FAN_MAX_SPEED}% (max)")
            try:
                self._set_all_fan_speeds(thermal_info_dict, FAN_MAX_SPEED)
            except Exception as fan_exc:
                self.log_error(f"Failed to apply fail-safe fan speed: {fan_exc}")
            # Not re-raised: nothing up the stack handles it, so propagating would abort
            # every remaining policy for this iteration.

    def _execute_raise_on_error(self, thermal_info_dict: Dict[str, Any]) -> None:
        """
        Execute PID algorithm, raising exceptions on errors.

        Args:
            thermal_info_dict: Dictionary containing thermal information
        """
        thermal_info = thermal_info_dict.get(ThermalInfo.INFO_TYPE)
        if not thermal_info:
            raise ValueError("No thermal info available in thermal_info_dict")
        fan_drawer_info = thermal_info_dict.get(FanDrawerInfo.INFO_TYPE)
        if not fan_drawer_info:
            raise ValueError("No fan drawer info available in thermal_info_dict")

        # Fan's max speed limit can change at runtime, so retrieve it every time
        fan_max_speed = self._get_fan_max_speed(fan_drawer_info)

        # Initialize PID controllers if needed
        if not self._pidControllers:
            interval = thermal_info.get_thermal_manager().get_interval()
            self._initialize_pid_controllers(interval, fan_max_speed)

        # The loop period is not guaranteed to equal the configured interval, so measure
        # it once per pass and share it across domains.
        now = time.monotonic()
        dt = None if self._last_run_timestamp is None else now - self._last_run_timestamp
        self._last_run_timestamp = now

        # Get all thermals and group by PID domain
        thermals = thermal_info.get_thermals()
        domain_thermals = self._group_thermals_by_domain(thermals)

        # Compute PID output for each domain
        pid_outputs = {}
        for domain, domain_thermal_list in domain_thermals.items():
            pid_outputs[domain], _ = self._compute_domain_pid_output(
                domain, domain_thermal_list, fan_max_speed, dt
            )

        if not pid_outputs:
            raise ValueError("No valid PID outputs computed, keeping current fan speeds")

        # Use maximum PID output to set fan speed
        max_output = max(pid_outputs.values())
        max_domain = max(pid_outputs, key=pid_outputs.get)

        # Convert PID output to fan speed percentage
        final_speed = self._convert_pid_output_to_speed(max_output, fan_max_speed)

        self.log_info(f"Max PID output: {max_output:.3f} from domain '{max_domain}', "
                      f"setting fan speed to {final_speed:.1f}%")

        # Set all fan speeds
        self._set_all_fan_speeds(thermal_info_dict, final_speed)

    def _initialize_pid_controllers(self, interval: int, fan_max_speed: float) -> None:
        """
        Initialize PID controllers for each domain.

        Args:
            interval: Control loop interval in seconds
            fan_max_speed: Maximum fan speed in percentage (0-100)
        """
        if interval != self._constants['interval']:
            # Only a tuning concern: compute() is given the measured elapsed time, and
            # raising here would abort the action and drive the fans to 100%.
            self.log_warning(
                f"Manager interval {interval}s does not match interval "
                f"{self._constants.get('interval')}s in the JSON policy file; "
                "PID gains were tuned for the latter"
            )
        for domain, domain_config in self._pidDomains.items():
            output_min = self._fan_limits.get('min', FAN_MIN_SPEED)
            controller = PIDController(
                kp=domain_config['KP'],
                ki=domain_config['KI'],
                kd=domain_config['KD'],
                output_min=output_min,
                output_max=fan_max_speed,
                interval=interval,
                # This platform's gains are tuned around the midpoint of the fan range.
                setpoint_output=(output_min + fan_max_speed) / 2,
                name=f"pid[{domain}]",
                logger=_PidLogAdapter(self, domain),
            )
            self._pidControllers[domain] = controller
            self._extra_setpoint_margin[domain] = domain_config.get('extra_setpoint_margin', 0)
            self.log_info(f"Initialized PID controller for domain '{domain}'")
            if self._extra_setpoint_margin[domain]:
                self.log_notice(f"Extra setpoint margin for domain '{domain}': {self._extra_setpoint_margin[domain]}")

    def _group_thermals_by_domain(self, thermals: List[Any]) -> Dict[str, List[Any]]:
        """
        Group thermals by their PID domain.

        Args:
            thermals: List of thermal objects

        Returns:
            Dictionary mapping domain names to lists of thermal objects
        """
        domain_thermals = {}
        for thermal in thermals:
            if hasattr(thermal, 'is_controlled_by_pid'):
                if not thermal.is_controlled_by_pid():
                    continue
                domain = thermal.get_pid_domain()
                if domain and domain in self._pidControllers:
                    if domain not in domain_thermals:
                        domain_thermals[domain] = []
                    domain_thermals[domain].append(thermal)
            else:
                self.log_warning(f"Thermal {thermal.get_name()} does not define is_controlled_by_pid()")
        if not domain_thermals:
            raise ValueError("No thermals available for PID control")
        for domain, domain_thermals_list in domain_thermals.items():
            if not domain_thermals_list:
                raise ValueError(f"Domain '{domain}' has no thermals")
        self.log_debug(f"Grouped thermals by domain: {[(d, len(ts)) for d, ts in domain_thermals.items()]}")
        return domain_thermals

    def _compute_domain_pid_output(
        self, domain: str, domain_thermals: List[Any], fan_max_speed: float,
        dt: Optional[float] = None
    ) -> tuple[float, Any]:
        """
        Compute PID output using thermal with largest error in domain.

        Args:
            domain: PID domain name
            domain_thermals: List of thermal objects in this domain
            fan_max_speed: Maximum fan speed in percentage (0-100)
            dt: Measured seconds since the previous pass, or None on the first pass

        Returns:
            Tuple of (PID output value, max error thermal object)
        """
        controller = self._pidControllers[domain]

        # Fan's max speed limit can change at runtime, so update it first. A cap below
        # the configured minimum would invert the range.
        if fan_max_speed >= controller.output_min:
            controller.set_output_limits(output_max=fan_max_speed)
        else:
            self.log_error(
                f"Domain '{domain}': fan max speed {fan_max_speed} is below the "
                f"configured minimum {controller.output_min}; keeping previous limit"
            )

        # Find thermal with largest error (current temp - setpoint)
        max_error = None
        max_error_thermal = None
        max_error_thermal_setpoint = None

        for thermal in domain_thermals:
            current_temp = thermal.get_temperature()
            if current_temp is None:
                # We may have no temperature reading if thermal is not present
                self.log_info(f"Thermal '{thermal.get_name()}' has no temperature reading, skipping")
                continue

            setpoint = thermal.get_pid_setpoint()
            if setpoint is None:
                # If the thermal was just unplugged, we may got the temperature, but not the setpoint
                self.log_info(f"Thermal '{thermal.get_name()}' has no setpoint, skipping")
                continue

            error = current_temp - setpoint - self._extra_setpoint_margin[domain]

            if max_error is None or error > max_error:
                max_error = error
                max_error_thermal = thermal
                max_error_thermal_setpoint = setpoint

        if max_error_thermal is None:
            raise ValueError(f"No valid thermal found for domain '{domain}'")

        self.log_debug(f"Domain '{domain}': using thermal '{max_error_thermal.get_name()}' "
                       f"with error {max_error:.2f}°C (setpoint={max_error_thermal_setpoint:.2f}°C)")

        # Compute PID output using the largest error
        pid_output = controller.compute(max_error, dt)
        return pid_output, max_error_thermal

    def _convert_pid_output_to_speed(self, pid_output: float, max_speed: float) -> float:
        """
        Convert PID output to fan speed percentage.

        Args:
            pid_output: Raw PID controller output
            max_speed: Maximum fan speed in percentage (0-100)

        Returns:
            Fan speed percentage saturated to configured limits
        """
        min_speed = self._fan_limits.get('min', FAN_MIN_SPEED)
        return max(min_speed, min(max_speed, pid_output))

    def _get_fan_max_speed(self, fan_drawer_info: FanDrawerInfo) -> float:
        """
        Gets fan speed limit that satisfy all fans.
        
        If the value is out of range ([self._fan_limits['min'], FAN_MAX_SPEED]),
        clamps it into the range.

        Args:
            thermal_info_dict: Dictionary containing thermal information

        Returns:
            Max speed for all fans, saturated to the configured limits
        """
        fans = fan_drawer_info.get_fans()
        if not fans:
            raise FanException("No fans available to get max speed")
        fan_max_speed = min(fan.get_max_speed() for fan in fans)
        fan_min_speed = self._fan_limits.get('min', FAN_MIN_SPEED)
        if fan_max_speed < fan_min_speed or fan_max_speed > FAN_MAX_SPEED:
            self.log_error(
                f"Fan max speed {fan_max_speed} is out of range [{fan_min_speed}, {FAN_MAX_SPEED}]. "
                "Clamping it into the range."
            )
            fan_max_speed = max(fan_min_speed, min(fan_max_speed, FAN_MAX_SPEED))
        return fan_max_speed

    def _set_all_fan_speeds(self, thermal_info_dict: Dict[str, Any], speed: float) -> None:
        """
        Set speed for all fans.

        Args:
            thermal_info_dict: Dictionary containing thermal information
            speed: Target fan speed percentage
        """
        set_all_fan_speeds(self, thermal_info_dict.get(FanDrawerInfo.INFO_TYPE).get_fans(), speed)
