"""Device identity and user-owned model credentials. Never fall back to plaintext keys."""
import base64
import hashlib
import json
import os
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, PrivateFormat, NoEncryption


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def b64(value):
    return base64.b64encode(value).decode('ascii')


def unb64(value):
    return base64.b64decode(value, validate=True)


class SystemVault:
    def __init__(self, namespace):
        import keyring
        self.backend = keyring.get_keyring()
        module = type(self.backend).__module__
        # Only OS-backed stores. Third-party plaintext/fail backends are not accepted.
        if not module.startswith(('keyring.backends.Windows', 'keyring.backends.macOS', 'keyring.backends.SecretService', 'keyring.backends.kwallet')):
            raise ValueError('本机系统密钥库不可用。Windows请使用正常登录的用户启动；Linux需要Secret Service。不会把密钥改存明文。')
        self.namespace = namespace

    def get(self, key):
        return self.backend.get_password(self.namespace, key)

    def set(self, key, value):
        self.backend.set_password(self.namespace, key, value)

    def delete(self, key):
        if self.get(key) is not None:
            self.backend.delete_password(self.namespace, key)


class Identity:
    def __init__(self, folder, vault=None):
        self.folder = Path(folder).resolve()
        self.folder.mkdir(parents=True, exist_ok=True)
        self.vault = vault or SystemVault('hyper-growth-local:' + hashlib.sha256(str(self.folder).encode()).hexdigest()[:24])
        raw = self.vault.get('identity')
        if raw:
            self.key = Ed25519PrivateKey.from_private_bytes(unb64(raw))
        else:
            # Never replace an existing identity when its vault is missing.
            if (self.folder / 'device.json').exists():
                raise ValueError('设备身份已存在，但系统密钥库中缺少对应密钥。请恢复密钥，或选择新的空数据目录；不会覆盖原记录。')
            self.key = Ed25519PrivateKey.generate()
            self.vault.set('identity', b64(self.key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())))
        self.public_key = b64(self.key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
        self.id = hashlib.sha256(unb64(self.public_key)).hexdigest()
        p = self.folder / 'device.json'
        if p.exists() and json.loads(p.read_text(encoding='utf8'))['id'] != self.id:
            raise ValueError('设备密钥与数据目录不匹配，已停止启动。')
        if not p.exists():
            p.write_text(json.dumps({'id': self.id, 'public_key': self.public_key}), encoding='utf8')

    def sign(self, value):
        return b64(self.key.sign(canonical(value)))

    @staticmethod
    def verify(public_key, value, signature):
        try:
            Ed25519PublicKey.from_public_bytes(unb64(public_key)).verify(unb64(signature), canonical(value))
        except Exception:
            raise PermissionError('设备签名校验失败，未接收数据。') from None

    def envelope(self, peer_id, kind, payload, event_id):
        body = {'id': event_id, 'sender': self.id, 'recipient': peer_id, 'kind': kind, 'payload': payload}
        return {'body': body, 'signature': self.sign(body)}
