#!/bin/bash
set -e

VENV_CACHE="/venv_cache"
MARKER="$VENV_CACHE/.torch_installed"

# Use cu121 by default - best compatibility with CUDA 12.1 base image and PyTorch.
# Override with TORCH_CUDA_TAG env var (e.g. cu118, cu121, cu124).
CUDA_TAG="${TORCH_CUDA_TAG:-cu121}"

# Install torch wheel for the target CUDA version.
# Cached on a Docker volume so we only install once per version change.
if [ ! -f "$MARKER" ] || [ "$(cat "$MARKER" 2>/dev/null)" != "$CUDA_TAG" ]; then
    echo "Installing torch for $CUDA_TAG (matches CUDA 12.1 base image)..."
    if [ "$CUDA_TAG" = "cpu" ]; then
        python3 -m pip install --no-cache-dir torch
    else
        python3 -m pip install --no-cache-dir torch \
            --extra-index-url "https://download.pytorch.org/whl/${CUDA_TAG}"
    fi

    mkdir -p "$VENV_CACHE"
    echo "$CUDA_TAG" > "$MARKER"
    echo "Torch installed for $CUDA_TAG."
else
    echo "Torch already installed ($(cat $MARKER)). Skipping."
fi

# CUDA libs: prefer base image /usr/local/cuda, then pip nvidia packages
if [ -d "/usr/local/cuda/lib64" ]; then
    export LD_LIBRARY_PATH="/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-}"
fi
SITE_PKGS=$(python -c "import site; print(site.getsitepackages()[0])")
PIP_CUDA_LIBS=$(find "$SITE_PKGS/nvidia" -name "lib" -type d 2>/dev/null | tr '\n' ':')
export LD_LIBRARY_PATH="${PIP_CUDA_LIBS}${LD_LIBRARY_PATH:-}"
echo "LD_LIBRARY_PATH=$LD_LIBRARY_PATH"

echo "Starting Celery worker..."
exec "$@"
