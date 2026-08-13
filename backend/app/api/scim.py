from __future__ import annotations

import re
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ROLES, hash_api_token, new_api_token
from app.core.config import settings
from app.db import get_db
from app.models.app_user import AppUser
from app.services.sessions import revoke_all_user_sessions

router = APIRouter(prefix="/scim/v2", tags=["scim"])
_scim_bearer = HTTPBearer(auto_error=False)
SCIM_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
SCIM_GROUP_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Group"
SCIM_LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
SCIM_PATCH_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
_FILTER_RE = re.compile(r'^\s*(userName|externalId)\s+eq\s+"([^"]+)"\s*$', re.IGNORECASE)


def _scim_error(code: int, detail: str, scim_type: str | None = None) -> HTTPException:
    payload = {"schemas": ["urn:ietf:params:scim:api:messages:2.0:Error"], "status": str(code), "detail": detail}
    if scim_type:
        payload["scimType"] = scim_type
    return HTTPException(status_code=code, detail=payload)


async def require_scim(credentials: HTTPAuthorizationCredentials | None = Depends(_scim_bearer)) -> None:
    if not settings.scim_enabled:
        raise _scim_error(404, "SCIM is not enabled")
    configured = settings.scim_bearer_token
    if (
        not configured
        or credentials is None
        or credentials.scheme.lower() != "bearer"
        or not secrets.compare_digest(configured, credentials.credentials)
    ):
        raise _scim_error(401, "Invalid SCIM bearer token")


def _location(request: Request, resource: str, value: str) -> str:
    return f"{str(request.base_url).rstrip('/')}/scim/v2/{resource}/{value}"


def _group_id(role: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"booktranslate:role:{role}"))


def _role_for_group_id(group_id: str) -> str | None:
    return next((role for role in ROLES if _group_id(role) == group_id), None)


def _role_from_payload(payload: dict) -> str:
    roles = payload.get("roles") or []
    for item in roles:
        value = item.get("value") if isinstance(item, dict) else item
        if str(value) in ROLES:
            return str(value)
    groups = payload.get("groups") or []
    for item in groups:
        display = str((item or {}).get("display") or "") if isinstance(item, dict) else str(item)
        prefix = settings.scim_role_group_prefix
        if display.startswith(prefix) and display[len(prefix):] in ROLES:
            return display[len(prefix):]
    return settings.scim_default_role if settings.scim_default_role in ROLES else "viewer"


def _user_out(request: Request, user: AppUser) -> dict:
    return {
        "schemas": [SCIM_USER_SCHEMA],
        "id": str(user.id),
        "externalId": user.scim_external_id,
        "userName": user.email,
        "displayName": user.display_name,
        "active": user.is_active,
        "emails": [{"value": user.email, "primary": True, "type": "work"}],
        "roles": [{"value": user.role, "primary": True}],
        "groups": [
            {
                "value": _group_id(user.role),
                "display": f"{settings.scim_role_group_prefix}{user.role}",
                "$ref": _location(request, "Groups", _group_id(user.role)),
            }
        ],
        "meta": {
            "resourceType": "User",
            "created": user.created_at,
            "lastModified": user.updated_at,
            "location": _location(request, "Users", str(user.id)),
        },
    }


def _group_out(request: Request, role: str, members: list[AppUser]) -> dict:
    group_id = _group_id(role)
    return {
        "schemas": [SCIM_GROUP_SCHEMA],
        "id": group_id,
        "displayName": f"{settings.scim_role_group_prefix}{role}",
        "members": [
            {"value": str(user.id), "display": user.email, "$ref": _location(request, "Users", str(user.id))}
            for user in members
        ],
        "meta": {"resourceType": "Group", "location": _location(request, "Groups", group_id)},
    }


def _email(payload: dict) -> str:
    value = str(payload.get("userName") or "").strip().lower()
    if not value:
        for item in payload.get("emails") or []:
            if isinstance(item, dict) and item.get("value"):
                value = str(item["value"]).strip().lower()
                break
    if "@" not in value or value.startswith("@") or value.endswith("@"):
        raise _scim_error(400, "SCIM userName/email must be a valid email", "invalidValue")
    return value


@router.get("/ServiceProviderConfig", dependencies=[Depends(require_scim)])
async def service_provider_config() -> dict:
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
        "patch": {"supported": True},
        "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
        "filter": {"supported": True, "maxResults": 200},
        "changePassword": {"supported": False},
        "sort": {"supported": False},
        "etag": {"supported": False},
        "authenticationSchemes": [{"type": "oauthbearertoken", "name": "Bearer Token", "primary": True}],
    }


