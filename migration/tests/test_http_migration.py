#!/usr/bin/env python3
import json
import os
import time
import subprocess
import requests
import argparse
from datetime import datetime, timedelta

def get_pod_ip(pod_id=None):
    """Get the pod IP address using crictl."""
    try:
        if pod_id:
            # Get specific pod by ID
            result = subprocess.run(
                ['sudo', 'crictl', 'inspectp', pod_id],
                capture_output=True,
                text=True,
                check=True
            )
        else:
            # List pods and get the first running http-server pod
            result = subprocess.run(
                ['sudo', 'crictl', 'pods', '--name', 'http-server', '--state', 'ready', '--quiet'],
                capture_output=True,
                text=True,
                check=True
            )
            pod_id = result.stdout.strip()
            if not pod_id:
                raise RuntimeError("No running http-server pod found")
            
            # Get pod details
            result = subprocess.run(
                ['sudo', 'crictl', 'inspectp', pod_id],
                capture_output=True,
                text=True,
                check=True
            )
            
        # Get pod details including IP
        result = subprocess.run(
            ['sudo', 'crictl', 'inspectp', pod_id],
            capture_output=True,
            text=True,
            check=True
        )
        import json
        pod_info = json.loads(result.stdout)
        pod_ip = pod_info['status']['network']['ip']
        if not pod_ip:
            raise RuntimeError("Pod IP not found")
            
        return pod_ip
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to get pod IP: {e}")

def wait_for_http_server(url, timeout=30):
    """Wait for HTTP server to become available."""
    start_time = datetime.now()
    while (datetime.now() - start_time) < timedelta(seconds=timeout):
        try:
            response = requests.get(url)
            if response.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(1)
    return False

def verify_containers_running(pod_id):
    """Verify both HTTP server and log generator containers are running."""
    try:
        result = subprocess.run(
            ['sudo', 'crictl', 'ps', '--pod', pod_id, '--quiet'],
            capture_output=True,
            text=True,
            check=True
        )
        container_ids = result.stdout.strip().split('\n')
        if len(container_ids) != 2:
            print(f"ERROR: Expected 2 containers, found {len(container_ids)}")
            return False
        return True
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to verify containers: {e}")
        return False

def check_logs_continuity(shared_volume_path):
    """Verify log continuity and growth."""
    log_file = os.path.join(shared_volume_path, 'app.log')
    
    if not os.path.exists(log_file):
        print(f"ERROR: Log file not found at {log_file}")
        return False
        
    with open(log_file, 'r') as f:
        logs = f.readlines()
    
    if not logs:
        print("ERROR: Log file is empty")
        return False
        
    # Check for recent logs and verify ISO format
    last_log_time = None
    for line in logs:
        try:
            # Verify ISO format timestamp
            timestamp_str = line.split(":")[0]
            last_log_time = datetime.fromisoformat(timestamp_str)
            
            # Verify log entry format matches specification
            if not line.strip().endswith("Log entry"):
                print("ERROR: Log entry format doesn't match specification")
                return False
        except (ValueError, IndexError):
            print("ERROR: Invalid log format, expected ISO timestamp")
            return False
            
    if not last_log_time:
        print("ERROR: No valid timestamps found in logs")
        return False
        
    # Verify logs are recent (within last minute)
    if datetime.now() - last_log_time > timedelta(minutes=1):
        print(f"ERROR: Logs are stale. Last log: {last_log_time}")
        return False
        
    return True

def verify_shared_volume_annotation(pod_id, expected_path):
    """Verify the shared volume annotation is preserved."""
    try:
        result = subprocess.run(
            ['sudo', 'crictl', 'inspectp', pod_id],
            capture_output=True,
            text=True,
            check=True
        )
        pod_info = json.loads(result.stdout)
        actual_path = pod_info['annotations'].get('shared-volume')
        if actual_path != expected_path:
            print(f"ERROR: Shared volume annotation mismatch. Expected {expected_path}, got {actual_path}")
            return False
        return True
    except (subprocess.CalledProcessError, KeyError, json.JSONDecodeError) as e:
        print(f"ERROR: Failed to verify shared volume annotation: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Test HTTP server pod post-migration')
    parser.add_argument('--pod-id', type=str, help='Specific pod ID to test')
    parser.add_argument('--port', type=int, default=8080, help='HTTP server port')
    parser.add_argument('--shared-volume', type=str, default='/tmp/shared-logs',
                      help='Path to shared volume')
    args = parser.parse_args()
    
    try:
        # Step 1: Verify pod and containers are running
        print("\nVerifying pod status...")
        pod_ip = get_pod_ip(args.pod_id)
        print(f"✓ Found running http-server pod at IP: {pod_ip}")
        
        if not verify_containers_running(args.pod_id):
            print("ERROR: Container verification failed")
            return 1
        print("✓ Both containers running")
        
        # Verify shared volume annotation
        if not verify_shared_volume_annotation(args.pod_id, args.shared_volume):
            print("ERROR: Shared volume annotation verification failed")
            return 1
        print("✓ Shared volume annotation verified")
        
        http_url = f"http://{pod_ip}:{args.port}"
        
        # Step 2: Verify HTTP server is responding
        print("\nChecking HTTP server...")
        if not wait_for_http_server(http_url):
            print("ERROR: HTTP server not responding")
            return 1
        print("✓ HTTP server responding")
        
        # Step 3: Verify logs
        print("\nChecking log continuity...")
        if not check_logs_continuity(args.shared_volume):
            print("ERROR: Log verification failed")
            return 1
        print("✓ Logs being generated and accessible")
        
        # Step 4: Monitor log growth
        print("\nMonitoring log growth...")
        log_file = os.path.join(args.shared_volume, 'app.log')
        initial_size = os.path.getsize(log_file)
        print(f"Initial log size: {initial_size} bytes")
        
        # Wait and check for log growth
        time.sleep(10)
        final_size = os.path.getsize(log_file)
        log_growth = final_size - initial_size
        print(f"Final log size: {final_size} bytes")
        print(f"Log growth: {log_growth} bytes")
        
        if log_growth <= 0:
            print("ERROR: Logs not growing")
            return 1
        print("✓ Logs growing as expected")
        
        print("\nPost-migration verification successful! ✅")
        print("- HTTP server accessible")
        print("- Logs accessible and growing")
        print("- Shared volume maintained")
        return 0
        
    except RuntimeError as e:
        print(f"ERROR: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
