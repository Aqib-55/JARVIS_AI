"""Tests for the permission manager."""

from core.permissions import PermissionManager
from tools import PermissionLevel


class TestPermissionManager:

    def setup_method(self):
        self.pm = PermissionManager()

    def test_read_only_allowed(self):
        check = self.pm.check(PermissionLevel.READ_ONLY, "get_datetime")
        assert check.allowed is True
        assert check.needs_approval is False

    def test_safe_write_allowed(self):
        check = self.pm.check(PermissionLevel.SAFE_WRITE, "create_folder")
        assert check.allowed is True
        assert check.needs_approval is False

    def test_destructive_needs_approval(self):
        check = self.pm.check(PermissionLevel.DESTRUCTIVE, "delete_file")
        assert check.allowed is False
        assert check.needs_approval is True

    def test_external_needs_approval(self):
        check = self.pm.check(PermissionLevel.EXTERNAL, "send_email")
        assert check.allowed is False
        assert check.needs_approval is True

    def test_approve_destructive(self):
        check = self.pm.check(PermissionLevel.DESTRUCTIVE, "delete_file")
        assert check.needs_approval is True

        approved = self.pm.approve(check)
        assert approved.allowed is True
        assert approved.needs_approval is False
