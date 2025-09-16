import json
import os
import sqlite3
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import httpx
from pydantic import BaseModel
from kouroshai.core.config import DB_PATH, DEFAULT_MODEL, OLLAMA_HOST
from kouroshai.modules.codegen.service import get_gpt4o_response, stream_gpt4o_response
from kouroshai.utils.text_utils import clean_code_response, validate_code
from .service import chat_response
from kouroshai.core.database import get_db_connection
from .service import chat_response, route_llm
import logging

router = APIRouter(prefix="/chat", tags=["chat"])
# DEFAULT_MODEL = os.getenv("DEFAULT_OLLAMA_MODEL", "llama3.2:3b")

logger = logging.getLogger(__name__)

class ChatRequest(BaseModel):
    message: str
    model: str = None

# @router.post("")
# async def chat_endpoint(req: ChatRequest):
#     response, used_model = chat_response(req.message, req.model)
#     return {"response": response, "model": used_model}

@router.post("")
async def chat(req: ChatRequest):
    """Handle general chat requests with model routing."""
    try:
        # ensure DB directory exists and use centralized connection helper
        db_dir = os.path.dirname(DB_PATH)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT model FROM code_snippets WHERE code != ''")
        available_models = [row[0] for row in cursor.fetchall()]
        conn.close()

        message = req.message
        if not message:
            raise HTTPException(status_code=400, detail="Message or prompt is required")

        model = req.model if req.model else route_llm(message, available_models)
        logger.info("Routing to model: %s", model)

        if model == DEFAULT_MODEL:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(f"{OLLAMA_HOST}/api/generate", json={
                    "model": model,
                    "prompt": message,
                    "stream": False
                })
                if response.status_code != 200:
                    logger.error("Ollama API error: %s", response.status_code)
                    raise HTTPException(status_code=response.status_code, detail="Error from Ollama API")
                data = response.json()
                response_text = clean_code_response(data.get("response", ""))
                if not response_text:
                    logger.error("Empty response from %s", model)
                    raise HTTPException(status_code=500, detail=f"Empty response from {model}")
                if "code" in message.lower() or "python" in message.lower():
                    is_valid = validate_code(response_text)
                    logger.info("Code validation result: %s", is_valid)
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO code_snippets (prompt, code, model) VALUES (?, ?, ?)",
                                  (message, response_text, model))
                    conn.commit()
                    snippet_id = cursor.lastrowid
                    conn.close()
                    if not is_valid:
                        return {"response": response_text, "model": model, "snippet_id": snippet_id, "warning": "Code may contain syntax errors, check invalid_code.log"}
                return {"response": response_text, "model": model}
        else:
            code, error = await get_gpt4o_response(message, model)
            if error:
                logger.error("GitHub Models error: %s", error)
                raise HTTPException(status_code=500, detail=f"GitHub Models error: {error}")
            if not code:
                logger.error("Empty response from %s", model)
                raise HTTPException(status_code=500, detail=f"Empty response from {model}")
            response_text = clean_code_response(code.strip())
            if "code" in message.lower() or "python" in message.lower():
                is_valid = validate_code(response_text)
                logger.info("Code validation result: %s", is_valid)
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("INSERT INTO code_snippets (prompt, code, model) VALUES (?, ?, ?)",
                              (message, response_text, model))
                conn.commit()
                snippet_id = cursor.lastrowid
                conn.close()
                if not is_valid:
                    return {"response": response_text, "model": model, "snippet_id": snippet_id, "warning": "Code may contain syntax errors, check invalid_code.log"}
            return {"response": response_text, "model": model}
    except Exception as e:
        logger.error("Chat error: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")

@router.post("/chat-stream")
async def chat_stream(req: ChatRequest):
    """Stream responses with model routing."""
    async def stream():
        try:
            # conn = sqlite3.connect(DB_PATH)
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT model FROM code_snippets WHERE code != ''")
            available_models = [row[0] for row in cursor.fetchall()]
            conn.close()
            message = req.message
            if not message:
                yield f"data: {{\"error\": \"Message or prompt is required\"}}\n\n"
                return
            model = req.model if req.model else route_llm(message, available_models)
            logger.info("Streaming with model: %s", model)

            if model == DEFAULT_MODEL:
                async with httpx.AsyncClient(timeout=None) as client:
                    async with client.stream("POST", f"{OLLAMA_HOST}/api/generate", json={
                        "model": model,
                        "prompt": message,
                        "stream": True
                    }) as response:
                        if response.status_code != 200:
                            yield f"data: {{\"error\": \"Error from Ollama API: {response.status_code}\"}}\n\n"
                            return
                        result = ""
                        async for line in response.aiter_lines():
                            if line.strip():
                                data = json.loads(line)
                                if data.get("response"):
                                    content = clean_code_response(data["response"])
                                    if content:
                                        result += content
                                        yield f"data: {{\"response\": \"{content.replace('"', '\\"')}\", \"model\": \"{model}\"}}\n\n"
                                if data.get("done"):
                                    if "code" in message.lower() or "python" in message.lower() and result:
                                        is_valid = validate_code(result)
                                        logger.info("Code validation result: %s", is_valid)
                                        conn = get_db_connection()
                                        cursor = conn.cursor()
                                        cursor.execute("INSERT INTO code_snippets (prompt, code, model) VALUES (?, ?, ?)",
                                                      (message, result, model))
                                        conn.commit()
                                        snippet_id = cursor.lastrowid
                                        conn.close()
                                        if not is_valid:
                                            yield f"data: {{\"warning\": \"Code may contain syntax errors, check invalid_code.log\", \"snippet_id\": {snippet_id}}}\n\n"
                                    break
            else:
                result = ""
                async for chunk in stream_gpt4o_response(message, model):
                    if isinstance(chunk, str) and chunk:
                        content = clean_code_response(chunk)
                        if content:
                            result += content
                            yield f"data: {{\"response\": \"{content.replace('"', '\\"')}\", \"model\": \"{model}\"}}\n\n"
                    else:
                        logger.error("Invalid chunk received: %s", chunk)
                        yield f"data: {{\"error\": \"Invalid chunk: {str(chunk).replace('"', '\\"')}\"}}\n\n"
                if result and ("code" in message.lower() or "python" in message.lower()):
                    is_valid = validate_code(result)
                    logger.info("Code validation result: %s", is_valid)
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO code_snippets (prompt, code, model) VALUES (?, ?, ?)",
                                  (message, result, model))
                    conn.commit()
                    snippet_id = cursor.lastrowid
                    conn.close()
                    if not is_valid:
                        yield f"data: {{\"warning\": \"Code may contain syntax errors, check invalid_code.log\", \"snippet_id\": {snippet_id}}}\n\n"
        except Exception as e:
            logger.error("Stream error: %s", str(e))
            yield f"data: {{\"error\": \"{str(e).replace('"', '\\"')}\"}}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")