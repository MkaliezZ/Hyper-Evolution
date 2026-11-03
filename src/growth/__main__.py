import argparse, os
from pathlib import Path
import uvicorn
from dotenv import load_dotenv

load_dotenv(override=False)
from growth.web import create_app

parser = argparse.ArgumentParser(description="超维成长：教师、学生网页及MCP服务")
parser.add_argument("--host", default="127.0.0.1")
parser.add_argument("--port", type=int, default=8877)
parser.add_argument("--data", default=os.environ.get("BASE_DATA", "data/growth"))
args = parser.parse_args()
app = create_app(args.data)
print(
    f"超维成长 http://{args.host}:{args.port}\n教师口令在 {Path(args.data).resolve() / 'owner-token.txt'}\nHTTP MCP: /mcp/（Bearer教师口令），或使用 stdio。",
    flush=True,
)
uvicorn.run(app, host=args.host, port=args.port)
