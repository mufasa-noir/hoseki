from __future__ import annotations

from fastapi.testclient import TestClient

from hoseki.app import create_app
from hoseki.auth import get_or_create_token


def _client(config):
    """Build a TestClient whose Host header matches the configured server.

    Starlette's TestClient defaults to `Host: testserver`, which our
    DNS-rebinding middleware correctly rejects. Setting base_url makes the
    client send the same Host a real loopback request would.
    """
    app = create_app(config)
    token = get_or_create_token(config.token_file)
    base = f"http://{config.server.host}:{config.server.port}"
    return TestClient(app, base_url=base), token


def test_health_no_auth(config):
    client, _ = _client(config)
    r = client.get("/v1/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_status_requires_token(config):
    client, _ = _client(config)
    r = client.get("/v1/status")
    assert r.status_code == 401


def test_status_with_token(config):
    client, token = _client(config)
    r = client.get("/v1/status",
                   headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "list_dir" in body["tools"]
    assert "tree" in body["tools"]
    assert "write_file" in body["tools"]


def test_call_list_dir(config):
    client, token = _client(config)
    r = client.post(
        "/v1/call",
        headers={"Authorization": f"Bearer {token}"},
        json={"id": "c1", "name": "list_dir", "args": {"path": "."}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "src" in body["output"]


def test_call_unknown_tool(config):
    client, token = _client(config)
    r = client.post(
        "/v1/call",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "nope", "args": {}},
    )
    body = r.json()
    assert body["ok"] is False
    assert "unknown tool" in body["error"]


def test_call_bad_args(config):
    client, token = _client(config)
    r = client.post(
        "/v1/call",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "read_file", "args": {"path": "src/app.py", "bogus": 1}},
    )
    body = r.json()
    assert body["ok"] is False
    assert "invalid arguments" in body["error"]


def test_bad_host_rejected(config):
    client, token = _client(config)
    r = client.get(
        "/v1/status",
        headers={
            "Authorization": f"Bearer {token}",
            "Host": "evil.example",
        },
    )
    assert r.status_code == 400


def test_bad_origin_rejected(config):
    client, token = _client(config)
    r = client.get(
        "/v1/status",
        headers={
            "Authorization": f"Bearer {token}",
            "Origin": "https://evil.example",
        },
    )
    assert r.status_code == 403