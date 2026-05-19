FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libxrender1 \
    libxext6 \
    libx11-6 \
    libgomp1 \
    libfontconfig1 \
    libfreetype6 \
    libsm6 \
    libice6 \
    && rm -rf /var/lib/apt/lists/*

ENV DISPLAY=:99
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p outputs

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
