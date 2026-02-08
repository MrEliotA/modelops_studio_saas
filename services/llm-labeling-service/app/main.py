from __future__ import annotations

from fastapi import APIRouter, Request
import asyncpg

from mlops_common.app_factory import create_app
from mlops_common.errors import ApiError

from .labeling import Rule, apply_rules

app = create_app("llm-labeling-service", enable_idempotency=True)
router = APIRouter(prefix="/api/v1")


@router.get("/healthz", include_in_schema=False)
async def healthz():
    return {"ok": True, "service": "llm-labeling-service"}


def _rule_from_payload(d: dict) -> Rule:
    name = str(d.get("name") or "").strip()
    label = str(d.get("label") or "").strip()
    keywords = d.get("keywords") or []
    if not name or not label:
        raise ApiError("BadRequest", "rule requires name and label", 400)
    if not isinstance(keywords, list):
        raise ApiError("BadRequest", "keywords must be a list", 400)
    keywords_str = [str(x) for x in keywords if str(x).strip()]
    return Rule(name=name, label=label, keywords=keywords_str, is_active=bool(d.get("is_active", True)))


@router.post("/labeling/rules", status_code=201)
async def create_rule(request: Request, payload: dict):
    t = request.state.tenancy
    rule = _rule_from_payload(payload)

    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                """INSERT INTO labeling_rules(tenant_id, project_id, name, label, keywords, is_active, created_by)
                   VALUES ($1,$2,$3,$4,$5,$6,$7)
                   RETURNING id, name, label, keywords, is_active, created_by, created_at, updated_at""",
                t.tenant_id, t.project_id, rule.name, rule.label, rule.keywords, rule.is_active, t.user_id,
            )
        except asyncpg.UniqueViolationError:
            raise ApiError("Conflict", "Rule name already exists", 409)
    return dict(row)


@router.get("/labeling/rules")
async def list_rules(request: Request):
    t = request.state.tenancy
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, name, label, keywords, is_active, created_by, created_at, updated_at
               FROM labeling_rules
               WHERE tenant_id=$1 AND project_id=$2
               ORDER BY created_at DESC""",
            t.tenant_id, t.project_id
        )
    return {"items": [dict(r) for r in rows]}


@router.patch("/labeling/rules/{rule_id}")
async def update_rule(request: Request, rule_id: str, payload: dict):
    t = request.state.tenancy
    fields = {}
    if "label" in payload:
        fields["label"] = str(payload.get("label") or "").strip()
    if "keywords" in payload:
        kw = payload.get("keywords")
        if not isinstance(kw, list):
            raise ApiError("BadRequest", "keywords must be a list", 400)
        fields["keywords"] = [str(x) for x in kw if str(x).strip()]
    if "is_active" in payload:
        fields["is_active"] = bool(payload.get("is_active"))

    if not fields:
        raise ApiError("BadRequest", "No fields to update", 400)

    sets = []
    args = [t.tenant_id, t.project_id, rule_id]
    idx = 4
    for k, v in fields.items():
        sets.append(f"{k}=${idx}")
        args.append(v)
        idx += 1

    q = "UPDATE labeling_rules SET " + ",".join(sets) + " WHERE tenant_id=$1 AND project_id=$2 AND id=$3 RETURNING id, name, label, keywords, is_active, created_by, created_at, updated_at"

    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        row = await conn.fetchrow(q, *args)
    if not row:
        raise ApiError("NotFound", "Rule not found", 404)
    return dict(row)


@router.delete("/labeling/rules/{rule_id}", status_code=204)
async def delete_rule(request: Request, rule_id: str):
    t = request.state.tenancy
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        res = await conn.execute(
            """DELETE FROM labeling_rules WHERE tenant_id=$1 AND project_id=$2 AND id=$3""",
            t.tenant_id, t.project_id, rule_id
        )
    # asyncpg returns e.g. 'DELETE 1'
    return None


async def _load_active_rules(request: Request) -> list[Rule]:
    t = request.state.tenancy
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT name, label, keywords, is_active
               FROM labeling_rules
               WHERE tenant_id=$1 AND project_id=$2 AND is_active=true""",
            t.tenant_id, t.project_id
        )
    out: list[Rule] = []
    for r in rows:
        out.append(Rule(name=r["name"], label=r["label"], keywords=list(r["keywords"] or []), is_active=bool(r["is_active"])))
    return out


@router.post("/labeling")
async def label_items(request: Request, payload: dict):
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise ApiError("BadRequest", "items must be a non-empty list", 400)

    rules_payload = payload.get("rules")
    if rules_payload is None:
        rules = await _load_active_rules(request)
    else:
        if not isinstance(rules_payload, list):
            raise ApiError("BadRequest", "rules must be a list", 400)
        rules = [_rule_from_payload(r) for r in rules_payload]

    top_n = int(payload.get("top_n", 3))
    top_n = max(1, min(top_n, 10))

    out_items = []
    for it in items:
        if isinstance(it, str):
            text = it
            item_id = None
        elif isinstance(it, dict):
            text = str(it.get("text") or "")
            item_id = it.get("id")
        else:
            continue

        res = apply_rules(text, rules, top_n=top_n)
        out_items.append({"id": item_id, "text": text, **res})

    return {"top_n": top_n, "rule_count": len(rules), "items": out_items}


app.include_router(router)
