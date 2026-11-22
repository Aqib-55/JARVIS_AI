"""
Command-Line Interface for JARVIS AI with Voice Integration.

Provides a terminal chat interface with commands:
/help, /status, /history, /tools, /memory, /voice, /speak, /stop, /resume, /clear, /exit.
Supports Text Mode, Push-to-Talk Voice Mode, and Continuous Conversation Mode.
"""

import logging
from typing import Any

from config.settings import settings
from core.agent import JarvisAgent
from core.permissions import PermissionCheck
from core.planner import TaskStep
from tools import ToolCategory
from voice.voice_controller import AudioState, VoiceController, VoiceMode

logger = logging.getLogger(__name__)


# ANSI colour codes for terminal output
class _C:
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


_HELP = f"""
{_C.CYAN}Available Commands:{_C.RESET}
  /help               — Show this help message
  /status             — Show system status, voice engine & connectivity
  /tools              — List all registered tools by category
  /history            — Show recent tasks and execution outcomes
  /memory [query]     — Search or view stored facts & preferences
  /voice [mode]       — Switch or trigger voice mode (ptt, continuous, text)
  /speak <text>       — Speak custom text aloud via TTS
  /stop               — Emergency Stop (halts active executions & speech)
  /resume             — Clear Emergency Stop and resume operations
  /clear              — Clear conversation history and start fresh
  /exit               — Shut down JARVIS
"""


