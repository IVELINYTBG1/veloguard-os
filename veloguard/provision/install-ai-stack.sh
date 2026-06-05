#!/usr/bin/env bash
#
# VeloGuardOS — local AI stack provisioner.
#
# Makes the "go fully local" path turnkey for a VeloGuardOS image:
#   1. install Ollama (the local AI plane backend)
#   2. detect the GPU and wire up the RIGHT acceleration (CUDA on NVIDIA,
#      ROCm on AMD, CPU/Vulkan otherwise) — no CUDA on a box with no NVIDIA
#   3. pull a default model and prove VeloGuard can drive it
#
# Run on the target machine/image (needs root for installs):
#   sudo ./install-ai-stack.sh
#
set -euo pipefail

say() { printf '\033[1;36m[veloguard]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[veloguard]\033[0m %s\n' "$*" >&2; }

# ---------------------------------------------------------------------------
# 1. GPU detection — decides the acceleration story
# ---------------------------------------------------------------------------
detect_gpu() {
  if lspci 2>/dev/null | grep -qi nvidia; then echo nvidia; return; fi
  if lspci 2>/dev/null | grep -qiE 'amd/ati|radeon';  then echo amd;   return; fi
  echo cpu
}

# ---------------------------------------------------------------------------
# 2. GPU acceleration setup
#    CUDA is NVIDIA-only and lives in the DISTRO layer, never in the kernel
#    binary. The kernel just needs the matching module loadable; CUDA itself
#    is userspace (libcuda + the toolkit). Ollama auto-uses it once present.
# ---------------------------------------------------------------------------
setup_accel() {
  local gpu="$1"
  case "$gpu" in
    nvidia)
      say "NVIDIA GPU detected → installing proprietary driver + CUDA runtime"
      if command -v dnf >/dev/null; then
        # Fedora/RHEL path (RPM Fusion provides akmod-nvidia + cuda).
        dnf install -y akmod-nvidia xorg-x11-drv-nvidia-cuda || \
          warn "enable RPM Fusion first: see provision/README.md"
      elif command -v apt-get >/dev/null; then
        apt-get update && apt-get install -y nvidia-driver-cuda nvidia-cuda-toolkit || \
          warn "add NVIDIA's CUDA apt repo first: see provision/README.md"
      else
        warn "unknown distro — install the NVIDIA driver + CUDA toolkit manually"
      fi
      command -v nvidia-smi >/dev/null && nvidia-smi -L || \
        warn "reboot may be required for the kernel module to load"
      ;;
    amd)
      say "AMD GPU detected → Ollama will use ROCm/Vulkan (no CUDA needed)"
      ;;
    cpu)
      warn "No discrete NVIDIA/AMD GPU found (e.g. Intel iGPU or VM)."
      warn "Ollama will run on CPU. CUDA is NOT installed — it would do nothing here."
      ;;
  esac
}

# ---------------------------------------------------------------------------
# 3. Ollama install + service
# ---------------------------------------------------------------------------
install_ollama() {
  if command -v ollama >/dev/null; then
    say "Ollama already installed ($(ollama --version 2>/dev/null | tail -1))"
  else
    say "Installing Ollama"
    curl -fsSL https://ollama.com/install.sh | sh
  fi
  # On a systemd image this is the "preinstalled & always connected" guarantee.
  if command -v systemctl >/dev/null; then
    systemctl enable --now ollama 2>/dev/null || warn "start ollama manually: 'ollama serve &'"
  fi
}

# ---------------------------------------------------------------------------
# 4. Hand off to the setup screen — the USER picks local vs API and the model.
#    (The installer only lays the infrastructure; the choice is the wizard's.)
# ---------------------------------------------------------------------------
launch_setup() {
  local here; here="$(cd "$(dirname "$0")/.." && pwd)"
  if [ -t 0 ] && [ -t 1 ]; then
    say "Launching the VeloGuard setup screen…"
    ( cd "$here" && python3 -m guardd setup )
  else
    say "Stack installed. The setup screen runs on first boot,"
    say "or launch it now:  cd $here && python3 -m guardd setup"
  fi
}

main() {
  local gpu; gpu="$(detect_gpu)"
  say "GPU class: $gpu"
  setup_accel "$gpu"
  install_ollama
  launch_setup
  say "Done."
}

main "$@"
