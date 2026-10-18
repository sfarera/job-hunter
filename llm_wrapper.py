import asyncio
import json
import os
import re
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv()


async def generate_action(prompt: str) -> Optional[list[dict[str, Any]]]:
    """
    Calls the configured LLM and returns parsed JSON actions.
    The form agent is DOM-first, so this wrapper is text-only by design.
    """
    raw_provider = os.getenv("AI", "gemini").lower()
    ai_provider = re.sub(r'[^a-z]', '', raw_provider)

    if ai_provider in ("cursor", "openai", "openrouter"):
        result = await _call_cursor(prompt)
        if result is None:
            print("  Falling back to Gemini...")
            result = await _call_gemini(prompt)
            if result is None:
                claude_key = os.getenv("ANTHROPIC_API_KEY", "")
                if claude_key and not claude_key.startswith("your_"):
                    print("  Falling back to Claude...")
                    result = await _call_claude(prompt)
    elif ai_provider == "claude":
        result = await _call_claude(prompt)
        if result is None:
            print("  Falling back to Gemini...")
            result = await _call_gemini(prompt)
    else:
        result = await _call_gemini(prompt)
        if result is None:
            cursor_key = os.getenv("CURSOR_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
            if cursor_key and not cursor_key.startswith("your_"):
                print("  Falling back to Cursor/OpenAI...")
                result = await _call_cursor(prompt)
            if result is None:
                claude_key = os.getenv("ANTHROPIC_API_KEY", "")
                if claude_key and not claude_key.startswith("your_"):
                    print("  Falling back to Claude...")
                    result = await _call_claude(prompt)

    return result


async def _call_cursor(prompt: str) -> Optional[list[dict[str, Any]]]:
    import httpx

    api_key = os.getenv("CURSOR_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key or api_key.startswith("your_"):
        print("WARNING: CURSOR_API_KEY not found in .env")
        return None

    base_url = os.getenv("CURSOR_BASE_URL", "https://api.cursor.com").rstrip("/")
    model_name = os.getenv("CURSOR_MODEL", "claude-sonnet-4-6")

    # If it's a native Cursor API key (starts with crsr_) or target is api.cursor.com,
    # use the official Cursor Cloud Agent API
    if api_key.startswith("crsr_") or "api.cursor.com" in base_url:
        return await _call_cursor_cloud_agent(prompt, api_key, model_name, "https://api.cursor.com")

    # Otherwise standard OpenAI-compatible / OpenRouter endpoint
    endpoint = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_name,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt in range(3):
            try:
                resp = await client.post(endpoint, json=payload, headers=headers)
                if resp.status_code == 401:
                    print("Cursor/OpenAI Error: Authentication failed (invalid CURSOR_API_KEY)")
                    return None
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return _parse_json_response(content.strip())
            except Exception as exc:
                err_str = str(exc)
                if "authentication_error" in err_str.lower() or "401" in err_str:
                    print("Cursor/OpenAI Error: Authentication failed (invalid CURSOR_API_KEY)")
                    return None
                if _is_transient_error(exc) and attempt < 2:
                    wait_secs = _retry_delay_seconds(exc, default=3 * (attempt + 1))
                    print(f"  Cursor/OpenAI rate limited/busy. Waiting {wait_secs}s...")
                    await asyncio.sleep(wait_secs)
                    continue
                print(f"Cursor/OpenAI Error: {exc}")
                return None

    return None


async def _call_cursor_cloud_agent(
    prompt: str, api_key: str, model_name: str, base_url: str = "https://api.cursor.com"
) -> Optional[list[dict[str, Any]]]:
    import httpx

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": {"id": model_name},
        "prompt": {"text": prompt},
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(f"{base_url}/v1/agents", json=payload, headers=headers)
            if resp.status_code == 401:
                print("Cursor Cloud Agent Error: Authentication failed (invalid CURSOR_API_KEY)")
                return None
            if resp.status_code != 201:
                print(f"Cursor Cloud Agent Error: {resp.status_code} - {resp.text}")
                return None

            data = resp.json()
            agent_id = data.get("agent", {}).get("id")
            run_id = data.get("run", {}).get("id")
            if not agent_id or not run_id:
                print("Cursor Cloud Agent Error: Missing agent or run ID in response")
                return None

            result_text = None
            for _ in range(25):  # poll up to ~37s
                await asyncio.sleep(1.5)
                r_run = await client.get(f"{base_url}/v1/agents/{agent_id}/runs/{run_id}", headers=headers)
                if r_run.status_code == 200:
                    run_data = r_run.json()
                    status = run_data.get("status")
                    if status in ("FINISHED", "COMPLETED"):
                        result_text = run_data.get("result", "")
                        break
                    elif status in ("FAILED", "CANCELLED"):
                        print(f"Cursor Cloud Agent Run {status}: {run_data.get('error') or run_data}")
                        break

            # Best-effort async cleanup of temporary agent
            try:
                await client.delete(f"{base_url}/v1/agents/{agent_id}", headers=headers)
            except Exception:
                pass

            if result_text:
                return _parse_json_response(result_text.strip())
            else:
                print("Cursor Cloud Agent Error: Did not receive finished result within timeout")
                return None

        except Exception as exc:
            print(f"Cursor Cloud Agent Error: {exc}")
            return None




async def _call_claude(prompt: str) -> Optional[list[dict[str, Any]]]:
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("WARNING: ANTHROPIC_API_KEY not found in .env")
        return None

    client = anthropic.AsyncAnthropic(api_key=api_key)
    model_name = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-latest")

    for attempt in range(3):
        try:
            response = await client.messages.create(
                model=model_name,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            return _parse_json_response(response.content[0].text.strip())
        except Exception as exc:
            err_str = str(exc)
            if "authentication_error" in err_str or "invalid x-api-key" in err_str or "401" in err_str:
                print(f"Claude Error: Authentication failed (invalid ANTHROPIC_API_KEY)")
                return None
            if _is_transient_error(exc) and attempt < 2:
                wait_secs = _retry_delay_seconds(exc, default=5 * (attempt + 1))
                print(f"  Claude rate limited/busy. Waiting {wait_secs}s...")
                await asyncio.sleep(wait_secs)
                continue
            print(f"Claude Error: {exc}")
            return None

    return None


async def _call_gemini(prompt: str) -> Optional[list[dict[str, Any]]]:
    from google import genai

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("WARNING: GEMINI_API_KEY not found in .env")
        return None

    client = genai.Client(api_key=api_key)
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

    # Modern fallback models with separate quotas
    candidate_models = [model_name]
    for alt in ["gemini-3.8-flash", "gemini-flash-latest", "gemini-3.5-flash"]:
        if alt not in candidate_models:
            candidate_models.append(alt)

    for current_model in candidate_models:
        for attempt in range(3):
            try:
                response = await client.aio.models.generate_content(
                    model=current_model,
                    contents=prompt,
                )
                return _parse_json_response(response.text.strip())
            except Exception as exc:
                err_str = str(exc).lower()
                is_daily_quota = (
                    "generaterequestsperday" in err_str
                    or "requests_per_day" in err_str
                )
                wait_secs = _retry_delay_seconds(exc, default=3 * (attempt + 1))
                if is_daily_quota or wait_secs < 0:
                    print(f"  Gemini ({current_model}) daily quota exhausted. Switching model immediately...")
                    break

                if _is_transient_error(exc) and attempt < 2:
                    print(f"  Gemini ({current_model}) transient error. Retrying in {wait_secs}s...")
                    await asyncio.sleep(wait_secs)
                    continue
                print(f"Gemini ({current_model}) Error: {exc}")
                break

    return None


def _is_transient_error(exc: Exception) -> bool:
    error = str(exc).lower()
    return any(
        term in error
        for term in [
            "429",
            "rate",
            "resource_exhausted",
            "503",
            "unavailable",
            "high demand",
            "overloaded",
            "500",
            "502",
            "504",
            "internal",
            "timeout",
            "deadline",
        ]
    )


def _retry_delay_seconds(exc: Exception, default: int = 5) -> int:
    match = re.search(r"retryDelay.*?(\d+)", str(exc))
    if match:
        delay = int(match.group(1)) + 2
        # If the requested delay is longer than 25s (e.g., daily quota reset),
        # return -1 so we don't stall execution and can switch models immediately.
        if delay > 25:
            return -1
        return delay
    return default


def _parse_json_response(text: str) -> Optional[list[dict[str, Any]]]:
    json_text = _extract_json(text)
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as exc:
        print(f"JSON Parsing Error: {exc}\nRaw Text: {text[:500]}")
        return None

    if not isinstance(parsed, list):
        print(f"JSON Schema Error: expected a list of actions, got {type(parsed).__name__}")
        return None

    valid_actions = []
    for item in parsed:
        if isinstance(item, dict) and isinstance(item.get("action"), str):
            valid_actions.append(item)

    if not valid_actions:
        print("JSON Schema Error: response contained no valid actions.")
        return None

    return valid_actions


def _extract_json(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```json"):
        return stripped.split("```json", 1)[1].split("```", 1)[0].strip()
    if stripped.startswith("```"):
        return stripped.split("```", 1)[1].split("```", 1)[0].strip()
    if stripped.startswith("["):
        return stripped

    match = re.search(r"\[[\s\S]*\]", stripped)
    return match.group(0) if match else stripped
