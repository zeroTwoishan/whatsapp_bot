# WhatsApp Bot

A small Python tool that sends WhatsApp messages for you through WhatsApp Web. You give it a list of recipients and it opens each chat in Chrome and sends text, images, or files. It can also wait until a set time before sending.

Built with [Selenium](https://www.selenium.dev/). Everything runs on your own computer.

## Features

- **Send to numbers or contact names.** Phone numbers open the chat directly; names (contacts or groups) are found with the WhatsApp search box.
- **Text, media, or both.** Attach images, videos, or documents, one or several per recipient.
- **Personalised messages.** Use `{ColumnName}` in a message to fill in values from that recipient's CSV row.
- **Repeat sends.** Send the same message to a recipient several times.
- **Scheduling.** Give a recipient a `HH:MM` time and the bot waits until then. Times already past today mean tomorrow, so `00:30` works for a midnight message.
- **Resume after stopping.** Progress is saved after every message. If you stop with `Ctrl+C` or something fails, the next run offers to pick up where it left off.
- **Interactive CSV builder.** No CSV yet? The bot asks you questions and creates one.
- **Saved login.** Scan the QR code once; the session is kept for next time.
- **Diagnostics script.** Checks every part of the WhatsApp Web interface the bot depends on, so you can spot what broke after a WhatsApp update.

## Requirements

- Python 3.10 or newer
- Google Chrome
- A WhatsApp account on your phone (to scan the QR code)
- Windows is recommended. The bot runs elsewhere, but its cleanup of leftover Chrome processes uses Windows commands.

ChromeDriver is downloaded automatically by `webdriver-manager`.

## Installation

```bash
git clone https://github.com/zeroTwoishan/whatsapp_bot.git
cd whatsapp_bot
pip install -r requirements.txt
```

## Usage

```bash
python main.py
```

1. If a saved session exists, choose to keep it or start fresh.
2. Choose to use your existing `data/targets.csv` or create a new one with the builder.
3. Check the execution order the bot prints, then press Enter.
4. Chrome opens WhatsApp Web. The first time, scan the QR code from your phone: **Settings → Linked Devices → Link a Device**.
5. The bot sends everything and prints a summary at the end.

Press `Ctrl+C` at any time to stop. Run `python main.py` again and answer `y` to resume.

## The targets CSV

Recipients live in `data/targets.csv`. Create it with the builder or write it yourself:

```csv
Target,Message,Media,Repeat,Time,Name
+919876543210,Hi {Name}! See you tomorrow.,,1,,Aarav
Family Group,Happy new year!,images/card.jpg,1,00:00,
Riya,,docs/notes.pdf;images/diagram.png,1,,
```

| Column | Required | Description |
|---|---|---|
| `Target` | Yes | A phone number with country code (`+919876543210`), or a contact or group name exactly as it appears in WhatsApp. |
| `Message` | Yes (can be empty) | The text to send. `{ColumnName}` is replaced with that row's value from the column. To include a literal brace, write `{{` or `}}`. |
| `Media` | No | Path(s) to files to send. Separate several with `;`. Relative paths are taken from the project folder. |
| `Repeat` | No | How many times to send. Defaults to `1`. |
| `Time` | No | When to send, as 24-hour `HH:MM`. Leave empty to send immediately. |

You can add any other columns (like `Name` above) and use them in messages.

What gets sent depends on what's filled in: just `Message` sends text, just `Media` sends the files, and both sends the files first and then the text.

## Configuration

Settings are in [`core/config.py`](core/config.py):

| Setting | What it does |
|---|---|
| `explicit_wait` | Seconds to wait for page elements before giving up. |
| `retry_attempts` | How many times to retry opening a chat. |
| `min_phone_digits` | A target with at least this many digits is treated as a phone number. |
| `send_jitter_min` / `send_jitter_max` | Random pause (seconds) between repeated messages to the same recipient. |
| `recipient_delay_min` / `recipient_delay_max` | Random pause (seconds) between recipients. |

The same file holds the XPath selectors the bot uses to find WhatsApp Web elements, with fallbacks for older and newer layouts.

## Troubleshooting

WhatsApp Web changes its page layout from time to time, which can break the selectors. If sends start failing or timing out, run the diagnostics:

```bash
python debug/run_diagnostics.py
```

It asks for a test contact name and number, then checks the search box, opening chats, invalid number detection, sending text, attaching media, and sending both. Note that it sends real test messages to that contact. Any phase marked `FAIL` points to the selectors in `core/config.py` that need updating.

Other common issues:

- **Emoji don't send:** make sure `pyperclip` is installed (`pip install -r requirements.txt`).
- **QR code every run:** the session is stored in `whatsapp_session/` in the project folder. Choosing "Delete session" on startup removes it.
- **Chrome says the profile is in use:** close any Chrome window the bot left open and try again. The bot tries to clean these up on start.

To check the scheduling and resume logic without opening a browser:

```bash
python debug/test_utils.py
```

## Project structure

```
whatsapp_bot/
├── main.py                  # Entry point: menus, CSV loading, send loop
├── requirements.txt
├── core/
│   ├── client.py            # WhatsAppClient: opening chats, sending text and media
│   ├── config.py            # Settings and XPath selectors
│   ├── logger.py            # Logging to console and log.txt
│   └── utils.py             # CSV builder, checkpoints, scheduling, helpers
├── debug/
│   ├── run_diagnostics.py   # Live check of WhatsApp Web selectors
│   └── test_utils.py        # Offline self-check
└── data/                    # Your targets.csv and checkpoint (not committed)
```

## Privacy

Your data stays on your computer. The login session (`whatsapp_session/`), recipient lists (`data/`), and logs (`log.txt`) are listed in `.gitignore` so they are never committed.

## License

[MIT](LICENSE)

This is a personal project and is not affiliated with or endorsed by WhatsApp or Meta.
