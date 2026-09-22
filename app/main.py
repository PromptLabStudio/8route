import time
import json
import logging
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.db import init_db, get_db
from app.auth import verify_api_key, deduct_quota
from app.router import resolve_model_pipeline
from app.proxy import forward_chat_completion
from app.admin import router as admin_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("8route.main")

app = FastAPI(title="8Route AI Gateway", version="1.0.0")

# Include Admin Router
app.include_router(admin_router)

# Mount Static Files
app.mount("/static", StaticFiles(directory="/home/ubuntu/8route/static"), name="static")

@app.get("/")
def serve_dashboard():
    return FileResponse("/home/ubuntu/8route/static/index.html")

# CORS middleware for Web Dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    init_db()
    logger.info("8Route AI Gateway Initialized.")

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "8Route", "version": "1.0.0"}

@app.get("/v1/models")
def list_models(user_token: dict = Depends(verify_api_key)):
    conn = get_db()
    # Return combos + default models
    combos = conn.execute("SELECT name FROM combos WHERE is_active = 1").fetchall()
    conn.close()
    
    data = []
    for c in combos:
        data.append({"id": c["name"], "object": "model", "owned_by": "8route"})
    
    # Common model aliases
    standard_models = [
        "claude-3.5-sonnet", "gpt-4o", "gpt-4o-mini",
        "deepseek-chat", "deepseek-r1", "codestral-latest", "llama-3.3-70b"
    ]
    for sm in standard_models:
        data.append({"id": sm, "object": "model", "owned_by": "upstream"})
        
    return {"object": "list", "data": data}

@app.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    user_token: dict = Depends(verify_api_key)
):
    body = await request.json()
    model = body.get("model", "8r-flagship")
    stream = body.get("stream", False)
    
    pipeline = resolve_model_pipeline(model)
    if not pipeline:
        raise HTTPException(
            status_code=404,
            detail={"error": {"message": f"Model '{model}' is not available or has no active upstream providers", "type": "model_error"}}
        )
    
    start_time = time.time()
    last_error = None
    
    # Loop through priority pipeline until one succeeds (Smart Failover)
    for step in pipeline:
        provider = step["provider"]
        target_model = step["model"]
        
        try:
            logger.info(f"Routing request [{model}] -> Provider: {provider['name']} ({target_model})")
            
            if stream:
                upstream_resp, client = await forward_chat_completion(provider, target_model, body, stream=True)
                
                async def stream_generator():
                    try:
                        async for chunk in upstream_resp.aiter_bytes():
                            yield chunk
                    finally:
                        await upstream_resp.aclose()
                        if client:
                            await client.aclose()
                        latency_ms = int((time.time() - start_time) * 1000)
                        deduct_quota(user_token["id"], 50, model, provider["name"], latency_ms)
                
                return StreamingResponse(
                    stream_generator(),
                    media_type=upstream_resp.headers.get("content-type", "text/event-stream")
                )
            else:
                resp_json, _ = await forward_chat_completion(provider, target_model, body, stream=False)
                latency_ms = int((time.time() - start_time) * 1000)
                
                # Calculate tokens used
                total_tokens = 100
                if isinstance(resp_json, dict):
                    usage = resp_json.get("usage", {})
                    total_tokens = usage.get("total_tokens", 100)
                deduct_quota(user_token["id"], total_tokens, model, provider["name"], latency_ms)
                
                return JSONResponse(content=resp_json)
                
        except Exception as e:
            last_error = str(e)
            logger.warning(f"Provider {provider['name']} failed for model {target_model}: {e}. Trying next in pipeline...")
            continue
            
    # All providers in pipeline failed
    raise HTTPException(
        status_code=502,
        detail={"error": {"message": f"All upstream providers failed. Last error: {last_error}", "type": "upstream_error"}}
    )
