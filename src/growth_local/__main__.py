"""One local launcher: browser UI and MCP share data; packaged console entry also supports stdio."""
import argparse
import os
from pathlib import Path
import socket
import sys
import threading
import time
import webbrowser


def main():
    from growth_local.mcp import default_data
    parser = argparse.ArgumentParser(description='超维成长本地版')
    parser.add_argument('--data', default=os.environ.get('HYPER_GROWTH_DATA'))
    parser.add_argument('--edition', choices=['teacher', 'student', 'self'], help='预选首次使用入口，并使用该版本的独立默认数据目录')
    parser.add_argument('--coordinator', default=os.environ.get('HYPER_EVOLUTION_COORDINATOR'), help='自己的 wss:// 连接服务地址')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--mcp', action='store_true')
    parser.add_argument('--web', action='store_true', help='用控制台启动HTML服务，便于排查启动问题')
    args = parser.parse_args()
    from growth_local.edition import edition_data
    args.data = args.data or str(edition_data(args.edition) if args.edition else default_data())
    if args.mcp or ('mcp' in Path(sys.executable).stem.lower() and not args.web):
        from base.app.local_runtime import LocalRuntime
        from growth_local.mcp import create_mcp
        create_mcp(LocalRuntime(args.data)).run(transport='stdio')
        return
    folder = Path(args.data).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    # Single companion process per data directory. Reopening never interrupts live jobs.
    lock = open(folder/'.instance.lock','a+b')
    try:
        if os.name == 'nt':
            import msvcrt
            if lock.tell()==0: lock.write(b'0'); lock.flush()
            lock.seek(0); msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except (OSError, IOError):
        import httpx,json
        running=json.loads((folder/'running.json').read_text(encoding='utf8'))
        port=int(running['port'])
        if not 1 <= port <= 65535: raise ValueError('本机端口状态无效')
        token=(folder/'owner-token.txt').read_text(encoding='utf8').strip()
        response=httpx.post(f'http://127.0.0.1:{port}/api/local/reopen',headers={'Authorization':'Bearer '+token},timeout=10,trust_env=False)
        response.raise_for_status()
        if args.no_browser:
            (folder/'qa-launch-url.txt').write_text(response.json()['url'],encoding='utf8')
        else: webbrowser.open(response.json()['url'])
        return
    if getattr(sys, 'frozen', False):
        # GUI builds have no console streams; never log credentials to a terminal.
        if sys.stdout is None:
            sys.stdout = open(folder/'runtime.log', 'a', encoding='utf8')
        if sys.stderr is None:
            sys.stderr = sys.stdout
    from growth_local.web import create_app
    import uvicorn
    app = create_app(folder)
    app.state.launch_edition = args.edition
    if args.coordinator:
        from growth_local.edition import validate_coordinator
        app.state.runtime.save_config('network', {'coordinator': validate_coordinator(args.coordinator)})
    sock = socket.socket()
    sock.bind(('127.0.0.1', args.port))
    sock.listen(128)
    port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}/#start={app.state.bootstrap}'
    (folder/'running.json').write_text(__import__('json').dumps({'pid': os.getpid(), 'port': port, 'url': f'http://127.0.0.1:{port}/'}), encoding='utf8')
    if not args.no_browser:
        def open_browser():
            time.sleep(1)
            webbrowser.open(url)
        threading.Thread(target=open_browser, daemon=True).start()
    else:
        # Private file for local automated QA only, never part of release or logs.
        (folder/'qa-launch-url.txt').write_text(url, encoding='utf8')
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, access_log=False, log_level='warning'))
    app.state.shutdown = lambda: setattr(server, 'should_exit', True)
    server.run(sockets=[sock])


if __name__ == '__main__':
    main()
