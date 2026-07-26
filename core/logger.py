# core/logger.py
# Updated 2026-07-26 — project-root-relative paths, one shared per-agent logger factory. Jay Pratt + AI (Claude, Anthropic).

import logging
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
LOG_FILE = os.path.join(LOG_DIR, "system.log")

os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    filename=LOG_FILE,
    filemode='a',
    format='[%(asctime)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.INFO
)


def log(message):
    logging.info(message)


def setup_agent_logger(agent_name):
    """Per-agent logger writing to logs/<agent_name>.log.

    Safe to call repeatedly for the same agent: the handler is only attached
    once, so re-instantiating an agent does not duplicate every log line.
    """
    logger = logging.getLogger(agent_name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(os.path.join(LOG_DIR, f'{agent_name}.log'))
        handler.setFormatter(
            logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s')
        )
        logger.addHandler(handler)
    return logger