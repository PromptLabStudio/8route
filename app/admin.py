import sqlite3
import time
import uuid
import logging
import json
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from app.db import get_db
from app.auth import verify_api_key

router = APIRouter(prefix="/api/admin", tags=["Admin"])
logger = logging.getLogger("8route.admin")

# --- Pydantic Models ---
class ProviderCreate(BaseModel):
    name: str
    type: str # 'openai_compatible', 'openrouter', 'mistral', 'antigravity'
    base_url: Optional[str] = ""
    api_key: Optional[str] = ""
    refresh_token: Optional[str] = ""
    project_id: Optional[str] = ""

class ProviderUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    refresh_token: Optional[str] = None
    project_id: Optional[str] = None
    is_active: Optional[int] = None

class ComboStep(BaseModel):
    provider_id: int
    model: str

class ComboCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    pipeline: List[ComboStep]

class TokenCreate(BaseModel):
    name: str
    remain_quota: int = 5000000
    unlimited_quota: bool = False
    models_allowed: str = "*"
    expires_in_days: int = 30

class TokenUpdate(BaseModel):
    name: Optional[str] = None
    remain_quota: Optional[int] = None
    unlimited_quota: Optional[bool] = None
    models_allowed: Optional[str] = None
    status: Optional[int] = None

# --- Analytics & Dashboard Stats ---
@router.get("/stats")
def get_dashboard_stats(user: dict = Depends(verify_api_key)):
    conn = get_db()
    total_tokens = conn.execute("SELECT count(*) FROM tokens").fetchone()[0]
    total_providers = conn.execute("SELECT count(*) FROM providers WHERE is_active = 1").fetchone()[0]
    total_combos = conn.execute("SELECT count(*) FROM combos WHERE is_active = 1").fetchone()[0]
    total_requests = conn.execute("SELECT count(*) FROM usage_logs").fetchone()[0]
    
    # Calculate total tokens consumed
    total_consumed = conn.execute("SELECT COALESCE(SUM(prompt_tokens + completion_tokens), 0) FROM usage_logs").fetchone()[0]
    
    # Average Latency
    avg_latency = conn.execute("SELECT COALESCE(AVG(latency_ms), 0) FROM usage_logs WHERE status_code = 200").fetchone()[0]
    
    # Hourly distribution for charts (last 24 hours)
    now = int(time.time())
    day_ago = now - 86400
    hourly_logs = conn.execute("""
        SELECT strftime('%H:00', datetime(created_at, 'unixepoch', 'localtime')) as hour, count(*) as count
        FROM usage_logs
        WHERE created_at >= ?
        GROUP BY hour
        ORDER BY created_at ASC
    """, (day_ago,)).fetchall()

    recent_logs = conn.execute("""
        SELECT l.*, t.name as token_name FROM usage_logs l
        LEFT JOIN tokens t ON l.token_id = t.id
        ORDER BY l.id DESC LIMIT 50
    """).fetchall()
    
    conn.close()
    return {
        "stats": {
            "total_tokens": total_tokens,
            "total_providers": total_providers,
            "total_combos": total_combos,
            "total_requests": total_requests,
            "total_consumed_tokens": total_consumed,
            "avg_latency_ms": int(avg_latency)
        },
        "chart_data": [dict(r) for r in hourly_logs],
        "recent_logs": [dict(r) for r in recent_logs]
    }

# --- Tokens / API Keys Management ---
@router.get("/tokens")
def list_tokens(user: dict = Depends(verify_api_key)):
    conn = get_db()
    tokens = conn.execute("SELECT * FROM tokens ORDER BY id DESC").fetchall()
    conn.close()
    return {"tokens": [dict(t) for t in tokens]}

