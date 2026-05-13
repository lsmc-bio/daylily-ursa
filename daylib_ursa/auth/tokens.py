from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from collections.abc import Callable

from daylib_ursa.auth.dependencies import AuthError, CurrentUser
from daylib_ursa.tapdb_graph import TapDBBackend, from_json_addl, utc_now_iso

USER_TOKEN_TEMPLATE = "RGX/auth/user-token/1.0/"
USER_TOKEN_USAGE_TEMPLATE = "RGX/auth/user-token-usage/1.0/"

USER_TOKEN_PREFIX = "urs_"
TOKEN_STATUS_ACTIVE = "ACTIVE"
TOKEN_STATUS_REVOKED = "REVOKED"


@dataclass(frozen=True)
class UserTokenRecord:
    token_euid: str
    owner_user_id: str
    token_name: str
    token_prefix: str
    scope: str
    status: str
    expires_at: str
    created_at: str
    updated_at: str
    created_by: str | None
    last_used_at: str | None
    revoked_at: str | None
    note: str | None
    client_registration_euid: str | None


@dataclass(frozen=True)
class UserTokenUsageRecord:
    usage_euid: str
    token_euid: str
    actor_user_id: str
    endpoint: str
    http_method: str
    response_status: int
    ip_address: str | None
    user_agent: str | None
    request_metadata: dict[str, Any]
    created_at: str


@dataclass(frozen=True)
class TokenValidationResult:
    actor: CurrentUser
    token: UserTokenRecord


def _iso_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _current_user_snapshot(current_user: CurrentUser) -> dict[str, Any]:
    return {
        "sub": current_user.sub,
        "email": current_user.email,
        "name": current_user.name,
        "tenant_id": str(current_user.tenant_id),
        "roles": list(current_user.roles),
    }


def _normalize_snapshot(snapshot: dict[str, Any]) -> CurrentUser:
    from uuid import UUID

    sub = str(snapshot.get("sub") or "").strip()
    tenant_value = str(snapshot.get("tenant_id") or "").strip()
    if not sub or not tenant_value:
        raise AuthError("Token snapshot is incomplete; reissue required")
    try:
        tenant_uuid = UUID(tenant_value)
    except ValueError as exc:
        raise AuthError("Token snapshot has invalid tenant_id; reissue required") from exc
    return CurrentUser(
        sub=sub,
        email=str(snapshot.get("email") or "").strip(),
        name=str(snapshot.get("name") or "").strip() or None,
        tenant_id=tenant_uuid,
        roles=[str(item) for item in list(snapshot.get("roles") or [])],
    )


