import argparse
import os
from pathlib import Path
import uvicorn

parser = argparse.ArgumentParser(description='base 本地伴学服务')
parser.add_argument('--port', type=int, default=8765)
parser.add_argument('--host', default='127.0.0.1')
parser.add_argument('--data', default=os.environ.get('BASE_DATA', 'data/base'))
args = parser.parse_args()
os.environ['BASE_DATA'] = str(Path(args.data).resolve())
print(f'base: http://{args.host}:{args.port}  | 管理口令文件: {Path(args.data).resolve() / "owner-token.txt"}', flush=True)
uvicorn.run('base.web:create_app', factory=True, host=args.host, port=args.port, access_log=False)
