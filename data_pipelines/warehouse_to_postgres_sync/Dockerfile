FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py tables.yml ./

ENV PYTHONUNBUFFERED=1
# One worker, long timeout: a sync is a single long request, not many short ones.
CMD exec gunicorn --bind :$PORT --workers 1 --threads 2 --timeout 3600 main:app
