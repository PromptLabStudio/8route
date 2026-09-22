import time
import httpx
import logging
from app.db import get_db

logger = logging.getLogger("8route.oauth")

async def refresh_antigravity_token(provider_id: int, refresh_token: str) -> str:
    """
    Auto-refresh Google OAuth token using the refresh_token.
    """
    token_url = "https://oauth2.googleapis.com/token"
    # Standard Google OAuth Client ID / Secret used for cloud SDK / antigravity
    # Or fallback to standard token refresh payload
    data = {
        "client_id": "764086051850-6qr4p6gpi6hn506pt8ejuq83di341hur.apps.googleusercontent.com",
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(token_url, data=data)
            if resp.status_code == 200:
                res_data = resp.json()
                new_access_token = res_data.get("access_token")
                expires_in = res_data.get("expires_in", 3599)
                expires_at = int(time.time()) + expires_in - 300 # refresh 5 min early
                
                # Update DB
                conn = get_db()
                conn.execute(
                    "UPDATE providers SET access_token = ?, token_expires_at = ? WHERE id = ?",
                    (new_access_token, expires_at, provider_id)
                )
                conn.commit()
                conn.close()
                logger.info(f"Refreshed Antigravity OAuth Token for provider ID {provider_id}")
                return new_access_token
            else:
                logger.error(f"Failed to refresh OAuth token for provider {provider_id}: {resp.text}")
                return ""
    except Exception as e:
        logger.error(f"OAuth refresh exception for provider {provider_id}: {e}")
        return ""

async def get_valid_provider_token(provider: dict) -> str:
    """
    Get token, auto-refreshing if it's an OAuth provider and expired.
    """
    p_type = provider.get("type")
    if p_type == "antigravity":
        now = int(time.time())
        expires_at = provider.get("token_expires_at", 0)
        access_token = provider.get("access_token")
        
        # If we have an access token and it hasn't expired, return it immediately
        if access_token and (expires_at == 0 or now < expires_at):
            return access_token
            
        # Try refreshing if expired or missing
        refresh_tok = provider.get("refresh_token")
        if refresh_tok:
            new_token = await refresh_antigravity_token(provider["id"], refresh_tok)
            if new_token:
                return new_token
                
        return access_token or ""
    
    # Standard API Key
    return provider.get("api_key") or provider.get("access_token") or ""
