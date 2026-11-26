"""OpenAI 兼容 /chat/completions 客户端：多家服务 + 本地模型 + 看图（vision）。

约定：provider = {base_url, api_key, model, vision, temperature, max_tokens, extra_json}
base_url 可写 https://api.deepseek.com、https://api.deepseek.com/v1、http://127.0.0.1:1234/v1
"""
from __future__ import annotations

import json
import re

import requests

TIMEOUT = 240


def normalize_base(base_url: str) -> str:
    b = (base_url or "").strip().rstrip("/")
    if not b:
        raise ValueError("base_url 为空")
    b = re.sub(r"/chat/completions$", "", b)
    if not b.endswith("/v1"):
        b = b + "/v1"
    return b


def extra_params(provider: dict) -> dict:
    raw = (provider.get("extra_json") or "").strip()
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def build_user_content(text: str, images: list | None):
    """无图 → 纯字符串；有图 → OpenAI 多模态数组。"""
    images = images or []
    if not images:
        return text
    parts = [{"type": "text", "text": text}]
    for img in images:
        url = img.get("data_url")
        if url:
            parts.append(
                {"type": "image_url", "image_url": {"url": url, "detail": "high"}}
            )
    return parts


def chat(
    provider: dict,
    system: str,
    user_text: str,
    images: list | None = None,
    fast: bool = False,
    temperature: float | None = None,
    max_tokens: int | None = None,
    expect_json: bool = False,
) -> dict:
    """返回 {ok, content, usage, elapsed, note}。"""
    url = normalize_base(provider["base_url"]) + "/chat/completions"
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": build_user_content(user_text, images)})

    body = {
        "model": provider.get("model") or "",
        "messages": msgs,
        "stream": False,
        "temperature": float(
            temperature if temperature is not None else provider.get("temperature", 0.7)
        ),
        "max_tokens": int(
            max_tokens or provider.get("max_tokens") or 8000
        ),
    }
    host = (provider.get("base_url") or "").lower()
    if fast and "deepseek" in host:
        # DeepSeek 官方扩展参数：关闭思考链，直接出结果（"无需过多思考"）
        body["thinking"] = {"type": "disabled"}
    if expect_json:
        body["response_format"] = {"type": "json_object"}
    body.update(extra_params(provider))

    headers = {"Content-Type": "application/json"}
    key = (provider.get("api_key") or "").strip()
    if key:
        headers["Authorization"] = "Bearer " + key

    import time

    t0 = time.time()
    try:
        r = requests.post(url, json=body, headers=headers, timeout=TIMEOUT)
    except requests.exceptions.RequestException as exc:
        return {
            "ok": False,
            "error": f"连接失败：{exc}。检查 base_url 是否可达（{url}），本地模型是否已启动。",
        }
    elapsed = round(time.time() - t0, 2)

    if r.status_code >= 400:
        return {
            "ok": False,
            "error": _extract_error(r),
            "status": r.status_code,
            "elapsed": elapsed,
        }
    try:
        data = r.json()
    except Exception:
        return {"ok": False, "error": "返回不是合法 JSON（网关异常）", "elapsed": elapsed}

    content = ""
    choices = data.get("choices") or []
    if choices:
        msg = choices[0].get("message") or {}
        content = msg.get("content") or ""
        # 部分网关把推理内容放在 reasoning_content，正文为空时兜底
        if not content:
            content = msg.get("reasoning_content") or ""
        if choices[0].get("text"):
            content = content or choices[0]["text"]
    if not content:
        return {
            "ok": False,
            "error": "返回内容为空。多为模型名不存在、请求被拒、或该服务要求流式返回。",
            "raw": json.dumps(data, ensure_ascii=False)[:800],
            "elapsed": elapsed,
        }
    return {
        "ok": True,
        "content": content,
        "usage": data.get("usage") or {},
        "elapsed": elapsed,
    }


def _extract_error(r) -> str:
    txt = ""
    try:
        data = r.json()
        err = data.get("error")
        if isinstance(err, dict):
            txt = err.get("message") or json.dumps(err, ensure_ascii=False)
        elif err:
            txt = str(err)
        else:
            txt = data.get("message") or json.dumps(data, ensure_ascii=False)
    except Exception:
        txt = (r.text or "")[:500]
    return f"HTTP {r.status_code}：{txt[:600]}"


def extract_json(text: str) -> dict | None:
    """从模型输出里抠出 JSON（支持 ```json 围栏、裸对象、单引号轻微修正）。"""
    if not text:
        return None
    candidates = []
    fence = re.search(r"```json\s*(.+?)\s*```", text, re.S)
    if fence:
        candidates.append(fence.group(1))
    fence_any = re.search(r"```\s*(\{.+?\})\s*```", text, re.S)
    if fence_any:
        candidates.append(fence_any.group(1))
    brace = re.search(r"\{.*\}", text, re.S)
    if brace:
        candidates.append(brace.group(0))
    candidates.append(text.strip())
    for c in candidates:
        c = c.strip()
        if not c.startswith("{"):
            continue
        for attempt in (c, c.replace("'", '"')):
            try:
                obj = json.loads(attempt)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass
    return None
