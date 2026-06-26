"""
API key management endpoints.

POST   /v1/auth/keys          — create a new API key (returns raw key once)
GET    /v1/auth/keys          — list keys for authenticated customer
DELETE /v1/auth/keys/{key_id} — revoke a key

Bootstrap:
  The first key is created by passing `customer_id` in the request body with
  no Authorization header. Subsequent keys require a valid Bearer token.
  In production, the bootstrap endpoint should be rate-limited and tied to
  a registration / onboarding flow.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from api.deps import CustomerId, DbSession
from api.auth import create_api_key, list_api_keys, revoke_api_key, validate_api_key

router = APIRouter(prefix="/v1/auth", tags=["Auth"])

_bearer = HTTPBearer(auto_error=False)


# ── Schemas ────────────────────────────────────────────────────────────

class KeyCreateRequest(BaseModel):
    name:        str            = Field(..., min_length=1, max_length=100,
                                        description="Human label for this key")
    customer_id: Optional[str]  = Field(None,
                                        description="Required for first-time bootstrap "
                                                    "(no auth header). Ignored when a valid "
                                                    "Bearer token is present.")
    expires_at:  Optional[datetime] = Field(None, description="Optional expiry (ISO 8601)")


class KeyCreateResponse(BaseModel):
    key_id:      str
    customer_id: str
    name:        str
    key_prefix:  str
    raw_key:     str   = Field(description="Shown ONCE — store it securely")
    created_at:  str
    expires_at:  Optional[str]


class KeySummary(BaseModel):
    key_id:       str
    key_prefix:   str
    name:         str
    is_active:    bool
    created_at:   Optional[str]
    last_used_at: Optional[str]
    expires_at:   Optional[str]


class RevokeResponse(BaseModel):
    revoked: bool
    key_id:  str


# ── Endpoints ──────────────────────────────────────────────────────────

@router.post(
    "/keys",
    response_model=KeyCreateResponse,
    status_code=201,
    summary="Create API key",
    description=(
        "Creates a new API key. "
        "**First-time bootstrap**: no Authorization header required — pass `customer_id` "
        "in the request body. "
        "**Additional keys**: include `Authorization: Bearer <existing_key>` — "
        "`customer_id` in body is ignored. "
        "The `raw_key` field is returned **exactly once** — store it securely."
    ),
)
def create_key(
    body:        KeyCreateRequest,
    session:     DbSession,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
):
    # Resolve customer_id: from auth token if present, else from body (bootstrap)
    if credentials and credentials.credentials:
        auth_result = validate_api_key(session, credentials.credentials)
        if not auth_result:
            raise HTTPException(status_code=401, detail={
                "error":   "invalid_api_key",
                "message": "API key is invalid, revoked, or expired.",
            })
        resolved_customer_id = auth_result["customer_id"]
    else:
        # Bootstrap: customer_id must be in body and be a valid UUID
        if not body.customer_id:
            raise HTTPException(status_code=422, detail={
                "error":   "customer_id_required",
                "message": "Provide customer_id in the request body for first-time key creation, "
                           "or include Authorization: Bearer <key> header.",
            })
        try:
            uuid.UUID(body.customer_id)
        except ValueError:
            raise HTTPException(status_code=422, detail={
                "error":   "invalid_customer_id",
                "message": "customer_id must be a valid UUID.",
            })
        resolved_customer_id = body.customer_id

    result = create_api_key(
        session=session,
        customer_id=resolved_customer_id,
        name=body.name,
        expires_at=body.expires_at,
    )
    return KeyCreateResponse(**result)


@router.get(
    "/keys",
    response_model=list[KeySummary],
    summary="List API keys",
    description="List all API keys for the authenticated customer. Raw keys are never returned.",
)
def list_keys(customer_id: CustomerId, session: DbSession):
    return [KeySummary(**k) for k in list_api_keys(session, customer_id)]


@router.delete(
    "/keys/{key_id}",
    response_model=RevokeResponse,
    summary="Revoke API key",
    description="Permanently revoke an API key. Cannot be undone.",
)
def revoke_key(key_id: str, customer_id: CustomerId, session: DbSession):
    revoked = revoke_api_key(session, key_id=key_id, customer_id=customer_id)
    if not revoked:
        raise HTTPException(
            status_code=404,
            detail=f"Key {key_id} not found or already revoked.",
        )
    return RevokeResponse(revoked=True, key_id=key_id)
