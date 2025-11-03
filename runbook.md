# Blue/Green Deployment Runbook

## Alerts and Operator Actions

### 🔄 Failover Detected Alert
**What it means**: Traffic has automatically switched from one pool to another due to failures.

**Operator Actions**:
1. Check primary pool health: `curl http://localhost:8081/healthz`
2. Check secondary pool health: `curl http://localhost:8082/healthz`
3. Investigate primary pool issues in container logs
4. Stop chaos if active: `curl -X POST http://localhost:8081/chaos/stop`

### ❌ High Error Rate Alert
**What it means**: >2% of requests are returning 5xx errors in the last 200 requests.

**Operator Actions**:
1. Check Nginx logs: `docker-compose logs nginx`
2. Identify affected pool from logs
3. Check application health and resources
4. Consider manual intervention if needed

### 🛡️ Maintenance Mode
During planned maintenance:
- Stop watcher: `docker-compose stop alert_watcher`
- Or increase error threshold temporarily
- Use Slack's "Do Not Disturb" mode

## Quick Commands
```bash
# Check status
docker-compose ps

# View logs
docker-compose logs nginx
docker-compose logs alert_watcher

# Test endpoints
curl http://localhost:8080/version
curl http://localhost:8081/healthz
curl http://localhost:8082/healthz

# Chaos testing
curl -X POST "http://localhost:8081/chaos/start?mode=error"
curl -X POST "http://localhost:8081/chaos/stop"