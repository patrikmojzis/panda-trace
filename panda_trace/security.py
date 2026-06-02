from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import secrets
from dataclasses import dataclass


CONTROL_SCOPES = {
    "orgs:write",
    "projects:write",
    "sources:read",
    "sources:write",
    "agents:write",
    "keys:write",
    "audit:read",
}

LOG_SCOPES = {
    "logs:write",
    "logs:read",
    "logs:tail",
    "logs:export",
}

ALL_SCOPES = CONTROL_SCOPES | LOG_SCOPES


@dataclass(frozen=True)
class SecretHash:
    salt: str
    digest: str
    iterations: int = 210_000


def make_api_key_secret(key_id: str) -> str:
    token = secrets.token_urlsafe(32)
    return f"ptk.{key_id}.{token}"


def extract_key_id(secret: str) -> str | None:
    parts = secret.split(".", 2)
    if len(parts) != 3 or parts[0] != "ptk":
        return None
    return parts[1]


def hash_secret(secret: str, *, iterations: int = 210_000) -> SecretHash:
    salt_bytes = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", secret.encode(), salt_bytes, iterations)
    return SecretHash(
        salt=base64.urlsafe_b64encode(salt_bytes).decode(),
        digest=base64.urlsafe_b64encode(digest).decode(),
        iterations=iterations,
    )


def verify_secret(secret: str, stored: SecretHash) -> bool:
    salt = base64.urlsafe_b64decode(stored.salt.encode())
    expected = base64.urlsafe_b64decode(stored.digest.encode())
    actual = hashlib.pbkdf2_hmac("sha256", secret.encode(), salt, stored.iterations)
    return hmac.compare_digest(actual, expected)


def ip_allowed(client_ip: str | None, allowlist: list[str]) -> bool:
    if not allowlist:
        return True
    if not client_ip:
        return False
    try:
        ip = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    for entry in allowlist:
        try:
            network = ipaddress.ip_network(entry, strict=False)
        except ValueError:
            continue
        if ip in network:
            return True
    return False
