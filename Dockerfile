# Dockerfile for the Python-based Alert Watcher service.
# This image is built by docker-compose for the 'alert_watcher' service.

# Use a lightweight Python base image
FROM python:3.9-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file and install Python dependencies
# Using --no-cache-dir to prevent pip from storing cache data, reducing image size
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the watcher script into the container
COPY watcher.py .

# Command to run the watcher script when the container starts
CMD ["python", "watcher.py"]
