"""
Date and Time tool — provides current date, time, and timezone information.
"""

import logging
import time as _time
from datetime import datetime, timezone as tz

from tools import ToolCategory, ToolDefinition, ToolParameter, PermissionLevel, ToolResult

logger = logging.getLogger(__name__)


def get_datetime(detail: str = "full") -> ToolResult:
    """
    Get current date and time information.

    Args:
        detail: What to return — "date", "time", "weekday", "timezone", or "full".
    """
    try:
        now = datetime.now()

        # Local timezone info
        local_tz_name = (
            _time.tzname[_time.daylight] if _time.daylight else _time.tzname[0]
        )
        utc_offset_seconds = -_time.timezone if not _time.daylight else -_time.altzone
        utc_offset_hours = utc_offset_seconds / 3600

        result: dict = {}

        if detail in ("date", "full"):
            result["date"] = now.strftime("%Y-%m-%d")
            result["date_formatted"] = now.strftime("%A, %B %d, %Y")

        if detail in ("time", "full"):
            result["time"] = now.strftime("%H:%M:%S")
            result["time_12h"] = now.strftime("%I:%M:%S %p")

        if detail in ("weekday", "full"):
            result["weekday"] = now.strftime("%A")

        if detail in ("timezone", "full"):
            result["timezone"] = local_tz_name
            sign = "+" if utc_offset_hours >= 0 else ""
            result["utc_offset"] = f"UTC{sign}{utc_offset_hours:.1f}"

        if not result:
            return ToolResult(
                success=False,
                error=(
                    f"Unknown detail type: '{detail}'. "
                    "Use: date, time, weekday, timezone, or full."
                ),
            )

        return ToolResult(success=True, result=result)

    except Exception as e:
        logger.error("DateTime tool error: %s", e)
        return ToolResult(success=False, error=f"Failed to get date/time: {e}")


# ---- Tool definition for the registry ----
definition = ToolDefinition(
    name="get_datetime",
    description="Get current date, time, weekday, or timezone.",
    parameters=[
        ToolParameter(
            name="detail",
            type="string",
            description="Detail level.",
            required=False,
            enum=["date", "time", "weekday", "timezone", "full"],
        ),
    ],
    permission_level=PermissionLevel.LEVEL_0_READ_ONLY,
    category=ToolCategory.PRODUCTIVITY,
)
