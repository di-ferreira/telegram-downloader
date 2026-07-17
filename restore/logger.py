import os
import sys
import logging

LOG_DIR = "logs"


def create_logs():
    os.makedirs(LOG_DIR, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    restore_handler = logging.FileHandler(
        os.path.join(LOG_DIR, "restore.log"), encoding="utf-8"
    )
    restore_handler.setLevel(logging.INFO)
    restore_handler.setFormatter(formatter)
    root.addHandler(restore_handler)

    errors_handler = logging.FileHandler(
        os.path.join(LOG_DIR, "errors.log"), encoding="utf-8"
    )
    errors_handler.setLevel(logging.ERROR)
    errors_handler.setFormatter(formatter)
    root.addHandler(errors_handler)

    missing_handler = logging.FileHandler(
        os.path.join(LOG_DIR, "missing_media.log"), encoding="utf-8"
    )
    missing_handler.setLevel(logging.WARNING)
    missing_handler.setFormatter(formatter)
    root.addHandler(missing_handler)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    root.addHandler(console)

    return logging.getLogger(__name__)
