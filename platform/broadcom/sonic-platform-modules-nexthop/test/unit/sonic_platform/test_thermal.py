#!/usr/bin/env python

# Copyright 2025 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for the thermal_actions.py module.
These tests run in isolation from the SONiC environment using pytest:
python -m pytest test/unit/sonic_platform/test_thermal.py -v
"""

import types
from unittest.mock import Mock, call, patch
from fixtures.test_helpers_common import mock_data_in_swsscommon

import pytest


@pytest.fixture
def thermal_actions_module():
    """Loads the module before each test. This is to let conftest.py inject deps first."""
    from sonic_platform import thermal_actions

    yield thermal_actions

@pytest.fixture
def thermal_module():
    """Loads the module before each test. This is to let conftest.py inject deps first."""
    from sonic_platform import thermal

    yield thermal


# PIDController lives in sonic-platform-common and is unit-tested there in
# tests/pid_controller_test.py; only this platform's use of it is tested below.


class TestFanDrawerConditions:
    """Fan drawer presence conditions used to gate the thermal policies."""

    @pytest.fixture
    def conditions_module(self):
        from sonic_platform import thermal_conditions

        return thermal_conditions

    def _info(self, num_present):
        from sonic_platform.thermal_infos import FanDrawerInfo

        info = Mock()
        info.get_num_present_fan_drawers.return_value = num_present
        return {FanDrawerInfo.INFO_TYPE: info}

    @pytest.mark.parametrize("num_present,expected", [
        (0, True), (1, True), (2, True), (3, False), (4, False),
    ])
    def test_two_or_fewer_present(self, conditions_module, num_present, expected):
        """Must include zero present, which the exact-count conditions leave unmatched."""
        condition = conditions_module.FanDrawerTwoOrFewerPresentCondition()
        assert condition.is_match(self._info(num_present)) is expected

    @pytest.mark.parametrize("num_present,expected", [
        (2, False), (3, True), (4, True),
    ])
    def test_default_operation_is_the_complement(self, conditions_module, num_present, expected):
        condition = conditions_module.ThermalControlAlgorithmCondition()
        assert condition.is_match(self._info(num_present)) is expected

    @pytest.mark.parametrize("num_present", [0, 1, 2, 3, 4])
    def test_every_drawer_count_is_covered(self, conditions_module, num_present):
        """No drawer count may fall through both gates without an action."""
        degraded = conditions_module.FanDrawerTwoOrFewerPresentCondition()
        normal = conditions_module.ThermalControlAlgorithmCondition()
        info = self._info(num_present)
        assert degraded.is_match(info) or normal.is_match(info)


class TestFanSetSpeedAction:
    """Test class for FanSetSpeedAction functionality."""

    @pytest.fixture
    def fan_set_speed_action(self, thermal_actions_module):
        """Fixture providing a FanSetSpeedAction instance."""
        return thermal_actions_module.FanSetSpeedAction()

    @pytest.fixture
    def mock_fans(self):
        """Fixture providing mock fan objects."""
        fans = []
        for i in range(3):
            fan = Mock()
            fan.set_speed = Mock(return_value=True)
            fans.append(fan)
        return fans

    @pytest.fixture
    def thermal_info_dict(self, thermal_actions_module, mock_fans):
        """Fixture providing mock thermal info dictionary."""
        fan_drawer_info = Mock()
        fan_drawer_info.get_fans = Mock(return_value=mock_fans)
        return {
            thermal_actions_module.FanDrawerInfo.INFO_TYPE: fan_drawer_info
        }

    def test_fan_set_speed_action_initialization(self, fan_set_speed_action):
        """Test FanSetSpeedAction initialization."""
        assert fan_set_speed_action._speed is None

    def test_fan_set_speed_action_load_from_json_valid(self, fan_set_speed_action):
        """Test loading valid JSON configuration."""
        json_config = {'speed': 75}
        fan_set_speed_action.load_from_json(json_config)
        assert fan_set_speed_action._speed == 75

    def test_fan_set_speed_action_load_from_json_invalid(self, fan_set_speed_action):
        """Test loading invalid JSON configuration."""
        with pytest.raises(KeyError):
            fan_set_speed_action.load_from_json({})  # Missing speed field

    def test_fan_set_speed_action_execute(self, fan_set_speed_action, thermal_info_dict, mock_fans):
        """Test FanSetSpeedAction execution."""
        # Configure action
        fan_set_speed_action.load_from_json({'speed': 75})

        # Execute action
        fan_set_speed_action.execute(thermal_info_dict)

        # Verify all fans were set to correct speed
        for fan in mock_fans:
            fan.set_speed.assert_called_once_with(75)


class TestFanSetMaxSpeedAction:
    """Test class for FanSetMaxSpeedAction functionality."""

    @pytest.fixture
    def fan_set_max_speed_action(self, thermal_actions_module):
        """Fixture providing a FanSetMaxSpeedAction instance."""
        return thermal_actions_module.FanSetMaxSpeedAction()

    @pytest.fixture
    def mock_fans(self):
        """Fixture providing mock fan objects."""
        fans = []
        for _ in range(3):
            fan = Mock()
            fan.set_speed = Mock(return_value=True)
            fans.append(fan)
        return fans

    @pytest.fixture
    def mock_thermal_info_dict(self, thermal_actions_module, mock_fans):
        """Fixture providing mock thermal info dictionary."""
        fan_drawer_info = Mock()
        fan_drawer_info.get_fans = Mock(return_value=mock_fans)
        
        return {
            thermal_actions_module.FanDrawerInfo.INFO_TYPE: fan_drawer_info
        }

    def test_fan_set_max_speed_action_initialization(self, fan_set_max_speed_action):
        """Test FanSetMaxSpeedAction initialization."""
        assert fan_set_max_speed_action._max_speed is None

    def test_fan_set_max_speed_action_load_from_json_valid(self, fan_set_max_speed_action):
        """Test loading valid JSON configuration."""
        json_config = {'max_speed': 75}
        fan_set_max_speed_action.load_from_json(json_config)
        assert fan_set_max_speed_action._max_speed == 75

    def test_fan_set_max_speed_action_load_from_json_invalid(self, fan_set_max_speed_action):
        """Test loading invalid JSON configuration."""
        with pytest.raises(KeyError):
            fan_set_max_speed_action.load_from_json({})  # Missing max_speed field

    def test_fan_set_max_speed_action_load_from_json_range_validation(self, fan_set_max_speed_action):
        """Test max_speed range validation during JSON loading."""
        with pytest.raises(ValueError, match="Max speed 5.0 is out of range"):
            fan_set_max_speed_action.load_from_json({'max_speed': 5})
        
        with pytest.raises(ValueError, match="Max speed 105.0 is out of range"):
            fan_set_max_speed_action.load_from_json({'max_speed': 105})

    def test_fan_set_max_speed_action_execute(self, fan_set_max_speed_action, mock_thermal_info_dict, mock_fans):
        """Test FanSetMaxSpeedAction execution."""
        # Configure action
        fan_set_max_speed_action.load_from_json({'max_speed': 75})
        
        # Execute action
        fan_set_max_speed_action.execute(mock_thermal_info_dict)
        
        # Verify all fans were set to correct max speed
        for fan in mock_fans:
            fan.set_max_speed.assert_called_once_with(75)


class TestThermalControlAlgorithmAction:
    """Test class for ThermalControlAlgorithmAction functionality."""

    @pytest.fixture
    def thermal_control_action(self, thermal_actions_module):
        """Fixture providing a ThermalControlAlgorithmAction instance."""
        return thermal_actions_module.ThermalControlAlgorithmAction()

    @pytest.fixture
    def valid_json_config(self):
        """Fixture providing valid JSON configuration for thermal control."""
        return {
            'pid_domains': {
                'cpu': {'KP': 1.0, 'KI': 0.5, 'KD': 0.1},
            },
            'constants': {
                'interval': 5,
                'extra_setpoint_margin': {'cpu': 2.0}
            },
            'fan_limits': {
                'min': 30
            }
        }

    def test_thermal_control_action_initialization(self, thermal_control_action):
        """Test ThermalControlAlgorithmAction initialization."""
        assert thermal_control_action._pidDomains is None
        assert thermal_control_action._constants is None
        assert thermal_control_action._fan_limits is None
        assert thermal_control_action._pidControllers == {}

    def test_thermal_control_action_load_from_json_valid(self, thermal_control_action, valid_json_config):
        """Test loading valid JSON configuration."""
        thermal_control_action.load_from_json(valid_json_config)

        assert thermal_control_action._pidDomains == valid_json_config['pid_domains']
        assert thermal_control_action._constants == valid_json_config['constants']
        assert thermal_control_action._fan_limits == valid_json_config['fan_limits']

    def test_thermal_control_action_load_from_json_missing_fields(self, thermal_control_action, valid_json_config):
        """Test loading JSON configuration with missing required fields."""
        invalid_config = valid_json_config.copy()
        del invalid_config['pid_domains']

        with pytest.raises(KeyError):
            thermal_control_action.load_from_json(invalid_config)

    def test_thermal_control_action_pid_controller_creation(self, thermal_control_action, valid_json_config):
        """Test that PID controllers are created correctly from JSON config."""
        thermal_control_action.load_from_json(valid_json_config)

        # Initialize PID controllers
        thermal_control_action._initialize_pid_controllers(interval=5, fan_max_speed=100)

        # Verify controller was created for the domain
        assert 'cpu' in thermal_control_action._pidControllers
        controller = thermal_control_action._pidControllers['cpu']

        # Verify controller parameters match JSON config
        assert controller._kp == 1.0
        assert controller._ki == 0.5
        assert controller._kd == 0.1
        assert controller._output_min == 30
        assert controller._output_max == 100
        assert controller._interval == 5

    def test_thermal_control_action_interval_mismatch(self, thermal_control_action, valid_json_config):
        """A mismatched interval must warn, not abort: aborting drives the fans to 100%."""
        thermal_control_action.load_from_json(valid_json_config)

        thermal_control_action._initialize_pid_controllers(interval=10, fan_max_speed=100)

        assert 'cpu' in thermal_control_action._pidControllers

    def test_thermal_control_action_preserves_midpoint_operating_point(
            self, thermal_control_action, valid_json_config):
        """This platform's gains are tuned around the midpoint of the usable fan range."""
        thermal_control_action.load_from_json(valid_json_config)
        thermal_control_action._initialize_pid_controllers(interval=5, fan_max_speed=100)

        controller = thermal_control_action._pidControllers['cpu']
        assert controller.compute(0.0) == (30 + 100) / 2

    def test_thermal_control_action_convert_pid_output_to_speed(self, thermal_control_action, valid_json_config):
        """Test PID output to fan speed conversion with precise validation."""
        thermal_control_action.load_from_json(valid_json_config)

        # Test various PID outputs
        test_cases = [
            (25.0, 30),    # Below min, should clamp to min
            (30.0, 30),    # At min
            (65.0, 65),    # In range
            (100.0, 100),  # At max
            (105.0, 100),  # Above max, should clamp to max
        ]

        for pid_output, expected_speed in test_cases:
            speed = thermal_control_action._convert_pid_output_to_speed(pid_output, max_speed=100)
            assert speed == expected_speed, f"PID output {pid_output} should convert to {expected_speed}, got {speed}"

    def test_thermal_control_action_multiple_domains(self, thermal_actions_module):
        """Test thermal control action with multiple PID domains."""
        action = thermal_actions_module.ThermalControlAlgorithmAction()

        multi_domain_config = {
            'pid_domains': {
                'cpu': {'KP': 1.0, 'KI': 0.5, 'KD': 0.1},
                'switch': {'KP': 2.0, 'KI': 1.0, 'KD': 0.2},
                'ambient': {'KP': 0.5, 'KI': 0.25, 'KD': 0.05},
            },
            'constants': {
                'interval': 5,
                'extra_setpoint_margin': {'cpu': 2.0, 'switch': 3.0, 'ambient': 1.0}
            },
            'fan_limits': {
                'min': 35
            }
        }

        action.load_from_json(multi_domain_config)
        action._initialize_pid_controllers(interval=5, fan_max_speed=95)

        # Verify all controllers were created
        assert len(action._pidControllers) == 3
        assert 'cpu' in action._pidControllers
        assert 'switch' in action._pidControllers
        assert 'ambient' in action._pidControllers

        # Verify each controller has correct parameters
        cpu_controller = action._pidControllers['cpu']
        assert cpu_controller._kp == 1.0 and cpu_controller._ki == 0.5 and cpu_controller._kd == 0.1

        switch_controller = action._pidControllers['switch']
        assert switch_controller._kp == 2.0 and switch_controller._ki == 1.0 and switch_controller._kd == 0.2

        ambient_controller = action._pidControllers['ambient']
        assert ambient_controller._kp == 0.5 and ambient_controller._ki == 0.25 and ambient_controller._kd == 0.05

    def test_thermal_control_action_fan_limits_validation(self, thermal_control_action):
        """Test fan limits validation during JSON loading."""
        # Test invalid fan limits (out of range)
        invalid_config = {
            'pid_domains': {'cpu': {'KP': 1.0, 'KI': 0.5, 'KD': 0.1}},
            'constants': {'interval': 5, 'extra_setpoint_margin': {'cpu': 2.0}},
            'fan_limits': {'min': 5}  # Out of valid range
        }

        with pytest.raises(ValueError, match="Min fan limit 5 is out of range"):
            thermal_control_action.load_from_json(invalid_config)

    def test_thermal_control_action_missing_interval(self, thermal_control_action):
        """Test that missing interval raises ValueError."""
        invalid_config = {
            'pid_domains': {'cpu': {'KP': 1.0, 'KI': 0.5, 'KD': 0.1}},
            'constants': {'extra_setpoint_margin': {'cpu': 2.0}},  # Missing interval
            'fan_limits': {'min': 30}
        }

        with pytest.raises(ValueError, match="Interval must be defined"):
            thermal_control_action.load_from_json(invalid_config)


