# JARVIS AI — Voice Testing & Verification Guide (Phase 3)

Automated testing of voice subsystems presents unique challenges: CI and automated testing environments often lack physical microphones or audio output cards.

JARVIS AI addresses this using an abstract engine architecture with **Mock Engines** (`MockSTTEngine` and `MockTTSEngine`).

---

## 1. Automated Unit Testing

All 12 voice unit tests run in memory without requiring microphones or speakers:

```powershell
& ".\.venv\Scripts\pytest.exe" tests/test_voice.py -v
```

### Coverage Areas in `tests/test_voice.py`:
1. `test_strip_markdown_code_blocks`: Verifies that Python code blocks are sanitized and not read aloud.
2. `test_strip_bold_italics_backticks`: Verifies formatting asterisks, underscores, and backticks are removed.
3. `test_strip_urls_and_markdown_links`: Verifies raw URLs and Markdown links are converted to spoken text.
4. `test_strip_headers_and_bullets`: Verifies Markdown headers and bullet symbols are removed.
5. `test_voice_push_to_talk_cycle`: Tests full cycle: mock audio -> STT -> Agent -> TTS -> State transitions.
6. `test_voice_command_stop_speaking`: Verifies `"Jarvis, stop speaking"` halts playback.
7. `test_voice_command_repeat_that`: Verifies `"Jarvis, repeat that"` repeats the prior answer.
8. `test_voice_command_mode_switch`: Verifies spoken mode switching (`"switch to text mode"`).
9. `test_voice_command_what_can_you_do`: Verifies capability summary query.
10. `test_empty_speech_transcription`: Verifies silence does not cause crashes or unintended execution.
11. `test_permission_enforcement_on_voice_commands`: Verifies high-risk commands spoken by voice cannot bypass user confirmation.
12. `test_text_mode_bypasses_voice_input`: Verifies Text Mode completely disables microphone reading.

---

## 2. Interactive Hardware Verification

When testing on your local Windows PC with a physical microphone and speakers:

### Step 1: Test Speech Synthesis (TTS)
Launch JARVIS:
```powershell
python main.py
```
In the prompt, run:
```
You: /speak Hello! JARVIS voice output is operational.
```
**Expected**: Your speakers speak the message clearly.

### Step 2: Test Push-to-Talk Voice Input (STT)
In the prompt, type:
```
You: /voice
```
**Expected**:
Terminal shows: `[JARVIS] 🎙️ Listening... (Speak now)`
Speak clearly: `"What time is it?"`
Terminal shows:
```
[VOICE] Recognized: What time is it?
[JARVIS] ⚙️ Processing...
[JARVIS] 🔊 Speaking...
Jarvis: The current time is ...
```
And speaks the answer aloud.

### Step 3: Test Voice Task Execution
Say: `"Create a folder named VoiceTest inside workspace."`
**Expected**:
JARVIS plans the task, executes `create_folder`, creates the directory, and speaks `"Folder created: VoiceTest"`.