@router.post("/tokens")
def create_token(payload: TokenCreate, user: dict = Depends(verify_api_key)):
    conn = get_db()
    raw_key = f"sk-8r-{uuid.uuid4().hex}"
    expires_at = -1 if payload.expires_in_days == -1 else int(time.time()) + (payload.expires_in_days * 86400)
    
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO tokens (key, name, remain_quota, unlimited_quota, models_allowed, status, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, 1, ?, ?)
    """, (raw_key, payload.name, payload.remain_quota, 1 if payload.unlimited_quota else 0, payload.models_allowed, int(time.time()), expires_at))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {"success": True, "id": new_id, "key": raw_key, "name": payload.name}

@router.patch("/tokens/{token_id}")
def update_token(token_id: int, payload: TokenUpdate, user: dict = Depends(verify_api_key)):
    conn = get_db()
    fields = []
    values = []
    if payload.name is not None:
        fields.append("name = ?")
        values.append(payload.name)
    if payload.remain_quota is not None:
        fields.append("remain_quota = ?")
        values.append(payload.remain_quota)
    if payload.unlimited_quota is not None:
        fields.append("unlimited_quota = ?")
        values.append(1 if payload.unlimited_quota else 0)
    if payload.models_allowed is not None:
        fields.append("models_allowed = ?")
        values.append(payload.models_allowed)
    if payload.status is not None:
        fields.append("status = ?")
        values.append(payload.status)

    if fields:
        values.append(token_id)
        conn.execute(f"UPDATE tokens SET {', '.join(fields)} WHERE id = ?", tuple(values))
        conn.commit()
    conn.close()
    return {"success": True}

@router.delete("/tokens/{token_id}")
def delete_token(token_id: int, user: dict = Depends(verify_api_key)):
    conn = get_db()
    conn.execute("DELETE FROM tokens WHERE id = ?", (token_id,))
    conn.commit()
    conn.close()
    return {"success": True}

# --- Providers Management ---
@router.get("/providers")
def list_providers(user: dict = Depends(verify_api_key)):
    conn = get_db()
    providers = conn.execute("SELECT id, name, type, base_url, project_id, is_active, token_expires_at FROM providers ORDER BY id ASC").fetchall()
    conn.close()
    return {"providers": [dict(p) for p in providers]}

@router.post("/providers")
def create_provider(payload: ProviderCreate, user: dict = Depends(verify_api_key)):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO providers (name, type, base_url, api_key, refresh_token, project_id, is_active, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?)
    """, (payload.name, payload.type, payload.base_url, payload.api_key, payload.refresh_token, payload.project_id, int(time.time())))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {"success": True, "id": new_id}

@router.patch("/providers/{provider_id}")
def update_provider(provider_id: int, payload: ProviderUpdate, user: dict = Depends(verify_api_key)):
    conn = get_db()
    fields = []
    values = []
    for field, val in payload.dict(exclude_unset=True).items():
        if val is not None:
            fields.append(f"{field} = ?")
            values.append(val)
    if fields:
        values.append(provider_id)
        conn.execute(f"UPDATE providers SET {', '.join(fields)} WHERE id = ?", tuple(values))
        conn.commit()
    conn.close()
    return {"success": True}

@router.delete("/providers/{provider_id}")
def delete_provider(provider_id: int, user: dict = Depends(verify_api_key)):
    conn = get_db()
    conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
    conn.commit()
    conn.close()
    return {"success": True}

# --- Combos (Virtual Fallback Pipeline) Management ---
@router.get("/combos")
def list_combos(user: dict = Depends(verify_api_key)):
    conn = get_db()
    combos = conn.execute("SELECT * FROM combos ORDER BY id ASC").fetchall()
    providers = {p["id"]: p["name"] for p in conn.execute("SELECT id, name FROM providers").fetchall()}
    conn.close()
    
    result = []
    for c in combos:
        cdict = dict(c)
        try:
            pipeline = json.loads(cdict["pipeline"])
            for step in pipeline:
                step["provider_name"] = providers.get(step.get("provider_id"), "Unknown")
            cdict["pipeline_details"] = pipeline
        except Exception:
            cdict["pipeline_details"] = []
        result.append(cdict)
    return {"combos": result}

@router.post("/combos")
def create_combo(payload: ComboCreate, user: dict = Depends(verify_api_key)):
    conn = get_db()
    pipeline_json = json.dumps([s.dict() for s in payload.pipeline])
    conn.execute("""
        INSERT OR REPLACE INTO combos (name, description, pipeline, is_active, created_at)
        VALUES (?, ?, ?, 1, ?)
    """, (payload.name, payload.description, pipeline_json, int(time.time())))
    conn.commit()
    conn.close()
    return {"success": True, "name": payload.name}

@router.delete("/combos/{combo_id}")
def delete_combo(combo_id: int, user: dict = Depends(verify_api_key)):
    conn = get_db()
    conn.execute("DELETE FROM combos WHERE id = ?", (combo_id,))
    conn.commit()
    conn.close()
    return {"success": True}
