import json
import time
import logging
import httpx
from fastapi import HTTPException
from app.db import get_db
from app.oauth import get_valid_provider_token

logger = logging.getLogger("8route.proxy")

async def forward_chat_completion(provider: dict, target_model: str, body: dict, stream: bool = False):
    """
    Forward OpenAI chat completion payload to upstream provider.
    Handles custom headers for Antigravity, OpenRouter, and standard endpoints.
    """
    token = await get_valid_provider_token(provider)
    if not token:
        raise HTTPException(status_code=502, detail=f"No valid auth token for provider {provider['name']}")
    
    p_type = provider["type"]
    base_url = provider.get("base_url") or "https://api.openai.com/v1"
    base_url = base_url.rstrip("/")
    
    # Construct target URL
    if p_type == "antigravity":
        # Antigravity upstream endpoint
        url = f"{base_url}/chat/completions" if "/v1" in base_url or "/chat" in base_url else f"{base_url}/v1/chat/completions"
    elif not base_url.endswith("/chat/completions"):
        url = f"{base_url}/chat/completions" if base_url.endswith("/v1") else f"{base_url}/v1/chat/completions"
    else:
        url = base_url

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    if p_type == "openrouter":
        headers["HTTP-Referer"] = "https://swiftlink.web.id"
        headers["X-Title"] = "8Route Gateway"
    elif p_type == "antigravity":
        headers["User-Agent"] = "8Route-Antigravity/1.0"
        if provider.get("project_id"):
            headers["x-goog-user-project"] = provider["project_id"]

    # Clone payload and swap model name to target model
    upstream_body = dict(body)
    upstream_body["model"] = target_model
    
    client = httpx.AsyncClient(timeout=60.0)
    
    if stream:
        req = client.build_request("POST", url, headers=headers, json=upstream_body)
        resp = await client.send(req, stream=True)
        if resp.status_code >= 400:
            err_body = await resp.aread()
            await client.aclose()
            raise HTTPException(status_code=resp.status_code, detail=err_body.decode(errors="ignore"))
        return resp, client
    else:
        async with client:
            resp = await client.post(url, headers=headers, json=upstream_body)
            if resp.status_code >= 400:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            return resp.json(), None
