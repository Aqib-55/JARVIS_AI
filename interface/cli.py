"""
Command-Line Interface for JARVIS AI with Voice Integration.

Provides a terminal chat interface with commands:
/help, /status, /history, /tools, /memory, /voice, /speak, /stop, /resume, /clear, /exit.
Supports Text Mode, Push-to-Talk Voice Mode, and Continuous Conversation Mode.
"""

import logging
import threading
from typing import Any

from config.settings import settings
from core.agent import JarvisAgent
from core.permissions import PermissionCheck
from core.planner import TaskStep
from tools import ToolCategory
from voice.conversation_manager import HandsFreeConversationManager, VoicePipelineState
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
  /voice on           — Enable hands-free wake-word & microphone monitoring
  /voice off          — Disable hands-free wake-word & stop microphone access
  /voice status       — Show actual wake-word, mic, STT, and TTS status
  /voice test         — Test microphone, wake-word model, STT and TTS
  /voice [mode]       — Trigger push-to-talk, or switch mode (ptt, continuous, text)
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
        hands_free_manager: HandsFreeConversationManager | None = None,
        auto_start_wake_word: bool = True,
    ) -> None:
        self._agent = agent
        self._agent_lock = threading.RLock()
        self._main_thread_id = threading.get_ident()
        self._approval_lock = threading.Lock()
        self._pending_approval_event: threading.Event | None = None
        self._pending_approval_answer: bool = False

        # Initialize voice controller if enabled or provided
        if voice_controller is not None:
            self._voice = voice_controller
        elif settings.VOICE_ENABLED:
            try:
                mode_val = settings.VOICE_MODE
                if mode_val == "hands_free":
                    vc_mode = VoiceMode.CONTINUOUS
                elif mode_val in [m.value for m in VoiceMode]:
                    vc_mode = VoiceMode(mode_val)
                else:
                    vc_mode = VoiceMode.PUSH_TO_TALK
                self._voice = VoiceController(
                    agent=self._agent,
                    mode=vc_mode,
                    on_state_change=self._on_audio_state_change,
                    on_transcription=self._on_audio_transcription,
                    on_speech_unavailable=self._on_speech_unavailable,
                )
            except Exception as e:
                logger.warning("Voice subsystem initialization failed, falling back to text-only: %s", e)
                self._voice = None
        else:
            self._voice = None

        # Initialize hands-free wake-word manager when using real voice controller
        if hands_free_manager is not None:
            self._hands_free: HandsFreeConversationManager | None = hands_free_manager
        elif self._voice is not None and voice_controller is None:
            self._hands_free = HandsFreeConversationManager(
                agent=self._agent,
                voice_controller=self._voice,
                agent_lock=self._agent_lock,
            )
            if (
                auto_start_wake_word
                and settings.VOICE_INPUT_ENABLED
                and settings.WAKE_WORD_ENABLED
                and settings.VOICE_MODE != "text"
            ):
                self._hands_free.start()
        else:
            self._hands_free = None

        if self._voice is not None:
            self._agent.set_voice_diagnostics_provider(self._combined_voice_diagnostics)

    def _combined_voice_diagnostics(self) -> dict[str, Any]:
        diag = self._voice.get_diagnostics() if self._voice else {}
        if self._hands_free is not None:
            hf = self._hands_free.get_status()
            diag.update(
                {
                    "wake_detection_enabled": hf.get("wake_detection_enabled", False),
                    "wake_word_phrase": hf.get("wake_word_phrase"),
                    "mic_monitoring": hf.get("mic_monitoring", False),
                    "pipeline_state": hf.get("pipeline_state"),
                }
            )
        return diag

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

    def _on_speech_unavailable(self, reason: str) -> None:
        """Display accurate message when TTS synthesis/playback fails."""
        detail = f" ({reason})" if reason else ""
        print(f"{_C.YELLOW}[JARVIS] 🔇 Speech output unavailable{detail}{_C.RESET}")

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

        # Build live voice & wake-word diagnostics
        stt_label = "Disabled"
        tts_label = "Disabled"
        wake_active = False
        wake_status_line = f"{_C.DIM}Disabled{_C.RESET}"
        voice_mode_label = "Text"
        warning_lines: list[str] = []

        if self._voice:
            vd = self._voice.get_diagnostics()
            stt_ok = vd.get("stt_available", False)
            tts_ok = vd.get("tts_available", False)
            raw_stt = vd.get("stt_engine", "Unknown")
            raw_tts = vd.get("tts_engine", "Unknown")
            stt_nice = "Faster-Whisper" if "Whisper" in raw_stt else raw_stt
            tts_nice = "Piper" if "Piper" in raw_tts else raw_tts

            stt_label = (
                f"{_C.GREEN}{stt_nice}{_C.RESET}"
                if stt_ok
                else f"{_C.RED}{stt_nice} (unavailable){_C.RESET}"
            )
            tts_label = (
                f"{_C.GREEN}{tts_nice}{_C.RESET}"
                if tts_ok
                else f"{_C.RED}{tts_nice} (unavailable){_C.RESET}"
            )
            if not settings.VOICE_INPUT_ENABLED:
                stt_label = f"{_C.DIM}Disabled{_C.RESET}"

            if self._hands_free is not None:
                hf = self._hands_free.get_status()
                wake_active = bool(hf.get("wake_detection_enabled", False))
                if wake_active:
                    wake_status_line = f"{_C.GREEN}Enabled{_C.RESET}"
                    voice_mode_label = "Hands-Free"
                elif not settings.VOICE_INPUT_ENABLED or not settings.WAKE_WORD_ENABLED:
                    wake_status_line = f"{_C.DIM}Disabled{_C.RESET}"
                    voice_mode_label = "Text" if self._voice.mode == VoiceMode.TEXT else "Push-to-Talk"
                else:
                    wake_status_line = f"{_C.RED}Unavailable{_C.RESET}"
                    voice_mode_label = "Text (fallback)"
                    if hf.get("last_error"):
                        warning_lines.append(f"  {_C.YELLOW}⚠️  Wake word / mic warning: {hf['last_error']}{_C.RESET}")
            else:
                voice_mode_label = vd.get("mode", settings.VOICE_MODE).replace("_", " ").title()

        local_only = f"{_C.GREEN}Enabled{_C.RESET}" if settings.LOCAL_AI_ONLY else f"{_C.YELLOW}Disabled{_C.RESET}"
        wake_phrase_display = settings.WAKE_WORD_PHRASE.title().replace("Jarvis", "JARVIS")
        stop_status = (
            f"  {_C.RED}⚠️ EMERGENCY STOP ACTIVE{_C.RESET}\n"
            if s.get("emergency_stopped")
            else ""
        )
        warnings_block = ("\n" + "\n".join(warning_lines) + "\n") if warning_lines else ""
        activation_hint = (
            f'  Say {_C.YELLOW}"Hey JARVIS"{_C.RESET} to activate.'
            if wake_active
            else f"  Use {_C.YELLOW}/voice on{_C.RESET} for hands-free mode or {_C.YELLOW}/voice{_C.RESET} for push-to-talk."
        )

        print(f"""
{_C.CYAN}{'=' * 58}
       JARVIS AI — LOCAL PERSONAL ASSISTANT
{'=' * 58}{_C.RESET}

  {_C.GREEN}Status:{_C.RESET} {connected}
  {_C.GREEN}Provider:{_C.RESET} {s['provider'].title()}
  {_C.GREEN}Model:{_C.RESET} {s['model']}
  {_C.GREEN}Local AI Only:{_C.RESET} {local_only}

  {_C.GREEN}Tools:{_C.RESET} {s['tools']} registered across 4 categories
  {_C.GREEN}Memory:{_C.RESET} {s['memory'].title()}

  {_C.GREEN}Voice Input:{_C.RESET} {stt_label}
  {_C.GREEN}Voice Output:{_C.RESET} {tts_label}

  {_C.GREEN}Wake Word:{_C.RESET} {wake_phrase_display}
  {_C.GREEN}Wake Detection:{_C.RESET} {wake_status_line}
  {_C.GREEN}Voice Mode:{_C.RESET} {voice_mode_label}
{stop_status}{warnings_block}
  Type {_C.YELLOW}/help{_C.RESET} for commands.
{activation_hint}
{_C.CYAN}{'=' * 58}{_C.RESET}
""")

    def _print_status(self) -> None:
        s = self._agent.get_status()
        stop_state = f"{_C.RED}ACTIVE{_C.RESET}" if s.get("emergency_stopped") else f"{_C.GREEN}Normal{_C.RESET}"
        voice_diag = self._voice.get_diagnostics() if self._voice else {"mode": "disabled"}
        hf_diag = self._hands_free.get_status() if self._hands_free else {}
        print(f"""
{_C.CYAN}System Status:{_C.RESET}
  Connected:       {"Yes" if s['connected'] else "No"}
  Provider:        {s['provider'].title()}
  Model:           {s['model']}
  Tools:           {s['tools']} registered
  Messages:        {s['conversation_messages']} in session
  Memory:          {s['memory'].title()}
  Emergency Stop:  {stop_state}
  Voice Mode:      {voice_diag.get('mode')}
  STT Engine:      {voice_diag.get('stt_engine', 'None')} (available: {voice_diag.get('stt_available', False)})
  TTS Engine:      {voice_diag.get('tts_engine', 'None')} (available: {voice_diag.get('tts_available', False)})
  Wake Detection:  {"Enabled" if hf_diag.get('wake_detection_enabled') else "Disabled"} ({hf_diag.get('pipeline_state', 'N/A')})
  Mic Monitoring:  {"Active" if hf_diag.get('mic_monitoring') else "Stopped"} ({hf_diag.get('mic_device', 'N/A')})
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

    def handle_approval_request(self, step: TaskStep, check: PermissionCheck) -> bool:
        """
        Thread-safe approval handler that prevents the background voice worker
        from calling input() concurrently with the main CLI prompt.
        """
        if threading.get_ident() == self._main_thread_id:
            return self.approval_callback(step, check)

        risk_name = check.risk_level.value.replace("_", " ").upper()
        print(f"\n{_C.YELLOW}{'=' * 50}{_C.RESET}")
        print(f"{_C.YELLOW}🔐 Confirmation Required [{risk_name}]{_C.RESET}")
        print(f"   Tool:   {step.tool_name}")
        print(f"   Args:   {step.arguments}")
        print(f"   Reason: {check.reason}")
        print(f"   {_C.YELLOW}Type 'yes' or 'no' at the prompt to approve/deny:{_C.RESET}")
        print(f"{_C.YELLOW}{'=' * 50}{_C.RESET}")

        ev = threading.Event()
        with self._approval_lock:
            self._pending_approval_event = ev
            self._pending_approval_answer = False

        if self._voice and settings.VOICE_OUTPUT_ENABLED:
            try:
                self._voice.speak_response(
                    f"Confirmation required for {step.tool_name}. Please type yes or no."
                )
            except Exception:
                pass

        approved = False
        if ev.wait(timeout=60.0):
            with self._approval_lock:
                approved = self._pending_approval_answer
        with self._approval_lock:
            self._pending_approval_event = None
        return approved

    def _shutdown_voice(self) -> None:
        if self._hands_free is not None:
            self._hands_free.stop()
        if self._voice:
            self._voice.stop_speaking()
            self._voice.cancel_listening()

    def _print_voice_status(self) -> None:
        if not self._voice:
            print(f"\n{_C.RED}Voice subsystem is disabled.{_C.RESET}\n")
            return
        if self._hands_free is not None:
            st = self._hands_free.get_status()
            print(f"\n{_C.CYAN}Voice & Wake-Word Status:{_C.RESET}")
            print(f"  Pipeline State:        {st['pipeline_state']}")
            print(f"  Wake Word Phrase:      {st['wake_word_phrase']}")
            print(f"  Wake Word Available:   {st['wake_word_available']}")
            print(f"  Wake Detection Active: {st['wake_detection_enabled']}")
            print(f"  Microphone Monitoring: {'Active' if st['mic_monitoring'] else 'Stopped'}")
            print(f"  Microphone Device:     {st['mic_device']}")
            print(f"  STT Engine:            {st['stt_engine']} (available: {st['stt_available']})")
            print(f"  TTS Engine:            {st['tts_engine']} (available: {st['tts_available']})")
            print(f"  Conversation Timeout:  {st['conversation_timeout_seconds']}s")
            if st.get("last_error"):
                print(f"  Last Error:            {_C.RED}{st['last_error']}{_C.RESET}")
            print()
        else:
            vd = self._voice.get_diagnostics()
            print(f"\n{_C.CYAN}Voice Status:{_C.RESET}")
            for k, v in vd.items():
                print(f"  {k}: {v}")
            print()

    def _run_voice_test(self) -> None:
        if self._hands_free is None:
            print(f"\n{_C.YELLOW}Hands-free manager not initialized.{_C.RESET}\n")
            return
        print(f"\n{_C.CYAN}Running Voice Subsystem Diagnostic Test...{_C.RESET}")
        res = self._hands_free.run_self_test()
        mic = res.get("microphone", {})
        ww = res.get("wake_word", {})
        stt = res.get("stt", {})
        tts = res.get("tts", {})
        print(f"  Microphone:  {'✅ PASS' if mic.get('ok') else '❌ FAIL'} ({mic.get('device', '')}, samples={mic.get('samples', 0)})")
        print(f"  Wake Word:   {'✅ PASS' if ww.get('ok') else '❌ FAIL'} ({ww.get('phrase', ww.get('error', ''))})")
        print(f"  STT Engine:  {'✅ PASS' if stt.get('ok') else '❌ FAIL'} ({stt.get('engine', '')} {stt.get('error', '')})")
        print(f"  TTS Engine:  {'✅ PASS' if tts.get('ok') else '❌ FAIL'} ({tts.get('engine', '')} {tts.get('error', '')})")
        print()

    # ------------------------------------------------------------------
    #  Command Dispatcher
    # ------------------------------------------------------------------

    def _handle_command(self, command: str) -> bool:
        """Handle a /command. Returns False when user requests shutdown."""
        parts = command.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "/exit":
            self._shutdown_voice()
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
            if mode_arg == "on":
                if self._hands_free is None:
                    self._hands_free = HandsFreeConversationManager(
                        agent=self._agent,
                        voice_controller=self._voice,
                        agent_lock=self._agent_lock,
                    )
                if self._hands_free.start():
                    print(f"\n{_C.GREEN}[VOICE] Hands-free wake-word monitoring enabled. Say 'Hey JARVIS'.{_C.RESET}\n")
                else:
                    print(f"\n{_C.RED}[VOICE] Could not enable hands-free mode: {self._hands_free.last_error}{_C.RESET}\n")
            elif mode_arg == "off":
                if self._hands_free is not None:
                    self._hands_free.stop()
                self._voice.stop_speaking()
                self._voice.cancel_listening()
                self._voice.set_mode(VoiceMode.TEXT)
                print(f"\n{_C.YELLOW}[VOICE] Microphone monitoring stopped and voice mode disabled.{_C.RESET}\n")
            elif mode_arg == "status":
                self._print_voice_status()
            elif mode_arg == "test":
                self._run_voice_test()
            elif mode_arg in ("ptt", "push_to_talk", ""):
                print(f"\n{_C.CYAN}[VOICE] Push-to-Talk activated. Listening...{_C.RESET}")
                if self._hands_free is not None:
                    reply = self._hands_free.trigger_push_to_talk()
                    if reply and not self._hands_free.is_monitoring:
                        print(f"\n{_C.BLUE}Jarvis:{_C.RESET} {reply}\n")
                else:
                    with self._agent_lock:
                        reply = self._voice.listen_and_process()
                    if reply:
                        print(f"\n{_C.BLUE}Jarvis:{_C.RESET} {reply}\n")
            elif mode_arg in ("continuous", "cont"):
                if self._hands_free is not None and self._hands_free.start():
                    print(f"\n{_C.GREEN}[VOICE] Hands-free continuous wake-word mode active.{_C.RESET}\n")
                else:
                    print(f"\n{_C.CYAN}[VOICE] Continuous mode started. Say 'Jarvis, stop listening' or press Ctrl+C to stop.{_C.RESET}\n")
                    try:
                        self._voice.run_continuous_listening(
                            on_turn_complete=lambda inp, out: print(f"\n{_C.BLUE}Jarvis:{_C.RESET} {out}\n")
                        )
                    except KeyboardInterrupt:
                        print(f"\n{_C.YELLOW}Continuous voice mode halted.{_C.RESET}\n")
            elif mode_arg == "text":
                if self._hands_free is not None:
                    self._hands_free.stop()
                self._voice.set_mode(VoiceMode.TEXT)
                print(f"\n{_C.GREEN}Switched to Text Mode.{_C.RESET}\n")
            else:
                print(f"Unknown voice command: '{arg}'. Options: on, off, status, test, ptt, continuous, text")

        elif cmd == "/speak":
            if not self._voice:
                print(f"\n{_C.RED}Voice output is unavailable.{_C.RESET}\n")
            elif not arg:
                print("Usage: /speak <text to speak>")
            else:
                self._voice.speak_response(arg)

        elif cmd in ("/stop", "/emergency-stop"):
            self._shutdown_voice()
            self._agent.trigger_emergency_stop("Triggered by user command /stop.")
            print(f"\n{_C.RED}🛑 EMERGENCY STOP ACTIVATED. All tool executions and speech halted.{_C.RESET}")
            print(f"Type {_C.YELLOW}/resume{_C.RESET} to resume normal operations.\n")

        elif cmd == "/resume":
            self._agent.clear_emergency_stop()
            print(f"\n{_C.GREEN}✅ Emergency stop cleared. Normal operations resumed.{_C.RESET}\n")

        elif cmd == "/clear":
            with self._agent_lock:
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

                # Route yes/no answers to any pending background voice approval request
                with self._approval_lock:
                    pending_ev = self._pending_approval_event
                if pending_ev is not None and not pending_ev.is_set():
                    low = user_input.lower()
                    if low in ("yes", "y", "no", "n"):
                        with self._approval_lock:
                            self._pending_approval_answer = low in ("yes", "y")
                            pending_ev.set()
                        continue

                if user_input.startswith("/"):
                    if not self._handle_command(user_input):
                        break
                    continue

                # Process via Agent under shared lock (serializes typed & spoken requests)
                print(f"\n{_C.DIM}Thinking…{_C.RESET}")
                with self._agent_lock:
                    response = self._agent.process_message(user_input)
                print(f"\n{_C.BLUE}Jarvis:{_C.RESET} {response}\n")

                # If voice is enabled and mode is not text-only, speak response
                if self._voice and self._voice.mode != VoiceMode.TEXT and settings.VOICE_OUTPUT_ENABLED:
                    if self._hands_free is not None and self._hands_free.is_monitoring:
                        self._hands_free._speak_safe(response)
                    else:
                        self._voice.speak_response(response)

            except KeyboardInterrupt:
                self._shutdown_voice()
                print(f"\n\n{_C.CYAN}Goodbye! JARVIS shutting down…{_C.RESET}\n")
                self._agent.shutdown()
                break
            except EOFError:
                self._shutdown_voice()
                print(f"\n{_C.CYAN}Session ended.{_C.RESET}\n")
                self._agent.shutdown()
                break
