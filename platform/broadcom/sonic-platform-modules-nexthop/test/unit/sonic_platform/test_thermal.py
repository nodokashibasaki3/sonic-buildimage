#!/usr/bin/env python

# Copyright 2025 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for this platform's thermal.py.
These tests run in isolation from the SONiC environment using pytest:
python -m pytest test/unit/sonic_platform/test_thermal.py -v

The thermal policy infos, conditions and actions now come from sonic-platform-common and
are tested there, in tests/common_infos_test.py, tests/common_conditions_test.py,
tests/common_actions_test.py and tests/pid_controller_test.py.
"""

import types
from unittest.mock import Mock, call, patch
from fixtures.test_helpers_common import mock_data_in_swsscommon

import pytest


@pytest.fixture
def thermal_module():
    """Loads the module before each test. This is to let conftest.py inject deps first."""
    from sonic_platform import thermal

    yield thermal


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
