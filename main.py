# TODO: file change monitor works inefficiently when too many files
from pathlib import Path
import pyperclip
import time
import hashlib
from datetime import datetime
import threading
import json
import os
import platform
import logging
import sys

logging.basicConfig(level=logging.INFO)

shared_state = {"seen_hash": None, "lock": threading.Lock()}


def get_cache_path(app_name):
    current_os = platform.system()
    if current_os == "Linux" or current_os == "Darwin":
        user_cache_dir = Path.home() / ".cache" / app_name
        return user_cache_dir
    elif current_os == "Windows":
        appdata_dir = Path(os.getenv("LOCALAPPDATA")) / app_name
        return appdata_dir
    raise OSError("Unsupported operating system")


def get_config_path(app_name):
    current_os = platform.system()
    if current_os == "Linux" or current_os == "Darwin":
        return Path.home() / ".config" / app_name / "config.json"
    elif current_os == "Windows":
        return Path(os.getenv("APPDATA")) / app_name / "config.json"
    raise OSError("Unsupported operating system")


def generate_filename():
    now = datetime.now().astimezone()
    timestamp = now.strftime("%Y%m%dT%H%M%S")
    ns = time.time_ns() % 1_000_000_000
    return f"{timestamp}_{ns:09d}.txt"


def clipboard_monitor_loop(sync_dir):
    while True:
        try:
            content = pyperclip.paste()
            if content is None:
                continue
            h = hashlib.md5(content.encode()).hexdigest()
            with shared_state["lock"]:
                if content and h != shared_state["seen_hash"]:
                    logging.info("<== clipboard changed")
                    logging.info({content})
                    logging.info("<==")
                    fname = generate_filename()
                    path = Path(sync_dir) / "items" / fname
                    with open(path, "w", encoding="utf-8", newline="") as f:
                        f.write(content)
                    shared_state["seen_hash"] = h
                    applied_item_record_file = cache_dir / "last_applied.txt"
                    applied_item_record_file.write_text(fname)
            time.sleep(0.1)
        except Exception as ex:
            logging.error(f"Clipboard Monitor Thread Exception Occured: {str(ex)}")

def clipboard_update_loop(sync_dir):
    applied_item_record_file = cache_dir / "last_applied.txt"
    while True:
        try:
            applied_item_name = (
                applied_item_record_file.read_text().strip()
                if applied_item_record_file.exists()
                else ""
            )

            items = sorted(Path(sync_dir).joinpath("items").glob("*.txt"))
            for item in reversed(items):  # newest item first
                if item.name == applied_item_name:
                    break

                # found item never applied to clipboard, apply it to clipboard then
                item_content = item.read_text(encoding="utf-8")
                logging.info("==> items changed, update clipboard")
                logging.info({item_content})
                logging.info("==>")

                # overwrite clipboard with new item
                pyperclip.copy(item_content)

                # record the item as applied(so next time it probably won't be applied again)
                applied_item_record_file.write_text(item.name)

                # tell clipboard monitor thread not to create new item on this clipboard change
                with shared_state["lock"]:
                    shared_state["seen_hash"] = hashlib.md5(
                        item_content.encode()
                    ).hexdigest()
                break

            time.sleep(0.1)
        except Exception as ex:
            logging.error(f"Items Monitor Thread Exception Occured: {str(ex)}")


logging.info(f"python version: {sys.version}")

app_name = "SynCopy"

# make sure config file exists
cfg_file = get_config_path(app_name=app_name)
cfg_file.parent.mkdir(parents=True, exist_ok=True)
if not cfg_file.exists():
    with open(cfg_file.absolute(), "w") as f:
        f.write("{}")

# read config content
logging.info(f"try read config file: {cfg_file}")
with cfg_file.open("r", encoding="utf-8") as f:
    cfg = json.load(f)

# read config: sync_dir
sync_dir = cfg.get("sync_dir")
if sync_dir is None:
    logging.info("sync_dir option required")
    os._exit(1)
logging.info(f"sync-dir: {sync_dir}")

# prepare sync folder
Path(sync_dir, "items").mkdir(parents=True, exist_ok=True)

# prepare cache dir
cache_dir = get_cache_path(app_name=app_name)
cache_dir.mkdir(exist_ok=True, parents=True)

# start working threads
threading.Thread(target=clipboard_monitor_loop, args=(sync_dir,), daemon=True).start()
threading.Thread(target=clipboard_update_loop, args=(sync_dir,), daemon=True).start()

while True:
    time.sleep(60)
