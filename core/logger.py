import sys
import logging
from logging.handlers import RotatingFileHandler

log = logging.getLogger("whatsapp_sender")
log.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

fh = RotatingFileHandler("log.txt", maxBytes=10_000_000, backupCount=5)
fh.setFormatter(formatter)
log.addHandler(fh)

ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(formatter)
log.addHandler(ch)
