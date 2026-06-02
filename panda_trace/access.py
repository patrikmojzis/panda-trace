from __future__ import annotations

from panda_trace.errors import not_found, permission_denied
from panda_trace.models import ApiKeyRecord, AuthContext, LogRecord


def require_key_org(key: ApiKeyRecord, org_id: str) -> None:
    if org_id != key.org_id:
        raise permission_denied("API key cannot access this org.")


def require_auth_org(auth: AuthContext, org_id: str, org_exists: bool) -> None:
    require_key_org(auth.key, org_id)
    if not org_exists:
        raise not_found("Org")


def project_allowed(key: ApiKeyRecord, project_id: str) -> bool:
    return not key.project_ids or project_id in key.project_ids


def source_allowed(key: ApiKeyRecord, source_id: str) -> bool:
    return not key.source_ids or source_id in key.source_ids


def assert_log_read_allowed(key: ApiKeyRecord, record: LogRecord) -> None:
    if record.org_id != key.org_id:
        raise not_found("Log")
    if not project_allowed(key, record.project_id):
        raise permission_denied("API key cannot read logs for this project.")
    if not source_allowed(key, record.source_id):
        raise permission_denied("API key cannot read logs for this source.")


def assert_log_write_allowed(key: ApiKeyRecord, record: LogRecord) -> None:
    if record.org_id != key.org_id:
        raise not_found("Log")
    if not project_allowed(key, record.project_id):
        raise permission_denied("API key cannot write logs for this project.")
    if not source_allowed(key, record.source_id):
        raise permission_denied("API key cannot write logs for this source.")
