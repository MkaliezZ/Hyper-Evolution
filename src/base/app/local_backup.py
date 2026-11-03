"""Password-encrypted portable backup including device identity; never export plaintext credentials."""
import hashlib
import io
import json
import secrets
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from contextlib import closing
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from base.app.local_identity import b64, unb64

MAGIC = b'HGRECOVERY1\n'


def derive(password, salt):
    if not isinstance(password, str) or not 12 <= len(password) <= 200:
        raise ValueError('恢复密码请使用12—200个字符，并保存在你能找回的地方')
    return Scrypt(salt=salt, length=32, n=32768, r=8, p=1).derive(password.encode('utf8'))


def export_backup(runtime, password):
    from base.app.companion.functional.workspaces import host
    from base.app.companion.functional.workspace_lock import lock
    with lock(host(runtime).root.folder):return _export_backup(runtime,password)

def _export_backup(runtime,password):
    from base.app.companion.functional.workspaces import host
    workspace=host(runtime);runtime=workspace.root
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    key = derive(password, salt)
    with tempfile.TemporaryDirectory(prefix='hyper-growth-backup-') as temp:
        datasets=[('',runtime)]+[('subjects/'+id,workspace.runtime(id)) for id in (workspace.state() or {}).get('subjects',{})]
        for prefix,current in datasets:
            snapshot=Path(temp)/prefix/'base.sqlite3';snapshot.parent.mkdir(parents=True,exist_ok=True)
            with current.db() as live,closing(sqlite3.connect(snapshot)) as backup:live.backup(backup)
        with closing(sqlite3.connect(Path(temp)/'base.sqlite3')) as db:
            peer_ids = [r[0] for r in db.execute('SELECT id FROM local_peers')]
        keys = {'identity': runtime.vault.get('identity')}
        if runtime.vault.get('api'): keys['api'] = runtime.vault.get('api')
        for id in peer_ids:
            secret = runtime.vault.get('peer:' + id)
            if secret: keys['peer:' + id] = secret
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('keys.json', json.dumps(keys))
            for prefix,current in datasets:
                base=prefix+'/' if prefix else ''
                archive.write(Path(temp)/prefix/'base.sqlite3',base+'base.sqlite3')
                archive.write(current.folder/'device.json',base+'device.json')
                if prefix:archive.write(current.folder/'workspace.json',base+'workspace.json')
                for name in ['media','peer-media','uploads','materials']:
                    folder=current.folder/name
                    if folder.is_dir():
                        for file in folder.rglob('*'):
                            if file.is_file() and not file.is_symlink() and file.resolve().is_relative_to(folder.resolve()):
                                archive.write(file,base+file.relative_to(current.folder).as_posix())
        raw = stream.getvalue()
        if len(raw) > 80*1024*1024:
            raise ValueError('当前恢复包超过80MB，请先使用完整数据目录备份；没有生成不完整恢复包')
    return MAGIC + salt + nonce + AESGCM(key).encrypt(nonce, raw, MAGIC)


def validate_dataset(staging,target,expected_role=None):
    with closing(sqlite3.connect(staging/'base.sqlite3')) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise ValueError('恢复数据库完整性检查未通过')
        profile = json.loads(db.execute("SELECT body FROM local_config WHERE key='profile'").fetchone()[0])
        if profile['role'] not in ['teacher','student'] or expected_role and profile['role']!=expected_role:raise ValueError('恢复包身份或学科角色不一致')
        # Paths in the backup move to the new device's selected data directory.
        for row in db.execute('SELECT id,body FROM hd_resources').fetchall():
            pack = json.loads(row[1])
            if pack.get('media_path'):
                name = Path(pack['media_path'].replace('\\', '/')).name
                file = staging/'media'/name
                if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != pack['audio_sha256']: raise ValueError('备份音频校验失败')
                pack['media_path'] = str(target/'media'/name)
                db.execute('UPDATE hd_resources SET body=? WHERE id=?', (json.dumps(pack,ensure_ascii=False),row[0]))
        for id, path, digest in db.execute('SELECT id,path,sha256 FROM hd_files').fetchall():
            name = Path(path.replace('\\', '/')).name
            file = staging/'uploads'/name
            if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != digest: raise ValueError('备份附件校验失败')
            db.execute('UPDATE hd_files SET path=? WHERE id=?',(str(target/'uploads'/name),id))
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='companion_pages'").fetchone():
            for row in db.execute('SELECT body FROM companion_pages'):
                page=json.loads(row[0]);checksum=page['source_hash']
                if not isinstance(checksum,str) or len(checksum)!=64 or any(c not in '0123456789abcdef' for c in checksum):raise ValueError('原图引用无效')
                original=staging/'uploads'/('page-'+checksum)
                if not original.is_file() or hashlib.sha256(original.read_bytes()).hexdigest()!=checksum:raise ValueError('恢复包原图校验失败')
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='companion_materials'").fetchone() and (staging/'materials').exists():
            from base.app.companion.assets.workspaces import text_path,check_text
            for row in db.execute('SELECT body FROM companion_materials'):
                material=json.loads(row[0]);check_text(material,text_path(staging,material).read_bytes())
        db.commit()
        return profile['role']


