import os
import sys
import logging
from logging.handlers import RotatingFileHandler

from core.config import BASE_DIR

log = logging.getLogger("whatsapp_sender")
log.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

fh = RotatingFileHandler(os.path.join(BASE_DIR, "log.txt"), maxBytes=10_000_000, backupCount=5)
fh.setFormatter(formatter)
log.addHandler(fh)

ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(formatter)
log.addHandler(ch)
