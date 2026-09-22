import json
import logging
from app.db import get_db

logger = logging.getLogger("8route.router")

def resolve_model_pipeline(requested_model: str) -> list:
    """
    Resolve requested model into an execution pipeline:
    1. If requested model is a Combo (e.g. '8r-flagship', 'hermes-wa'), return its pipeline list.
    2. If it's a direct provider/model (e.g. 'openrouter/deepseek/deepseek-chat'), match provider.
    3. If it's a generic model name (e.g. 'gpt-4o'), find all providers offering it.
    """
    conn = get_db()
    
    # 1. Check Combo table
    combo = conn.execute("SELECT pipeline FROM combos WHERE name = ? AND is_active = 1", (requested_model,)).fetchone()
    if combo:
        try:
            pipeline = json.loads(combo["pipeline"])
            resolved = []
            for item in pipeline:
                pid = item.get("provider_id")
                target_m = item.get("model")
                p = conn.execute("SELECT * FROM providers WHERE id = ? AND is_active = 1", (pid,)).fetchone()
                if p:
                    resolved.append({
                        "provider": dict(p),
                        "model": target_m
                    })
            conn.close()
            return resolved
        except Exception as e:
            logger.error(f"Error parsing combo pipeline for {requested_model}: {e}")

    # 2. Check direct prefix matching (e.g. 'openrouter/...')
    if "/" in requested_model:
        prefix, *rest = requested_model.split("/", 1)
        sub_model = rest[0]
        p = conn.execute("SELECT * FROM providers WHERE (type = ? OR name LIKE ?) AND is_active = 1", (prefix, f"%{prefix}%")).fetchone()
        if p:
            conn.close()
            return [{"provider": dict(p), "model": sub_model}]

    # 3. Default: search all active providers
    providers = conn.execute("SELECT * FROM providers WHERE is_active = 1").fetchall()
    conn.close()
    
    resolved = []
    for p in providers:
        resolved.append({
            "provider": dict(p),
            "model": requested_model
        })
    return resolved
