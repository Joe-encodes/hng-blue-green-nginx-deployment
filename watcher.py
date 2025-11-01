import os
import time
import re
from collections import deque
from slack_sdk.webhook import WebhookClient
from pathlib import Path

# --- LogWatcher Class ---
# This class is responsible for tailing Nginx access logs, parsing them,
# detecting failover events and elevated error rates, and sending Slack alerts.
class LogWatcher:
    def __init__(self):
        # Initialize configuration from environment variables with default values.
        self.slack_webhook = os.getenv('SLACK_WEBHOOK_URL')
        self.error_rate_threshold = float(os.getenv('ERROR_RATE_THRESHOLD', 2)) # in percentage
        self.window_size = int(os.getenv('WINDOW_SIZE', 200)) # number of requests
        self.alert_cooldown = int(os.getenv('ALERT_COOLDOWN_SEC', 300)) # in seconds
        
        # Deque (double-ended queue) to store recent request data for error rate calculation.
        self.request_window = deque(maxlen=self.window_size)
        
        # Keep track of the last observed active pool to detect failovers.
        self.last_pool = os.getenv('ACTIVE_POOL', 'blue')
        
        # Timestamps for rate-limiting alerts.
        self.last_alert_time = 0 # For general error rate alerts
        self.last_failover_alert_time = 0 # For failover specific alerts
        
        # Initialize Slack client if a webhook URL is provided.
        self.slack_client = WebhookClient(self.slack_webhook) if self.slack_webhook else None
        print(f"Watcher initialized: threshold={self.error_rate_threshold}%, window={self.window_size}, cooldown={self.alert_cooldown}s")
        
    def parse_log_line(self, line):
        """Parse Nginx custom log format to extract relevant metrics."""
        try:
            # Regex to parse the custom_log format defined in nginx.conf.template.
            # It extracts request, status, upstream_addr, upstream_status, pool, and release.
            # The regex is more robust to handle potential variations in log lines.
            log_pattern = re.compile(r'^\[(?P<time_local>[^\]]+)\] "(?P<request>[^"]+)" (?P<status>\d{3}) '
                                     r'"(?P<upstream_addr>[^"]*)" "(?P<upstream_status>\d{3}|-)" '
                                     r'rt=(?P<request_time>\d+\.\d+) urt=(?P<upstream_response_time>\d+\.\d+|-) '
                                     r'pool="(?P<pool>[^"]*)" '
                                     r'release="(?P<release>[^"]*)"$')
            
            match = log_pattern.match(line)
            if match:
                data = match.groupdict()
                
                # Convert status codes and times to appropriate types, handle missing values.
                data['status'] = int(data['status'])
                data['upstream_status'] = int(data['upstream_status']) if data['upstream_status'] != '-' else data['status']
                data['request_time'] = float(data['request_time'])
                data['upstream_response_time'] = float(data['upstream_response_time']) if data['upstream_response_time'] != '-' else 0.0
                data['timestamp'] = time.time() # Add current timestamp for windowing
                data['raw_line'] = line.strip() # Keep original line for debugging
                
                return data
        except Exception as e:
            print(f"Error parsing log line: {e} - Line: {line.strip()}")
        
        return None

    def calculate_error_rate(self):
        """Calculate the percentage of 5xx errors within the current request window."""
        if not self.request_window:
            return 0
        
        # Count requests where upstream_status is a 5xx error.
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
            # Enforce cooldown for failover alerts.
            if current_time - self.last_failover_alert_time > self.alert_cooldown:
                self.send_slack_alert(f"🔄 {failover_msg}")
                self.last_failover_alert_time = current_time
            
            self.last_pool = current_pool # Update last observed pool
            return True
        return False

    def check_error_rate(self):
        """Checks if the current 5xx error rate exceeds the defined threshold."""
        error_rate = self.calculate_error_rate()
        
        if error_rate > self.error_rate_threshold:
            current_time = time.time()
            # Enforce cooldown for error rate alerts.
            if current_time - self.last_alert_time > self.alert_cooldown:
                alert_msg = (f"High error rate detected: {error_rate:.1f}% "
                           f"(threshold: {self.error_rate_threshold}% over {self.window_size} requests)\n"
                           f"Current active pool: {self.last_pool.upper()}")
                
                self.send_slack_alert(f"❌ {alert_msg}")
                self.last_alert_time = current_time
                return True
        return False

    def watch_logs(self):
        """Main loop to continuously watch, parse Nginx access logs, and trigger alerts."""
        log_file = Path('/var/log/nginx/access.log')
        
        print(f"Starting Nginx log watcher... Monitoring: {log_file}")
        print(f"Config: Error Rate Threshold={self.error_rate_threshold}%, Window Size={self.window_size}, Alert Cooldown={self.alert_cooldown}s")
        
        # Wait until the Nginx log file exists before attempting to read.
        while not log_file.exists():
            print("Waiting for Nginx log file to be created...")
            time.sleep(2)
        
        # Open the log file and seek to the end to only process new log entries.
        with open(log_file, 'r') as file:
            file.seek(0, 2)  # Go to the end of the file
            
            while True:
                line = file.readline()
                if line:
                    log_data = self.parse_log_line(line)
                    if log_data:
                        self.request_window.append(log_data) # Add request to the sliding window
                        
                        # Check for failover on every parsed log entry.
                        self.check_failover(log_data['pool'])
                        
                        # Periodically check error rate to avoid excessive computation.
                        # For example, check every 10 requests or when the window is full.
                        if len(self.request_window) % 10 == 0 or len(self.request_window) == self.window_size:
                            self.check_error_rate()
                        
                        # Optional: Debug output to see watcher activity.
                        if len(self.request_window) % 50 == 0:
                            current_error_rate = self.calculate_error_rate()
                            print(f"Processed {len(self.request_window)} requests. Current Error Rate: {current_error_rate:.1f}%. Current Pool: {log_data['pool'].upper()}")
                
                time.sleep(0.01) # Short delay to prevent busy-waiting

if __name__ == '__main__':
    watcher = LogWatcher()
    watcher.watch_logs()
