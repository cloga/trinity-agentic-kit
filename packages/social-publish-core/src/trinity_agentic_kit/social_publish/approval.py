from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from .contracts import (
    EXECUTE_PUBLISH_CAPABILITY,
    SOCIAL_PUBLISH_SCHEMA_VERSION,
    ApprovalGrant,
    ApprovalGrantError,
    SocialPublishRequest,
    request_digest,
    stable_json,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def _encode_token_part(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_token_part(payload: str) -> bytes:
    padding = "=" * (-len(payload) % 4)
    try:
        return base64.b64decode(
            f"{payload}{padding}".encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, UnicodeEncodeError) as exc:
        raise ApprovalGrantError("Approval grant is malformed") from exc


class HmacApprovalAuthority:
    """Issue and verify short-lived approval grants bound to exact requests."""

    def __init__(
        self,
        secret: bytes,
        *,
        issuer: str = "social-publish",
        max_ttl_seconds: int = 900,
    ) -> None:
        if len(secret) < 32:
            raise ValueError("Approval secret must contain at least 32 bytes")
        if max_ttl_seconds <= 0:
            raise ValueError("Maximum approval TTL must be positive")
        self._secret = bytes(secret)
        self._issuer = str(issuer or "").strip()
        self._max_ttl_seconds = max_ttl_seconds
        if not self._issuer:
            raise ValueError("Approval issuer is required")

    def issue(
        self,
        request: SocialPublishRequest,
        *,
        grant_id: str,
        ttl_seconds: int = 300,
        capabilities: tuple[str, ...] = (EXECUTE_PUBLISH_CAPABILITY,),
        now: datetime | None = None,
    ) -> str:
        if ttl_seconds <= 0 or ttl_seconds > self._max_ttl_seconds:
            raise ValueError(
                f"Approval TTL must be between 1 and {self._max_ttl_seconds} seconds"
            )
        normalized_grant_id = str(grant_id or "").strip()
        if not normalized_grant_id:
            raise ValueError("grant_id is required")
        issued_at = (now or utc_now()).astimezone(timezone.utc)
        grant = ApprovalGrant(
            grant_id=normalized_grant_id,
            request_id=request.request_id,
            platform=request.platform,
            idempotency_key=request.idempotency_key,
            request_digest=request_digest(request),
            capabilities=tuple(sorted(set(capabilities))),
            issued_at=iso_utc(issued_at),
            expires_at=iso_utc(issued_at + timedelta(seconds=ttl_seconds)),
            issuer=self._issuer,
        )
        payload = stable_json(asdict(grant))
        signature = hmac.new(self._secret, payload, hashlib.sha256).digest()
        return f"{_encode_token_part(payload)}.{_encode_token_part(signature)}"

    def verify(
        self,
        token: str,
        request: SocialPublishRequest,
        *,
        capability: str = EXECUTE_PUBLISH_CAPABILITY,
        now: datetime | None = None,
    ) -> ApprovalGrant:
        try:
            payload_part, signature_part = str(token or "").split(".", 1)
        except ValueError as exc:
            raise ApprovalGrantError("Approval grant is malformed") from exc
        payload = _decode_token_part(payload_part)
        signature = _decode_token_part(signature_part)
        expected = hmac.new(self._secret, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise ApprovalGrantError("Approval grant signature is invalid")

        grant = self._parse_grant(payload)
        if (
            grant.schema_version != SOCIAL_PUBLISH_SCHEMA_VERSION
            or grant.issuer != self._issuer
        ):
            raise ApprovalGrantError("Approval grant authority is invalid")
        if (
            grant.request_id != request.request_id
            or grant.platform != request.platform
            or grant.idempotency_key != request.idempotency_key
            or grant.request_digest != request_digest(request)
        ):
            raise ApprovalGrantError(
                "Approval grant does not match the publish request"
            )
        if capability not in grant.capabilities:
            raise ApprovalGrantError(f"Approval grant lacks capability: {capability}")

        issued_at = self._parse_timestamp(grant.issued_at)
        expires_at = self._parse_timestamp(grant.expires_at)
        if expires_at <= issued_at:
            raise ApprovalGrantError("Approval grant expiry is invalid")
        if expires_at - issued_at > timedelta(seconds=self._max_ttl_seconds):
            raise ApprovalGrantError("Approval grant lifetime is too long")
        current = (now or utc_now()).astimezone(timezone.utc)
        if current < issued_at:
            raise ApprovalGrantError("Approval grant is not active yet")
        if current >= expires_at:
            raise ApprovalGrantError("Approval grant has expired")
        return grant

    @staticmethod
    def _parse_grant(payload: bytes) -> ApprovalGrant:
        try:
            raw_object: object = json.loads(payload.decode("utf-8"))
            if not isinstance(raw_object, dict):
                raise ApprovalGrantError("Approval grant payload is invalid")
            raw = cast(dict[str, Any], raw_object)
            capabilities = raw["capabilities"]
            if not isinstance(capabilities, list):
                raise ApprovalGrantError("Approval grant capabilities are invalid")
            capability_objects = cast(list[object], capabilities)
            if not all(isinstance(item, str) for item in capability_objects):
                raise ApprovalGrantError("Approval grant capabilities are invalid")
            capability_values = cast(list[str], capability_objects)
            return ApprovalGrant(
                grant_id=str(raw["grant_id"]),
                request_id=str(raw["request_id"]),
                platform=str(raw["platform"]),
                idempotency_key=str(raw["idempotency_key"]),
                request_digest=str(raw["request_digest"]),
                capabilities=tuple(capability_values),
                issued_at=str(raw["issued_at"]),
                expires_at=str(raw["expires_at"]),
                issuer=str(raw["issuer"]),
                schema_version=int(raw["schema_version"]),
            )
        except (
            KeyError,
            TypeError,
            ValueError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise ApprovalGrantError("Approval grant payload is invalid") from exc

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ApprovalGrantError("Approval grant timestamps are invalid") from exc
        if parsed.tzinfo is None:
            raise ApprovalGrantError("Approval grant timestamps must include UTC")
        return parsed.astimezone(timezone.utc)
