# Sandbox where Sensai runs the Python code the model writes.
# Build: docker build -t sensai-sandbox src/sensai/adapters/sandbox/image
FROM python:3.13-slim

RUN pip install --no-cache-dir \
        sympy==1.14.0 \
        numpy==2.5.4 \
        scipy==1.18.1 \
        matplotlib==3.11.2 \
        pandas==3.1.0 \
    && useradd --create-home --uid 1000 sandbox

# Render figures to files; there is no display.
ENV MPLBACKEND=Agg \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/matplotlib

USER sandbox
WORKDIR /work
