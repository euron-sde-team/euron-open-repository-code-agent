# syntax=docker/dockerfile:1.7
# The image every sandboxed test run starts in: Python and pytest, nothing else. The worker
# creates one throwaway container per run from it, with networking disabled, every
# capability dropped, a non-root user and cgroup limits (see sandbox/docker.py).
#   docker build -f infra/docker/sandbox.Dockerfile -t codeagent-sandbox:local .
ARG PYTHON_IMAGE=python:3.12.15-slim-bookworm
FROM ${PYTHON_IMAGE}
LABEL org.opencontainers.image.title="Euron CodeAgent sandbox" \
      org.opencontainers.image.description="Throwaway test runner for CodeAgent: Python and pytest" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.vendor="ENGAGESPHERE TECHNOLOGY PRIVATE LIMITED"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install "pytest==9.1.0" "pytest-timeout==2.4.0" \
 && useradd --uid 10001 --user-group --no-create-home --home-dir /tmp sandbox \
 && mkdir /workspace && chown 10001:10001 /workspace
WORKDIR /workspace
USER 10001:10001
CMD ["python", "--version"]
