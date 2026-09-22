import time
import logging
from fastapi import Request, HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.db import get_db

logger = logging.getLogger("8route.auth")
security = HTTPBearer(auto_error=False)

async def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(security)) -> dict:
    """
    Validate incoming client API Key (Bearer sk-8r-... or swf-live-...).
    Checks remain_quota, expiration, and status.
    """
    if not credentials:
        raise HTTPException(status_code=401, detail={"error": {"message": "Missing Authorization header", "type": "auth_error"}})
    
    raw_key = credentials.credentials
    # Strip optional 'sk-' or keep full key
    conn = get_db()
    
    # Try exact match or match without prefix
    token = conn.execute(
        "SELECT * FROM tokens WHERE (key = ? OR key = ?) AND status = 1",
        (raw_key, raw_key.replace("sk-", ""))
    ).fetchone()
    
    if not token:
        conn.close()
        raise HTTPException(status_code=401, detail={"error": {"message": "Invalid API token", "type": "auth_error"}})
    
    token_dict = dict(token)
    
    # Check expiration
    now = int(time.time())
    if token_dict["expires_at"] != -1 and now > token_dict["expires_at"]:
        conn.close()
        raise HTTPException(status_code=403, detail={"error": {"message": "API token has expired", "type": "quota_error"}})
    
    # Check quota
    if not token_dict["unlimited_quota"] and token_dict["remain_quota"] <= 0:
        conn.close()
        raise HTTPException(status_code=403, detail={"error": {"message": "Quota exceeded", "type": "quota_error"}})
    
    conn.close()
    return token_dict

def deduct_quota(token_id: int, total_tokens: int, model: str, provider_name: str, latency_ms: int, status_code: int = 200):
    """
    Deduct token quota and record usage log.
    """
    conn = get_db()
    try:
        # Deduct quota (1 token standard cost)
        conn.execute(
            "UPDATE tokens SET remain_quota = MAX(0, remain_quota - ?) WHERE id = ? AND unlimited_quota = 0",
            (total_tokens, token_id)
        )
        # Insert log
        conn.execute("""
            INSERT INTO usage_logs (token_id, model, provider_name, prompt_tokens, completion_tokens, latency_ms, status_code, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (token_id, model, provider_name, total_tokens, 0, latency_ms, status_code, int(time.time())))
        conn.commit()
    except Exception as e:
        logger.error(f"Error deducting quota for token {token_id}: {e}")
    finally:
        conn.close()
