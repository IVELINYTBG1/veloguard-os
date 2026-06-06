#!/usr/bin/env bash
#
# VeloGuardOS — voice assistant engines (OPTIONAL, heavy; opt-in). All USERSPACE.
#
# TTS : Piper by default (fast, natural, light, CPU-friendly).
#       IndexTTS2 is the highest-quality option but heavy (PyTorch + GPU) — see
#       the note at the end; it slots in as a drop-in TTS backend.
# STT : faster-whisper (Whisper, runs local).
# Wake: openWakeWord (say your wake word → the assistant starts listening).
#
# Installed into the VeloGuard venv (compatible Python, from install-ai-memory.sh).
#
#   sudo ./install-voice.sh
#
set -euo pipefail
say()  { printf '\033[1;36m[veloguard]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[veloguard]\033[0m %s\n' "$*" >&2; }
[ "$(id -u)" -eq 0 ] || { warn "run as root (sudo)"; exit 1; }

HOME_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${VELOGUARD_VENV:-$HOME_DIR/.venv}"

# System audio + the lightweight Piper TTS binary.
if command -v pacman >/dev/null; then
  pacman -Syu --noconfirm --needed piper-tts portaudio || \
    warn "piper-tts may be in the AUR/Chaotic — falling back to pip piper"
fi

[ -x "$VENV/bin/pip" ] || { warn "run provision/install-ai-memory.sh first (it builds the venv)"; exit 1; }
say "installing voice engines into $VENV …"
"$VENV/bin/pip" install --upgrade \
  faster-whisper openwakeword sounddevice numpy piper-tts \
  || warn "some voice packages failed — STT/TTS may be partial"

# Pull a small Whisper model so STT works offline.
"$VENV/bin/python" - <<'PY' 2>/dev/null || warn "whisper model fetch deferred to first use"
from faster_whisper import WhisperModel
WhisperModel("base.en")   # downloads + caches
print("whisper base.en ready")
PY

say "Voice ready. Set a wake word in:  guardd setup"
say "Start the assistant:  guardd voice"
say "Highest-quality TTS (heavy, GPU): pip install indextts2 in the venv, then"
say "  set VELOGUARD_TTS=indextts2 — the assistant uses it as the TTS backend."
