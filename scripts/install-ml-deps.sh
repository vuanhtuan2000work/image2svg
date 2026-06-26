#!/usr/bin/env bash
# Install OpenMMLab / MMPose into a dedicated venv (.venv-ml).
#
# Common failures on macOS:
#   ensurepip error  -> Homebrew python@3.11 broken (pyexpat/libexpat mismatch)
#   mmcv source build -> torch not installed first; use this script, not plain pip

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT}/.venv-ml"

log() { printf '%s\n' "$*"; }
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }

python_usable() {
  local py="$1"
  "${py}" --version >/dev/null 2>&1
}

python_health_check() {
  local py="$1"
  python_usable "${py}" || return 1
  "${py}" - <<'PY' >/dev/null 2>&1
import xml.parsers.expat
import ssl
import venv
PY
}

pick_homebrew_python() {
  for candidate in python3.11 python3.10 /opt/homebrew/bin/python3.11 /usr/local/bin/python3.11; do
    if command -v "${candidate}" >/dev/null 2>&1; then
      echo "${candidate}"
      return
    fi
  done
  echo ""
}

ensure_uv() {
  if command -v uv >/dev/null 2>&1; then
    return 0
  fi
  if command -v brew >/dev/null 2>&1; then
    log "Installing uv (standalone Python manager) via Homebrew..."
    brew install uv
    return 0
  fi
  return 1
}

create_venv_with_uv() {
  local py_version="$1"
  log "Creating ${VENV_DIR} with uv (standalone Python ${py_version})..."
  rm -rf "${VENV_DIR}"
  uv python install "${py_version}"
  uv venv "${VENV_DIR}" --python "${py_version}" --seed
  if ! python_usable "${VENV_DIR}/bin/python"; then
    rm -rf "${VENV_DIR}"
    fail "uv venv created but ${VENV_DIR}/bin/python is not runnable (retry: uv python install ${py_version})"
  fi
  echo "${VENV_DIR}/bin/python"
}

create_venv_with_system_python() {
  local py="$1"
  log "Creating ${VENV_DIR} with ${py}..."
  rm -rf "${VENV_DIR}"
  if "${py}" -m venv "${VENV_DIR}" 2>/dev/null; then
    echo "${VENV_DIR}/bin/python"
    return 0
  fi
  log "Standard venv failed (ensurepip). Retrying with --without-pip..."
  "${py}" -m venv "${VENV_DIR}" --without-pip
  if ! python_health_check "${VENV_DIR}/bin/python"; then
    rm -rf "${VENV_DIR}"
    return 1
  fi
  curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/image2svg-get-pip.py
  "${VENV_DIR}/bin/python" /tmp/image2svg-get-pip.py
  echo "${VENV_DIR}/bin/python"
}

print_broken_python_help() {
  cat >&2 <<'EOF'

Homebrew python@3.11 is broken on this Mac (pyexpat / libexpat mismatch).
That causes: ensurepip failed / KeyError __version__ when installing mmcv.

Fix options (pick one):

  A) Use uv-managed Python (recommended — script tries this automatically):
       brew install uv
       ./scripts/install-ml-deps.sh

  B) Repair Homebrew Python, then re-run:
       brew install expat
       brew reinstall python@3.11
       /opt/homebrew/bin/python3.11 -c "import xml.parsers.expat; print('ok')"
       ./scripts/install-ml-deps.sh

  C) Skip MMPose — silhouette landmarks work in the main .venv (Python 3.13):
       .venv/bin/python scripts/export_game_manifest.py sheet.svg --ml-landmarks
EOF
}