class TestSetAllFanSpeedsErrorCases:
    """Test class for set_all_fan_speeds error cases."""

    @pytest.fixture
    def mock_logger(self):
        """Fixture providing a mock logger."""
        logger = Mock()
        logger.log_error = Mock()
        logger.log_warning = Mock()
        return logger

    def test_set_all_fan_speeds_no_fans_available(self, thermal_actions_module, mock_logger):
        """Test set_all_fan_speeds with empty fan list."""
        empty_fans = []

        with pytest.raises(thermal_actions_module.FanException, match="No fans available to set speed"):
            thermal_actions_module.set_all_fan_speeds(mock_logger, empty_fans, 50.0)

        # Verify error was logged
        mock_logger.log_error.assert_called_once_with("No fans available to set speed")

    def test_set_all_fan_speeds_fan_set_speed_returns_false(self, thermal_actions_module, mock_logger):
        """Test set_all_fan_speeds when fan.set_speed returns False."""
        # Create mock fans that return False from set_speed
        mock_fans = []
        for i in range(3):
            fan = Mock()
            fan.set_speed = Mock(return_value=False)
            mock_fans.append(fan)

        speed = 75.0

        # Should not raise exception, but should log warnings
        thermal_actions_module.set_all_fan_speeds(mock_logger, mock_fans, speed)

        # Verify all fans were called
        for i, fan in enumerate(mock_fans):
            fan.set_speed.assert_called_once_with(speed)

        # Verify warnings were logged for each fan
        expected_calls = [
            call(f"Failed to set speed {speed:.1f}% for fan {i} (fan may not be present)")
            for i in range(3)
        ]
        mock_logger.log_warning.assert_has_calls(expected_calls)

    def test_set_all_fan_speeds_fan_set_speed_raises_exception(self, thermal_actions_module, mock_logger):
        """Test set_all_fan_speeds when fan.set_speed raises an exception."""
        # Create mock fan that raises exception
        mock_fan = Mock()
        test_exception = RuntimeError("Hardware failure")
        mock_fan.set_speed = Mock(side_effect=test_exception)
        mock_fans = [mock_fan]

        speed = 60.0

        # Should re-raise the exception
        with pytest.raises(RuntimeError, match="Hardware failure"):
            thermal_actions_module.set_all_fan_speeds(mock_logger, mock_fans, speed)

        # Verify fan was called
        mock_fan.set_speed.assert_called_once_with(speed)

        # Verify error was logged
        mock_logger.log_error.assert_any_call(f"Exception setting speed {speed:.1f}% for fan 0: {test_exception}")
        # Also verify traceback was logged (we can't easily test the exact traceback content)
        assert any("Traceback:" in str(call) for call in mock_logger.log_error.call_args_list)

    def test_set_all_fan_speeds_mixed_success_and_failure(self, thermal_actions_module, mock_logger):
        """Test set_all_fan_speeds with mix of successful and failed fan operations."""
        # Create mix of fans: some succeed, some fail, some raise exceptions
        mock_fans = []

        # Fan 0: Success
        fan0 = Mock()
        fan0.set_speed = Mock(return_value=True)
        mock_fans.append(fan0)

        # Fan 1: Returns False
        fan1 = Mock()
        fan1.set_speed = Mock(return_value=False)
        mock_fans.append(fan1)

        # Fan 2: Success
        fan2 = Mock()
        fan2.set_speed = Mock(return_value=True)
        mock_fans.append(fan2)

        # Fan 3: Raises exception
        fan3 = Mock()
        fan3.set_speed = Mock(side_effect=IOError("I/O error"))
        mock_fans.append(fan3)

        speed = 80.0

        # Should raise exception from fan3
        with pytest.raises(IOError, match="I/O error"):
            thermal_actions_module.set_all_fan_speeds(mock_logger, mock_fans, speed)

        # Verify all fans up to the failing one were called
        fan0.set_speed.assert_called_once_with(speed)
        fan1.set_speed.assert_called_once_with(speed)
        fan2.set_speed.assert_called_once_with(speed)
        fan3.set_speed.assert_called_once_with(speed)

        # Verify warning was logged for fan1 (returned False)
        mock_logger.log_warning.assert_called_with(f"Failed to set speed {speed:.1f}% for fan 1 (fan may not be present)")

        # Verify error was logged for fan3 (raised exception)
        mock_logger.log_error.assert_any_call(f"Exception setting speed {speed:.1f}% for fan 3: I/O error")

    def test_set_all_fan_speeds_none_fans_list(self, thermal_actions_module, mock_logger):
        """Test set_all_fan_speeds with None as fan list."""
        with pytest.raises(thermal_actions_module.FanException, match="No fans available to set speed"):
            thermal_actions_module.set_all_fan_speeds(mock_logger, None, 50.0)

        # Verify error was logged
        mock_logger.log_error.assert_called_once_with("No fans available to set speed")


