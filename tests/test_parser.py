"""Table-driven parser tests for all supported proxy protocols (AUDIT §3.1).

Covers: vless, vmess, trojan, ss, hy2 (hysteria2) — valid links produce
expected ProxyConfig fields; garbage / malformed links return None.

Also tests the LinkParser.parse_link dispatcher for auto-detection and the
garbage-word filter (_is_garbage).
"""
import base64
import json
import pytest

# ── Graceful skip when pydantic 2.x is unavailable ──────────────────────
# The repo pins pydantic==2.6.1 which uses `field_validator` (2.x only).
# On cp314 local dev there is no pydantic-core wheel, so imports fail.
# Tests still syntax-check with py_compile and run fully in CI (3.11).
_PYDANTIC_V2 = False
try:
    from core.models import ProxyNode, ProxyConfig  # noqa: F401  (availability probe)
    from core.parser import LinkParser

    _PYDANTIC_V2 = True
except ImportError:
    pass

pytestmark = pytest.mark.skipif(
    not _PYDANTIC_V2, reason="pydantic 2.x required (CI runs Python 3.11)"
)

# ── Reusable test constants ─────────────────────────────────────────────

VALID_UUID = "b54f3d62-5a7c-4e8f-9b1a-2c3d4e5f6a7b"
# 32 zero-bytes → 43-char base64url (passes the PBK len+decode check)
VALID_PBK = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8"


def _vmess_b64(payload: dict) -> str:
    """Return unpadded base64 of a JSON payload (VMess wire format)."""
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return base64.b64encode(raw.encode()).decode().rstrip("=")


# ══════════════════════════════════════════════════════════════════════════
# VLESS
# ══════════════════════════════════════════════════════════════════════════


class TestVlessValid:
    """Valid VLESS links across common transport / security combos."""

    def test_basic_tcp_reality(self):
        uri = (
            f"vless://{VALID_UUID}@example.com:443"
            f"?type=tcp&security=reality&pbk={VALID_PBK}&sid=6ba85179e3&fp=chrome"
        )
        node = LinkParser.parse_vless(uri)
        assert node is not None
        assert node.protocol == "vless"
        c = node.config
        assert c.server == "example.com"
        assert c.port == 443
        assert c.uuid == VALID_UUID
        assert c.type == "tcp"
        assert c.security == "reality"
        assert c.fp == "chrome"
        assert c.sid == "6ba85179e3"

    def test_ws_tls_with_host_and_path(self):
        uri = (
            f"vless://{VALID_UUID}@example.com:8443"
            f"?type=ws&security=tls&host=cdn.example.com&path=%2Fws"
        )
        node = LinkParser.parse_vless(uri)
        assert node is not None
        c = node.config
        assert c.type == "ws"
        assert c.security == "tls"
        assert c.host == "cdn.example.com"
        assert c.path == "/ws"

    def test_grpc_with_service_name(self):
        uri = (
            f"vless://{VALID_UUID}@example.com:443"
            f"?type=grpc&security=reality&pbk={VALID_PBK}&sid=abc123&serviceName=gRPCSvc"
        )
        node = LinkParser.parse_vless(uri)
        assert node is not None
        c = node.config
        assert c.type == "grpc"
        assert c.service_name == "gRPCSvc"

    def test_raw_uri_preserved(self):
        uri = (
            f"vless://{VALID_UUID}@example.com:443"
            f"?type=tcp&security=reality&pbk={VALID_PBK}&sid=abc&fp=chrome"
        )
        node = LinkParser.parse_vless(uri)
        assert node is not None
        assert node.raw_uri == uri


class TestVlessGarbage:
    """VLESS links that must return None."""

    def test_invalid_uuid_format(self):
        uri = "vless://not-a-valid-uuid@example.com:443?type=tcp&security=reality"
        assert LinkParser.parse_vless(uri) is None

    def test_localhost_rejected(self):
        uri = f"vless://{VALID_UUID}@127.0.0.1:443?type=tcp"
        assert LinkParser.parse_vless(uri) is None

    def test_missing_port(self):
        uri = f"vless://{VALID_UUID}@example.com?type=tcp"
        assert LinkParser.parse_vless(uri) is None

    def test_garbage_word_in_uri(self):
        uri = f"vless://{VALID_UUID}@example.com:443?type=tcp#test1-proxy"
        assert LinkParser.parse_vless(uri) is None

    def test_pbk_too_short_for_reality(self):
        uri = f"vless://{VALID_UUID}@example.com:443?type=tcp&security=reality&pbk=short&sid=abc"
        assert LinkParser.parse_vless(uri) is None

    def test_missing_uuid(self):
        uri = "vless://example.com:443?type=tcp"
        assert LinkParser.parse_vless(uri) is None


