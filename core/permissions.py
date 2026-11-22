"""
Permission Manager — controls tool authorizations, risk levels, and safety policies.

Implements the 4-tier permission model:
- LEVEL 0: READ ONLY (always permitted)
- LEVEL 1: LOW RISK (safe additions, permitted without confirmation)
- LEVEL 2: MODERATE RISK (modifications, moves, renames, approved scripts - requires confirmation)
- LEVEL 3: HIGH RISK (deletions, administrative changes - requires explicit confirmation)

Also provides:
- Global Emergency Stop mechanism
- Directory Allowlist management & path safety checks
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config.settings import settings
from tools import PermissionLevel

logger = logging.getLogger(__name__)


@dataclass
class PermissionCheck:
    """Result of a permission authorization check."""
    allowed: bool
    needs_approval: bool
    reason: str
    risk_level: PermissionLevel = PermissionLevel.LEVEL_0_READ_ONLY


class PermissionManager:
    """
    Evaluates and enforces permission policies across all tool actions.
    """

    def __init__(self, allowed_directories: list[Path] | None = None) -> None:
        self._emergency_stop: bool = False
        self._emergency_reason: str = ""

        # Default allowed directories: always includes workspace
        self._allowed_directories: list[Path] = [
            settings.WORKSPACE_DIR.resolve()
        ]
        if allowed_directories:
            for p in allowed_directories:
                self.add_allowed_directory(p)

    # ------------------------------------------------------------------
    #  Emergency Stop Controls
    # ------------------------------------------------------------------

    @property
    def is_emergency_stopped(self) -> bool:
        """Check if global emergency stop is active."""
        return self._emergency_stop

    @property
    def emergency_reason(self) -> str:
        """Reason why emergency stop was engaged."""
        return self._emergency_reason

    def trigger_emergency_stop(self, reason: str = "User triggered emergency stop.") -> None:
        """Immediately halt all tool executions across the entire agent."""
        self._emergency_stop = True
        self._emergency_reason = reason
        logger.critical("EMERGENCY STOP ACTIVATED: %s", reason)

    def clear_emergency_stop(self) -> None:
        """Reset emergency stop and resume normal operations."""
        self._emergency_stop = False
        self._emergency_reason = ""
        logger.warning("EMERGENCY STOP CLEARED. Normal operations resumed.")

    # ------------------------------------------------------------------
    #  Directory Allowlists
    # ------------------------------------------------------------------

    def add_allowed_directory(self, path: Path | str) -> None:
        """Add an approved directory to the allowlist."""
        resolved = Path(path).resolve()
        if resolved not in self._allowed_directories:
            self._allowed_directories.append(resolved)
            logger.info("Added allowed directory: %s", resolved)

    def is_path_allowed(self, target_path: Path | str) -> tuple[bool, str]:
        """
        Check if a given path falls within an allowed directory.
        Strictly prevents path traversal outside authorized roots.
        """
        try:
            resolved = Path(target_path).resolve()
            for allowed in self._allowed_directories:
                try:
                    resolved.relative_to(allowed)
                    return True, ""
                except ValueError:
                    continue

            allowed_str = ", ".join(str(d) for d in self._allowed_directories)
            return False, f"Access denied: '{target_path}' is outside approved directories ({allowed_str})."
        except Exception as e:
            return False, f"Invalid path '{target_path}': {e}"

    # ------------------------------------------------------------------
    #  Permission Authorization
    # ------------------------------------------------------------------

    def check(
        self,
        permission_level: PermissionLevel,
        tool_name: str,
        args: dict[str, Any] | None = None,
    ) -> PermissionCheck:
        """
        Check whether an action is permitted under the 4-tier security model.

        Policy:
        - Emergency stop: BLOCKS EVERYTHING.
        - LEVEL 0: Allowed, no approval needed.
        - LEVEL 1: Allowed, no approval needed.
        - LEVEL 2: Moderate risk (requires confirmation).
        - LEVEL 3: High risk (requires explicit confirmation).
        """
        if self._emergency_stop:
            return PermissionCheck(
                allowed=False,
                needs_approval=False,
                reason=f"Execution blocked by EMERGENCY STOP: {self._emergency_reason}",
                risk_level=permission_level,
            )

        # Level 0: Read Only
        if permission_level in (PermissionLevel.LEVEL_0_READ_ONLY, PermissionLevel.READ_ONLY):
            return PermissionCheck(
                allowed=True,
                needs_approval=False,
                reason="Level 0 (Read-Only): Safe inspection — no approval required.",
                risk_level=PermissionLevel.LEVEL_0_READ_ONLY,
            )

        # Level 1: Low Risk (Safe additions)
        if permission_level in (PermissionLevel.LEVEL_1_LOW_RISK, PermissionLevel.SAFE_WRITE):
            return PermissionCheck(
                allowed=True,
                needs_approval=False,
                reason="Level 1 (Low Risk): Safe addition — no approval required.",
                risk_level=PermissionLevel.LEVEL_1_LOW_RISK,
            )

        # Level 2: Moderate Risk (Modifications, renames, moves, script runs)
        if permission_level in (PermissionLevel.LEVEL_2_MODERATE_RISK, PermissionLevel.EXTERNAL):
            return PermissionCheck(
                allowed=False,
                needs_approval=True,
                reason=f"Level 2 (Moderate Risk): Tool '{tool_name}' modifies files, moves data, or runs scripts. Confirmation required.",
                risk_level=PermissionLevel.LEVEL_2_MODERATE_RISK,
            )

        # Level 3: High Risk (Deletions, administrative actions)
        if permission_level in (PermissionLevel.LEVEL_3_HIGH_RISK, PermissionLevel.DESTRUCTIVE):
            return PermissionCheck(
                allowed=False,
                needs_approval=True,
                reason=f"Level 3 (High Risk): Tool '{tool_name}' performs destructive or irreversible actions. Explicit confirmation required.",
                risk_level=PermissionLevel.LEVEL_3_HIGH_RISK,
            )

        # Unknown level — deny by default
        logger.warning("Unknown permission level: %s for tool %s", permission_level, tool_name)
        return PermissionCheck(
            allowed=False,
            needs_approval=True,
            reason=f"Unknown permission level for tool '{tool_name}'. Defaulting to requiring approval.",
            risk_level=PermissionLevel.LEVEL_3_HIGH_RISK,
        )

    def approve(self, check: PermissionCheck) -> PermissionCheck:
        """Grant user approval for an action that required confirmation."""
        return PermissionCheck(
            allowed=True,
            needs_approval=False,
            reason=f"User approved: {check.reason}",
            risk_level=check.risk_level,
        )
