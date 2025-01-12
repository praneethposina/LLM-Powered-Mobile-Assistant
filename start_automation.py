import subprocess
import time
import requests
import sys

def check_appium_server():
    try:
        response = requests.get('http://localhost:4723/status')
        return response.status_code == 200
    except:
        return False

def check_adb_devices():
    result = subprocess.run(['adb', 'devices'], capture_output=True, text=True)
    return len(result.stdout.strip().split('\n')) > 1

def main():
    # 1. Check if Appium is running
    print("Checking Appium server...")
    if not check_appium_server():
        print("Starting Appium server...")
        appium_process = subprocess.Popen(['appium', '--allow-cors'])
        time.sleep(5)  # Wait for Appium to start
        
        if not check_appium_server():
            print("Failed to start Appium server")
            sys.exit(1)
    
    # 2. Check for connected devices
    print("Checking for connected Android devices...")
    if not check_adb_devices():
        print("No Android devices found. Please connect a device and enable USB debugging")
        sys.exit(1)
    
    # 3. Start the automation server
    print("Starting automation server...")
    subprocess.run(['python', 'automation_server.py'])

if __name__ == '__main__':
    main() 