class UserTokenService:
    def __init__(
        self,
        *,
        backend: TapDBBackend,
        user_lookup: Callable[[str], CurrentUser | None] | None = None,
    ) -> None:
        self.backend = backend
        self.user_lookup = user_lookup

    @staticmethod
    def generate_plaintext_token() -> str:
        return USER_TOKEN_PREFIX + secrets.token_hex(32)

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def display_prefix(token: str) -> str:
        return f"{token[:12]}..."

    def _token_record(self, token_instance) -> UserTokenRecord:
        token_payload = from_json_addl(token_instance)
        return UserTokenRecord(
            token_euid=str(token_instance.euid),
            owner_user_id=str(token_payload.get("owner_user_id") or ""),
            token_name=str(token_instance.name or token_payload.get("token_name") or ""),
            token_prefix=str(token_payload.get("token_prefix") or ""),
            scope=str(token_payload.get("scope") or "internal_ro"),
            status=str(token_payload.get("status") or ""),
            expires_at=str(token_payload.get("expires_at") or ""),
            created_at=str(token_payload.get("created_at") or utc_now_iso()),
            updated_at=str(
                token_payload.get("updated_at") or token_payload.get("created_at") or utc_now_iso()
            ),
            created_by=str(token_payload.get("created_by") or "").strip() or None,
            last_used_at=str(token_payload.get("last_used_at") or "").strip() or None,
            revoked_at=str(token_payload.get("revoked_at") or "").strip() or None,
            note=str(token_payload.get("note") or "").strip() or None,
            client_registration_euid=str(
                token_payload.get("client_registration_euid") or ""
            ).strip()
            or None,
        )

    def _resolve_owner_snapshot(self, *, actor: CurrentUser, owner_user_id: str) -> CurrentUser:
        owner = str(owner_user_id or "").strip()
        if owner == actor.sub:
            return actor
        if not actor.is_admin:
            raise AuthError("Cannot create tokens for another user")
        if self.user_lookup is None:
            raise AuthError("User lookup is required to create tokens for another user")
        resolved = self.user_lookup(owner)
        if resolved is None:
            raise AuthError(f"User not found for token creation: {owner}")
        return resolved

    def create_token(
        self,
        *,
        actor: CurrentUser,
        owner_user_id: str,
        token_name: str,
        scope: str,
        expires_in_days: int = 30,
        note: str | None = None,
        client_registration_euid: str | None = None,
    ) -> tuple[UserTokenRecord, str]:
        owner = str(owner_user_id or "").strip()
        if not owner:
            raise AuthError("owner_user_id is required")
        if client_registration_euid and not actor.is_admin:
            raise AuthError("Client-bound tokens require admin privileges")
        owner_user = self._resolve_owner_snapshot(actor=actor, owner_user_id=owner)
        expires_at = (
            (datetime.now(UTC) + timedelta(days=max(1, min(int(expires_in_days or 30), 3650))))
            .isoformat()
            .replace("+00:00", "Z")
        )
        plaintext = self.generate_plaintext_token()
        token_hash = self.hash_token(plaintext)
        token_prefix = self.display_prefix(plaintext)
        created_at = _iso_now()

        with self.backend.session_scope(commit=True) as session:
            token = self.backend.create_instance(
                session,
                USER_TOKEN_TEMPLATE,
                token_name.strip(),
                json_addl={
                    "owner_user_id": owner_user.sub,
                    "tenant_id": str(owner_user.tenant_id),
                    "user_snapshot": _current_user_snapshot(owner_user),
                    "token_name": token_name.strip(),
                    "token_prefix": token_prefix,
                    "token_hash": token_hash,
                    "scope": str(scope or "internal_ro").strip().lower() or "internal_ro",
                    "status": TOKEN_STATUS_ACTIVE,
                    "expires_at": expires_at,
                    "last_used_at": None,
                    "revoked_at": None,
                    "note": note,
                    "created_by": actor.sub,
                    "created_at": created_at,
                    "updated_at": created_at,
                    "client_registration_euid": str(client_registration_euid or "").strip() or None,
                },
                bstatus=TOKEN_STATUS_ACTIVE,
                tenant_id=owner_user.tenant_id,
            )
            return self._token_record(token), plaintext

    def list_tokens(
        self, *, actor: CurrentUser, owner_user_id: str | None = None
    ) -> list[UserTokenRecord]:
        target_owner = None if owner_user_id is None else str(owner_user_id).strip()
        if target_owner is None:
            target_owner = actor.sub
        if target_owner != actor.sub and not actor.is_admin:
            raise AuthError("Cannot list another user's tokens")
        with self.backend.session_scope(commit=False) as session:
            if actor.is_admin and target_owner == "*":
                tokens = self.backend.list_instances_by_template(
                    session,
                    template_code=USER_TOKEN_TEMPLATE,
                    limit=500,
                )
            else:
                tokens = self.backend.list_instances_by_property(
                    session,
                    template_code=USER_TOKEN_TEMPLATE,
                    key="owner_user_id",
                    value=target_owner,
                    limit=500,
                )
            return [self._token_record(token) for token in tokens]

    def revoke_token(
        self, *, actor: CurrentUser, token_euid: str, note: str | None = None
    ) -> UserTokenRecord:
        with self.backend.session_scope(commit=True) as session:
            token = self.backend.find_instance_by_euid(
                session,
                template_code=USER_TOKEN_TEMPLATE,
                value=token_euid,
                for_update=True,
            )
            if token is None:
                raise KeyError(f"token not found: {token_euid}")
            token_payload = from_json_addl(token)
            owner_user_id = str(token_payload.get("owner_user_id") or "")
            if owner_user_id != actor.sub and not actor.is_admin:
                raise AuthError("Cannot revoke another user's token")
            if str(token_payload.get("status") or "") == TOKEN_STATUS_REVOKED:
                return self._token_record(token)
            created_at = _iso_now()
            self.backend.update_instance_json(
                session,
                token,
                {
                    "status": TOKEN_STATUS_REVOKED,
                    "revoked_at": created_at,
                    "note": note or "revoked",
                    "updated_at": created_at,
                    "updated_by": actor.sub,
                },
            )
            token.bstatus = TOKEN_STATUS_REVOKED
            return self._token_record(token)

    def validate_token(self, plaintext_token: str) -> TokenValidationResult:
        token_value = str(plaintext_token or "").strip()
        if not token_value.startswith(USER_TOKEN_PREFIX):
            raise AuthError("Invalid Ursa token prefix")
        token_hash = self.hash_token(token_value)
        with self.backend.session_scope(commit=False) as session:
            token = self.backend.find_instance_by_external_id(
                session,
                template_code=USER_TOKEN_TEMPLATE,
                key="token_hash",
                value=token_hash,
            )
            if token is None:
                raise AuthError("Token not found")
            record = self._token_record(token)
            snapshot = from_json_addl(token).get("user_snapshot")
        if not hmac.compare_digest(self.hash_token(token_value), token_hash):
            raise AuthError("Token hash mismatch")
        if record.status == TOKEN_STATUS_REVOKED:
            raise AuthError("Token is revoked")
        expires_at = str(record.expires_at or "").strip()
        if expires_at:
            expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if expires_dt <= datetime.now(UTC):
                raise AuthError("Token is expired")
        if not isinstance(snapshot, dict):
            raise AuthError("Token snapshot missing; reissue required")
        actor = _normalize_snapshot(snapshot)
        return TokenValidationResult(actor=actor, token=record)

    def log_usage(
        self,
        *,
        token_euid: str,
        actor_user_id: str,
        endpoint: str,
        http_method: str,
        response_status: int,
        ip_address: str | None,
        user_agent: str | None,
        request_metadata: dict[str, Any] | None,
    ) -> None:
        with self.backend.session_scope(commit=True) as session:
            token = self.backend.find_instance_by_euid(
                session,
                template_code=USER_TOKEN_TEMPLATE,
                value=token_euid,
                for_update=True,
            )
            if token is None:
                return
            used_at = _iso_now()
            self.backend.update_instance_json(
                session,
                token,
                {
                    "last_used_at": used_at,
                    "updated_at": used_at,
                    "updated_by": actor_user_id,
                },
            )
            usage = self.backend.create_instance(
                session,
                USER_TOKEN_USAGE_TEMPLATE,
                f"usage:{token_euid}:{_iso_now()}",
                json_addl={
                    "token_euid": token_euid,
                    "actor_user_id": actor_user_id,
                    "endpoint": endpoint,
                    "http_method": http_method,
                    "response_status": int(response_status),
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                    "request_metadata": dict(request_metadata or {}),
                    "created_at": utc_now_iso(),
                },
                bstatus="LOGGED",
                tenant_id=token.tenant_id,
            )
            self.backend.create_lineage(
                session,
                parent=token,
                child=usage,
                relationship_type="usage",
            )

    def list_usage(self, *, actor: CurrentUser, token_euid: str) -> list[UserTokenUsageRecord]:
        with self.backend.session_scope(commit=False) as session:
            token = self.backend.find_instance_by_euid(
                session,
                template_code=USER_TOKEN_TEMPLATE,
                value=token_euid,
            )
            if token is None:
                raise KeyError(f"token not found: {token_euid}")
            record = self._token_record(token)
            if record.owner_user_id != actor.sub and not actor.is_admin:
                raise AuthError("Cannot inspect another user's token usage")
            usages = self.backend.list_children(
                session,
                parent=token,
                relationship_type="usage",
            )
            results: list[UserTokenUsageRecord] = []
            for usage in usages:
                payload = from_json_addl(usage)
                results.append(
                    UserTokenUsageRecord(
                        usage_euid=str(usage.euid),
                        token_euid=token_euid,
                        actor_user_id=str(payload.get("actor_user_id") or ""),
                        endpoint=str(payload.get("endpoint") or ""),
                        http_method=str(payload.get("http_method") or ""),
                        response_status=int(payload.get("response_status") or 0),
                        ip_address=str(payload.get("ip_address") or "").strip() or None,
                        user_agent=str(payload.get("user_agent") or "").strip() or None,
                        request_metadata=dict(payload.get("request_metadata") or {}),
                        created_at=str(payload.get("created_at") or utc_now_iso()),
                    )
                )
            results.sort(key=lambda row: row.created_at, reverse=True)
            return results
