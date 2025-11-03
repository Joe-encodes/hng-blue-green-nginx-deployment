import os
import time
import requests
import json
from datetime import datetime
from slack_sdk.webhook import WebhookClient
from collections import deque

class EnhancedWatcher:
    def __init__(self):
        self.slack_webhook = os.getenv('SLACK_WEBHOOK_URL')
        self.active_pool = os.getenv('ACTIVE_POOL', 'blue')
        self.error_rate_threshold = float(os.getenv('ERROR_RATE_THRESHOLD', 2))
        self.window_size = int(os.getenv('WINDOW_SIZE', 50))
        self.alert_cooldown = int(os.getenv('ALERT_COOLDOWN_SEC', 300))
        
        # Monitoring state
        self.last_pool = self.active_pool
        self.request_window = deque(maxlen=self.window_size)
        self.last_alert_time = 0
        self.last_failover_alert_time = 0
        self.health_check_failures = 0
        
        # Slack client
        self.slack_client = WebhookClient(self.slack_webhook) if self.slack_webhook else None
        
        print(f"🚀 Enhanced Watcher Initialized")
        print(f"   - Target Pool: {self.active_pool}")
        print(f"   - Error Threshold: {self.error_rate_threshold}%")
        print(f"   - Monitoring Window: {self.window_size} requests")
        print(f"   - Alert Cooldown: {self.alert_cooldown}s")

    def send_slack_alert(self, title, message, level="info"):
        """Send formatted alert to Slack"""
        colors = {
            "info": "#36a64f",      # Green
            "warning": "#f2c744",   # Yellow  
            "error": "#e01e5a",     # Red
            "failover": "#4a154b"   # Purple
        }
        
        color = colors.get(level, "#36a64f")
        icon = "🔔" if level == "info" else "⚠️" if level == "warning" else "🚨"
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{icon} {title}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": message
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
                        "text": f"*Timestamp:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                    },
                    {
                        "type": "mrkdwn", 
                        "text": f"*Monitor:* Blue/Green Deployment"
                    }
                ]
            }
        ]
        
        print(f"📤 {level.upper()} ALERT: {title}")
        print(f"   {message}")
        
        if self.slack_client:
            try:
                response = self.slack_client.send(
                    text=f"{icon} {title}: {message}",
                    blocks=blocks
                )
                print(f"   ✅ Sent to Slack (Status: {response.status_code})")
                return True
            except Exception as e:
                print(f"   ❌ Slack Error: {e}")
                return False
        else:
            print("   ⚠️ No Slack webhook configured")
            return False

    def check_service_health(self):
        """Check health of both blue and green services"""
        health_status = {}
        
        for pool, port in [('blue', 8081), ('green', 8082)]:
            try:
                response = requests.get(f'http://localhost:{port}/healthz', timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    health_status[pool] = {
                        'status': 'healthy',
                        'uptime': data.get('data', {}).get('uptime', 'unknown'),
                        'metrics': data.get('data', {}).get('metrics', {}),
                        'chaos_mode': data.get('data', {}).get('checks', {}).get('chaos') == 'active'
                    }
                else:
                    health_status[pool] = {'status': 'unhealthy', 'error': f'HTTP {response.status_code}'}
            except Exception as e:
                health_status[pool] = {'status': 'unreachable', 'error': str(e)}
        
        return health_status

    def get_service_metrics(self, pool, port):
        """Get detailed metrics from a service"""
        try:
            response = requests.get(f'http://localhost:{port}/metrics', timeout=5)
            if response.status_code == 200:
                return response.json().get('data', {})
        except Exception as e:
            print(f"❌ Failed to get metrics from {pool}: {e}")
        return {}

    def detect_failover(self, current_pool):
        """Detect and alert on failover events"""
        if current_pool and current_pool != self.last_pool:
            current_time = time.time()
            
            # Check cooldown
            if current_time - self.last_failover_alert_time > self.alert_cooldown:
                health_status = self.check_service_health()
                
                message = f"*Failover Event Detected*\n"
                message += f"• *From:* `{self.last_pool}` → *To:* `{current_pool}`\n"
                message += f"• *Time:* {datetime.now().strftime('%H:%M:%S')}\n\n"
                message += f"*Health Status:*\n"
                
                for pool, status in health_status.items():
                    icon = "✅" if status['status'] == 'healthy' else "❌"
                    chaos_icon = "⚡" if status.get('chaos_mode') else "⚪"
                    message += f"• `{pool}`: {icon} {status['status']} {chaos_icon}\n"
                
                self.send_slack_alert(
                    "🔄 Blue/Green Failover Detected", 
                    message,
                    "failover"
                )
                self.last_failover_alert_time = current_time
            
            self.last_pool = current_pool
            return True
        return False

    def check_error_rates(self):
        """Check for elevated error rates"""
        if len(self.request_window) < 10:  # Need minimum data
            return
        
        error_count = sum(1 for req in self.request_window if not req.get('success', True))
        error_rate = (error_count / len(self.request_window)) * 100
        
        if error_rate > self.error_rate_threshold:
            current_time = time.time()
            if current_time - self.last_alert_time > self.alert_cooldown:
                message = f"*High Error Rate Alert*\n"
                message += f"• *Current Rate:* `{error_rate:.1f}%`\n"
                message += f"• *Threshold:* `{self.error_rate_threshold}%`\n"
                message += f"• *Window Size:* `{len(self.request_window)}` requests\n"
                message += f"• *Active Pool:* `{self.last_pool}`\n\n"
                message += f"*Recent Errors:* {error_count} of {len(self.request_window)} requests failed"
                
                self.send_slack_alert(
                    "❌ High Error Rate Detected",
                    message,
                    "error"
                )
                self.last_alert_time = current_time
                return True
        return False

    def monitor_services(self):
        """Main monitoring loop"""
        print("🔍 Starting enhanced service monitoring...")
        self.send_slack_alert(
            "🚀 Blue/Green Monitor Started",
            f"*Monitoring Configuration:*\n• Active Pool: `{self.active_pool}`\n• Error Threshold: `{self.error_rate_threshold}%`\n• Window Size: `{self.window_size}` requests\n• Alert Cooldown: `{self.alert_cooldown}s`"
        )
        
        consecutive_failures = 0
        max_consecutive_failures = 3
        
        while True:
            try:
                # Check current active pool through nginx
                response = requests.get('http://nginx:80/version', timeout=10)
                
                if response.status_code == 200:
                    consecutive_failures = 0
                    data = response.json()
                    
                    # Extract pool from headers or response
                    current_pool = response.headers.get('X-App-Pool') 
                    if not current_pool and 'data' in data:
                        current_pool = data['data'].get('service', {}).get('pool')
                    
                    # Track request success
                    self.request_window.append({
                        'success': True,
                        'pool': current_pool,
                        'timestamp': datetime.now().isoformat(),
                        'status_code': response.status_code
                    })
                    
                    # Check for failover
                    if current_pool:
                        self.detect_failover(current_pool)
                    
                    # Check error rates periodically
                    if len(self.request_window) % 5 == 0:  # Every 5 requests
                        self.check_error_rates()
                    
                    # Periodic health report (every 30 checks)
                    if len(self.request_window) % 30 == 0:
                        health_status = self.check_service_health()
                        healthy_pools = [p for p, s in health_status.items() if s['status'] == 'healthy']
                        
                        message = f"*Periodic Health Check*\n"
                        message += f"• *Active Pool:* `{current_pool or 'unknown'}`\n"
                        message += f"• *Healthy Services:* `{len(healthy_pools)}/2`\n"
                        message += f"• *Total Requests:* `{len(self.request_window)}`\n"
                        message += f"• *Current Error Rate:* `{(sum(1 for r in self.request_window if not r.get('success', True)) / len(self.request_window) * 100):.1f}%`"
                        
                        self.send_slack_alert(
                            "📊 System Health Report",
                            message,
                            "info"
                        )
                
                else:
                    # Track failed request
                    self.request_window.append({
                        'success': False,
                        'timestamp': datetime.now().isoformat(),
                        'status_code': response.status_code,
                        'error': f'HTTP {response.status_code}'
                    })
                    consecutive_failures += 1
                    
            except requests.exceptions.RequestException as e:
                # Track connection error
                self.request_window.append({
                    'success': False,
                    'timestamp': datetime.now().isoformat(),
                    'error': str(e)
                })
                consecutive_failures += 1
                print(f"❌ Request failed: {e}")
            
            # Alert if multiple consecutive failures
            if consecutive_failures >= max_consecutive_failures:
                self.send_slack_alert(
                    "🚨 Service Unreachable",
                    f"*Critical Alert:* Failed to reach service {consecutive_failures} times consecutively\n• Last Error: `{self.request_window[-1].get('error', 'unknown')}`\n• Time: {datetime.now().strftime('%H:%M:%S')}",
                    "error"
                )
                consecutive_failures = 0  # Reset after alert
            
            # Wait before next check
            time.sleep(5)

def main():
    """Main entry point"""
    print("=" * 50)
    print("🔬 Blue/Green Deployment Monitor")
    print("=" * 50)
    
    watcher = EnhancedWatcher()
    
    try:
        watcher.monitor_services()
    except KeyboardInterrupt:
        print("\n⏹️ Monitoring stopped by user")
        watcher.send_slack_alert(
            "⏹️ Monitor Stopped",
            "Blue/Green monitoring has been manually stopped"
        )
    except Exception as e:
        print(f"💥 Critical error: {e}")
        watcher.send_slack_alert(
            "💥 Monitor Crashed",
            f"Monitoring service encountered a critical error:\n```{str(e)}```"
        )
        raise

if __name__ == '__main__':
    main()