# ══════════════════════════════════════════════════════════════════════════
# VMess
# ══════════════════════════════════════════════════════════════════════════


class TestVmessValid:
    """Valid VMess links."""

    def test_basic_tcp_tls(self):
        payload = {
            "v": "2", "ps": "test-node", "add": "example.com", "port": "443",
            "id": VALID_UUID, "aid": "0", "net": "tcp", "type": "none",
            "tls": "tls", "sni": "example.com",
        }
        uri = f"vmess://{_vmess_b64(payload)}"
        node = LinkParser.parse_vmess(uri)
        assert node is not None
        assert node.protocol == "vmess"
        c = node.config
        assert c.server == "example.com"
        assert c.port == 443
        assert c.uuid == VALID_UUID
        assert c.type == "tcp"
        assert c.security == "tls"
        assert c.alter_id == 0

    def test_ws_transport(self):
        payload = {
            "v": "2", "ps": "ws-node", "add": "example.com", "port": "8080",
            "id": VALID_UUID, "aid": "0", "net": "ws", "type": "none",
            "tls": "", "host": "cdn.example.com", "path": "/ws",
        }
        uri = f"vmess://{_vmess_b64(payload)}"
        node = LinkParser.parse_vmess(uri)
        assert node is not None
        c = node.config
        assert c.type == "ws"
        assert c.host == "cdn.example.com"
        assert c.path == "/ws"


class TestVmessGarbage:
    """VMess links that must return None."""

    def test_invalid_uuid(self):
        payload = {
            "v": "2", "add": "example.com", "port": "443",
            "id": "not-a-uuid", "aid": "0", "net": "tcp", "type": "none",
            "tls": "tls",
        }
        uri = f"vmess://{_vmess_b64(payload)}"
        assert LinkParser.parse_vmess(uri) is None

    def test_bad_host(self):
        payload = {
            "v": "2", "add": "0.0.0.0", "port": "443",
            "id": VALID_UUID, "aid": "0", "net": "tcp", "type": "none",
            "tls": "tls",
        }
        uri = f"vmess://{_vmess_b64(payload)}"
        assert LinkParser.parse_vmess(uri) is None

    def test_garbage_word_in_name(self):
        payload = {
            "v": "2", "ps": "test1-node", "add": "example.com", "port": "443",
            "id": VALID_UUID, "aid": "0", "net": "tcp", "type": "none",
            "tls": "tls",
        }
        uri = f"vmess://{_vmess_b64(payload)}"
        assert LinkParser.parse_vmess(uri) is None

    def test_missing_port(self):
        payload = {
            "v": "2", "add": "example.com", "id": VALID_UUID,
            "aid": "0", "net": "tcp", "type": "none", "tls": "tls",
        }
        uri = f"vmess://{_vmess_b64(payload)}"
        assert LinkParser.parse_vmess(uri) is None


# ══════════════════════════════════════════════════════════════════════════
# Trojan
# ══════════════════════════════════════════════════════════════════════════


class TestTrojanValid:
    """Valid Trojan links."""

    def test_basic_tls(self):
        uri = "trojan://securepassword@example.com:443?type=tcp&security=tls&sni=example.com"
        node = LinkParser.parse_trojan(uri)
        assert node is not None
        assert node.protocol == "trojan"
        c = node.config
        assert c.server == "example.com"
        assert c.port == 443
        assert c.password == "securepassword"
        assert c.type == "tcp"
        assert c.security == "tls"

    def test_ws_with_host(self):
        uri = (
            "trojan://password123@example.com:8443"
            "?type=ws&security=tls&host=cdn.example.com&path=%2Ftrojan"
        )
        node = LinkParser.parse_trojan(uri)
        assert node is not None
        c = node.config
        assert c.type == "ws"
        assert c.host == "cdn.example.com"
        assert c.path == "/trojan"