@router.get("/ResourceTypes", dependencies=[Depends(require_scim)])
async def resource_types(request: Request) -> dict:
    resources = [
        {"id": "User", "name": "User", "endpoint": "/Users", "schema": SCIM_USER_SCHEMA},
        {"id": "Group", "name": "Group", "endpoint": "/Groups", "schema": SCIM_GROUP_SCHEMA},
    ]
    return {"schemas": [SCIM_LIST_SCHEMA], "totalResults": len(resources), "startIndex": 1, "itemsPerPage": len(resources), "Resources": resources}


@router.get("/Schemas", dependencies=[Depends(require_scim)])
async def schemas() -> dict:
    rows = [
        {"id": SCIM_USER_SCHEMA, "name": "User", "description": "BookTranslate application user", "attributes": []},
        {"id": SCIM_GROUP_SCHEMA, "name": "Group", "description": "BookTranslate role group", "attributes": []},
    ]
    return {"schemas": [SCIM_LIST_SCHEMA], "totalResults": 2, "startIndex": 1, "itemsPerPage": 2, "Resources": rows}


@router.get("/Users", dependencies=[Depends(require_scim)])
async def list_scim_users(
    request: Request,
    filter_value: str | None = Query(default=None, alias="filter"),
    start_index: int = Query(default=1, alias="startIndex", ge=1),
    count: int = Query(default=100, ge=0, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict:
    query = select(AppUser)
    if filter_value:
        match = _FILTER_RE.match(filter_value)
        if not match:
            raise _scim_error(400, "Supported filters: userName eq or externalId eq", "invalidFilter")
        field, value = match.groups()
        if field.lower() == "username":
            query = query.where(AppUser.email == value.lower())
        else:
            query = query.where(AppUser.scim_external_id == value)
    rows = list((await db.execute(query.order_by(AppUser.created_at))).scalars().all())
    total = len(rows)
    selected = rows[start_index - 1:start_index - 1 + count]
    return {
        "schemas": [SCIM_LIST_SCHEMA],
        "totalResults": total,
        "startIndex": start_index,
        "itemsPerPage": len(selected),
        "Resources": [_user_out(request, row) for row in selected],
    }


@router.post("/Users", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_scim)])
async def create_scim_user(request: Request, payload: dict, db: AsyncSession = Depends(get_db)) -> dict:
    email = _email(payload)
    existing = (await db.execute(select(AppUser).where(AppUser.email == email))).scalar_one_or_none()
    if existing is not None:
        raise _scim_error(409, "User already exists", "uniqueness")
    external_id = str(payload.get("externalId") or "").strip() or None
    if external_id:
        duplicate = (await db.execute(select(AppUser).where(AppUser.scim_external_id == external_id))).scalar_one_or_none()
        if duplicate is not None:
            raise _scim_error(409, "externalId already exists", "uniqueness")
    hidden_token = new_api_token()
    user = AppUser(
        email=email,
        display_name=str(payload.get("displayName") or email).strip()[:200],
        role=_role_from_payload(payload),
        api_token_hash=hash_api_token(hidden_token),
        scim_external_id=external_id,
        scim_managed=True,
        is_active=bool(payload.get("active", True)),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _user_out(request, user)


@router.get("/Users/{user_id}", dependencies=[Depends(require_scim)])
async def get_scim_user(user_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    user = await db.get(AppUser, user_id)
    if user is None:
        raise _scim_error(404, "User not found")
    return _user_out(request, user)


async def _apply_user_payload(db: AsyncSession, user: AppUser, payload: dict) -> None:
    if "userName" in payload or "emails" in payload:
        email = _email(payload)
        duplicate = (
            await db.execute(select(AppUser).where(AppUser.email == email, AppUser.id != user.id))
        ).scalar_one_or_none()
        if duplicate is not None:
            raise _scim_error(409, "User email already exists", "uniqueness")
        user.email = email
    if "displayName" in payload:
        user.display_name = str(payload.get("displayName") or user.email).strip()[:200]
    if "externalId" in payload:
        external_id = str(payload.get("externalId") or "").strip() or None
        if external_id:
            duplicate = (
                await db.execute(select(AppUser).where(AppUser.scim_external_id == external_id, AppUser.id != user.id))
            ).scalar_one_or_none()
            if duplicate is not None:
                raise _scim_error(409, "externalId already exists", "uniqueness")
        user.scim_external_id = external_id
    if "roles" in payload or "groups" in payload:
        user.role = _role_from_payload(payload)
    if "active" in payload:
        was_active = user.is_active
        user.is_active = bool(payload.get("active"))
        if was_active and not user.is_active:
            await revoke_all_user_sessions(db, user_id=user.id)
    user.scim_managed = True


@router.put("/Users/{user_id}", dependencies=[Depends(require_scim)])
async def replace_scim_user(user_id: uuid.UUID, request: Request, payload: dict, db: AsyncSession = Depends(get_db)) -> dict:
    user = await db.get(AppUser, user_id)
    if user is None:
        raise _scim_error(404, "User not found")
    await _apply_user_payload(db, user, payload)
    await db.commit()
    await db.refresh(user)
    return _user_out(request, user)


@router.patch("/Users/{user_id}", dependencies=[Depends(require_scim)])
async def patch_scim_user(user_id: uuid.UUID, request: Request, payload: dict, db: AsyncSession = Depends(get_db)) -> dict:
    user = await db.get(AppUser, user_id)
    if user is None:
        raise _scim_error(404, "User not found")
    if SCIM_PATCH_SCHEMA not in (payload.get("schemas") or []):
        raise _scim_error(400, "PatchOp schema is required", "invalidSyntax")
    for operation in payload.get("Operations") or []:
        op = str(operation.get("op") or "").lower()
        path = str(operation.get("path") or "").strip()
        value = operation.get("value")
        if op not in {"add", "replace", "remove"}:
            raise _scim_error(400, f"Unsupported patch operation: {op}", "invalidSyntax")
        if not path and isinstance(value, dict):
            await _apply_user_payload(db, user, value)
        elif path.lower() == "active":
            user.is_active = False if op == "remove" else bool(value)
            if not user.is_active:
                await revoke_all_user_sessions(db, user_id=user.id)
        elif path.lower() == "displayname":
            user.display_name = user.email if op == "remove" else str(value or user.email).strip()[:200]
        elif path.lower() == "username":
            if op == "remove":
                raise _scim_error(400, "userName cannot be removed", "mutability")
            await _apply_user_payload(db, user, {"userName": value})
        elif path.lower() in {"roles", "groups"}:
            user.role = "viewer" if op == "remove" else _role_from_payload({path.lower(): value if isinstance(value, list) else [value]})
        else:
            raise _scim_error(400, f"Unsupported patch path: {path}", "invalidPath")
    user.scim_managed = True
    await db.commit()
    await db.refresh(user)
    return _user_out(request, user)


@router.delete("/Users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_scim)])
async def delete_scim_user(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    user = await db.get(AppUser, user_id)
    if user is None:
        raise _scim_error(404, "User not found")
    user.is_active = False
    user.scim_managed = True
    await revoke_all_user_sessions(db, user_id=user.id)
    await db.commit()


@router.get("/Groups", dependencies=[Depends(require_scim)])
async def list_scim_groups(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    users = list((await db.execute(select(AppUser).where(AppUser.is_active.is_(True)))).scalars().all())
    resources = [_group_out(request, role, [user for user in users if user.role == role]) for role in sorted(ROLES)]
    return {"schemas": [SCIM_LIST_SCHEMA], "totalResults": len(resources), "startIndex": 1, "itemsPerPage": len(resources), "Resources": resources}


@router.get("/Groups/{group_id}", dependencies=[Depends(require_scim)])
async def get_scim_group(group_id: str, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    role = _role_for_group_id(group_id)
    if role is None:
        raise _scim_error(404, "Group not found")
    users = list((await db.execute(select(AppUser).where(AppUser.role == role, AppUser.is_active.is_(True)))).scalars().all())
    return _group_out(request, role, users)


@router.patch("/Groups/{group_id}", dependencies=[Depends(require_scim)])
async def patch_scim_group(group_id: str, request: Request, payload: dict, db: AsyncSession = Depends(get_db)) -> dict:
    role = _role_for_group_id(group_id)
    if role is None:
        raise _scim_error(404, "Group not found")
    if SCIM_PATCH_SCHEMA not in (payload.get("schemas") or []):
        raise _scim_error(400, "PatchOp schema is required", "invalidSyntax")
    for operation in payload.get("Operations") or []:
        op = str(operation.get("op") or "").lower()
        values = operation.get("value") or []
        if isinstance(values, dict):
            values = [values]
        member_ids = []
        for item in values:
            if isinstance(item, dict) and item.get("value"):
                try:
                    member_ids.append(uuid.UUID(str(item["value"])))
                except ValueError:
                    raise _scim_error(400, "Invalid member id", "invalidValue")
        if op in {"add", "replace"}:
            for member_id in member_ids:
                user = await db.get(AppUser, member_id)
                if user is not None:
                    user.role = role
                    user.scim_managed = True
        elif op == "remove":
            for member_id in member_ids:
                user = await db.get(AppUser, member_id)
                if user is not None and user.role == role:
                    user.role = settings.scim_default_role if settings.scim_default_role in ROLES else "viewer"
                    user.scim_managed = True
        else:
            raise _scim_error(400, f"Unsupported group patch operation: {op}", "invalidSyntax")
    await db.commit()
    users = list((await db.execute(select(AppUser).where(AppUser.role == role, AppUser.is_active.is_(True)))).scalars().all())
    return _group_out(request, role, users)
