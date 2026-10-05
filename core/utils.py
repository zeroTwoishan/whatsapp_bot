import os
import time
import random
import csv
import json
from datetime import timedelta
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException

from core.config import CONFIG, READY_SELECTORS, BASE_DIR
from core.logger import log

def resolve_path(path):
    """Relative paths are taken from the project folder, not the current working directory."""
    return os.path.join(BASE_DIR, path)  # an absolute `path` is returned unchanged

def clean_number(number):
    return "".join(filter(str.isdigit, str(number)))

def validate_phone(digits):
    return len(digits) >= CONFIG["min_phone_digits"]

def jitter_sleep(min_s=None, max_s=None):
    time.sleep(random.uniform(
        min_s or CONFIG["send_jitter_min"],
        max_s or CONFIG["send_jitter_max"]
    ))

def with_retry(fn, *args, **kwargs):
    for i in range(CONFIG["retry_attempts"]):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            log.warning(f"Retry {i+1}: {type(e).__name__}")
            time.sleep(2 ** i)
    raise Exception("Max retries exceeded")

def wait_for_whatsapp(driver, timeout=60):
    """Wait for any of the READY_SELECTORS to appear."""
    end = time.time() + timeout
    while time.time() < end:
        for selector in READY_SELECTORS:
            try:
                driver.find_element(By.XPATH, selector)
                return True
            except NoSuchElementException:
                pass
            except Exception:
                pass
        time.sleep(1)
    return False

def is_session_active(driver):
    try:
        driver.current_url
        return True
    except Exception:
        return False

def create_template_csv(filepath):
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Target", "Message", "Media", "Repeat", "Time"])
        writer.writerow(["+1234567890", "Hello! This is a test.", "", "1", ""])
        writer.writerow(["John Doe", "", "path/to/image.jpg", "1", ""])  
    print(f"Created template at {os.path.abspath(filepath)}")

def build_csv_interactively(filepath):
    print("\n--- CSV Builder ---")
    print("Let's create your target list. Leave any optional field blank and press Enter to skip.")
    
    same_msg = input("Will all recipients receive the exact same message? (y/n): ").strip().lower() == 'y'
    default_msg = ""
    if same_msg:
        default_msg = input("  Default Message: ").strip()
    
    same_media = input("Will all recipients receive the exact same media? (y/n): ").strip().lower() == 'y'
    default_media_str = ""
    if same_media:
        default_media = input("  Default Media path(s) (separate multiple with ;): ").strip()
        valid_media = []
        if default_media:
            for p in [x.strip() for x in default_media.replace('|', ';').split(';') if x.strip()]:
                if not os.path.exists(resolve_path(p)):
                    print(f"  Warning: File not found: {p}")
                else:
                    valid_media.append(p)
        default_media_str = ";".join(valid_media)

    same_repeat = input("Will all recipients have the exact same repeat count? (y/n): ").strip().lower() == 'y'
    default_repeat = "1"
    if same_repeat:
        repeat_input = input("  Default Repeat count per recipient (default 1): ").strip()
        default_repeat = repeat_input if repeat_input.isdigit() else "1"

    targets = []
    print("\nEnter recipients. Type 'done' when finished.")
    while True:
        target = input("\nRecipient Name or Number: ").strip()
        if target.lower() == 'done':
            break
        if not target:
            continue
            
        target_msg = default_msg
        if not same_msg:
            target_msg = input("  Message for this recipient: ").strip()
            
        target_media_str = default_media_str
        if not same_media:
            t_media = input("  Media path(s) for this recipient [optional]: ").strip()
            v_media = []
            if t_media:
                for p in [x.strip() for x in t_media.replace('|', ';').split(';') if x.strip()]:
                    if not os.path.exists(resolve_path(p)):
                        print(f"  Warning: File not found: {p}")
                    else:
                        v_media.append(p)
            target_media_str = ";".join(v_media)
            
        target_repeat = default_repeat
        if not same_repeat:
            r_input = input("  Repeat count for this recipient (default 1): ").strip()
            target_repeat = r_input if r_input.isdigit() else "1"
            
        time_input = input("  Schedule Time (HH:MM) [optional]: ").strip()
        
        targets.append([target, target_msg, target_media_str, target_repeat, time_input])
        print(f"  -> Added: {target}")

    if not targets:
        print("No targets entered. Aborting.")
        return False

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Target", "Message", "Media", "Repeat", "Time"])
        writer.writerows(targets)
        
    print(f"\nSuccessfully saved {len(targets)} targets to {os.path.abspath(filepath)}\n")
    return True

def schedule_time(time_str, now):
    """Next HH:MM on or after `now` (minute precision). Times already passed today
    mean tomorrow, so 00:30 scheduled at 23:00 waits until after midnight.
    Returns None for blank or invalid times."""
    if not time_str:
        return None
    try:
        hour, minute = map(int, time_str.split(":"))
        when = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    except ValueError:
        return None
    if when < now.replace(second=0, microsecond=0):
        when += timedelta(days=1)
    return when

def target_key(t):
    """Identifies a CSV row independent of its position in the list."""
    return [t["target"], t["message"], t["time"]]

def find_resume_index(targets, index, key):
    """Where to resume: the checkpointed target's current position, even if the CSV
    was edited or re-sorted. None if that target is no longer in the list."""
    if key is None:  # old-format checkpoint or past the end of the list
        return index
    for i, t in enumerate(targets):
        if target_key(t) == key:
            return i
    return None

def load_checkpoint():
    """Returns (target_index, repeat_index, target_key) tuple."""
    if os.path.exists(CONFIG["checkpoint_file"]):
        with open(CONFIG["checkpoint_file"], 'r') as f:
            data = json.load(f)
            return data.get("last_index", 0), data.get("last_repeat", 0), data.get("target")
    return 0, 0, None

def save_checkpoint(index, repeat=0, key=None):
    """Save target index, repeat progress, and which target that index refers to."""
    with open(CONFIG["checkpoint_file"], 'w') as f:
        json.dump({"last_index": index, "last_repeat": repeat, "target": key}, f)

def clear_checkpoint():
    if os.path.exists(CONFIG["checkpoint_file"]):
        os.remove(CONFIG["checkpoint_file"])
