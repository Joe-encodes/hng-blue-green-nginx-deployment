FROM python:3.9-slim

WORKDIR /app

# Install docker client
RUN apt-get update && apt-get install -y docker.io

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY watcher.py .

# Run as root to access docker socket (for simplicity)
CMD ["python", "watcher.py"]