FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /app

COPY pyproject.toml ./
COPY backend ./backend
COPY simulator ./simulator

RUN python -m pip install --no-cache-dir '.[dev]'

CMD ["python", "-m", "simulator.memorial_sim.main"]
