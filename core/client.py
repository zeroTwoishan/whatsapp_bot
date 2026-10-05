import sys
import os
import time
import random

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, ElementNotInteractableException, NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains

from core.config import CONFIG, SEARCH_BOX_SELECTORS, MSG_BOX_SELECTORS, ATTACH_BTN, SEND_BTN, CAPTION_BOX, FILE_INPUT, ERROR_STATE
from core.logger import log
from core.utils import clean_number, validate_phone, jitter_sleep

try:
    import pyperclip
    PYPERCLIP_AVAILABLE = True
except ImportError:
    PYPERCLIP_AVAILABLE = False
    log.warning("pyperclip not installed. Falling back to send_keys.")

class WhatsAppClient:
    MODIFIER_KEY = Keys.COMMAND if sys.platform == 'darwin' else Keys.CONTROL

    def __init__(self, driver):
        self.driver = driver
        self.wait = WebDriverWait(driver, CONFIG["explicit_wait"])
        self.shutdown_flag = False

    def wait_for(self, xpath, clickable=False, visible=True, timeout=None):
        w = self.wait if timeout is None else WebDriverWait(self.driver, timeout)
        if clickable:
            return w.until(EC.element_to_be_clickable((By.XPATH, xpath)))
        if visible:
            return w.until(EC.visibility_of_element_located((By.XPATH, xpath)))
        return w.until(EC.presence_of_element_located((By.XPATH, xpath)))

    def find_search_box(self):
        """Try multiple selectors to find the search box element."""
        for selector in SEARCH_BOX_SELECTORS:
            try:
                element = self.driver.find_element(By.XPATH, selector)
                if element.is_displayed() and element.is_enabled():
                    return element
            except (NoSuchElementException, ElementNotInteractableException):
                continue
        return None

    def wait_for_search_box_interactable(self, timeout=15):
        """Robustly wait for any of the search box selectors to be interactable."""
        end_time = time.time() + timeout
        while time.time() < end_time:
            element = self.find_search_box()
            if element is not None:
                try:
                    if element.size['width'] > 0 and element.size['height'] > 0:
                        ActionChains(self.driver).move_to_element(element).perform()
                        return element
                except Exception:
                    pass
            time.sleep(0.5)
        raise TimeoutException(f"Search box not interactable after {timeout} seconds")

    def clear_search(self):
        """Clear the search box reliably using multiple strategies."""
        try:
            search = self.wait_for_search_box_interactable(timeout=15)
            # For native <input> elements, .clear() works directly
            try:
                search.click()
                if search.tag_name == 'input':
                    search.clear()
                else:
                    search.send_keys(Keys.CONTROL + "a")
                    search.send_keys(Keys.DELETE)
                    search.send_keys(Keys.BACKSPACE)  # extra cleanup
            except Exception:
                pass
            # Fallback: Ctrl+A Delete (works for both input and div)
            try:
                search.send_keys(Keys.CONTROL + "a")
                search.send_keys(Keys.DELETE)
            except Exception:
                pass
            # Fallback: clear via JS
            try:
                if search.tag_name == 'input':
                    self.driver.execute_script("arguments[0].value = '';", search)
                else:
                    self.driver.execute_script("arguments[0].innerText = '';", search)
                    self.driver.execute_script("arguments[0].innerHTML = '';", search)
            except Exception:
                pass
            # Press Escape to close any open search results panel
            try:
                search.send_keys(Keys.ESCAPE)
                time.sleep(0.3)
            except Exception:
                pass
        except TimeoutException as e:
            log.warning(f"Clear search failed (Timeout): {e}")
        except Exception as e:
            log.warning(f"Clear search failed: {e}")

    def open_chat_by_number(self, number):
        digits = clean_number(number)
        if not validate_phone(digits):
            raise ValueError(f"Invalid number: {number}")
        self.driver.get(f"https://web.whatsapp.com/send?phone={digits}")
        try:
            def check_ready(d):
                # 1. Check if chat is fully loaded
                if any(d.find_elements(By.XPATH, sel) for sel in MSG_BOX_SELECTORS):
                    return "ready"
                # 2. Check if the error message is visible anywhere in the body
                try:
                    body_text = d.find_element(By.TAG_NAME, "body").text.lower()
                    if "isn't on whatsapp" in body_text or "not registered" in body_text or "invalid" in body_text:
                        return "invalid"
                except:
                    pass
                return False

            result = WebDriverWait(self.driver, 15).until(check_ready)
            
            if result == "invalid":
                # Try to dismiss the popup if it has a dismiss button
                try:
                    btns = self.driver.find_elements(By.XPATH, '//button | //div[@role="button"]')
                    for b in btns:
                        if b.text.strip().lower() == "ok":
                            b.click()
                            break
                except:
                    pass
                raise Exception(f"Phone number {digits} is not registered on WhatsApp.")
                
            time.sleep(random.uniform(1, 1.5))
            return True
        except TimeoutException:
            log.error(f"Failed to open chat for {digits} (Timeout)")
            return False

    def open_chat_by_name(self, name):
        """
        Opens a chat by contact or group name.
        Returns True if successful, False otherwise.
        """
        try:
            search = self.wait_for_search_box_interactable(timeout=15)
        except TimeoutException:
            log.error("Search box not found or not interactable.")
            return False

        for attempt in range(CONFIG["retry_attempts"]):
            try:
                self.clear_search()
                time.sleep(0.5)
                search.click()
                search.send_keys(name)
                break
            except ElementNotInteractableException:
                log.warning(f"Search box not interactable on attempt {attempt+1}, retrying...")
                time.sleep(2)
                search = self.wait_for_search_box_interactable(timeout=10)
            except Exception as e:
                log.warning(f"Unexpected error on attempt {attempt+1}: {e}")
                time.sleep(2)
                search = self.wait_for_search_box_interactable(timeout=10)
        else:
            log.error("Failed to interact with search box after multiple attempts.")
            return False

        time.sleep(0.5)  # Let search results populate

        # Strategy 1: Press Enter to select first search result (most reliable)
        log.info(f"Selecting contact '{name}' via Enter key...")
        try:
            search.send_keys(Keys.ENTER)
        except Exception:
            try:
                self.driver.execute_script(
                    "arguments[0].dispatchEvent(new KeyboardEvent('keydown', {'key': 'Enter'}));",
                    search
                )
            except Exception:
                pass
        time.sleep(0.8)

        # Check if chat opened
        if self._is_chat_open():
            log.info(f"Chat opened for: {name}")
            return True

        # Strategy 2: Try clicking container-level elements (not inner spans)
        log.warning(f"Enter key didn't open chat for '{name}', trying click selectors...")
        contact_selectors = [
            f'//div[@data-testid="cell-frame-container"][contains(.,"{name}")]',
            f'//div[@data-testid="chat-list"]//div[@role="listitem"][contains(.,"{name}")]',
            f'//div[@data-testid="chat-list"]//div[@role="row"][contains(.,"{name}")]',
            f'//div[@data-testid="chat-list"]//div[@role="button"][contains(.,"{name}")]',
            f'//span[@title="{name}"]/ancestor::div[@data-testid="cell-frame-container"]',
            f'//span[contains(text(),"{name}")]/ancestor::div[@role="listitem"]',
            f'//span[contains(text(),"{name}")]/ancestor::div[@role="row"]',
        ]

        for selector in contact_selectors:
            try:
                contact = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, selector))
                )
                contact.click()
                log.info(f"Clicked container for: {name}")
                time.sleep(2)
                if self._is_chat_open():
                    return True
            except TimeoutException:
                continue
            except Exception:
                continue

        # Strategy 3: Arrow down + Enter
        log.warning(f"Click selectors failed for '{name}', trying arrow+enter...")
        try:
            search.send_keys(Keys.ARROW_DOWN)
            time.sleep(0.5)
            search.send_keys(Keys.ENTER)
            time.sleep(2)
            if self._is_chat_open():
                log.info(f"Chat opened via arrow+enter for: {name}")
                return True
        except Exception:
            pass

        log.error(f"Failed to open chat for name: {name}")
        return False

    def _is_chat_open(self):
        """Check if a chat conversation is currently open by looking for compose elements."""
        compose_selectors = MSG_BOX_SELECTORS + [
            '//div[@data-testid="conversation-panel-wrapper"]',
            '//footer//*[@role="textbox"]',
            '//div[@id="main"]',
        ]
        for sel in compose_selectors:
            try:
                el = self.driver.find_element(By.XPATH, sel)
                if el.is_displayed():
                    return True
            except (NoSuchElementException, Exception):
                continue
        return False

    def humanize(self):
        """Smart Anti-Ban: Moves the mouse randomly to simulate a human user."""
        try:
            # Find a safe element to move the mouse towards (like the chat header)
            header = self.driver.find_elements(By.XPATH, '//header')
            if header:
                action = ActionChains(self.driver)
                # Add random jitter offset
                x_offset = random.randint(-50, 50)
                y_offset = random.randint(-10, 10)
                action.move_to_element_with_offset(header[0], x_offset, y_offset).perform()
                time.sleep(random.uniform(0.1, 0.4))
        except:
            pass

    def send_text(self, message):
        """Sends a text message using the clipboard to support emojis."""
        box = None
        for sel in MSG_BOX_SELECTORS:
            try:
                # Use a shorter timeout per fallback to avoid freezing for too long
                box = self.wait_for(sel, clickable=True, timeout=5)
                if box:
                    break
            except Exception:
                pass
                
        if not box:
            raise TimeoutException("Could not find message box to type in using any MSG_BOX_SELECTORS.")
        try:
            box.click()
        except:
            # If a fading image preview overlay intercepts the click, use JS
            self.driver.execute_script("arguments[0].click();", box)
            
        time.sleep(random.uniform(0.1, 0.3))

        if PYPERCLIP_AVAILABLE:
            original_clipboard = pyperclip.paste()
            try:
                pyperclip.copy(message)
                box.send_keys(self.MODIFIER_KEY, 'v')
                time.sleep(0.1)
            finally:
                pyperclip.copy(original_clipboard)
        else:
            box.send_keys(message)
            
        box.send_keys(Keys.ENTER)

    def send_media(self, file_path):
        # We wrap the attach button click in a resilient try-except since WhatsApp overlays can block it
        attach_btn = self.wait_for(ATTACH_BTN, clickable=True)
        try:
            attach_btn.click()
        except:
            self.driver.execute_script("arguments[0].click();", attach_btn)
            
        time.sleep(0.5)  # Wait for menu to fully open
        
        # Determine if this is an image/video or a document
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ['.jpg', '.jpeg', '.png', '.mp4', '.gif', '.3gp']:
            # Target the specific Photos & Videos input
            xpath = '//input[@type="file" and contains(@accept, "image/")]'
        else:
            # Target the Document input
            xpath = '//input[@type="file" and not(contains(@accept, "image/"))]'
            
        file_inputs = self.driver.find_elements(By.XPATH, xpath)
        if not file_inputs:
            # Fallback to any file input
            file_inputs = self.driver.find_elements(By.XPATH, FILE_INPUT)
            if not file_inputs:
                raise Exception("No file inputs found")
            
        # CRITICAL: If WhatsApp reuses the exact same file input, uploading the exact same image twice 
        # will NOT trigger a browser 'change' event. We must clear the input value first!
        target_input = file_inputs[-1]
        self.driver.execute_script("arguments[0].value = '';", target_input)
        target_input.send_keys(os.path.abspath(file_path))
        
        send_btn_xpath = '//button[@aria-label="Send"] | //div[@aria-label="Send"] | //span[@data-icon="wds-ic-send-filled"]'
        
        # Wait dynamically for the preview to load
        try:
            WebDriverWait(self.driver, 5).until(
                lambda d: any(b.is_displayed() for b in d.find_elements(By.XPATH, send_btn_xpath))
            )
        except TimeoutException:
            log.info("Preview didn't open. Retrying upload pulse...")
            self.driver.execute_script("arguments[0].value = '';", target_input)
            target_input.send_keys(os.path.abspath(file_path))
            try:
                WebDriverWait(self.driver, 5).until(
                    lambda d: any(b.is_displayed() for b in d.find_elements(By.XPATH, send_btn_xpath))
                )
            except TimeoutException:
                pass
                
        send_btns = self.driver.find_elements(By.XPATH, send_btn_xpath)
        try:
            # Click the Send button for the preview
            clicked = False
            for btn in reversed(send_btns):
                if btn.is_displayed():
                    try:
                        btn.click()
                    except:
                        self.driver.execute_script("arguments[0].click();", btn)
                    clicked = True
                    break
            
            if not clicked:
                log.warning("Could not find a visible send button for media")
            else:
                # Wait for the send animation to close the preview modal
                try:
                    WebDriverWait(self.driver, 3).until_not(
                        lambda d: any(b.is_displayed() for b in d.find_elements(By.XPATH, send_btn_xpath))
                    )
                except TimeoutException:
                    pass

        except Exception as e:
            log.error(f"Failed to send media: {type(e).__name__}")
            try:
                ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            except:
                pass

    def send_to_chat(self, message, mode, media, repeat, start_repeat=0, on_progress=None):
        """Send messages to the current chat. Calls on_progress(repeat_index) after each send."""
        for i in range(start_repeat, repeat):
            if self.shutdown_flag:
                return
            if mode == "text":
                self.send_text(message)
            elif mode == "media":
                if media:
                    for m in media:
                        self.send_media(m)
            elif mode == "text+media":
                if media:
                    for m in media:
                        self.send_media(m)
                time.sleep(1) # Small gap between image and text
                self.send_text(message)
                
            log.info(f"Sent ({i+1}/{repeat})")
            
            # Save progress after each successful repeat
            if on_progress:
                on_progress(i + 1)
            
            if i < repeat - 1:
                jitter_sleep()

