"""
Tests for the 4-tier permission model, directory allowlists, and emergency stop.
"""

from pathlib import Path

from core.permissions import PermissionManager
from tools import PermissionLevel


class TestEnhancedPermissions:

    def setup_method(self):
        self.pm = PermissionManager()

    def test_level_0_read_only(self):
        check = self.pm.check(PermissionLevel.LEVEL_0_READ_ONLY, "get_system_info")
        assert check.allowed is True
        assert check.needs_approval is False

    def test_level_1_low_risk(self):
        check = self.pm.check(PermissionLevel.LEVEL_1_LOW_RISK, "create_folder")
        assert check.allowed is True
        assert check.needs_approval is False

    def test_level_2_moderate_risk(self):
        check = self.pm.check(PermissionLevel.LEVEL_2_MODERATE_RISK, "move_file")
        assert check.allowed is False
        assert check.needs_approval is True
        assert check.risk_level == PermissionLevel.LEVEL_2_MODERATE_RISK

    def test_level_3_high_risk(self):
        check = self.pm.check(PermissionLevel.LEVEL_3_HIGH_RISK, "delete_file")
        assert check.allowed is False
        assert check.needs_approval is True
        assert check.risk_level == PermissionLevel.LEVEL_3_HIGH_RISK

    def test_emergency_stop_halts_everything(self):
        self.pm.trigger_emergency_stop("System integrity test")
        assert self.pm.is_emergency_stopped is True

        # Even Level 0 should now be BLOCKED
        check = self.pm.check(PermissionLevel.LEVEL_0_READ_ONLY, "get_datetime")
        assert check.allowed is False
        assert check.needs_approval is False
        assert "EMERGENCY STOP" in check.reason

    def test_clear_emergency_stop(self):
        self.pm.trigger_emergency_stop()
        self.pm.clear_emergency_stop()
        assert self.pm.is_emergency_stopped is False

        check = self.pm.check(PermissionLevel.LEVEL_0_READ_ONLY, "get_datetime")
        assert check.allowed is True

    def test_directory_allowlist_enforcement(self, tmp_path):
        allowed_dir = tmp_path / "allowed"
        allowed_dir.mkdir()
        forbidden_dir = tmp_path / "forbidden"
        forbidden_dir.mkdir()

        pm = PermissionManager(allowed_directories=[allowed_dir])

        # Allowed path
        is_ok, err = pm.is_path_allowed(allowed_dir / "safe.txt")
        assert is_ok is True
        assert err == ""

        # Forbidden path
        is_ok, err = pm.is_path_allowed(forbidden_dir / "secret.txt")
        assert is_ok is False
        assert "outside approved directories" in err

        # Path traversal escaping allowed dir
        is_ok, err = pm.is_path_allowed(allowed_dir / ".." / "forbidden" / "secret.txt")
        assert is_ok is False
