FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8080 \
    U2NET_HOME=/app/.u2net \
    IMAGE2SVG_REMBG_MODEL=isnet-general-use

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir "rembg[cpu]>=2.0.67" onnxruntime opencv-python-headless \
    && mkdir -p "$U2NET_HOME" \
    && IMAGE2SVG_REMBG_ALLOW_DOWNLOAD=1 python -c "from rembg import new_session; new_session('isnet-general-use')"

COPY . .

EXPOSE 8080

CMD ["python", "server.py"]