class TestTrojanGarbage:
    """Trojan links that must return None."""

    def test_missing_password(self):
        uri = "trojan://example.com:443?type=tcp&security=tls"
        assert LinkParser.parse_trojan(uri) is None

    def test_bad_host(self):
        uri = "trojan://password@0.0.0.0:443?type=tcp&security=tls"
        assert LinkParser.parse_trojan(uri) is None

    def test_garbage_word(self):
        uri = "trojan://password@example.com:443?type=tcp#rootface-proxy"
        assert LinkParser.parse_trojan(uri) is None


# ══════════════════════════════════════════════════════════════════════════
# Shadowsocks (SS)
# ══════════════════════════════════════════════════════════════════════════


class TestSsValid:
    """Valid SS links."""

    def test_aes_256_gcm(self):
        # base64("aes-256-gcm:password") = "YWVzLTI1Ni1nY206cGFzc3dvcmQ="
        creds = base64.b64encode(b"aes-256-gcm:password").decode().rstrip("=")
        uri = f"ss://{creds}@example.com:8388"
        node = LinkParser.parse_ss(uri)
        assert node is not None
        assert node.protocol == "ss"
        c = node.config
        assert c.server == "example.com"
        assert c.port == 8388
        assert c.method == "aes-256-gcm"
        assert c.password == "password"

    def test_2022_blake3(self):
        # 2022-blake3-aes-256-gcm requires a base64 32-byte PSK; a wrong-length
        # key is a FATAL sing-box startup error that crashes the whole L7 batch,
        # so the parser only accepts a correctly-sized key.
        key = base64.b64encode(b"\x11" * 32).decode()
        creds = base64.b64encode(f"2022-blake3-aes-256-gcm:{key}".encode()).decode().rstrip("=")
        uri = f"ss://{creds}@example.com:443"
        node = LinkParser.parse_ss(uri)
        assert node is not None
        assert node.protocol == "ss"
        assert node.config.method == "2022-blake3-aes-256-gcm"
        assert node.config.password == key

    def test_2022_blake3_bad_key_rejected(self):
        # Non-base64 / wrong-length PSK must be dropped (would crash sing-box).
        creds = base64.b64encode(b"2022-blake3-aes-256-gcm:strongpassword").decode().rstrip("=")
        uri = f"ss://{creds}@example.com:443"
        assert LinkParser.parse_ss(uri) is None


class TestSsGarbage:
    """SS links that must return None."""

    def test_invalid_method(self):
        creds = base64.b64encode(b"rc4-md5:password").decode().rstrip("=")
        uri = f"ss://{creds}@example.com:8388"
        assert LinkParser.parse_ss(uri) is None

    def test_bad_host(self):
        creds = base64.b64encode(b"aes-256-gcm:password").decode().rstrip("=")
        uri = f"ss://{creds}@localhost:8388"
        assert LinkParser.parse_ss(uri) is None

    def test_garbage_word(self):
        creds = base64.b64encode(b"aes-256-gcm:password").decode().rstrip("=")
        uri = f"ss://{creds}@example.com:8388#01010101"
        assert LinkParser.parse_ss(uri) is None

    def test_not_ss_prefix(self):
        assert LinkParser.parse_ss("http://example.com") is None


# ══════════════════════════════════════════════════════════════════════════
# Hysteria2 / HY2
# ══════════════════════════════════════════════════════════════════════════


class TestHy2Valid:
    """Valid HY2 / Hysteria2 links."""

    def test_hy2_basic(self):
        uri = "hy2://password@example.com:443?sni=example.com&insecure=1"
        node = LinkParser.parse_hy2(uri)
        assert node is not None
        assert node.protocol == "hysteria2"
        c = node.config
        assert c.server == "example.com"
        assert c.port == 443
        assert c.password == "password"
        assert c.sni == "example.com"

    def test_hysteria2_prefix(self):
        uri = "hysteria2://password@example.com:443?sni=example.com"
        node = LinkParser.parse_hy2(uri)
        assert node is not None
        assert node.protocol == "hysteria2"

    def test_obfs(self):
        uri = "hy2://password@example.com:443?sni=example.com&obfs=salamander&obfs-password=obfspass"
        node = LinkParser.parse_hy2(uri)
        assert node is not None
        assert node.config.obfs == "salamander"
        assert node.config.obfs_password == "obfspass"


