"""Distribution selection is a hint; setup still owns role authorization."""
from pathlib import Path
from fastapi.testclient import TestClient
from base.app.local_runtime import LocalRuntime
from growth_local.edition import edition_data
from growth_local.edition import validate_coordinator
import pytest
from growth_local.web import create_app


class Vault:
    def __init__(self): self.values = {}
    def get(self, key): return self.values.get(key)
    def set(self, key, value): self.values[key] = value
    def delete(self, key): self.values.pop(key, None)


def test_edition_directories_are_distinct(monkeypatch, tmp_path):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    paths = [edition_data(k) for k in ['teacher', 'student', 'self']]
    assert len(set(paths)) == 3
    assert paths[0] == tmp_path / 'HyperEvolution' / 'Enlighter' / 'data'


def test_coordinator_accepts_tls_or_loopback_only():
    assert validate_coordinator('wss://connect.example.org/ws')
    assert validate_coordinator('ws://127.0.0.1:8878/ws')
    for address in ['ws://public.example/ws','https://connect.example/ws','wss://name:pass@example.org/ws']:
        with pytest.raises(ValueError):validate_coordinator(address)


def test_launch_hint_does_not_initialize_or_promote_identity(tmp_path):
    runtime = LocalRuntime(tmp_path, Vault())
    app = create_app(tmp_path, runtime=runtime, network=False)
    app.state.launch_edition = 'teacher'
    headers = {'Authorization': 'Bearer ' + runtime.service.base.owner_token}
    with TestClient(app, base_url='http://127.0.0.1') as client:
        result = client.get('/api/local/status', headers=headers).json()
        assert result['launch_edition'] == 'teacher' and not result['profile'].get('role')
        result = client.post('/api/local/setup', headers=headers, json={'role':'self','name':'Original engineering learner'}).json()
        assert result['profile']['role'] == 'student' and result['experience']['id'] == 'self'
        denied = client.post('/api/local/capabilities/invoke', headers=headers, json={
            'contract_version':'companion.capability.v11','request_id':'no-promotion',
            'operation':'experience.select','payload':{'experience':'teacher'}})
        assert denied.status_code == 403
