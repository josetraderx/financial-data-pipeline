# Minimal Dockerfile (adjust per repo)
FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir --upgrade pip \
    && if [ -f requirements.txt ]; then pip install -r requirements.txt; else pip install -e .; fi
CMD ["python", "-c", "print('Container ready. Override CMD in docker-compose or Docker run.')"]
