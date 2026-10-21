"""Read only official dictionary definitions; never collect examples or multimedia."""

import hashlib
import json
import logging
import re
import threading
import time
from collections import deque
from datetime import UTC, datetime
from typing import Literal

import httpx
from defusedxml.ElementTree import fromstring
from pydantic import BaseModel, Field

from culturebridge.config import get_settings

API_URL = "https://stdict.korean.go.kr/api/search.do"
POLICY_URL = "https://stdict.korean.go.kr/join/copyrightPolicy.do"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/2.0/kr/"
_lock = threading.Lock()
_cache = {}
_calls = deque()


class _RedactDictionaryKey(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        if "stdict.korean.go.kr/api/" in message:
            record.msg = re.sub(r"([?&]key=)[^&\s\"']+", r"\1[REDACTED]", message)
            record.args = ()
        return True


logging.getLogger("httpx").addFilter(_RedactDictionaryKey())


class DictionaryMeaning(BaseModel):
    word: str
    entry_id: str
    sense_no: str = ""
    definition: str
    category: str = ""
    part_of_speech: str = ""
    source_url: str


class DictionaryResult(BaseModel):
    query: str
    status: Literal[
        "ok", "not_configured", "not_found", "invalid_key", "unavailable", "rate_limited"
    ]
    meanings: list[DictionaryMeaning] = Field(default_factory=list)
    notice: str = ""
    attribution: str = "국립국어원 표준국어대사전"
    policy_url: str = POLICY_URL
    license_url: str = LICENSE_URL
    license_name: str = "CC BY-SA 2.0 KR"
    modified: bool = False
    retrieved_at: str = ""
    cached: bool = False


def _fetch(query, key):
    with httpx.Client(timeout=8, follow_redirects=False) as client:
        with client.stream(
            "GET",
            API_URL,
            params={
                "key": key,
                "q": query,
                "req_type": "json",
                "num": 10,
                "advanced": "y",
                "method": "exact",
            },
        ) as response:
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > 500_000:
                    raise ValueError("response_limit")
    text = bytes(body).decode("utf-8-sig").strip()
    if text.startswith("<"):
        root = fromstring(text)
        return {"error": {"error_code": root.findtext("error_code", "unknown")}}
    return json.loads(text)


def _parse(query, payload):
    if not isinstance(payload, dict):
        raise ValueError("invalid_response")
    if "error" in payload:
        code = str(payload["error"].get("error_code", "")).zfill(3)
        return DictionaryResult(
            query=query,
            status="invalid_key" if code in {"020", "021"} else "unavailable",
            notice="사전 연결 설정을 확인해야 해요. 공식 사이트에서 직접 뜻을 살펴볼 수 있어요.",
        )
    channel = payload.get("channel")
    if not isinstance(channel, dict) or "total" not in channel:
        raise ValueError("missing_channel")
    items = channel.get("item", [])
    if isinstance(items, dict):
        items = [items]
    meanings = []
    for item in items[:10]:
        if not isinstance(item, dict):
            continue
        identity, word = str(item.get("target_code", "")), item.get("word", "")
        if not identity.isdigit() or not isinstance(word, str):
            continue
        # Search the exact headword; do not silently choose a similarly spelled entry.
        if word.replace("-", "").replace("^", "") != query:
            continue
        senses = item.get("sense", [])
        if isinstance(senses, dict):
            senses = [senses]
        for sense in senses[:10]:
            if not isinstance(sense, dict):
                continue
            definition = sense.get("definition", "")
            if not isinstance(definition, str) or not 1 <= len(definition) <= 1000:
                continue
            meanings.append(
                DictionaryMeaning(
                    word=word,
                    entry_id=identity,
                    sense_no=str(sense.get("sense_no", "")),
                    definition=definition,
                    category=str(sense.get("cat", ""))[:80],
                    part_of_speech=str(item.get("pos", ""))[:30],
                    source_url="https://stdict.korean.go.kr/search/searchView.do?word_no="
                    + identity,
                )
            )
            if len(meanings) == 5:
                break
        if len(meanings) == 5:
            break
    if int(channel["total"]) > 0 and not meanings:
        raise ValueError("unusable_entries")
    return DictionaryResult(
        query=query,
        status="ok" if meanings else "not_found",
        meanings=meanings,
        notice="사전적 뜻이에요. 지금 이야기의 맥락과 맞는 뜻인지 함께 확인해요."
        if meanings
        else "일치하는 표제어를 찾지 못했어요. 표현을 바꿔 살펴볼까요?",
        retrieved_at=datetime.now(UTC).isoformat(),
    )


def lookup_term(query):
    query = query.strip()
    if not re.fullmatch(r"[가-힣A-Za-z0-9· -]{1,40}", query):
        raise ValueError("용어를 1~40자의 짧은 단어나 어구로 입력해 주세요.")
    secret = get_settings().stdict_api_key
    key = secret.get_secret_value() if secret else ""
    if not key:
        return DictionaryResult(
            query=query,
            status="not_configured",
            notice="사전 자동 조회는 아직 연결 전이에요. 표준국어대사전에서 직접 확인할 수 있어요.",
        )
    if not re.fullmatch(r"[0-9a-fA-F]{32}", key):
        return DictionaryResult(
            query=query, status="invalid_key", notice="사전 연결 설정을 확인해야 해요."
        )
    fingerprint = (hashlib.sha256(key.encode()).hexdigest(), query)
    now = time.monotonic()
    with _lock:
        for old in list(_cache):
            if _cache[old][0] <= now:
                del _cache[old]
        if fingerprint in _cache:
            result = _cache[fingerprint][1].model_copy(deep=True)
            result.cached = True
            return result
        while _calls and _calls[0] < now - 60:
            _calls.popleft()
        # Local conservative ceiling, not a claim about the provider's granted quota.
        if len(_calls) >= 20:
            return DictionaryResult(
                query=query,
                status="rate_limited",
                notice="사전 조회가 많아요. 잠시 후 다시 살펴봐요.",
            )
        _calls.append(now)
    try:
        result = _parse(query, _fetch(query, key))
    except Exception:
        # Never put an HTTP exception/request URL (which may contain the key) in a response/log.
        return DictionaryResult(
            query=query,
            status="unavailable",
            notice="사전 연결이 잠시 어려워요. 공식 사이트를 이용해 주세요.",
        )
    if result.status in {"ok", "not_found"}:
        with _lock:
            if len(_cache) >= 128:
                _cache.pop(next(iter(_cache)))
            _cache[fingerprint] = (time.monotonic() + 300, result.model_copy(deep=True))
    return result
