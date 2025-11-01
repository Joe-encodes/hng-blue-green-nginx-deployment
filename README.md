# Blue/Green Deployment with Nginx & Observability

## Stage 3 - Observability & Alerts

**Adamu Joseph (AKA TechGee)** - DevOps Intern Task

This project implements a Blue/Green deployment with Nginx for automatic failover and integrates observability features using a Python log watcher for Slack alerts.

### Features

-   **Blue/Green Deployment**: Seamless traffic switching between active (Blue) and backup (Green) application instances.
-   **Automatic Failover**: Nginx automatically redirects traffic to the healthy pool upon detecting failures in the active one.
-   **Slack Alerts**: Real-time notifications for failover events and elevated error rates, sent via a Python log watcher.
-   **Structured Logging**: Enhanced Nginx access logs capture critical metrics for monitoring.
-   **Chaos Engineering Endpoints**: Built-in endpoints to simulate application downtime for testing failover.

### Quick Start

1.  **Clone and Configure**:
    ```bash
    git clone <your-repo-url>
    cd ngnix_upstream # or your repo directory
    cp .env.example .env
    # Edit .env to set your SLACK_WEBHOOK_URL and other configurations
    ```

2.  **Deploy Services**:
    ```bash
    docker-compose up -d
    ```

3.  **Verify Deployment**:
    ```bash
    curl http://localhost:8080/version
    ```
    Expected output should indicate the `blue` pool.

### Slack Alerts Overview

-   **Failover Detected**: Alerts when traffic switches between Blue and Green pools.
-   **High Error Rate**: Notifies when 5xx errors exceed a defined threshold over a sliding window.
-   Alerts are rate-limited to prevent spam.

### Repository Contents

-   `docker-compose.yml`: Defines the Nginx, Blue app, Green app, and Alert Watcher services.
-   `nginx.conf.template`: Nginx configuration with failover logic and custom logging format.
-   `Dockerfile`: Dockerfile for the Python Alert Watcher service.
-   `requirements.txt`: Python dependencies for the Alert Watcher.
-   `watcher.py`: Python script for real-time Nginx log monitoring and Slack alerting.
-   `.env.example`: Template for environment variables.
-   `runbook.md`: Operational guide for understanding and responding to alerts.

Further details on testing, troubleshooting, and alert suppression can be found in `runbook.md`.
