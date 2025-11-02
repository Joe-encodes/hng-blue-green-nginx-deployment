import os
import time
import re
from collections import deque
from slack_sdk.webhook import WebhookClient
from pathlib import Path

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
        print(f"Watcher initialized: threshold={self.error_rate_threshold}%, window={self.window_size}, cooldown={self.alert_cooldown}s")
        
    def parse_log_line(self, line):
        """Parse Nginx custom log format to extract relevant metrics."""
        try:
            # Extract pool and status using simpler regex
            pool_match = re.search(r'pool="([^"]*)"', line)
            status_match = re.search(r'" (\d{3}) ', line)
            upstream_status_match = re.search(r'"(\d{3})"', line)
            
            if pool_match and status_match:
                pool = pool_match.group(1)
                status = int(status_match.group(1))
                upstream_status = int(upstream_status_match.group(1)) if upstream_status_match else status
                
                return {
                    'pool': pool,
                    'status': status,
                    'upstream_status': upstream_status,
                    'timestamp': time.time(),
                    'raw_line': line.strip()
                }
        except Exception as e:
            print(f"Error parsing log line: {e}")
        
        return None

    def calculate_error_rate(self):
        """Calculate the percentage of 5xx errors within the current request window."""
        if not self.request_window:
            return 0
        
        error_count = sum(1 for req in self.request_window 
                         if 500 <= req.get('upstream_status', 200) < 600)
        return (error_count / len(self.request_window)) * 100

    def send_slack_alert(self, message):
        """Sends a formatted alert message to Slack using the configured webhook."""
        if not self.slack_client:
            print(f"SLACK ALERT (no webhook configured): {message}")
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
                    },
                    {
                        "type": "divider"
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f"Timestamp: <!date^{int(time.time())}^{{date}} at {{time}}|{time.ctime()}>"
                            }
                        ]
                    }
                ]
            )
            print(f"Slack alert sent. Status Code: {response.status_code}")
        except Exception as e:
            print(f"Failed to send Slack alert: {e}")

    def check_failover(self, current_pool):
        """Detects if a failover has occurred by comparing the current pool to the last observed pool."""
        if current_pool and current_pool != self.last_pool:
            failover_msg = f"Failover detected: {self.last_pool.upper()} → {current_pool.upper()}"
            print(f"[FAILOVER DETECTED] {failover_msg}")
            
            current_time = time.time()
            if current_time - self.last_failover_alert_time > self.alert_cooldown:
                self.send_slack_alert(f"🔄 {failover_msg}")
                self.last_failover_alert_time = current_time
            
            self.last_pool = current_pool
            return True
        return False

    def check_error_rate(self):
        """Checks if the current 5xx error rate exceeds the defined threshold."""
        error_rate = self.calculate_error_rate()
        
        if error_rate > self.error_rate_threshold:
            current_time = time.time()
            if current_time - self.last_alert_time > self.alert_cooldown:
                alert_msg = (f"High error rate detected: {error_rate:.1f}% "
                           f"(threshold: {self.error_rate_threshold}% over {self.window_size} requests)\n"
                           f"Current active pool: {self.last_pool.upper()}")
                
                self.send_slack_alert(f"❌ {alert_msg}")
                self.last_alert_time = current_time
                return True
        return False

    def watch_logs(self):
        """Main loop to continuously watch and parse Nginx access logs."""
        log_file = Path('/var/log/nginx/access.log')
        
        print(f"Starting Nginx log watcher... Monitoring: {log_file}")
        print(f"Config: Error Rate Threshold={self.error_rate_threshold}%, Window Size={self.window_size}, Alert Cooldown={self.alert_cooldown}s")
        
        # Wait until the Nginx log file exists
        while not log_file.exists():
            print("Waiting for Nginx log file to be created...")
            time.sleep(2)
        
        # Read from beginning and track position
        file_position = 0
        
        while True:
            try:
                with open(log_file, 'r') as file:
                    # Go to last known position
                    file.seek(file_position)
                    
                    # Read new lines
                    for line in file:
                        log_data = self.parse_log_line(line)
                        if log_data:
                            self.request_window.append(log_data)
                            
                            # Check for failover
                            self.check_failover(log_data['pool'])
                            
                            # Check error rate periodically
                            if len(self.request_window) % 10 == 0:
                                self.check_error_rate()
                    
                    # Update position for next read
                    file_position = file.tell()
                    
            except Exception as e:
                print(f"Error reading log file: {e}")
            
            time.sleep(1)  # Check for new logs every second

if __name__ == '__main__':
    watcher = LogWatcher()
    watcher.watch_logs()