import os
import time
import re
from collections import deque
from pathlib import Path
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
        
        print(f"Log Watcher: threshold={self.error_rate_threshold}%, window={self.window_size}")

    def parse_log_line(self, line):
        try:
            # Parse Nginx log format: pool="blue" release="blue-v1.0.0" etc.
            pool_match = re.search(r'pool="([^"]*)"', line)
            status_match = re.search(r'" (\d{3}) ', line)
            upstream_status_match = re.search(r'"(\d{3})"', line)
            
            if pool_match and status_match:
                return {
                    'pool': pool_match.group(1),
                    'status': int(status_match.group(1)),
                    'upstream_status': int(upstream_status_match.group(1)) if upstream_status_match else int(status_match.group(1)),
                    'timestamp': time.time()
                }
        except Exception as e:
            print(f"Parse error: {e}")
        return None

    def calculate_error_rate(self):
        if not self.request_window:
            return 0
        error_count = sum(1 for req in self.request_window if 500 <= req.get('upstream_status', 200) < 600)
        return (error_count / len(self.request_window)) * 100

    def send_slack_alert(self, message):
        if not self.slack_client:
            print(f"SLACK: {message}")
            return
        
        try:
            response = self.slack_client.send(text=message)
            print(f"Alert sent: {response.status_code}")
        except Exception as e:
            print(f"Slack error: {e}")

    def check_failover(self, current_pool):
        if current_pool and current_pool != self.last_pool:
            current_time = time.time()
            if current_time - self.last_failover_alert_time > self.alert_cooldown:
                message = f"🔄 Failover detected: {self.last_pool} → {current_pool}"
                self.send_slack_alert(message)
                self.last_failover_alert_time = current_time
            self.last_pool = current_pool
            return True
        return False

    def check_error_rate(self):
        error_rate = self.calculate_error_rate()
        if error_rate > self.error_rate_threshold:
            current_time = time.time()
            if current_time - self.last_alert_time > self.alert_cooldown:
                message = f"❌ High error rate: {error_rate:.1f}% (threshold: {self.error_rate_threshold}%)"
                self.send_slack_alert(message)
                self.last_alert_time = current_time
                return True
        return False

    def watch_logs(self):
        log_file = Path('/var/log/nginx/access.log')
        
        while not log_file.exists():
            print("Waiting for log file...")
            time.sleep(2)
        
        with open(log_file, 'r') as file:
            while True:
                line = file.readline()
                if line:
                    log_data = self.parse_log_line(line)
                    if log_data:
                        self.request_window.append(log_data)
                        self.check_failover(log_data['pool'])
                        
                        if len(self.request_window) % 10 == 0:
                            self.check_error_rate()
                
                time.sleep(0.1)

if __name__ == '__main__':
    watcher = LogWatcher()
    watcher.watch_logs()