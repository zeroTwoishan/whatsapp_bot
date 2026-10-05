import sys
import os
import time
import subprocess
import base64
import traceback

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError as e:
    print(f"\n[ERROR] Missing required packages: {e.name}")
    print("Please install them by running:")
    print("    pip install -r requirements.txt\n")
    sys.exit(1)

from core.config import CONFIG
from core.client import WhatsAppClient
from core.utils import wait_for_whatsapp

def print_header(text):
    print(f"\n{'='*50}\n--- {text} ---\n{'='*50}")

def cleanup_ghosts():
    try:
        subprocess.run(['taskkill', '/F', '/IM', 'chromedriver.exe'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ps_cmd = (
            "Get-Process chrome -ErrorAction SilentlyContinue | "
            "ForEach-Object { "
            "  $p = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $_.Id) -ErrorAction SilentlyContinue; "
            "  if ($p -and $p.CommandLine -like '*whatsapp_session*') { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue } "
            "}"
        )
        encoded = base64.b64encode(ps_cmd.encode('utf-16-le')).decode('ascii')
        subprocess.run(['powershell', '-NoProfile', '-EncodedCommand', encoded], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    except:
        pass

def run_diagnostics():
    print_header("WhatsApp Agent Diagnostic Suite")
    print("This tool will test all UI interactions to ensure no selectors are broken.")
    
    test_name = input("Enter a valid test contact NAME: ").strip()
    test_number = input("Enter a valid test contact NUMBER: ").strip()
    
    if not test_name or not test_number:
        print("Test name and number are required. Aborting.")
        return

    # Create a dummy image for attachment tests
    dummy_img = os.path.join(os.path.dirname(__file__), 'dummy_test_img.jpg')
    if not os.path.exists(dummy_img):
        with open(dummy_img, 'wb') as f:
            f.write(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xd2\x7f\xff\xd9')

    print("\nStarting browser...")
    cleanup_ghosts()
    
    options = Options()
    options.add_argument(f"--user-data-dir={CONFIG['user_data_dir']}")
    if CONFIG.get("headless", False):
        options.add_argument("--headless")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    client = WhatsAppClient(driver)

    try:
        driver.get("https://web.whatsapp.com")
        print("Waiting for WhatsApp Web to load...")
        if not wait_for_whatsapp(driver, timeout=60):
            print("[FAIL] Could not load WhatsApp Web. Is your phone connected?")
            return
        
        print("\n[PASS] WhatsApp Web loaded successfully!")
        results = {}

        # Phase 1: Search by Name
        print_header("Phase 1: Search Box & Open by Name")
        if client.open_chat_by_name(test_name):
            print("[PASS] Search box works and chat opened successfully.")
            results["Phase 1: Search Box"] = "PASS"
        else:
            print("[FAIL] Could not open chat by name. Search box selectors may be broken.")
            results["Phase 1: Search Box"] = "FAIL"
            
        time.sleep(2)
            
        # Phase 2: URL Routing
        print_header("Phase 2: URL Routing & Open by Number")
        try:
            client.open_chat_by_number(test_number)
            print("[PASS] URL routing works and chat opened successfully.")
            results["Phase 2: URL Routing"] = "PASS"
        except Exception as e:
            print(f"[FAIL] Could not open chat by number: {type(e).__name__} - {e}")
            results["Phase 2: URL Routing"] = "FAIL"
            
        time.sleep(2)
            
        # Phase 3: Invalid Number Detection
        print_header("Phase 3: Invalid Number Popup Detection")
        try:
            client.open_chat_by_number("+1123456789098765")
            print("[FAIL] Opened an invalid number without raising an exception! Detection logic broken.")
            results["Phase 3: Invalid Number Popup"] = "FAIL"
        except Exception as e:
            if "not registered" in str(e).lower() or "invalid" in str(e).lower():
                print("[PASS] Correctly detected invalid number popup and aborted gracefully.")
                results["Phase 3: Invalid Number Popup"] = "PASS"
            else:
                print(f"[FAIL] Unexpected exception raised: {e}")
                results["Phase 3: Invalid Number Popup"] = "FAIL"
                
        time.sleep(2)
        try:
            client.open_chat_by_number(test_number) # Re-open valid chat
        except:
            pass
        time.sleep(2)
                
        # Phase 4: Text Message
        print_header("Phase 4: Message Box & Send Button")
        try:
            client.send_to_chat("Diagnostic Test: Text Message", "text", None, 1)
            print("[PASS] Message box and Send button work.")
            results["Phase 4: Text Message Sending"] = "PASS"
        except Exception as e:
            print(f"[FAIL] Could not send text message: {type(e).__name__} - {e}")
            results["Phase 4: Text Message Sending"] = "FAIL"
            
        time.sleep(2)
            
        # Phase 5: Media Attachment
        print_header("Phase 5: Media Attachment (+) Button")
        try:
            client.send_to_chat("", "media", [dummy_img], 1)
            print("[PASS] Media attachment works (Clicked '+', selected Photos, attached file).")
            results["Phase 5: Media Attachment"] = "PASS"
        except Exception as e:
            print(f"[FAIL] Could not attach media: {type(e).__name__} - {e}")
            results["Phase 5: Media Attachment"] = "FAIL"
            
        time.sleep(2)
            
        # Phase 6: Text + Media Verification
        print_header("Phase 6: Mixed Message (Text + Media)")
        try:
            client.send_to_chat("Diagnostic Test: Mixed", "text+media", [dummy_img], 1)
            print("[PASS] Mixed media send successful.")
            results["Phase 6: Mixed Media Sending"] = "PASS"
        except Exception as e:
            print(f"[FAIL] Could not send mixed message: {type(e).__name__} - {e}")
            results["Phase 6: Mixed Media Sending"] = "FAIL"
            
        print_header("Diagnostic Summary")
        print(f"{'Phase Name':<35} | {'Result':<10}")
        print("-" * 50)
        for phase, result in results.items():
            print(f"{phase:<35} | {result:<10}")
            
    finally:
        try:
            driver.quit()
        except:
            pass
        cleanup_ghosts()

if __name__ == "__main__":
    run_diagnostics()
