import os
import time
import requests
from slack_sdk.webhook import WebhookClient

# Configuration
SLACK_WEBHOOK = os.getenv('SLACK_WEBHOOK_URL')
ACTIVE_POOL = os.getenv('ACTIVE_POOL', 'blue')

slack_client = WebhookClient(SLACK_WEBHOOK) if SLACK_WEBHOOK else None

def send_slack_alert(message):
    """Send alert to Slack"""
    print(f"🔔 ALERT: {message}")
    if slack_client:
        try:
            response = slack_client.send(text=message)
            print(f"✅ Sent to Slack (status: {response.status_code})")
        except Exception as e:
            print(f"❌ Slack error: {e}")
    else:
        print("❌ No Slack webhook configured")

def monitor_failover():
    """Monitor for failovers by checking the active pool"""
    last_pool = ACTIVE_POOL
    print(f"🚀 Starting failover monitor. Initial pool: {last_pool}")
    
    while True:
        try:
            # Check current active pool
            response = requests.get('http://nginx:80/version', timeout=5)
            current_pool = response.headers.get('X-App-Pool', 'unknown')
            
            # Detect failover
            if current_pool != last_pool and current_pool in ['blue', 'green']:
                alert_msg = f"🔄 Failover detected: {last_pool} → {current_pool}"
                print(alert_msg)
                send_slack_alert(alert_msg)
                last_pool = current_pool
            
            # Check for high error rates (simplified)
            if response.status_code >= 500:
                error_msg = f"❌ 5xx Error detected: Status {response.status_code}, Pool: {current_pool}"
                print(error_msg)
                send_slack_alert(error_msg)
                
        except requests.exceptions.RequestException as e:
            error_msg = f"❌ Connection error: {str(e)}"
            print(error_msg)
            send_slack_alert(error_msg)
        
        time.sleep(5)  # Check every 5 seconds

if __name__ == '__main__':
    # Send startup message
    send_slack_alert("🚀 Blue/Green Alert Watcher Started")
    monitor_failover()