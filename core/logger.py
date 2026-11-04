# core/logger.py
# Updated 2026-07-26 — project-root-relative paths, one shared per-agent logger factory. Jay Pratt + AI (Claude, Anthropic).

import logging
import os
from logging.handlers import RotatingFileHandler

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
LOG_FILE = os.path.join(LOG_DIR, "system.log")


class _FastRotatingFileHandler(RotatingFileHandler):
    """Same rotation behaviour as RotatingFileHandler -- same files,
    same trigger point, same maxBytes/backupCount cap -- but tracks
    its own size in memory instead of the stock shouldRollover()'s
    stream.seek(0, 2) + stream.tell() on every single emitted record
    to find the current file size. That seek is a real, measured
    Windows cost (2026-11-04, Ccode update.txt "JOB 2: FIX THE LOG
    SIZE-CHECK" -- 43% of a channel's runtime when jump events are
    frequent, profiled as the `nt.stat`-level cost inside it). Only
    difference from the stock handler is speed."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._current_size = self._stat_size()
        self._pending_len = 0

    def _stat_size(self):
        try:
            return os.path.getsize(self.baseFilename)
        except OSError:
            return 0

    def shouldRollover(self, record):
        if self.stream is None:
            self.stream = self._open()
            self._current_size = self._stat_size()
        if self.maxBytes > 0:
            msg = "%s\n" % self.format(record)
            self._pending_len = len(msg)
            if self._current_size + self._pending_len >= self.maxBytes:
                return 1
        return 0

    def emit(self, record):
        super().emit(record)
        self._current_size += self._pending_len

    def doRollover(self):
        super().doRollover()
        self._current_size = 0

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
    # Without this, every per-agent message also propagates to the root
    # logger (configured by basicConfig() above to write logs/system.log),
    # so system.log silently duplicates the content of every other log
    # file instead of holding just main.py's own top-level narrative.
    logger.propagate = False
    if not logger.handlers:
        # Capped and rotated -- gracie.log and event_bus.log grew to 249GB
        # and 57GB uncapped over the project's life (plain FileHandler,
        # append forever) and filled the disk on 2026-10-29, crashing the
        # overnight compute queue. 20MB x 4 files = 80MB ceiling per agent.
        handler = _FastRotatingFileHandler(
            os.path.join(LOG_DIR, f'{agent_name}.log'), maxBytes=20 * 1024 * 1024, backupCount=3
        )
        handler.setFormatter(
            logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s')
        )
        logger.addHandler(handler)
    return logger