def restore_backup(runtime, encrypted, password):
    from base.app.companion.functional.workspaces import host
    runtime=host(runtime).root
    if runtime.profile:
        raise ValueError('只能恢复到尚未设置身份的新安装，不能覆盖正在使用的档案')
    if not encrypted.startswith(MAGIC) or len(encrypted) > 85*1024*1024:
        raise ValueError('恢复包格式或大小不正确')
    offset = len(MAGIC)
    salt, nonce = encrypted[offset:offset+16], encrypted[offset+16:offset+28]
    try:
        raw = AESGCM(derive(password, salt)).decrypt(nonce, encrypted[offset+28:], MAGIC)
    except Exception:
        raise ValueError('恢复密码不正确，或恢复包内容已损坏；原数据未修改') from None
    with tempfile.TemporaryDirectory(prefix='hyper-growth-restore-') as temp:
        staging = Path(temp)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if len(archive.infolist()) > 3000 or sum(i.file_size for i in archive.infolist()) > 150*1024*1024:
                raise ValueError('恢复包解压内容过大')
            for info in archive.infolist():
                parts = info.filename.split('/')
                local=parts
                if parts[0]=='subjects' and len(parts)>=3:
                    from base.app.companion.assets.workspaces import subject_path
                    subject_path(runtime.folder,parts[1]);local=parts[2:]
                allowed=(len(local)==1 and local[0] in ['base.sqlite3','device.json','workspace.json'] or info.filename=='keys.json' or
                    len(local)==2 and local[0] in ['media','peer-media','uploads'] or len(local)==3 and local[0]=='materials' and local[2].endswith(('.txt','.json')))
                allowed=allowed and all(p and p not in ['.','..'] for p in parts)
                if not allowed or '\\' in info.filename or ':' in info.filename:
                    raise ValueError('恢复包包含不允许的文件路径')
                archive.extract(info, staging)
        keys = json.loads((staging/'keys.json').read_text(encoding='utf8'))
        device = json.loads((staging/'device.json').read_text(encoding='utf8'))
        pub = b64(Ed25519PrivateKey.from_private_bytes(unb64(keys['identity'])).public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))
        if device['public_key'] != pub or device['id'] != hashlib.sha256(unb64(pub)).hexdigest():
            raise ValueError('恢复包身份与密钥不一致')
        role=validate_dataset(staging,runtime.folder)
        with closing(sqlite3.connect(staging/'base.sqlite3')) as db:
            row=db.execute("SELECT body FROM local_config WHERE key='subject-workspaces-v1'").fetchone()
            workspace=json.loads(row[0]) if row else None
        subjects=(workspace or {}).get('subjects',{})
        present={p.name for p in (staging/'subjects').iterdir()} if (staging/'subjects').exists() else set()
        if present!=set(subjects):raise ValueError('恢复包学科目录与登记不一致')
        from base.app.companion.assets.workspaces import subject_path
        for subject in subjects:
            target=subject_path(runtime.folder,subject);current=staging/'subjects'/subject
            if json.loads((current/'device.json').read_text(encoding='utf8'))!=device:raise ValueError('学科设备身份不一致')
            descriptor=json.loads((current/'workspace.json').read_text(encoding='utf8'))
            if descriptor!={'version':1,'subject':subject,'name':subjects[subject]['name'],'device':device['id']}:raise ValueError('学科目录说明不一致')
            validate_dataset(current,target,role)
        for name, value in keys.items():
            if name not in ['identity', 'api'] and not name.startswith('peer:'): raise ValueError('恢复包包含未知凭据类型')
            if not isinstance(value,str) or len(value)>2000: raise ValueError('恢复凭据无效')
        # All cryptographic, path and database checks complete before writing the fresh installation.
        if 'api' not in keys: runtime.vault.delete('api')
        for name, value in keys.items(): runtime.vault.set(name, value)
        for file in staging.rglob('*'):
            if file.is_file() and file.name != 'keys.json':
                target = runtime.folder/file.relative_to(staging)
                if not target.resolve().is_relative_to(runtime.folder): raise ValueError('恢复目标越界')
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(file,target)
    return {'restored': True, 'restart_required': True, 'identity_preserved': True}
