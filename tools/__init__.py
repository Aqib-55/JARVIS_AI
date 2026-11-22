"""
JARVIS AI tools module.

Tools are the actions JARVIS can perform on behalf of the user.
Each tool is registered with the ToolRegistry and has a defined
input schema, permission level, category, and execution function.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PermissionLevel(str, Enum):
    """
    Standardized 4-tier permission model for JARVIS tools.

    - LEVEL 0 (Read-Only): Safe inspection, queries, listings.
    - LEVEL 1 (Low Risk): Safe additions (creating folders, notes, files).
    - LEVEL 2 (Moderate Risk): Modifications, moves, renames, approved script execution.
    - LEVEL 3 (High Risk): Destructive operations (deletion, system configuration changes).
    """
    LEVEL_0_READ_ONLY = "level_0_read_only"
    LEVEL_1_LOW_RISK = "level_1_low_risk"
    LEVEL_2_MODERATE_RISK = "level_2_moderate_risk"
    LEVEL_3_HIGH_RISK = "level_3_high_risk"

    # Backward compatibility aliases for existing codebase & tests
    READ_ONLY = "level_0_read_only"
    SAFE_WRITE = "level_1_low_risk"
    DESTRUCTIVE = "level_3_high_risk"
    EXTERNAL = "level_2_moderate_risk"


class ToolCategory(str, Enum):
    """Categories for JARVIS tools."""
    FILE_MANAGEMENT = "file_management"
    SYSTEM_AUTOMATION = "system_automation"
    PRODUCTIVITY = "productivity"
    DEVELOPMENT = "development"


@dataclass
class ToolResult:
    """Standardized result from any tool execution."""
    success: bool
    result: Any = None
    error: str | None = None
    execution_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for model consumption."""
        data: dict[str, Any] = {
            "status": "success" if self.success else "error"
        }
        if self.success:
            data["result"] = self.result
        else:
            data["error"] = self.error
        if self.execution_time_ms > 0:
            data["execution_time_ms"] = round(self.execution_time_ms, 2)
        return data


@dataclass
class ToolParameter:
    """Definition of a single tool parameter."""
    name: str
    type: str                       # "string", "number", "integer", "boolean", "array", "object"
    description: str
    required: bool = True
    enum: list[str] | None = None   # Allowed values, if restricted
    default: Any = None


@dataclass
class ToolDefinition:
    """Complete definition of a registered tool."""
    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)
    permission_level: PermissionLevel = PermissionLevel.LEVEL_0_READ_ONLY
    category: ToolCategory = ToolCategory.PRODUCTIVITY
    timeout_seconds: float = 30.0

    def to_declaration(self) -> dict[str, Any]:
        """
        Convert to the JSON-schema format expected by AI providers.

        This format is passed to Gemini's function_declarations so the
        model knows which tools are available and what arguments they accept.
        """
        properties: dict[str, Any] = {}
        required: list[str] = []

        for param in self.parameters:
            prop: dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            properties[param.name] = prop
            if param.required:
                required.append(param.name)

        declaration: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
        }
        if properties:
            declaration["parameters"] = {
                "type": "object",
                "properties": properties,
                "required": required,
            }
        return declaration
