# core/logger.py

import logging
import os

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "system.log")

if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

logging.basicConfig(
    filename=LOG_FILE,
    filemode='a',
    format='[%(asctime)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.INFO
)

def log(message):
    logging.info(message)
