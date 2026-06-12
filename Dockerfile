FROM python:3.12-slim

# Install uv
RUN pip install uv

# Set working directory
WORKDIR /opt/arthabot

# Copy pyproject.toml and source
COPY pyproject.toml uv.lock ./
COPY src/ src/
COPY config/ config/
COPY scripts/ scripts/

# Install dependencies using uv
RUN uv pip install --system .

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)" || exit 1

# PAPER is the only deployed trading mode. LIVE promotion remains a separate,
# explicitly approved operation.
ENTRYPOINT ["python", "scripts/run_paper_loop.py"]
