import os

CONFIG = {
    "user_data_dir": os.path.abspath("whatsapp_session"),
    "explicit_wait": 35,          # Increased for reliability
    "retry_attempts": 3,
    "min_phone_digits": 8,

    # --- ANTI-SPAM TUNING ---
    # Delay between repeated messages to the same recipient (seconds)
    "send_jitter_min": 0.2,
    "send_jitter_max": 0.5,

    # Delay between each recipient (seconds)
    "recipient_delay_min": 0.5,
    "recipient_delay_max": 1.0,
    "checkpoint_file": "data/checkpoint.json"
}

# ========================
# SELECTORS
# ========================
# Multiple fallback XPaths for the search box - WhatsApp Web changes its DOM
# frequently, so we try several selectors to find the search input.
# As of 2026, WhatsApp Web uses a native <input> element instead of
# a contenteditable <div> for the search box.
SEARCH_BOX_SELECTORS = [
    # Current (2026) - native <input> element
    '//input[@aria-label="Search or start a new chat"]',
    '//input[@data-tab="3"]',
    '//input[@role="textbox"]',
    '//input[contains(@class, "html-input")]',
    '//div[@data-testid="chat-list-search-container"]//input',
    # Legacy fallbacks - contenteditable <div> (pre-2026)
    '//div[@data-testid="chat-list-search"]//div[@contenteditable="true"]',
    '//div[@aria-label="Search input textbox"]',
    '//div[@contenteditable="true"][@data-tab="3"]',
    '//div[@contenteditable="true"][@role="textbox"]',
]
MSG_BOX_SELECTORS = [
    # Newest (2026) dynamic selectors
    '//div[@aria-placeholder="Type a message"]',
    '//div[@title="Type a message"]',
    '//div[@data-testid="conversation-compose-box-input"]',
    # Extremely generic fallbacks (very robust)
    '//footer//div[@contenteditable="true"]',
    '//div[contains(@class, "lexical-rich-text-input")]//div[@contenteditable="true"]',
    # Legacy fallbacks
    '//div[@contenteditable="true"][@data-tab="10"]'
]
ATTACH_BTN  = '//button[@aria-label="Attach"] | //span[@data-testid="plus-rounded"] | //div[@data-testid="compose-attach-button"]'
SEND_BTN    = '//span[@data-testid="send"]'
CAPTION_BOX = '//div[@data-testid="image-caption"]'
FILE_INPUT  = '//input[@type="file"]'
ERROR_STATE = '//div[@data-testid="error-state"]'

READY_SELECTORS = [
    # Current (2026)
    '//input[@aria-label="Search or start a new chat"]',
    # Legacy
    '//div[@data-testid="chat-list-search"]',
    '//div[@aria-label="Search input textbox"]'
]
