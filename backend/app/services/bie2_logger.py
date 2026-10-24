import logging
import os
from datetime import datetime

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

bie2_logger = logging.getLogger("bie2_stempel")
bie2_logger.setLevel(logging.INFO)

if not bie2_logger.handlers:
    handler = logging.FileHandler(os.path.join(LOG_DIR, "bie2_stempel.log"), encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    bie2_logger.addHandler(handler)


def log_bie2(action: str, employee_name: str, object_name: str, details: str = ""):
    msg = f"{action} | {employee_name} | {object_name}"
    if details:
        msg += f" | {details}"
    bie2_logger.info(msg)
