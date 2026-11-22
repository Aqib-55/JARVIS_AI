"""
System Automation tools for JARVIS AI.

Provides safe system inspection, resource monitoring, process listing,
and controlled application/website launching.
"""

import logging
import os
import platform
import subprocess
import webbrowser
from typing import Any

import psutil

from tools import PermissionLevel, ToolCategory, ToolDefinition, ToolParameter, ToolResult

logger = logging.getLogger(__name__)

# Whitelist of approved applications that can be launched
_APPROVED_APPS: dict[str, list[str]] = {
    "chrome": ["start", "chrome"],
    "google chrome": ["start", "chrome"],
    "notepad": ["notepad.exe"],
    "calculator": ["calc.exe"],
    "calc": ["calc.exe"],
    "explorer": ["explorer.exe"],
    "file explorer": ["explorer.exe"],
    "vs code": ["code"],
    "vscode": ["code"],
    "code": ["code"],
    "edge": ["start", "msedge"],
    "microsoft edge": ["start", "msedge"],
    "terminal": ["wt.exe"],
    "task manager": ["taskmgr.exe"],
}


def get_system_info() -> ToolResult:
    """Return fundamental system specifications and environment info."""
    try:
        info = {
            "os": platform.system(),
            "os_release": platform.release(),
            "os_version": platform.version(),
            "architecture": platform.machine(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
            "python_compiler": platform.python_compiler(),
            "hostname": platform.node(),
        }
        return ToolResult(success=True, result=info)
    except Exception as e:
        logger.error("Failed to get system info: %s", e)
        return ToolResult(success=False, error=f"Failed to get system info: {e}")


def get_resource_usage() -> ToolResult:
    """Check current CPU, RAM, and Disk utilization."""
    try:
        cpu_percent = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(os.path.abspath(os.sep))

        data = {
            "cpu_usage_percent": cpu_percent,
            "ram_total_gb": round(memory.total / (1024 ** 3), 2),
            "ram_used_gb": round(memory.used / (1024 ** 3), 2),
            "ram_free_gb": round(memory.available / (1024 ** 3), 2),
            "ram_usage_percent": memory.percent,
            "disk_total_gb": round(disk.total / (1024 ** 3), 2),
            "disk_used_gb": round(disk.used / (1024 ** 3), 2),
            "disk_free_gb": round(disk.free / (1024 ** 3), 2),
            "disk_usage_percent": disk.percent,
        }
        return ToolResult(success=True, result=data)
    except Exception as e:
        logger.error("Failed to get resource usage: %s", e)
        return ToolResult(success=False, error=f"Failed to get resource usage: {e}")


def list_processes(limit: int = 15, sort_by: str = "memory") -> ToolResult:
    """
    List currently running processes on the system.

    Args:
        limit: Maximum number of processes to return (default: 15, max: 50).
        sort_by: Metric to sort by: 'memory' or 'cpu'.
    """
    try:
        limit = min(max(1, limit), 50)
        processes = []

        for p in psutil.process_iter(['pid', 'name', 'memory_percent', 'cpu_percent', 'status']):
            try:
                pinfo = p.info
                processes.append({
                    "pid": pinfo['pid'],
                    "name": pinfo['name'] or "Unknown",
                    "memory_percent": round(pinfo['memory_percent'] or 0.0, 2),
                    "cpu_percent": round(pinfo['cpu_percent'] or 0.0, 2),
                    "status": pinfo['status'],
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        sort_key = "memory_percent" if sort_by == "memory" else "cpu_percent"
        processes.sort(key=lambda x: x.get(sort_key, 0), reverse=True)
        top = processes[:limit]

        return ToolResult(
            success=True,
            result={
                "process_count": len(top),
                "sorted_by": sort_by,
                "processes": top,
            },
        )
    except Exception as e:
        logger.error("Failed to list processes: %s", e)
        return ToolResult(success=False, error=f"Failed to list processes: {e}")


def open_application(app_name: str) -> ToolResult:
    """
    Launch an approved application on Windows.
    Arbitrary executable paths or shell commands are blocked for safety.
    """
    clean_name = app_name.strip().lower()
    command = _APPROVED_APPS.get(clean_name)

    if not command:
        available = ", ".join(sorted(set(_APPROVED_APPS.keys())))
        return ToolResult(
            success=False,
            error=f"Application '{app_name}' is not in the approved whitelist. Available applications: {available}",
        )

    try:
        if platform.system() == "Windows":
            if command[0] == "start":
                # Use os.system with sanitized command or shell=True
                os.system(f"start {command[1]}")
            else:
                subprocess.Popen(command, shell=False)
        else:
            subprocess.Popen(command)

        return ToolResult(
            success=True,
            result={"message": f"Successfully launched {app_name}.", "app": clean_name},
        )
    except Exception as e:
        logger.error("Failed to open application '%s': %s", app_name, e)
        return ToolResult(success=False, error=f"Failed to open '{app_name}': {e}")


def open_website(url: str) -> ToolResult:
    """
    Open an approved HTTP/HTTPS website URL in the default browser.
    """
    clean_url = url.strip()
    if not clean_url.startswith(("http://", "https://")):
        clean_url = f"https://{clean_url}"

    try:
        webbrowser.open(clean_url)
        return ToolResult(
            success=True,
            result={"message": f"Opened website: {clean_url}", "url": clean_url},
        )
    except Exception as e:
        logger.error("Failed to open website '%s': %s", url, e)
        return ToolResult(success=False, error=f"Failed to open website '{url}': {e}")


# ===================================================================
#  Tool definitions for the registry
# ===================================================================

get_system_info_definition = ToolDefinition(
    name="get_system_info",
    description="Get system specifications including OS, processor, architecture, and Python runtime info.",
    parameters=[],
    permission_level=PermissionLevel.LEVEL_0_READ_ONLY,
    category=ToolCategory.SYSTEM_AUTOMATION,
)

get_resource_usage_definition = ToolDefinition(
    name="get_resource_usage",
    description="Check real-time CPU, RAM, and Disk storage utilization on the computer.",
    parameters=[],
    permission_level=PermissionLevel.LEVEL_0_READ_ONLY,
    category=ToolCategory.SYSTEM_AUTOMATION,
)

list_processes_definition = ToolDefinition(
    name="list_processes",
    description="List currently running processes sorted by RAM or CPU consumption.",
    parameters=[
        ToolParameter(
            name="limit",
            type="integer",
            description="Number of top processes to return (default: 15, max: 50).",
            required=False,
        ),
        ToolParameter(
            name="sort_by",
            type="string",
            description="Sort metric: 'memory' or 'cpu'.",
            required=False,
            enum=["memory", "cpu"],
        ),
    ],
    permission_level=PermissionLevel.LEVEL_0_READ_ONLY,
    category=ToolCategory.SYSTEM_AUTOMATION,
)

open_application_definition = ToolDefinition(
    name="open_application",
    description="Open an approved application (e.g., Chrome, Notepad, Calculator, VS Code, Edge).",
    parameters=[
        ToolParameter(
            name="app_name",
            type="string",
            description="Name of the application to open (e.g. 'chrome', 'notepad', 'calculator', 'vs code').",
        ),
    ],
    permission_level=PermissionLevel.LEVEL_2_MODERATE_RISK,
    category=ToolCategory.SYSTEM_AUTOMATION,
)

open_website_definition = ToolDefinition(
    name="open_website",
    description="Open a website URL in the default web browser.",
    parameters=[
        ToolParameter(
            name="url",
            type="string",
            description="Website address or URL to open (e.g. 'google.com', 'https://github.com').",
        ),
    ],
    permission_level=PermissionLevel.LEVEL_1_LOW_RISK,
    category=ToolCategory.SYSTEM_AUTOMATION,
)
