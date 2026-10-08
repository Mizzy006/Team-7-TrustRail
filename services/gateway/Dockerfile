FROM python:3.11-slim

WORKDIR /app

COPY services/gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/gateway/ .
COPY contracts/ ./contracts/

ENV PYTHONUNBUFFERED=1
ENV DEMO_MODE=true

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
