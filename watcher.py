import os
import time
import re
import docker
from collections import deque
from slack_sdk.webhook import WebhookClient

class LogWatcher:
    def __init__(self):
        self.slack_webhook = os.getenv('SLACK_WEBHOOK_URL')
        self.error_rate_threshold = float(os.getenv('ERROR_RATE_THRESHOLD', 2))
        self.window_size = int(os.getenv('WINDOW_SIZE', 200))
        self.alert_cooldown = int(os.getenv('ALERT_COOLDOWN_SEC', 300))
        
        self.request_window = deque(maxlen=self.window_size)
        self.last_pool = os.getenv('ACTIVE_POOL', 'blue')
        self.last_alert_time = 0
        self.last_failover_alert_time = 0
        
        self.slack_client = WebhookClient(self.slack_webhook) if self.slack_webhook else None
        self.docker_client = docker.from_env()
        
        print(f"Watcher initialized: threshold={self.error_rate_threshold}%, window={self.window_size}, cooldown={self.alert_cooldown}s")
        
    def parse_log_line(self, line):
        """Parse Nginx log line."""
        try:
            # Your existing logs show this format:
            # [02/Nov/2025:23:16:18 +0000] "GET /version HTTP/1.1" 200 "172.18.0.3:3000" "200" rt=0.002 urt=0.003 pool="blue" release="blue-v1.0.0"
            
            pool_match = re.search(r'pool="([^"]*)"', line)
            status_match = re.search(r'" (\d{3}) ', line)
            
            if pool_match and status_match:
                pool = pool_match.group(1)
                status = int(status_match.group(1))
                
                return {
                    'pool': pool,
                    'status': status,
                    'upstream_status': status,  # Use same as status for simplicity
                    'timestamp': time.time(),
                    'raw_line': line.strip()
                }
        except Exception as e:
            print(f"Error parsing log line: {e}")
        
        return None

    def calculate_error_rate(self):
        """Calculate the percentage of 5xx errors."""
        if not self.request_window:
            return 0
        
        error_count = sum(1 for req in self.request_window 
                         if 500 <= req.get('upstream_status', 200) < 600)
        return (error_count / len(self.request_window)) * 100

    def send_slack_alert(self, message):
        """Send alert to Slack."""
        if not self.slack_client:
            print(f"SLACK ALERT (no webhook): {message}")
            return
        
        try:
            response = self.slack_client.send(
                text=message,
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"🚨 *Blue/Green Alert*\n{message}"
                        }
                    }
                ]
            )
            print(f"✅ Slack alert sent: {response.status_code}")
        except Exception as e:
            print(f"❌ Failed to send Slack alert: {e}")

    def check_failover(self, current_pool):
        """Check if failover occurred."""
        if current_pool and current_pool != self.last_pool:
            failover_msg = f"Failover detected: {self.last_pool} → {current_pool}"
            print(f"🔄 {failover_msg}")
            
            current_time = time.time()
            if current_time - self.last_failover_alert_time > self.alert_cooldown:
                self.send_slack_alert(failover_msg)
                self.last_failover_alert_time = current_time
            
            self.last_pool = current_pool
            return True
        return False

    def check_error_rate(self):
        """Check if error rate exceeds threshold."""
        error_rate = self.calculate_error_rate()
        
        if error_rate > self.error_rate_threshold:
            current_time = time.time()
            if current_time - self.last_alert_time > self.alert_cooldown:
                alert_msg = f"High error rate: {error_rate:.1f}% (threshold: {self.error_rate_threshold}%)"
                self.send_slack_alert(alert_msg)
                self.last_alert_time = current_time
                return True
        return False

    def watch_logs(self):
        """Watch Docker container logs directly."""
        print("Starting Docker logs watcher...")
        
        try:
            # Get the nginx container
            containers = self.docker_client.containers.list()
            nginx_container = None
            for container in containers:
                if 'nginx' in container.name:
                    nginx_container = container
                    break
            
            if not nginx_container:
                print("❌ Nginx container not found!")
                return
            
            print(f"✅ Watching logs from: {nginx_container.name}")
            
            # Stream logs
            for line in nginx_container.logs(stream=True, follow=True):
                line = line.decode('utf-8').strip()
                log_data = self.parse_log_line(line)
                
                if log_data:
                    self.request_window.append(log_data)
                    self.check_failover(log_data['pool'])
                    
                    if len(self.request_window) % 10 == 0:
                        self.check_error_rate()
                    
                    # Debug output
                    if len(self.request_window) % 20 == 0:
                        error_rate = self.calculate_error_rate()
                        print(f"📊 Processed {len(self.request_window)} requests. Error rate: {error_rate:.1f}%")
                        
        except Exception as e:
            print(f"❌ Error watching logs: {e}")
            time.sleep(5)
            self.watch_logs()  # Restart on error

if __name__ == '__main__':
    watcher = LogWatcher()
    watcher.watch_logs()