"""Distribution defaults only; identity and authorization remain Runtime responsibilities."""
import os
from pathlib import Path

EDITIONS = {'teacher': 'Enlighter', 'student': 'Evolver', 'self': 'Self-Evolver'}


def edition_data(edition):
    """Each edition starts in its own workspace; explicit --data always wins."""
    name = EDITIONS[edition]
    root = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.local' / 'share')
    return root / 'HyperEvolution' / name / 'data'


def validate_coordinator(value):
    from urllib.parse import urlsplit
    parts = urlsplit(value)
    local = parts.hostname in ['127.0.0.1', 'localhost', '::1']
    if not parts.hostname or parts.username or parts.password or parts.fragment or parts.query:
        raise ValueError('请填写不含凭据的完整连接服务地址')
    if parts.scheme != 'wss' and not (local and parts.scheme == 'ws'):
        raise ValueError('公开连接服务使用 wss://；本机测试可使用 ws://')
    return value
