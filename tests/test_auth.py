from __future__ import annotations

import os
import stat

from hoseki.auth import check_host, check_origin, get_or_create_token, verify_token
from hoseki.config import ServerConfig


def test_token_created_with_0600(tmp_path):
    path = tmp_path / "tok"
    token = get_or_create_token(path)
    assert path.exists()
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600
    assert len(token) > 20


def test_token_stable_across_calls(tmp_path):
    path = tmp_path / "tok"
    t1 = get_or_create_token(path)
    t2 = get_or_create_token(path)
    assert t1 == t2


def test_verify_token():
    assert verify_token("abc", "Bearer abc")
    assert not verify_token("abc", "Bearer xyz")
    assert not verify_token("abc", None)
    assert not verify_token("abc", "abc")
    assert not verify_token("abc", "Basic abc")


def test_origin_allowlist():
    assert check_origin("chrome-extension://abc", ["chrome-extension://*"], False)
    assert not check_origin("https://evil.example", ["chrome-extension://*"], False)
    assert not check_origin(None, ["chrome-extension://*"], False)
    assert check_origin(None, ["chrome-extension://*"], True)


def test_host_check():
    server = ServerConfig(port=8787)
    assert check_host("127.0.0.1:8787", server)
    assert check_host("localhost:8787", server)
    assert check_host("[::1]:8787", server)
    assert not check_host("evil.example:8787", server)
    assert not check_host("127.0.0.1:9999", server)
    assert not check_host(None, server)