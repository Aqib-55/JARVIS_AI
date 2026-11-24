"""
Setup script for JARVIS AI local models.

Downloads and verifies:
  1. Faster-Whisper STT model (base, CPU INT8)
  2. Piper TTS voice model (en_GB-alan-medium or en_GB-northern_english_male-medium)

Run once before starting JARVIS:
    python setup_local_models.py

After running, verify models are present and start JARVIS:
    python main.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def download_whisper_model(model_size: str = "base", output_dir: Path | None = None) -> bool:
    """Download the Faster-Whisper model once into local models/stt/ directory."""
    dest = output_dir or (PROJECT_ROOT / "models" / "stt" / f"faster-whisper-{model_size}")
    dest.mkdir(parents=True, exist_ok=True)

    try:
        from faster_whisper import WhisperModel
        from faster_whisper.utils import _MODELS
        from huggingface_hub import snapshot_download
        from voice.speech_to_text import verify_whisper_model_files
    except ImportError as e:
        print(f"[STT] ❌ Missing dependency: {e}. Run: pip install faster-whisper")
        return False

    repo_id = _MODELS.get(model_size)
    if not repo_id:
        print(f"[STT] ❌ Unknown Whisper model '{model_size}'.")
        return False

    try:
        already_ok, _ = verify_whisper_model_files(dest)
        if already_ok:
            print(f"\n[STT] ✅ Faster-Whisper '{model_size}' files already exist at {dest}")
        else:
            print(f"\n[STT] Downloading '{repo_id}' into {dest} ...")
            print("[STT] Public repository — no Hugging Face token required.")
            snapshot_download(
                repo_id,
                local_dir=str(dest),
                allow_patterns=[
                    "config.json",
                    "preprocessor_config.json",
                    "model.bin",
                    "tokenizer.json",
                    "vocabulary.*",
                ],
            )

        ok, missing = verify_whisper_model_files(dest)
        if not ok:
            print(f"[STT] ❌ Model verification failed at {dest}. Missing: {', '.join(missing)}")
            return False

        # Verify offline load using the local directory path (CPU INT8, no network)
        _ = WhisperModel(str(dest), device="cpu", compute_type="int8", local_files_only=True)
        print(f"[STT] ✅ Verified offline Faster-Whisper '{model_size}' at {dest}")
        return True
    except Exception as e:
        print(f"[STT] ❌ Failed to set up Whisper model: {e}")
        return False


def download_piper_voice(
    voice_name: str = "en_GB-alan-medium",
    output_dir: Path | None = None,
) -> bool:
    """
    Download a Piper TTS voice model from the official Hugging Face repository.

    Voice model files required:
      - <voice_name>.onnx
      - <voice_name>.onnx.json

    Official voice list: https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_GB
    """
    dest = output_dir or (PROJECT_ROOT / "models" / "tts")
    dest.mkdir(parents=True, exist_ok=True)

    # Construct Hugging Face download URLs
    base_url = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
    # Voice name format: en_GB-alan-medium -> en/en_GB/alan/medium/
    parts = voice_name.split("-")
    if len(parts) < 3:
        print(f"[TTS] ❌ Cannot parse voice name '{voice_name}'. Expected format: lang_region-name-quality")
        return False

    lang_region = parts[0]           # e.g. en_GB
    lang_prefix = lang_region[:2]    # e.g. en
    speaker = parts[1]               # e.g. alan
    quality = parts[2]               # e.g. medium

    path_prefix = f"{lang_prefix}/{lang_region}/{speaker}/{quality}"
    onnx_url = f"{base_url}/{path_prefix}/{voice_name}.onnx"
    json_url = f"{base_url}/{path_prefix}/{voice_name}.onnx.json"

    onnx_dest = dest / f"{voice_name}.onnx"
    json_dest = dest / f"{voice_name}.onnx.json"

    if onnx_dest.exists() and json_dest.exists():
        print(f"[TTS] ✅ Piper voice '{voice_name}' already exists at {dest}")
        return True

    try:
        import urllib.request
        print(f"\n[TTS] Downloading Piper voice '{voice_name}'...")
        print(f"[TTS] ONNX: {onnx_url}")
        urllib.request.urlretrieve(onnx_url, onnx_dest)
        print(f"[TTS] JSON: {json_url}")
        urllib.request.urlretrieve(json_url, json_dest)
        print(f"[TTS] ✅ Piper voice '{voice_name}' downloaded to {dest}")
        return True
    except Exception as e:
        print(f"[TTS] ❌ Failed to download Piper voice: {e}")
        print(f"[TTS] Manual download: visit https://huggingface.co/rhasspy/piper-voices")
        return False


def download_wakeword_models(output_dir: Path | None = None) -> bool:
    """
    Download official pretrained openWakeWord ONNX assets ('hey_jarvis_v0.1.onnx',
    'melspectrogram.onnx', 'embedding_model.onnx') into models/wakeword/.

    Licensing note:
      - openWakeWord code: Apache-2.0
      - Pretrained models: CC BY-NC-SA 4.0 (non-commercial)
    """
    dest = output_dir or (PROJECT_ROOT / "models" / "wakeword")
    dest.mkdir(parents=True, exist_ok=True)

    urls = {
        "hey_jarvis_v0.1.onnx": "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/hey_jarvis_v0.1.onnx",
        "melspectrogram.onnx": "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/melspectrogram.onnx",
        "embedding_model.onnx": "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/embedding_model.onnx",
    }

    try:
        from voice.wake_word import OpenWakeWordDetector, verify_wakeword_model_files
    except ImportError as e:
        print(f"[WAKE] ❌ Missing dependency: {e}")
        return False

    try:
        already_ok, _, _ = verify_wakeword_model_files(dest, "hey jarvis")
        if already_ok:
            print(f"\n[WAKE] ✅ openWakeWord ONNX files already exist at {dest}")
        else:
            import urllib.request
            print(f"\n[WAKE] Downloading openWakeWord 'Hey Jarvis' ONNX assets into {dest} ...")
            for filename, url in urls.items():
                target = dest / filename
                if not target.exists() or target.stat().st_size == 0:
                    print(f"[WAKE] Downloading {filename}...")
                    urllib.request.urlretrieve(url, target)

        detector = OpenWakeWordDetector(model_dir=dest, phrase="hey jarvis")
        detector.load()
        print(f"[WAKE] ✅ Verified offline openWakeWord 'hey jarvis' at {dest}")
        print("[WAKE] ℹ️  License: openWakeWord code = Apache-2.0; pretrained model = CC BY-NC-SA 4.0 (non-commercial).")
        return True
    except Exception as e:
        print(f"[WAKE] ❌ Failed to set up wake-word model: {e}")
        return False


def main() -> None:
    print("=" * 60)
    print("  JARVIS AI — Local Model Setup")
    print("=" * 60)

    stt_ok = download_whisper_model(model_size="base")

    # Try preferred voice first, then fallback
    tts_ok = download_piper_voice("en_GB-alan-medium")
    if not tts_ok:
        print("[TTS] Trying fallback voice: en_GB-northern_english_male-medium")
        tts_ok = download_piper_voice("en_GB-northern_english_male-medium")

    wake_ok = download_wakeword_models()

    print("\n" + "=" * 60)
    print("  Setup Results")
    print("=" * 60)
    print(f"  STT (Faster-Whisper):    {'✅ Ready' if stt_ok else '❌ Failed'}")
    print(f"  TTS (Piper):             {'✅ Ready' if tts_ok else '❌ Failed'}")
    print(f"  Wake Word (openWakeWord):{'✅ Ready' if wake_ok else '❌ Failed'}")
    print()

    if stt_ok and tts_ok and wake_ok:
        print("  All local models ready. Start JARVIS with:")
        print("    python main.py")
    else:
        print("  Some models failed to download.")
        print("  See HANDS_FREE_VOICE_SETUP.md for manual installation instructions.")
        sys.exit(1)


if __name__ == "__main__":
    main()
