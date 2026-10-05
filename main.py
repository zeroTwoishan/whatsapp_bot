"""
WhatsApp Web Automation Tool - Main Entry Point
"""

import os
import sys
import time
import csv
import random
import subprocess
import base64
from datetime import datetime

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

# Import from core package
from core.config import CONFIG
from core.logger import log
from core.utils import (
    load_checkpoint, save_checkpoint, clear_checkpoint,
    create_template_csv, build_csv_interactively, wait_for_whatsapp, is_session_active,
    jitter_sleep, with_retry, schedule_time, target_key, find_resume_index, resolve_path
)
from core.client import WhatsAppClient

def main():
    driver = None
    pids_to_kill = []
    try:
        print("")
        print("=" * 60)
        print("   WhatsApp Web Automation Tool")
        print("=" * 60)
        print("")
        csv_file = CONFIG["targets_file"]

        # 1. Ask about Session first
        session_dir = CONFIG['user_data_dir']
        if os.path.exists(session_dir):
            print("\nFound existing WhatsApp session.")
            print("  [1] Continue with current session (no QR scan needed)")
            print("  [2] Delete session and start fresh (requires QR scan)")
            session_choice = input("Choice (1/2): ").strip()
            if session_choice == "2":
                import shutil
                try:
                    shutil.rmtree(session_dir)
                    print("-> Previous session deleted. You will need to scan the QR code.")
                except Exception as e:
                    print(f"Warning: Could not completely delete session dir: {e}")
                    
                # Clean up previous user's data
                clear_checkpoint()
                if os.path.exists(csv_file):
                    try:
                        os.remove(csv_file)
                        print("-> Cleared previous user's target list and checkpoint.")
                    except:
                        pass
        print("")
        resume = False
        start_index, start_repeat = 0, 0

        # 1. Check for checkpoint
        current_index, current_repeat, resume_key = load_checkpoint()
        if current_index > 0 or current_repeat > 0:
            if input(f"Found checkpoint at target #{current_index + 1}, repeat #{current_repeat + 1}. Resume? (y/n): ").strip().lower() == "y":
                resume = True
                start_index, start_repeat = current_index, current_repeat
                print(f"Resuming from target #{start_index + 1}, repeat #{start_repeat + 1}")

        # 2. If not resuming, check for existing CSV and prompt
        if not resume:
            if os.path.exists(csv_file) and os.path.getsize(csv_file) > 50:
                print(f"\nFound existing {csv_file}.")
                print("  [1] Use existing targets")
                print("  [2] Create new targets (CSV Builder)")
                choice = input("Choice (1/2): ").strip()
                if choice == "2":
                    if not build_csv_interactively(csv_file):
                        return
            else:
                # No file exists, run builder automatically
                if not build_csv_interactively(csv_file):
                    return
        
        # 3. Read targets from CSV
        targets = []
        if not os.path.exists(csv_file):
            print("Error: targets.csv not found.")
            return

        print(f"Reading targets from {csv_file}...\n")
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames or "Target" not in reader.fieldnames or "Message" not in reader.fieldnames:
                print("CSV must contain at least 'Target' and 'Message' columns.")
                return

            for row in reader:
                if row["Target"].strip():
                    t_msg = row["Message"].strip()
                    
                    t_media_raw = row.get("Media", "").strip() if "Media" in row else None
                    t_media = []
                    if t_media_raw:
                        for p in [x.strip() for x in t_media_raw.replace('|', ';').split(';') if x.strip()]:
                            if not os.path.exists(resolve_path(p)):
                                print(f"Media file '{p}' for {row['Target']} not found. Skipping this file.")
                            else:
                                t_media.append(resolve_path(p))
                                
                    t_media_val = t_media if t_media else None

                    mode = "text"
                    if t_media_val and t_msg:
                        mode = "text+media"
                    elif t_media_val:
                        mode = "media"

                    t_repeat = 1
                    if "Repeat" in row and row["Repeat"].strip().isdigit():
                        t_repeat = int(row["Repeat"].strip())
                        
                    t_time = row.get("Time", "").strip() if "Time" in row else None

                    t_vars = {k: v for k, v in row.items()}
                    
                    t_digits = "".join(filter(str.isdigit, row["Target"]))
                    auto_type = "1" if len(t_digits) >= CONFIG["min_phone_digits"] and row["Target"].replace("+", "").replace("-", "").replace(" ", "").isdigit() else "2"

                    targets.append({
                        "target": row["Target"].strip(),
                        "message": t_msg,
                        "media": t_media_val,
                        "mode": mode,
                        "repeat": t_repeat,
                        "time": t_time,
                        "vars": t_vars,
                        "type": auto_type
                    })

        if not targets:
            print("No recipients found in CSV.")
            return

        # Resolve each Time to its next occurrence and sort chronologically (unscheduled first)
        now = datetime.now()
        for t in targets:
            t["when"] = schedule_time(t["time"], now)
            if t["time"] and not t["when"]:
                print(f"Invalid time '{t['time']}' for {t['target']}. Sending immediately.")
        targets.sort(key=lambda t: t["when"] or datetime.min)

        # The checkpoint stores which target it was on, so find it again even if the CSV changed
        if resume:
            found = find_resume_index(targets, start_index, resume_key)
            if found is None:
                print("\nThe checkpointed recipient is no longer in targets.csv.")
                if input("Start from the first recipient instead? (y/n): ").strip().lower() != "y":
                    return
                start_index, start_repeat = 0, 0
            elif found != start_index:
                print(f"targets.csv changed. Resuming at {targets[found]['target']} (now #{found + 1}).")
                start_index = found

        print("\nExecution Order:")
        for idx, t in enumerate(targets):
            time_display = t["when"].strftime("%a %H:%M") if t["when"] else "Immediate"
            print(f"  {idx+1}. {t['target']} ({time_display})")

        def checkpoint(i, repeat=0):
            save_checkpoint(i, repeat, target_key(targets[i]) if i < len(targets) else None)

        print("\n-> A Chrome window will open.")
        print("   First time or deleted session? Scan the QR code with WhatsApp mobile.")
        print("   (Settings > Linked Devices > Link a Device)")
        print("   Session is saved - no scan needed next time.")
        
        input("\nPress Enter to launch browser...")
    
        options = Options()
        options.add_argument(f"--user-data-dir={CONFIG['user_data_dir']}")
        if CONFIG.get("headless", False):
            options.add_argument("--headless")

        # Pre-launch cleanup: kill any ghost Chrome/ChromeDriver from a previous crash
        try:
            subprocess.run(['taskkill', '/F', '/IM', 'chromedriver.exe'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            pass
        try:
            ps_cmd = (
                "Get-Process chrome -ErrorAction SilentlyContinue | "
                "ForEach-Object { "
                "  $p = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $_.Id) -ErrorAction SilentlyContinue; "
                "  if ($p -and $p.CommandLine -like '*whatsapp_session*') { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue } "
                "}"
            )
            encoded = base64.b64encode(ps_cmd.encode('utf-16-le')).decode('ascii')
            subprocess.run(['powershell', '-NoProfile', '-EncodedCommand', encoded],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        except:
            pass

        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
        except Exception as e:
            print(f"Error initializing WebDriver: {e}")
            print("Ensure you have installed: pip install selenium webdriver-manager")
            return
    
        # Immediately capture ALL process PIDs so we can force-kill them later
        pids_to_kill = []
        try:
            cd_pid = driver.service.process.pid
            pids_to_kill.append(str(cd_pid))
            # Find Chrome browser PIDs (children of ChromeDriver) using PowerShell
            result = subprocess.run(
                ['powershell', '-NoProfile', '-Command',
                 f'Get-CimInstance Win32_Process -Filter "ParentProcessId={cd_pid}" | Select-Object -ExpandProperty ProcessId'],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.strip().split('\n'):
                line = line.strip()
                if line.isdigit():
                    pids_to_kill.append(line)
        except:
            pass

        client = WhatsAppClient(driver)
    
        driver.get("https://web.whatsapp.com")
        print("")
        print("Loading WhatsApp Web...")
    
        if wait_for_whatsapp(driver, timeout=60):
            print("WhatsApp Web loaded!")
            print("")
        else:
            print("Auto-detection timed out.")
            if input("WhatsApp looks loaded? Continue anyway? (y/n): ").strip().lower() != "y":
                driver.quit()
                return
    
        # --- Confirm ---
        print("")
        print("=" * 60)
        print(f"  Recipients : {len(targets)}")
        print("=" * 60)
    
        # The bot will automatically proceed without prompting again.
    
        def send_all():
            if not is_session_active(driver):
                log.error("Session lost. Please restart.")
                driver.quit()
                return
    
            status = {"success": 0, "fail": 0, "total": len(targets)}
            current_repeat = start_repeat  # Track repeat offset for first target on resume
    
            try:
                for idx, t_obj in enumerate(targets[start_index:], start=start_index):
                    if client.shutdown_flag:
                        break
                        
                    t_name = t_obj["target"]
                    t_msg = t_obj["message"]
                    t_media = t_obj["media"]
                    t_mode = t_obj.get("mode", "text")
                    t_repeat = t_obj.get("repeat", 1)
    
                    print(f"--- [{idx+1}/{len(targets)}] {t_name} ---")
                    if not is_session_active(driver):
                        log.error("Browser session lost. Stopping.")
                        break
    
                    try:
                        # 1. Scheduled Sending
                        when = t_obj.get("when")
                        if when and datetime.now() < when:
                            while datetime.now() < when:
                                now = datetime.now().strftime("%H:%M")
                                sys.stdout.write(f"\r  [SCHEDULED] Waiting for {when:%a %H:%M} (Current: {now}) ... ")
                                sys.stdout.flush()
                                time.sleep(10)
                                if client.shutdown_flag:
                                    return
                            sys.stdout.write("\n")
    
                        # 2. Dynamic Message Personalization
                        try:
                            actual_msg = t_msg.format(**t_obj.get("vars", {}))
                        except Exception as e:
                            log.warning(f"Message personalization failed for {t_name}, using raw message. Error: {e}")
                            actual_msg = t_msg
    
                        # 3. Auto-Detect Target Type Routing
                        if t_obj.get("type", "1") == "1":
                            with_retry(lambda: client.open_chat_by_number(t_name))
                        else:
                            if not client.open_chat_by_name(t_name):
                                raise Exception(f"Could not open chat for {t_name}")

                        # Extra settling time for chat UI to fully render
                        time.sleep(random.uniform(0.5, 1.0))
                    
                        # 4. Smart Anti-Ban Humanization
                        client.humanize()

                        # Progress callback: saves checkpoint after each repeat
                        def on_repeat_done(repeat_num, _idx=idx):
                            nonlocal current_repeat
                            current_repeat = repeat_num
                            checkpoint(_idx, repeat_num)

                        client.send_to_chat(actual_msg, t_mode, t_media, t_repeat,
                                            start_repeat=current_repeat,
                                            on_progress=on_repeat_done)
                        status["success"] += 1
                        checkpoint(idx + 1, 0)  # Target fully done, reset repeat
                        log.info(f"Done: {t_name}")
                        current_repeat = 0  # Reset for subsequent targets
                    except Exception as e:
                        log.error(f"Failed {t_name}: {type(e).__name__} - {e}")
                        if "Max retries exceeded" in str(e) or "TimeoutException" in type(e).__name__:
                            print("\n⚠️ WhatsApp Web UI may have updated! Please run 'python debug/run_diagnostics.py' to pinpoint the broken selector.\n")
                        status["fail"] += 1
    
                    if idx < len(targets) - 1:
                        jitter_sleep(CONFIG["recipient_delay_min"], CONFIG["recipient_delay_max"])
    
            except KeyboardInterrupt:
                print("\n[Ctrl+C] Graceful shutdown requested... Aborting current operation.")
                client.shutdown_flag = True
    
            print("")
            print("=" * 60)
            print(f"STATUS REPORT: {status['success']} succeeded, {status['fail']} failed out of {status['total']}")
            
            if status["success"] == status["total"] and not client.shutdown_flag:
                clear_checkpoint()
                print("All messages sent! Checkpoint cleared.")
            else:
                # Progress is checkpointed after every send; re-saving idx here would
                # rewind past a completed last target and resend it on resume.
                print("Progress saved. Run again and choose resume to continue.")
                
            # Try to close browser (may fail if connection is broken from Ctrl+C)
            try:
                driver.quit()
            except:
                pass
    
        send_all()
    
    except KeyboardInterrupt:
        print("\n[Ctrl+C] Shutting down...")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
    finally:
        print("Closing browser...")
        # Strategy 1: Normal Selenium quit
        try:
            driver.quit()
        except:
            pass
        # Strategy 2: Force-kill captured PIDs
        for pid in pids_to_kill:
            try:
                subprocess.run(
                    ['taskkill', '/F', '/T', '/PID', pid],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            except:
                pass
        # Strategy 3: Nuclear fallback — find and kill ALL chrome.exe using our profile
        # Uses -EncodedCommand to avoid all shell escaping problems
        try:
            ps_cmd = (
                "Get-Process chrome -ErrorAction SilentlyContinue | "
                "ForEach-Object { "
                "  $p = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $_.Id) -ErrorAction SilentlyContinue; "
                "  if ($p -and $p.CommandLine -like '*whatsapp_session*') { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue } "
                "}"
            )
            encoded = base64.b64encode(ps_cmd.encode('utf-16-le')).decode('ascii')
            subprocess.run(
                ['powershell', '-NoProfile', '-EncodedCommand', encoded],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=10
            )
        except:
            pass

if __name__ == "__main__":
    main()