class JarvisCLI:
    """Terminal-based chat and voice interface for JARVIS."""

    def __init__(
        self,
        agent: JarvisAgent,
        voice_controller: VoiceController | None = None,
    ) -> None:
        self._agent = agent

        # Initialize voice controller if enabled or provided
        if voice_controller is not None:
            self._voice = voice_controller
        elif settings.VOICE_ENABLED:
            try:
                self._voice = VoiceController(
                    agent=self._agent,
                    mode=VoiceMode(settings.VOICE_MODE) if settings.VOICE_MODE in [m.value for m in VoiceMode] else VoiceMode.PUSH_TO_TALK,
                    on_state_change=self._on_audio_state_change,
                    on_transcription=self._on_audio_transcription,
                )
            except Exception as e:
                logger.warning("Voice subsystem initialization failed, falling back to text-only: %s", e)
                self._voice = None
        else:
            self._voice = None

    # ------------------------------------------------------------------
    #  Audio State Callbacks
    # ------------------------------------------------------------------

    def _on_audio_state_change(self, state: AudioState) -> None:
        """Visual indicator of audio state transitions."""
        indicators = {
            AudioState.IDLE: f"{_C.DIM}[JARVIS] Ready.{_C.RESET}",
            AudioState.LISTENING: f"{_C.YELLOW}[JARVIS] 🎙️ Listening... (Speak now){_C.RESET}",
            AudioState.PROCESSING: f"{_C.CYAN}[JARVIS] ⚙️ Processing...{_C.RESET}",
            AudioState.SPEAKING: f"{_C.BLUE}[JARVIS] 🔊 Speaking...{_C.RESET}",
            AudioState.WAITING_FOR_APPROVAL: f"{_C.MAGENTA}[JARVIS] 🔐 Waiting for approval...{_C.RESET}",
            AudioState.ERROR: f"{_C.RED}[JARVIS] ⚠️ Audio Error.{_C.RESET}",
        }
        print(indicators.get(state, f"[JARVIS] {state.value}"))

    def _on_audio_transcription(self, text: str) -> None:
        """Display recognized speech in terminal."""
        print(f"{_C.GREEN}[VOICE] Recognized: {_C.BOLD}{text}{_C.RESET}")

    # ------------------------------------------------------------------
    #  Screens & Reporting
    # ------------------------------------------------------------------

    def _print_welcome(self) -> None:
        s = self._agent.get_status()
        connected = (
            f"{_C.GREEN}Connected{_C.RESET}"
            if s["connected"]
            else f"{_C.RED}Disconnected{_C.RESET}"
        )
        voice_status = (
            f"{_C.GREEN}Enabled ({self._voice.mode.value}){_C.RESET}"
            if self._voice
            else f"{_C.DIM}Disabled / Text-only{_C.RESET}"
        )
        stop_status = (
            f"  {_C.RED}⚠️ EMERGENCY STOP ACTIVE{_C.RESET}\n"
            if s.get("emergency_stopped")
            else ""
        )
        print(f"""
{_C.CYAN}{'=' * 58}
       ░░░  JARVIS AI — Personal Assistant & Agent  ░░░
{'=' * 58}{_C.RESET}

  {_C.GREEN}Status:{_C.RESET}   {connected}
  {_C.GREEN}Provider:{_C.RESET} {s['provider'].title()}
  {_C.GREEN}Model:{_C.RESET}    {s['model']}
  {_C.GREEN}Tools:{_C.RESET}    {s['tools']} registered across 4 categories
  {_C.GREEN}Memory:{_C.RESET}   {s['memory'].title()}
  {_C.GREEN}Voice:{_C.RESET}    {voice_status}
{stop_status}
  Type {_C.YELLOW}/help{_C.RESET} for commands or {_C.YELLOW}/voice{_C.RESET} for voice input.
{_C.CYAN}{'=' * 58}{_C.RESET}
""")

    def _print_status(self) -> None:
        s = self._agent.get_status()
        stop_state = f"{_C.RED}ACTIVE{_C.RESET}" if s.get("emergency_stopped") else f"{_C.GREEN}Normal{_C.RESET}"
        voice_diag = self._voice.get_diagnostics() if self._voice else {"mode": "disabled"}
        print(f"""
{_C.CYAN}System Status:{_C.RESET}
  Connected:      {"Yes" if s['connected'] else "No"}
  Provider:       {s['provider'].title()}
  Model:          {s['model']}
  Tools:          {s['tools']} registered
  Messages:       {s['conversation_messages']} in session
  Memory:         {s['memory'].title()}
  Emergency Stop: {stop_state}
  Voice Mode:     {voice_diag.get('mode')}
  STT Engine:     {voice_diag.get('stt_engine', 'None')}
  TTS Engine:     {voice_diag.get('tts_engine', 'None')}
""")

    def _print_tools(self) -> None:
        registry = self._agent.tool_registry
        tools = registry.list_tools()
        print(f"\n{_C.CYAN}Registered Tools ({len(tools)} total):{_C.RESET}")

        for cat in ToolCategory:
            cat_tools = [t for t in tools if t.category == cat]
            if cat_tools:
                print(f"\n  {_C.BOLD}{cat.value.replace('_', ' ').title()}:{_C.RESET}")
                for t in cat_tools:
                    print(f"    • {_C.GREEN}{t.name:<25}{_C.RESET} {_C.DIM}[{t.permission_level.value}]{_C.RESET} — {t.description[:60]}...")
        print()

    def _print_history(self) -> None:
        tasks = self._agent.get_recent_tasks()
        if not tasks:
            print(f"\n{_C.DIM}No task history recorded yet.{_C.RESET}\n")
            return

        icons = {
            "completed": "✅", "failed": "❌", "running": "🔄",
            "pending": "⏳", "cancelled": "🚫", "waiting_for_approval": "🔐",
        }
        print(f"\n{_C.CYAN}Recent Tasks:{_C.RESET}")
        for t in tasks:
            icon = icons.get(t["status"], "❓")
            preview = t["user_request"][:60]
            if len(t["user_request"]) > 60:
                preview += "…"
            print(f"  {icon} [{t['id']}] {preview} {_C.DIM}({t['status']}){_C.RESET}")
        print()

    def _print_memory(self, query: str = "") -> None:
        mem = self._agent.memory_manager
        if query:
            results = mem.search_memory(query, limit=5)
            print(f"\n{_C.CYAN}Memory Search Results for '{query}':{_C.RESET}")
            for cat, items in results.items():
                if items:
                    print(f"  {_C.BOLD}{cat.title()}:{_C.RESET}")
                    for item in items:
                        text = item.get("fact") or item.get("title") or item.get("user_request") or item.get("content")
                        print(f"    • {text}")
        else:
            facts = mem.get_facts(limit=10)
            prefs = mem.get_all_preferences()
            print(f"\n{_C.CYAN}Stored Facts ({len(facts)}):{_C.RESET}")
            for f in facts:
                print(f"  • [{f['category']}] {f['fact']}")
            if prefs:
                print(f"\n{_C.CYAN}User Preferences:{_C.RESET}")
                for k, v in prefs.items():
                    print(f"  • {k}: {v}")
        print()

    # ------------------------------------------------------------------
    #  Approval Callback
    # ------------------------------------------------------------------

    @staticmethod
    def approval_callback(step: TaskStep, check: PermissionCheck) -> bool:
        """Prompt user for confirmation when executing Level 2 or Level 3 operations."""
        risk_name = check.risk_level.value.replace("_", " ").upper()
        print(f"\n{_C.YELLOW}{'=' * 50}{_C.RESET}")
        print(f"{_C.YELLOW}🔐 Confirmation Required [{risk_name}]{_C.RESET}")
        print(f"   Tool:   {step.tool_name}")
        print(f"   Args:   {step.arguments}")
        print(f"   Reason: {check.reason}")
        print(f"{_C.YELLOW}{'=' * 50}{_C.RESET}")

        while True:
            answer = input(f"\n   {_C.YELLOW}Approve execution? (yes/no): {_C.RESET}").strip().lower()
            if answer in ("yes", "y"):
                return True
            if answer in ("no", "n"):
                return False
            print("   Please enter 'yes' or 'no'.")

    # ------------------------------------------------------------------
    #  Command Dispatcher
    # ------------------------------------------------------------------

    def _handle_command(self, command: str) -> bool:
        """Handle a /command. Returns False when user requests shutdown."""
        parts = command.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "/exit":
            if self._voice:
                self._voice.stop_speaking()
                self._voice.cancel_listening()
            print(f"\n{_C.CYAN}Goodbye! JARVIS shutting down…{_C.RESET}\n")
            self._agent.shutdown()
            return False

        if cmd == "/help":
            print(_HELP)
        elif cmd == "/status":
            self._print_status()
        elif cmd == "/tools":
            self._print_tools()
        elif cmd == "/history":
            self._print_history()
        elif cmd == "/memory":
            self._print_memory(arg)

        elif cmd == "/voice":
            if not self._voice:
                print(f"\n{_C.RED}Voice subsystem is disabled or unavailable.{_C.RESET}\n")
                return True

            mode_arg = arg.strip().lower()
            if mode_arg in ("ptt", "push_to_talk", ""):
                print(f"\n{_C.CYAN}[VOICE] Push-to-Talk activated. Listening...{_C.RESET}")
                reply = self._voice.listen_and_process()
                if reply:
                    print(f"\n{_C.BLUE}Jarvis:{_C.RESET} {reply}\n")
            elif mode_arg in ("continuous", "cont"):
                print(f"\n{_C.CYAN}[VOICE] Continuous mode started. Say 'Jarvis, stop listening' or press Ctrl+C to stop.{_C.RESET}\n")
                try:
                    self._voice.run_continuous_listening(
                        on_turn_complete=lambda inp, out: print(f"\n{_C.BLUE}Jarvis:{_C.RESET} {out}\n")
                    )
                except KeyboardInterrupt:
                    print(f"\n{_C.YELLOW}Continuous voice mode halted.{_C.RESET}\n")
            elif mode_arg == "text":
                self._voice.set_mode(VoiceMode.TEXT)
                print(f"\n{_C.GREEN}Switched to Text Mode.{_C.RESET}\n")
            else:
                print(f"Unknown voice mode: '{arg}'. Options: ptt, continuous, text")

        elif cmd == "/speak":
            if not self._voice:
                print(f"\n{_C.RED}Voice output is unavailable.{_C.RESET}\n")
            elif not arg:
                print("Usage: /speak <text to speak>")
            else:
                self._voice.speak_response(arg)

        elif cmd in ("/stop", "/emergency-stop"):
            if self._voice:
                self._voice.stop_speaking()
                self._voice.cancel_listening()
            self._agent.trigger_emergency_stop("Triggered by user command /stop.")
            print(f"\n{_C.RED}🛑 EMERGENCY STOP ACTIVATED. All tool executions and speech halted.{_C.RESET}")
            print(f"Type {_C.YELLOW}/resume{_C.RESET} to resume normal operations.\n")

        elif cmd == "/resume":
            self._agent.clear_emergency_stop()
            print(f"\n{_C.GREEN}✅ Emergency stop cleared. Normal operations resumed.{_C.RESET}\n")

        elif cmd == "/clear":
            self._agent.clear_conversation()
            print(f"\n{_C.GREEN}Conversation cleared. New session started.{_C.RESET}\n")

        else:
            print(f"\n{_C.RED}Unknown command: {command}{_C.RESET}")
            print(f"Type {_C.YELLOW}/help{_C.RESET} for available commands.\n")

        return True

    # ------------------------------------------------------------------
    #  Main Interactive Loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Run the interactive chat and voice loop."""
        self._print_welcome()

        while True:
            try:
                user_input = input(f"{_C.GREEN}You: {_C.RESET}").strip()

                if not user_input:
                    continue

                if user_input.startswith("/"):
                    if not self._handle_command(user_input):
                        break
                    continue

                # Process via Agent
                print(f"\n{_C.DIM}Thinking…{_C.RESET}")
                response = self._agent.process_message(user_input)
                print(f"\n{_C.BLUE}Jarvis:{_C.RESET} {response}\n")

                # If voice is enabled and mode is not text-only, speak response
                if self._voice and self._voice.mode != VoiceMode.TEXT:
                    self._voice.speak_response(response)

            except KeyboardInterrupt:
                if self._voice:
                    self._voice.stop_speaking()
                    self._voice.cancel_listening()
                print(f"\n\n{_C.CYAN}Goodbye! JARVIS shutting down…{_C.RESET}\n")
                self._agent.shutdown()
                break
            except EOFError:
                if self._voice:
                    self._voice.stop_speaking()
                    self._voice.cancel_listening()
                print(f"\n{_C.CYAN}Session ended.{_C.RESET}\n")
                self._agent.shutdown()
                break