class TestSfpThermalGetPidSetpoint:
    """Test class for SfpThermal get_pid_setpoint invalid setpoint handling."""

    @pytest.fixture
    def mock_sfp(self):
        """Fixture providing a mock SFP object."""
        sfp = Mock()
        sfp.get_name = Mock(return_value="sfp1")
        return sfp

    @pytest.fixture
    def mock_thermal_syslogger(self):
        """Fixture providing a mock thermal syslogger."""
        mock_syslogger = Mock()
        mock_syslogger.log_warning = Mock()
        return mock_syslogger

    @pytest.fixture
    def sfp_thermal(self, mock_sfp, mock_thermal_syslogger):
        """Fixture providing a mock SfpThermal instance."""
        # Create a mock SfpThermal class that mimics the real behavior
        class MockSfpThermal:
            MIN_VALID_SETPOINT = 30.0
            DEFAULT_SETPOINT = 65.0

            def __init__(self, sfp, thermal_syslogger):
                self._sfp = sfp
                self._invalid_setpoint_logged = False
                self._thermal_syslogger = thermal_syslogger
                self._parent_setpoint = None  # Will be set by tests

            def get_name(self):
                return f"Transceiver {self._sfp.get_name().capitalize()}"

            def get_pid_setpoint(self):
                """Mock implementation of SfpThermal.get_pid_setpoint logic."""
                setpoint = self._parent_setpoint  # Simulates parent class call
                if setpoint is None:
                    return setpoint
                # Setpoint cannot be guaranteed on pluggables - some modules may have invalid values such as 0.
                # For these cases, use a default setpoint.
                if setpoint < self.MIN_VALID_SETPOINT:
                    if not self._invalid_setpoint_logged:
                        self._thermal_syslogger.log_warning(f"Invalid setpoint {setpoint:.1f} for {self.get_name()}, "
                                                          f"using default setpoint {self.DEFAULT_SETPOINT:.1f}")
                        self._invalid_setpoint_logged = True
                    return self.DEFAULT_SETPOINT
                return setpoint

        # Create instance
        sfp_thermal = MockSfpThermal(mock_sfp, mock_thermal_syslogger)
        return sfp_thermal

    def test_sfp_thermal_get_pid_setpoint_valid_setpoint(self, sfp_thermal):
        """Test SfpThermal get_pid_setpoint with valid setpoint."""
        # Set parent setpoint to a valid value
        sfp_thermal._parent_setpoint = 75.0
        setpoint = sfp_thermal.get_pid_setpoint()
        assert setpoint == 75.0
        # Should not log any warning for valid setpoint
        assert not sfp_thermal._invalid_setpoint_logged

    def test_sfp_thermal_get_pid_setpoint_none_setpoint(self, sfp_thermal):
        """Test SfpThermal get_pid_setpoint when parent returns None."""
        # Set parent setpoint to None
        sfp_thermal._parent_setpoint = None
        setpoint = sfp_thermal.get_pid_setpoint()
        assert setpoint is None
        # Should not log any warning for None setpoint
        assert not sfp_thermal._invalid_setpoint_logged

    def test_sfp_thermal_get_pid_setpoint_invalid_setpoint_below_minimum(self, sfp_thermal):
        """Test SfpThermal get_pid_setpoint with setpoint below minimum."""
        # Set parent setpoint to invalid value
        invalid_setpoint = 15.0  # Below MIN_VALID_SETPOINT (30.0)
        sfp_thermal._parent_setpoint = invalid_setpoint

        setpoint = sfp_thermal.get_pid_setpoint()

        # Should return default setpoint
        assert setpoint == sfp_thermal.DEFAULT_SETPOINT

        # Should log warning
        expected_warning = (f"Invalid setpoint {invalid_setpoint:.1f} for {sfp_thermal.get_name()}, "
                          f"using default setpoint {sfp_thermal.DEFAULT_SETPOINT:.1f}")
        sfp_thermal._thermal_syslogger.log_warning.assert_called_once_with(expected_warning)

        # Should mark as logged
        assert sfp_thermal._invalid_setpoint_logged

    def test_sfp_thermal_get_pid_setpoint_invalid_setpoint_zero(self, sfp_thermal):
        """Test SfpThermal get_pid_setpoint with zero setpoint."""
        # Set parent setpoint to zero
        invalid_setpoint = 0.0
        sfp_thermal._parent_setpoint = invalid_setpoint

        setpoint = sfp_thermal.get_pid_setpoint()

        # Should return default setpoint
        assert setpoint == sfp_thermal.DEFAULT_SETPOINT

        # Should log warning
        expected_warning = (f"Invalid setpoint {invalid_setpoint:.1f} for {sfp_thermal.get_name()}, "
                          f"using default setpoint {sfp_thermal.DEFAULT_SETPOINT:.1f}")
        sfp_thermal._thermal_syslogger.log_warning.assert_called_once_with(expected_warning)

    def test_sfp_thermal_get_pid_setpoint_invalid_setpoint_negative(self, sfp_thermal):
        """Test SfpThermal get_pid_setpoint with negative setpoint."""
        # Set parent setpoint to negative value
        invalid_setpoint = -5.0
        sfp_thermal._parent_setpoint = invalid_setpoint

        setpoint = sfp_thermal.get_pid_setpoint()

        # Should return default setpoint
        assert setpoint == sfp_thermal.DEFAULT_SETPOINT

        # Should log warning
        expected_warning = (f"Invalid setpoint {invalid_setpoint:.1f} for {sfp_thermal.get_name()}, "
                          f"using default setpoint {sfp_thermal.DEFAULT_SETPOINT:.1f}")
        sfp_thermal._thermal_syslogger.log_warning.assert_called_once_with(expected_warning)

    def test_sfp_thermal_get_pid_setpoint_warning_logged_only_once(self, sfp_thermal):
        """Test that invalid setpoint warning is logged only once."""
        invalid_setpoint = 10.0
        sfp_thermal._parent_setpoint = invalid_setpoint

        # Call multiple times
        setpoint1 = sfp_thermal.get_pid_setpoint()
        setpoint2 = sfp_thermal.get_pid_setpoint()
        setpoint3 = sfp_thermal.get_pid_setpoint()

        # All should return default setpoint
        assert setpoint1 == sfp_thermal.DEFAULT_SETPOINT
        assert setpoint2 == sfp_thermal.DEFAULT_SETPOINT
        assert setpoint3 == sfp_thermal.DEFAULT_SETPOINT

        # Warning should be logged only once
        assert sfp_thermal._thermal_syslogger.log_warning.call_count == 1

        # Flag should be set
        assert sfp_thermal._invalid_setpoint_logged

    def test_sfp_thermal_get_pid_setpoint_boundary_conditions(self, sfp_thermal):
        """Test SfpThermal get_pid_setpoint at boundary conditions."""
        # Test exactly at minimum valid setpoint
        boundary_setpoint = sfp_thermal.MIN_VALID_SETPOINT  # 30.0
        sfp_thermal._parent_setpoint = boundary_setpoint

        setpoint = sfp_thermal.get_pid_setpoint()

        # Should return the boundary setpoint (valid)
        assert setpoint == boundary_setpoint

        # Should not log warning
        sfp_thermal._thermal_syslogger.log_warning.assert_not_called()
        assert not sfp_thermal._invalid_setpoint_logged

        # Test just below minimum valid setpoint
        just_below_boundary = sfp_thermal.MIN_VALID_SETPOINT - 0.1  # 29.9

        # Reset the logged flag for this test
        sfp_thermal._invalid_setpoint_logged = False
        sfp_thermal._thermal_syslogger.reset_mock()


