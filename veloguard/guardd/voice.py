"""Voice assistant — wake word → listen → the AI reasons → speak (context-aware).

USERSPACE. It ties together: wake-word detection (openWakeWord), speech-to-text
(faster-whisper), the active AI plane (Claude/OpenAI/Ollama — and it can call the
guard's tools), and text-to-speech (Piper, or IndexTTS2 as a drop-in backend).

The key idea you asked for is CONTEXT-AWARENESS: before speaking, the AI decides
whether speaking aloud is appropriate given the situation — e.g. "someone's
sleeping" → stay silent; "someone's sleeping but I have earbuds" → speak. The LLM
handles that nuance; we just give it the context.

This is a scaffold: the audio path needs a mic + the engines (install-voice.sh)
and a hardware test. The orchestration + the context decision are real.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

from . import memory, state
from .ai_adapter import get_adapter

WAKE_WORD = lambda: memory.get_pref("wake_word", "hey guard")
CONTEXT = lambda: memory.get_pref("voice_context", "")  # e.g. "someone is sleeping"


# --- the context-aware decision (the heart of the request) -----------------

def should_speak(context: str, adapter) -> bool:
    """Ask the AI whether to speak ALOUD given the situation. Empty context =>
    yes. The model resolves nuance (earbuds override 'someone sleeping', etc.)."""
    if not context:
        return True
    try:
        ans = adapter.complete(
            "You decide whether a voice assistant should speak ALOUD right now. "
            "Consider the situation carefully (e.g. earbuds override 'someone is "
            "sleeping'). Answer with only YES or NO.",
            f"Situation: {context}\nSpeak aloud?", 8).strip().upper()
        return ans.startswith("Y")
    except Exception:
        return True            # fail open: better to answer than go silent on error


# --- pluggable backends (subprocess; swap freely) --------------------------

def speak(text: str) -> None:
    engine = os.environ.get("VELOGUARD_TTS", "piper")
    if engine == "indextts2":
        subprocess.run(["indextts2", "--text", text], check=False)
        return
    if shutil.which("piper"):
        with tempfile.NamedTemporaryFile(suffix=".wav") as w:
            subprocess.run(["piper", "--output_file", w.name],
                           input=text.encode(), check=False)
            player = shutil.which("paplay") or shutil.which("aplay")
            if player:
                subprocess.run([player, w.name], check=False)
    else:
        print(f"[tts:{engine} unavailable] {text}")


def transcribe(seconds: float = 6.0) -> str:
    """Record from the mic and transcribe with faster-whisper. Needs the venv
    engines + a mic; returns '' if unavailable (scaffold-safe)."""
    try:
        import numpy as np
        import sounddevice as sd
        from faster_whisper import WhisperModel
    except Exception:
        return ""
    sr = 16000
    audio = sd.rec(int(seconds * sr), samplerate=sr, channels=1, dtype="float32")
    sd.wait()
    model = WhisperModel(os.environ.get("VELOGUARD_STT_MODEL", "base.en"))
    segs, _ = model.transcribe(audio.flatten())
    return " ".join(s.text for s in segs).strip()


def _wake_loop():
    """Yield once per wake-word detection. Falls back to Enter-to-talk if the
    wake engine isn't installed, so the loop is still usable for testing."""
    try:
        from openwakeword.model import Model
        import numpy as np, sounddevice as sd          # noqa: E401
        Model()  # default models
        # (real detection loop wired here once tested on hardware)
        raise ImportError  # fall through to keypress mode until hardware-tested
    except Exception:
        while True:
            try:
                input(f"[voice] press Enter to talk (wake word: '{WAKE_WORD()}') ")
            except EOFError:
                return
            yield


# --- the assistant loop ----------------------------------------------------

def run(once: bool = False) -> int:
    provider = state.active_provider(config_default="mock")
    if provider == "mock":
        print("voice needs an AI plane — run: guardd use ollama|claude|openai")
        return 2
    cfg = state.adapter_config(provider)
    try:
        adapter = get_adapter(provider, **cfg)
    except (ValueError, RuntimeError) as e:
        print(f"voice: {e}")
        return 2

    print(f"🎙️  VeloGuard voice — wake word '{WAKE_WORD()}', brain {provider}. Ctrl-C to stop.")
    for _ in _wake_loop():
        # (UI hook: a shell extension can play the 'listening' animation here.)
        text = transcribe()
        if not text:
            print("  (heard nothing / engines not installed — run install-voice.sh)")
            if once:
                break
            continue
        print(f"  you: {text}")
        reply = adapter.complete(
            "You are VeloGuard's voice assistant. Be brief and helpful.",
            text, 300)
        print(f"  ai : {reply}")
        if should_speak(CONTEXT(), adapter):
            speak(reply)
        else:
            print(f"  (staying silent — context: {CONTEXT()!r})")
        memory.log_decision("voice", text[:60], "answered",
                            "spoke" if should_speak(CONTEXT(), adapter) else "silent")
        if once:
            break
    return 0
