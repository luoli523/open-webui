"""Import only Telegram settings from a local dotenv file. Never print credentials."""

import argparse
import json
import sqlite3
import time
from pathlib import Path

from dotenv import dotenv_values

parser = argparse.ArgumentParser()
parser.add_argument('env_file', type=Path)
parser.add_argument('database', type=Path)
args = parser.parse_args()
values = dotenv_values(args.env_file)
token = values.get('TELEGRAM_BOT_TOKEN')
chat_id = values.get('TELEGRAM_CHAT_ID')
if not token or not chat_id:
    raise SystemExit('Telegram configuration is incomplete')
with sqlite3.connect(args.database) as db:
    db.execute(
        'INSERT INTO config (key, value, updated_at) VALUES (?, ?, ?) '
        'ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at',
        ('audio.studio.telegram', json.dumps({'token': token, 'chat_id': chat_id}), int(time.time())),
    )
print('Telegram configuration imported; credentials remain in the local server database.')
