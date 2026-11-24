"""
JARVIS AI — Entry Point

Run:  python main.py

This application uses a fully local AI and voice stack:
  AI Provider:  Ollama (http://127.0.0.1:11434) — model: qwen3.5:4b
  STT:          Faster-Whisper (local CPU inference)
  TTS:          Piper (local neural voice)
  Memory:       SQLite
  Tools:        26 registered across 4 categories
"""

import logging
import sys

from config.settings import settings
from core.agent import JarvisAgent
from interface.cli import JarvisCLI
from memory.database import DatabaseManager
from providers.factory import get_provider
from tools import calculator, datetime_tool, development, filesystem, productivity, system_automation
from tools.registry import ToolRegistry


def setup_logging() -> None:
    """Configure application logging (file + minimal console)."""
    log_file = settings.LOG_DIR / "jarvis.log"

    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stderr),
        ],
    )

    # Keep console quiet so it doesn't clutter the CLI
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.StreamHandler) and handler.stream is sys.stderr:
            handler.setLevel(logging.WARNING)

    # Suppress noisy third-party loggers
    for name in ("httpcore", "httpx", "urllib3", "urllib.request"):
        logging.getLogger(name).setLevel(logging.WARNING)


def register_tools(registry: ToolRegistry) -> None:
    """Register all available tools organized by category."""
    # Productivity: Calculator & DateTime
    registry.register(calculator.definition, calculator.calculate)
    registry.register(datetime_tool.definition, datetime_tool.get_datetime)

    # File Management
    registry.register(filesystem.list_files_definition, filesystem.list_files)
    registry.register(filesystem.create_folder_definition, filesystem.create_folder)
    registry.register(filesystem.create_file_definition, filesystem.create_file)
    registry.register(filesystem.read_file_definition, filesystem.read_file)
    registry.register(filesystem.search_files_definition, filesystem.search_files)
    registry.register(filesystem.file_exists_definition, filesystem.file_exists)
    registry.register(filesystem.rename_file_definition, filesystem.rename_file)
    registry.register(filesystem.copy_file_definition, filesystem.copy_file)
    registry.register(filesystem.move_file_definition, filesystem.move_file)
    registry.register(filesystem.delete_file_definition, filesystem.delete_file)

    # System Automation
    registry.register(system_automation.get_system_info_definition, system_automation.get_system_info)
    registry.register(system_automation.get_resource_usage_definition, system_automation.get_resource_usage)
    registry.register(system_automation.list_processes_definition, system_automation.list_processes)
    registry.register(system_automation.open_application_definition, system_automation.open_application)
    registry.register(system_automation.open_website_definition, system_automation.open_website)

    # Productivity
    registry.register(productivity.manage_notes_definition, productivity.manage_notes)
    registry.register(productivity.manage_reminders_definition, productivity.manage_reminders)
    registry.register(productivity.manage_tasks_definition, productivity.manage_tasks)
    registry.register(productivity.summarize_text_definition, productivity.summarize_text)

    # Development Assistance
    registry.register(development.create_python_file_definition, development.create_python_file)
    registry.register(development.read_code_file_definition, development.read_code_file)
    registry.register(development.explain_code_error_definition, development.explain_code_error)
    registry.register(development.run_python_script_definition, development.run_python_script)
    registry.register(development.execute_approved_command_definition, development.execute_approved_command)


def main() -> None:
    """Main entry point for JARVIS AI."""
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("JARVIS AI starting up…")

    # --- Validate settings ---
    errors = settings.validate()
    if errors:
        print("\n⚠️  Configuration errors:")
        for error in errors:
            print(f"   • {error}")
        print("\nPlease fix the errors above and try again.")
        print("See .env.example for configuration instructions.\n")
        sys.exit(1)

    # --- Create provider (Ollama) ---
    try:
        provider = get_provider(settings.AI_PROVIDER)
    except (ValueError, RuntimeError) as e:
        print(f"\n⚠️  Provider error: {e}\n")
        sys.exit(1)

    # --- Create tool registry ---
    registry = ToolRegistry()
    register_tools(registry)
    tool_count = len(registry.list_tools())
    logger.info("Registered %d tools.", tool_count)

    # --- Create database ---
    db = DatabaseManager()

    # --- Build the agent ---
    agent = JarvisAgent(
        provider=provider,
        registry=registry,
        db=db,
        approval_callback=JarvisCLI.approval_callback,
    )

    # --- Initialize (connects to Ollama, creates DB tables) ---
    print("\n🔄 Initializing JARVIS…")
    if not agent.initialize():
        print("\n⚠️  Failed to initialize JARVIS.")
        print("Please ensure Ollama is running: ollama serve")
        print(f"And that model '{settings.OLLAMA_MODEL}' is available: ollama list\n")
        sys.exit(1)

    # --- Launch the CLI (hands-free wake-word starts automatically if enabled) ---
    cli = JarvisCLI(agent)
    agent._approval_callback = cli.handle_approval_request
    cli.run()


if __name__ == "__main__":
    main()
