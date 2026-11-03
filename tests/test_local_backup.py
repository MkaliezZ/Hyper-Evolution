import json
import pytest
from base.app.local_runtime import LocalRuntime
from base.app.local_backup import export_backup, restore_backup
from test_local_runtime import instance, pair, MemoryVault


def test_encrypted_restore_preserves_identity_key_peers_and_work(tmp_path):
    original=instance(tmp_path/'original','student','合成迁移学生')
    teacher=instance(tmp_path/'teacher','teacher','合成教师')
    pair(original,teacher)
    original.save_model({'provider':'deepseek','base_url':'https://api.deepseek.com','model':'synthetic'},'synthetic-key',True)
    task=original.start_self('diagnostic','backup-test')
    encrypted=export_backup(original,'synthetic-password-2026')
    assert b'synthetic-key' not in encrypted and b'base.sqlite3' not in encrypted
    fresh=LocalRuntime(tmp_path/'fresh',MemoryVault())
    with pytest.raises(ValueError,match='密码'):
        restore_backup(fresh,encrypted,'incorrect-password')
    assert not fresh.profile
    restore_backup(fresh,encrypted,'synthetic-password-2026')
    restored=LocalRuntime(fresh.folder,fresh.vault)
    assert restored.identity.id==original.identity.id
    assert restored.model_key()=='synthetic-key'
    assert restored.peers()==original.peers()
    assert restored.task(task['id'])['id']==task['id']
    with pytest.raises(ValueError,match='新安装'):
        restore_backup(restored,encrypted,'synthetic-password-2026')


def test_external_process_changes_revision(tmp_path):
    first=instance(tmp_path/'shared','student','合成学生')
    before=first.status()['revision']
    second=LocalRuntime(first.folder,first.vault)
    second.start_self('diagnostic','external-mcp')
    assert first.status()['revision']!=before
