"""Bounded, short-lived reuse of successful expensive learning requests."""

import hashlib
import json
import threading
import time
from collections import defaultdict, deque
from contextvars import ContextVar
from copy import deepcopy
from functools import wraps

from culturebridge.config import get_settings

session_owner = ContextVar("culturebridge_session_owner", default=None)
_depth = ContextVar("culturebridge_operation_depth", default=0)
_cache = {}
_lock = threading.RLock()
_active = 0
_requests = defaultdict(deque)


class OperationBusyError(RuntimeError):
    pass


def owner_key():
    return session_owner.get() or "local"


def reused_operation(name):
    def decorate(function):
        @wraps(function)
        def call(*args, **kwargs):
            global _active
            payload = json.dumps([args, kwargs], sort_keys=True, ensure_ascii=False, default=str)
            key = (
                str(get_settings().db_path.resolve()),
                owner_key(),
                name,
                hashlib.sha256(payload.encode()).hexdigest(),
                get_settings().gemini_enabled,
                get_settings().gemini_model,
                bool(get_settings().gemini_api_key),
            )
            # Serialize only identical jobs; completed results are copied to avoid mutation.
            with _lock:
                now = time.monotonic()
                for old in list(_cache):
                    if _cache[old][0] <= now:
                        del _cache[old]
                entry = _cache.get(key)
                if entry:
                    return deepcopy(entry[1])
                if get_settings().public_mode and not _depth.get():
                    for request_key in list(_requests):
                        if not _requests[request_key] or _requests[request_key][-1] <= now - 60:
                            del _requests[request_key]
                    if len(_requests) >= 4096:
                        raise OperationBusyError("요청이 많습니다. 잠시 후 다시 시도하세요.")
                    bucket = _requests[(key[0], owner_key())]
                    while bucket and bucket[0] <= now - 60:
                        bucket.popleft()
                    if len(bucket) >= get_settings().requests_per_minute:
                        raise OperationBusyError("학습 요청이 많습니다. 잠시 후 다시 시도하세요.")
                    bucket.append(now)
                if not _depth.get() and _active >= get_settings().max_learning_jobs:
                    raise OperationBusyError(
                        "다른 학습 요청을 처리 중입니다. 잠시 후 다시 시도하세요."
                    )
                nested = bool(_depth.get())
                if not nested:
                    _active += 1
            token = _depth.set(_depth.get() + 1)
            try:
                # A per-key lock prevents repeated UI/API requests from doing the same work.
                with _job_lock(key):
                    with _lock:
                        entry = _cache.get(key)
                        if entry and entry[0] > time.monotonic():
                            return deepcopy(entry[1])
                    result = function(*args, **kwargs)
                    if not (hasattr(result, "used_ai") and not result.used_ai) and (
                        not isinstance(result, dict)
                        or result.get("comparison")
                        or result.get("saved_id")
                    ):
                        with _lock:
                            if len(_cache) >= 256:
                                _cache.pop(next(iter(_cache)))
                            _cache[key] = (
                                time.monotonic() + get_settings().learning_reuse_seconds,
                                deepcopy(result),
                            )
                    return result
            finally:
                _depth.reset(token)
                if not nested:
                    with _lock:
                        _active -= 1

        return call

    return decorate


_jobs = {}


class _job_lock:
    def __init__(self, key):
        self.key = key

    def __enter__(self):
        with _lock:
            item = _jobs.setdefault(self.key, [threading.RLock(), 0])
            item[1] += 1
            self.lock = item[0]
        self.lock.acquire()

    def __exit__(self, *args):
        self.lock.release()
        with _lock:
            _jobs[self.key][1] -= 1
            if not _jobs[self.key][1]:
                del _jobs[self.key]
