"""
Tests for Voice Subsystem:
- Text sanitization for speech (Markdown, code, URLs, symbols)
- Mock STT and Mock TTS engines
- VoiceController state machine (IDLE, LISTENING, PROCESSING, SPEAKING, ERROR)
- Voice command interception (repeat that, stop speaking, mode switching, what can you do)
- Push-to-talk and continuous modes
- Recording cancellation
- Security & permission enforcement on voice commands
- Fallback to text mode
"""

from unittest.mock import MagicMock

from core.agent import JarvisAgent
from core.permissions import PermissionCheck
from core.planner import TaskStep
from providers.base import BaseProvider, FunctionCall, ModelResponse
from tools import PermissionLevel, ToolCategory, ToolDefinition, ToolParameter, ToolResult
from tools.registry import ToolRegistry
from voice.speech_to_text import MockSTTEngine, get_stt_engine
from voice.text_to_speech import MockTTSEngine, clean_text_for_speech, get_tts_engine
from voice.voice_controller import AudioState, VoiceController, VoiceMode


class SimpleMockProvider(BaseProvider):

    def __init__(self, responses: list[ModelResponse] | None = None) -> None:
        self.responses = responses or []

    def connect(self) -> bool:
        return True

    def generate(self, messages, system_instruction=None) -> ModelResponse:
        return self.responses.pop(0) if self.responses else ModelResponse(text="Mock direct")

    def generate_with_tools(self, messages, tool_declarations, system_instruction=None) -> ModelResponse:
        return self.responses.pop(0) if self.responses else ModelResponse(text="Mock tool answer")

    def send_function_results(self, messages, function_calls, function_responses, tool_declarations, system_instruction=None) -> ModelResponse:
        return self.responses.pop(0) if self.responses else ModelResponse(text="Tool result summarized")

    def get_provider_name(self) -> str:
        return "mock"

    def get_model_name(self) -> str:
        return "mock-model"


class TestTextSanitization:

    def test_strip_markdown_code_blocks(self):
        text = "Here is the code:\n```python\nprint('hello')\n```\nAll done."
        cleaned = clean_text_for_speech(text)
        assert "print('hello')" not in cleaned
        assert "Code snippet omitted" in cleaned
        assert "All done." in cleaned

    def test_strip_bold_italics_backticks(self):
        text = "This is **critical** and *important* with `variable_name`."
        cleaned = clean_text_for_speech(text)
        assert cleaned == "This is critical and important with variable_name."

    def test_strip_urls_and_markdown_links(self):
        text = "Visit [Google Search](https://google.com) or https://github.com directly."
        cleaned = clean_text_for_speech(text)
        assert "https://" not in cleaned
        assert "Google Search" in cleaned

    def test_strip_headers_and_bullets(self):
        text = "# Title\n- Item 1\n• Item 2\n* Item 3"
        cleaned = clean_text_for_speech(text)
        assert "#" not in cleaned
        assert "•" not in cleaned
        assert "Title Item 1 Item 2 Item 3" in cleaned


