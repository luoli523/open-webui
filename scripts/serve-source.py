"""Start this checkout using installed Open WebUI dependencies and the existing data directory."""

import argparse
import os
import secrets
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--host', default='127.0.0.1')
parser.add_argument('--port', type=int, default=8080)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
data = Path(os.environ.get('DATA_DIR', root / 'backend/data')).resolve()
data.mkdir(parents=True, exist_ok=True)
secret = data / '.webui_secret_key'
if not os.environ.get('WEBUI_SECRET_KEY'):
    if not secret.exists():
        with secret.open('x') as f:
            os.chmod(secret, 0o600)
            f.write(secrets.token_hex(32))
    os.environ['WEBUI_SECRET_KEY'] = secret.read_text().strip()
os.environ.setdefault('FRONTEND_BUILD_DIR', str(root / 'build'))
os.environ.setdefault('STATIC_DIR', str(data / 'static'))
Path(os.environ['STATIC_DIR']).mkdir(parents=True, exist_ok=True)
import uvicorn  # noqa: E402 - initialize the persistent secret before importing the server

uvicorn.run('open_webui.main:app', host=args.host, port=args.port)
