# Hugging Face Spaces entrypoint (Docker SDK, CPU Basic).
# Keep in sync with Dockerfile.worker (compose still builds Dockerfile.worker).
# Spaces requires this exact filename. Binds 0.0.0.0:${PORT:-7860}.
# Playwright is not required (Mercadona is httpx; DIA/Carrefour are stubs).

FROM python:3.12-slim-bookworm

RUN useradd -m -u 1000 user

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONPATH=/home/user/app/src \
    HF_HOME=/home/user/.cache/huggingface \
    TRANSFORMERS_CACHE=/home/user/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/home/user/.cache/huggingface \
    TORCH_HOME=/home/user/.cache/torch \
    CUDA_VISIBLE_DEVICES="" \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1

WORKDIR /home/user/app

USER user

COPY --chown=user pyproject.toml README.md ./
COPY --chown=user src ./src
COPY --chown=user tests/fixtures ./tests/fixtures

# CPU wheel first, then pin it so sentence-transformers does not pull CUDA torch from PyPI.
RUN python -m pip install --user --upgrade pip \
 && python -m pip install --user torch --index-url https://download.pytorch.org/whl/cpu \
 && python -c "import torch; open('/tmp/constraints.txt','w').write(f'torch=={torch.__version__}\n')" \
 && python -m pip install --user -c /tmp/constraints.txt \
      "sentence-transformers>=3.0" \
      "polars>=1.0,<2.0" \
      "polars-distance>=0.4" \
      "httpx>=0.27" \
      "fastapi>=0.115" \
      "uvicorn[standard]>=0.32" \
      "numpy>=1.26"

EXPOSE 7860

# HF Spaces default app_port is 7860. docker-compose maps host 8000 → 7860.
CMD ["sh", "-c", "exec uvicorn supermarket_linkage.worker.api:app --host 0.0.0.0 --port ${PORT:-7860}"]