class TestPortIndexMapper:
    def test_get_interface_name_picks_lowest_and_ignores_invalid(self, thermal_module):
        """Verify PortIndexMapper builds mapping and picks lowest Ethernet name for same index."""
        mock_data_in_swsscommon(
            "CONFIG_DB",
            "PORT",
            {
                "Ethernet4": {"index": "1"},
                "Ethernet0": {"index": "1"},
                "NotAnEthernet": {"index": "1"},
            },
        )

        # Reset singleton to rebuild mapping
        thermal_module.PortIndexMapper._instance = None
        mapper = thermal_module.PortIndexMapper()

        assert mapper.get_interface_name(1) == 'Ethernet0'
        assert mapper.get_interface_name(2) is None


class TestSfpThermal:
    @pytest.fixture
    def pddf_platform(self):
        # Provide minimal PLATFORM data to avoid None .lower() in PidThermalMixin
        return types.SimpleNamespace(data={'PLATFORM': {
            'nexthop_thermal_xcvr_setpoint_override': None,
            'nexthop_thermal_xcvr_pid_domain': 'none'
        }})

    def test_default_setpoint_when_thresholds_unavailable(self, thermal_module, pddf_platform):
        """When thresholds are not yet available but SFP is present, default setpoint is used."""
        sfp = Mock()
        sfp.get_name.return_value = 'sfp1'
        sfp.get_presence.return_value = True
        sfp.get_position_in_parent.return_value = 1

        with patch.object(thermal_module.PortIndexMapper, 'get_interface_name', return_value='Ethernet0'):
            sfp_th = thermal_module.SfpThermal(sfp, pddf_platform)
            setpoint = sfp_th.get_pid_setpoint()
            assert setpoint == thermal_module.SfpThermal.DEFAULT_SETPOINT

    def test_invalid_computed_setpoint_logs_once_and_uses_default(self, thermal_module, pddf_platform):
        """If computed setpoint < MIN_VALID_SETPOINT, fallback to default and log once."""
        mock_data_in_swsscommon(
            "STATE_DB",
            "TRANSCEIVER_DOM_THRESHOLD",
            {
                # temphighwarning - margin (10) => 25 < 30 -> invalid
                "Ethernet4": {"temphighwarning": "35"},
            },
        )

        sfp = Mock()
        sfp.get_name.return_value = 'sfp2'
        sfp.get_presence.return_value = True
        sfp.get_position_in_parent.return_value = 2

        with patch.object(thermal_module.PortIndexMapper, 'get_interface_name', return_value='Ethernet4'):
            sfp_th = thermal_module.SfpThermal(sfp, pddf_platform)
            logger = thermal_module.thermal_syslogger
            before = getattr(logger, 'log_warning').call_count

            sp1 = sfp_th.get_pid_setpoint()
            assert sp1 == thermal_module.SfpThermal.DEFAULT_SETPOINT
            assert getattr(logger, 'log_warning').call_count == before + 1

            # Second call should not log again
            sp2 = sfp_th.get_pid_setpoint()
            assert sp2 == thermal_module.SfpThermal.DEFAULT_SETPOINT
            assert getattr(logger, 'log_warning').call_count == before + 1

    def test_thresholds_parsing_and_cache(self, thermal_module, pddf_platform):
        """State DB threshold values are parsed to float and cached for THRESHOLDS_CACHE_INTERVAL_SEC."""
        mock_data_in_swsscommon(
            "STATE_DB",
            "TRANSCEIVER_DOM_THRESHOLD",
            {
                "Ethernet8": {
                    "temphighwarning": "75.0",
                    "templowwarning": "10.5",
                    "temphighalarm": "90",
                    "templowalarm": "5",
                    "irrelevant": "N/A",
                },
            },
        )

        sfp = Mock()
        sfp.get_name.return_value = 'sfp3'
        sfp.get_presence.return_value = True
        sfp.get_position_in_parent.return_value = 3

        with patch.object(thermal_module.PortIndexMapper, 'get_interface_name', return_value='Ethernet8'):
            sfp_th = thermal_module.SfpThermal(sfp, pddf_platform)

            # First fetch reads from DB and caches
            assert sfp_th.get_high_threshold() == 75.0
            assert sfp_th.get_low_threshold() == 10.5
            assert sfp_th.get_high_critical_threshold() == 90.0
            assert sfp_th.get_low_critical_threshold() == 5.0

            # Change underlying DB data; cache should prevent update immediately
            mock_data_in_swsscommon(
                "STATE_DB",
                "TRANSCEIVER_DOM_THRESHOLD",
                {
                    "Ethernet8": {
                        "temphighwarning": "10",
                        "templowwarning": "1",
                        "temphighalarm": "20",
                        "templowalarm": "0",
                    },
                },
            )
            # Values should remain cached (unchanged)
            assert sfp_th.get_high_threshold() == 75.0
            assert sfp_th.get_low_threshold() == 10.5