resolve_python() {
  local py="" version="" venv_py=""

  if [[ -d "${VENV_DIR}" && -f "${VENV_DIR}/bin/python" || -L "${VENV_DIR}/bin/python" ]]; then
    if python_usable "${VENV_DIR}/bin/python" && python_health_check "${VENV_DIR}/bin/python"; then
      echo "${VENV_DIR}/bin/python"
      return 0
    fi
    log "Removing broken existing ${VENV_DIR}"
    rm -rf "${VENV_DIR}"
  elif [[ -d "${VENV_DIR}" ]]; then
    log "Removing incomplete ${VENV_DIR} (missing bin/python)"
    rm -rf "${VENV_DIR}"
  fi

  py="$(pick_homebrew_python)"
  if [[ -n "${py}" ]] && python_health_check "${py}"; then
    version="$("${py}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    case "${version}" in
      3.10|3.11)
        venv_py="$(create_venv_with_system_python "${py}")"
        echo "${venv_py}"
        return 0
        ;;
      *)
        log "Found ${py} (${version}) but OpenMMLab needs 3.10 or 3.11."
        ;;
    esac
  fi

  if [[ -n "${py}" ]]; then
    log "Homebrew ${py} failed health check (pyexpat). Falling back to uv..."
  fi

  if ensure_uv; then
    venv_py="$(create_venv_with_uv 3.11)"
    echo "${venv_py}"
    return 0
  fi

  print_broken_python_help
  fail "Could not create a working Python 3.11 environment."
}

VENV_PY="$(resolve_python)"
PY_VERSION="$("${VENV_PY}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
case "${PY_VERSION}" in
  3.10|3.11) ;;
  *) fail "Refusing to install OpenMMLab on Python ${PY_VERSION}. Need 3.10 or 3.11." ;;
esac

log "Using ${VENV_PY} (Python ${PY_VERSION})"

if ! "${VENV_PY}" -m pip --version >/dev/null 2>&1; then
  log "Bootstrapping pip into ${VENV_DIR}..."
  if command -v uv >/dev/null 2>&1; then
    uv pip install --python "${VENV_PY}" pip setuptools wheel
  else
    curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/image2svg-get-pip.py
    "${VENV_PY}" /tmp/image2svg-get-pip.py
  fi
fi

"${VENV_PY}" -m pip install -U pip setuptools wheel

install_openmmlab() {
  local py="$1"
  local os arch
  os="$(uname -s)"
  arch="$(uname -m)"

  "${py}" -m pip install -U openmim

  if [[ "${os}" == "Darwin" ]]; then
    log "macOS detected (${arch}) — using pinned torch 2.1.2 + prebuilt mmcv wheel (no source build)."
    "${py}" -m pip install "torch==2.1.2" "torchvision==0.16.2"
    "${py}" -m pip install "numpy<2"
    "${py}" -m pip install mmengine
    "${py}" -m pip install mmcv==2.1.0 \
      -f https://download.openmmlab.com/mmcv/dist/cpu/torch2.1.0/index.html
    log "Installing chumpy (mmpose dep) without broken build isolation..."
    "${py}" -m pip install --no-build-isolation chumpy
    "${py}" -m mim install "mmdet==3.2.0"
    "${py}" -m mim install "mmpose>=1.3.0"
  else
    log "Installing PyTorch (CPU) first — required before mmcv..."
    "${py}" -m pip install torch torchvision "numpy<2"
    "${py}" -m mim install mmengine
    if ! "${py}" -m mim install "mmcv>=2.1.0"; then
      log "mim mmcv failed — trying mmcv-lite fallback..."
      "${py}" -m pip install "mmcv-lite>=2.1.0"
    fi
    "${py}" -m pip install --no-build-isolation chumpy
    "${py}" -m mim install "mmdet==3.2.0"
    "${py}" -m mim install "mmpose>=1.3.0"
  fi

  log "Verifying imports..."
  "${py}" - <<'PY'
import mmcv
import mmdet
import mmpose
print(f"mmcv {mmcv.__version__}, mmdet {mmdet.__version__}, mmpose {mmpose.__version__}")
PY
}

install_openmmlab "${VENV_PY}"

cat <<EOF

Done.

Activate:
  source ${VENV_DIR}/bin/activate

Set model paths, then export with MMPose:
  export IMAGE2SVG_ML_LANDMARKS=1
  export IMAGE2SVG_MMPOSE=1
  export IMAGE2SVG_MMPOSE_CONFIG=/path/to/config.py
  export IMAGE2SVG_MMPOSE_CHECKPOINT=/path/to/checkpoint.pth
  ${VENV_PY} scripts/export_game_manifest.py sheet.svg --ml-landmarks --mmpose
EOF