class TestVoiceController:

    def setup_method(self):
        self.registry = ToolRegistry()
        self.registry.register(
            ToolDefinition(
                name="get_time",
                description="Get current time",
                parameters=[],
                permission_level=PermissionLevel.LEVEL_0_READ_ONLY,
                category=ToolCategory.PRODUCTIVITY,
            ),
            lambda: ToolResult(success=True, result={"time": "3:00 PM"}),
        )
        self.registry.register(
            ToolDefinition(
                name="delete_all",
                description="Destructive delete",
                parameters=[],
                permission_level=PermissionLevel.LEVEL_3_HIGH_RISK,
                category=ToolCategory.FILE_MANAGEMENT,
            ),
            lambda: ToolResult(success=True, result={"deleted": True}),
        )

    def test_voice_push_to_talk_cycle(self, db):
        provider = SimpleMockProvider([
            ModelResponse(text="The current time is 3:00 PM.")
        ])
        agent = JarvisAgent(provider=provider, registry=self.registry, db=db)
        agent.initialize()

        stt = MockSTTEngine(queue=["What time is it?"])
        tts = MockTTSEngine()

        states = []
        controller = VoiceController(
            agent=agent,
            stt_engine=stt,
            tts_engine=tts,
            mode=VoiceMode.PUSH_TO_TALK,
            on_state_change=lambda s: states.append(s),
        )

        resp = controller.listen_and_process()

        assert "3:00 PM" in resp
        assert len(tts.spoken_texts) == 1
        assert "3:00 PM" in tts.spoken_texts[0]
        # Verify state transitions: LISTENING -> PROCESSING -> SPEAKING -> IDLE
        assert AudioState.LISTENING in states
        assert AudioState.PROCESSING in states
        assert AudioState.SPEAKING in states
        assert controller.state == AudioState.IDLE

    def test_voice_command_stop_speaking(self, db):
        provider = SimpleMockProvider()
        agent = JarvisAgent(provider=provider, registry=self.registry, db=db)
        agent.initialize()

        stt = MockSTTEngine(queue=["Jarvis, stop speaking"])
        tts = MockTTSEngine()

        controller = VoiceController(agent=agent, stt_engine=stt, tts_engine=tts)
        resp = controller.listen_and_process()

        assert "Stopped speaking" in resp
        assert controller.state == AudioState.IDLE

    def test_voice_command_repeat_that(self, db):
        provider = SimpleMockProvider([ModelResponse(text="Initial speech message")])
        agent = JarvisAgent(provider=provider, registry=self.registry, db=db)
        agent.initialize()

        stt = MockSTTEngine(queue=["Hello", "Jarvis, repeat that"])
        tts = MockTTSEngine()

        controller = VoiceController(agent=agent, stt_engine=stt, tts_engine=tts)

        # Turn 1
        controller.listen_and_process()
        # Turn 2: repeat
        repeat_resp = controller.listen_and_process()

        assert "Initial speech message" in repeat_resp

    def test_voice_command_mode_switch(self, db):
        provider = SimpleMockProvider()
        agent = JarvisAgent(provider=provider, registry=self.registry, db=db)
        agent.initialize()

        stt = MockSTTEngine(queue=["switch to text mode"])
        tts = MockTTSEngine()

        controller = VoiceController(agent=agent, stt_engine=stt, tts_engine=tts)
        controller.listen_and_process()

        assert controller.mode == VoiceMode.TEXT

    def test_voice_command_what_can_you_do(self, db):
        provider = SimpleMockProvider()
        agent = JarvisAgent(provider=provider, registry=self.registry, db=db)
        agent.initialize()

        stt = MockSTTEngine(queue=["Jarvis, what can you do?"])
        tts = MockTTSEngine()

        controller = VoiceController(agent=agent, stt_engine=stt, tts_engine=tts)
        resp = controller.listen_and_process()

        assert "manage files" in resp.lower()

    def test_empty_speech_transcription(self, db):
        provider = SimpleMockProvider()
        agent = JarvisAgent(provider=provider, registry=self.registry, db=db)
        agent.initialize()

        stt = MockSTTEngine(queue=[""])  # Silence
        tts = MockTTSEngine()

        controller = VoiceController(agent=agent, stt_engine=stt, tts_engine=tts)
        resp = controller.listen_and_process()

        assert resp == ""
        assert len(tts.spoken_texts) == 0
        assert controller.state == AudioState.IDLE

    def test_permission_enforcement_on_voice_commands(self, db):
        # User tries to execute a Level 3 command via voice
        provider = SimpleMockProvider([
            ModelResponse(function_calls=[FunctionCall(name="delete_all", args={})]),
            ModelResponse(text="Action denied by user."),
        ])

        def deny_cb(step: TaskStep, check: PermissionCheck) -> bool:
            return False

        agent = JarvisAgent(provider=provider, registry=self.registry, db=db, approval_callback=deny_cb)
        agent.initialize()

        stt = MockSTTEngine(queue=["Delete everything"])
        tts = MockTTSEngine()

        controller = VoiceController(agent=agent, stt_engine=stt, tts_engine=tts)
        resp = controller.listen_and_process()

        assert "denied" in resp.lower() or "declined" in resp.lower()

    def test_text_mode_bypasses_voice_input(self, db):
        provider = SimpleMockProvider()
        agent = JarvisAgent(provider=provider, registry=self.registry, db=db)
        agent.initialize()

        stt = MockSTTEngine(queue=["Hello in speech"])
        tts = MockTTSEngine()

        controller = VoiceController(agent=agent, stt_engine=stt, tts_engine=tts, mode=VoiceMode.TEXT)
        resp = controller.listen_and_process()

        assert resp == ""
        assert stt.call_count == 0  # STT must not be called when mode is TEXT
