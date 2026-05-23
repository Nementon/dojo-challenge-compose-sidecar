FROM python:3.12-alpine

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN apk add --no-cache docker-cli docker-cli-compose \
    && pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

CMD ["python", "app/orchestrator.py"]
