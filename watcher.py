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
        
        print(f"🚀 Log Watcher Initialized")
        print(f"   - Error Threshold: {self.error_rate_threshold}%")
        print(f"   - Window Size: {self.window_size} requests")
        print(f"   - Alert Cooldown: {self.alert_cooldown}s")

    def parse_log_line(self, line):
        """Parse Nginx custom log format"""
        try:
            # Parse: [timestamp] "request" status "upstream" "upstream_status" rt=... urt=... pool="..." release="..."
            pool_match = re.search(r'pool="([^"]*)"', line)
            status_match = re.search(r'" (\d{3}) ', line)
            upstream_status_match = re.search(r'"(\d{3})"', line)
            
            if pool_match and status_match:
                return {
                    'pool': pool_match.group(1),
                    'status': int(status_match.group(1)),
                    'upstream_status': int(upstream_status_match.group(1)) if upstream_status_match else int(status_match.group(1)),
                    'timestamp': time.time(),
                    'raw_line': line.strip()
                }
        except Exception as e:
            print(f"⚠️ Parse error: {e}")
        return None

    def calculate_error_rate(self):
        """Calculate 5xx error rate in current window"""
        if not self.request_window:
            return 0
        
        error_count = sum(1 for req in self.request_window 
                         if 500 <= req.get('upstream_status', 200) < 600)
        return (error_count / len(self.request_window)) * 100

    def send_slack_alert(self, message):
        """Send alert to Slack"""
        if not self.slack_client:
            print(f"📢 {message}")
            return
        
        try:
            response = self.slack_client.send(text=message)
            print(f"✅ Alert sent to Slack")
        except Exception as e:
            print(f"❌ Slack error: {e}")

    def check_failover(self, current_pool):
        """Detect and alert on failover events"""
        if current_pool and current_pool != self.last_pool:
            current_time = time.time()
            if current_time - self.last_failover_alert_time > self.alert_cooldown:
                message = f"🔄 Failover detected: {self.last_pool} → {current_pool}"
                print(f"🚨 {message}")
                self.send_slack_alert(message)
                self.last_failover_alert_time = current_time
            
            self.last_pool = current_pool
            return True
        return False

    def check_error_rate(self):
        """Check if error rate exceeds threshold"""
        error_rate = self.calculate_error_rate()
        
        if error_rate > self.error_rate_threshold:
            current_time = time.time()
            if current_time - self.last_alert_time > self.alert_cooldown:
                message = f"❌ High error rate: {error_rate:.1f}% (threshold: {self.error_rate_threshold}%)"
                print(f"🚨 {message}")
                self.send_slack_alert(message)
                self.last_alert_time = current_time
                return True
        return False

    def watch_logs(self):
        """Main loop to watch and parse Nginx logs"""
        log_file = Path('/var/log/nginx/access.log')
        
        print(f"📁 Monitoring: {log_file}")
        
        # Wait for log file
        while not log_file.exists():
            print("⏳ Waiting for log file...")
            time.sleep(2)
        
        print("✅ Starting to watch logs...")
        
        # Track file position
        file_position = 0
        
        while True:
            try:
                with open(log_file, 'r') as file:
                    # Go to last position
                    if file_position > 0:
                        file.seek(file_position)
                    
                    # Read new lines
                    for line in file:
                        log_data = self.parse_log_line(line)
                        if log_data:
                            self.request_window.append(log_data)
                            self.check_failover(log_data['pool'])
                    
                    # Update position
                    file_position = file.tell()
                
                # Check error rate periodically
                if len(self.request_window) % 10 == 0:
                    self.check_error_rate()
                
                # Debug output
                if len(self.request_window) % 20 == 0:
                    error_rate = self.calculate_error_rate()
                    print(f"📊 Processed {len(self.request_window)} requests. Error rate: {error_rate:.1f}%")
                
                time.sleep(1)
                
            except Exception as e:
                print(f"⚠️ Error reading logs: {e}")
                time.sleep(5)

if __name__ == '__main__':
    watcher = LogWatcher()
    watcher.watch_logs()