class TestHy2Garbage:
    """HY2 links that must return None."""

    def test_missing_password(self):
        uri = "hy2://example.com:443?sni=example.com"
        assert LinkParser.parse_hy2(uri) is None

    def test_bad_host(self):
        uri = "hy2://password@0.0.0.0:443"
        assert LinkParser.parse_hy2(uri) is None

    def test_garbage_word(self):
        uri = "hy2://password@example.com:443#pwn1337-telegram"
        assert LinkParser.parse_hy2(uri) is None


# ══════════════════════════════════════════════════════════════════════════
# parse_link dispatcher
# ══════════════════════════════════════════════════════════════════════════


class TestParseLink:
    """Auto-detection dispatcher."""

    def test_dispatches_vless(self):
        uri = f"vless://{VALID_UUID}@example.com:443?type=tcp&security=reality&pbk={VALID_PBK}&sid=abc&fp=chrome"
        node = LinkParser.parse_link(uri)
        assert node is not None
        assert node.protocol == "vless"

    def test_dispatches_vmess(self):
        payload = {
            "v": "2", "add": "example.com", "port": "443",
            "id": VALID_UUID, "aid": "0", "net": "tcp", "type": "none", "tls": "tls",
        }
        uri = f"vmess://{_vmess_b64(payload)}"
        node = LinkParser.parse_link(uri)
        assert node is not None
        assert node.protocol == "vmess"

    def test_dispatches_trojan(self):
        uri = "trojan://password@example.com:443?type=tcp&security=tls"
        node = LinkParser.parse_link(uri)
        assert node is not None
        assert node.protocol == "trojan"

    def test_dispatches_ss(self):
        creds = base64.b64encode(b"aes-256-gcm:password").decode().rstrip("=")
        uri = f"ss://{creds}@example.com:8388"
        node = LinkParser.parse_link(uri)
        assert node is not None
        assert node.protocol == "ss"

    def test_dispatches_hy2(self):
        uri = "hy2://password@example.com:443?sni=example.com"
        node = LinkParser.parse_link(uri)
        assert node is not None
        assert node.protocol == "hysteria2"

    def test_dispatches_hysteria2(self):
        uri = "hysteria2://password@example.com:443?sni=example.com"
        node = LinkParser.parse_link(uri)
        assert node is not None
        assert node.protocol == "hysteria2"

    def test_hysteria_alias_dispatches_to_hy2(self):
        uri = "hysteria://password@example.com:443?sni=example.com"
        node = LinkParser.parse_link(uri)
        assert node is not None
        assert node.protocol == "hysteria2"

    def test_unknown_protocol_returns_none(self):
        assert LinkParser.parse_link("notaproto://user@host:443") is None

    def test_empty_string_returns_none(self):
        assert LinkParser.parse_link("") is None

    def test_garbage_uri_returns_none(self):
        assert LinkParser.parse_link("garbage line without protocol") is None

    def test_comment_line_returns_none(self):
        assert LinkParser.parse_link("# this is a comment") is None


# ══════════════════════════════════════════════════════════════════════════
# Garbage-word filter (_is_garbage)
# ══════════════════════════════════════════════════════════════════════════


class TestIsGarbage:
    """The class-level garbage-word filter."""

    def test_flags_known_garbage(self):
        assert LinkParser._is_garbage("vmess://test1@host") is True
        assert LinkParser._is_garbage("vless://rootface@host") is True
        assert LinkParser._is_garbage("trojan://01010101@host") is True

    def test_clean_uri_passes(self):
        assert LinkParser._is_garbage("vless://valid-uuid@example.com:443") is False
        assert LinkParser._is_garbage("vmess://real-node") is False

    def test_case_insensitive(self):
        assert LinkParser._is_garbage("vless://TEST1@host") is True
        assert LinkParser._is_garbage("vless://RootFace@host") is True
