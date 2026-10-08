FROM python:3.11-slim

WORKDIR /app

COPY services/agent/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY services/agent/ ./services/agent/
COPY data/ ./data/

WORKDIR /app/services/agent

ENV PYTHONUNBUFFERED=1

EXPOSE 8003

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003"]
