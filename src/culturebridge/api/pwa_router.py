"""Installable web shell. Only generic public assets are available offline."""

import struct
import zlib
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response

router = APIRouter()
ASSETS = Path(__file__).parents[1] / "web"
PWA_HEAD = """
<link rel="manifest" href="/manifest.webmanifest">
<meta name="theme-color" content="#193e3a">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<link rel="apple-touch-icon" href="/pwa/icon-180.png">
<script src="/pwa/voice.js" defer></script>
<script src="/pwa/pwa.js" defer></script>
"""


@router.get("/manifest.webmanifest")
def manifest():
    return JSONResponse(
        {
            "id": "/",
            "name": "CultureBridge · 함께 배우는 역사",
            "short_name": "컬처브릿지",
            "lang": "ko",
            "start_url": "/learn",
            "scope": "/",
            "display": "standalone",
            "theme_color": "#193e3a",
            "background_color": "#f7f3e9",
            "prefer_related_applications": False,
            "icons": [
                {
                    "src": f"/pwa/icon-{size}.png",
                    "sizes": f"{size}x{size}",
                    "type": "image/png",
                    "purpose": "any maskable",
                }
                for size in (192, 512)
            ],
        },
        media_type="application/manifest+json",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/sw.js")
def service_worker():
    return Response(
        (ASSETS / "sw.js").read_text(encoding="utf-8"),
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
    )


@router.get("/pwa/{name}.js")
def client_script(name: str):
    if name not in {"voice", "pwa"}:
        raise HTTPException(404)
    return Response(
        (ASSETS / f"{name}.js").read_text(encoding="utf-8"),
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )


@lru_cache(maxsize=3)
def icon_png(size):
    # Original geometric pavilion, centered inside the maskable safe zone. No external image.
    rows = bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            px, py = x / size, y / size
            roof = 0.29 <= py <= 0.43 and abs(px - 0.5) <= (py - 0.25) * 1.45
            beam = 0.31 <= px <= 0.69 and 0.45 <= py <= 0.49
            pillar = 0.49 <= py <= 0.67 and any(a <= px <= a + 0.045 for a in (0.34, 0.477, 0.615))
            base = 0.29 <= px <= 0.71 and 0.68 <= py <= 0.72
            rows.extend((247, 243, 233) if roof or beam or pillar or base else (25, 62, 58))

    def chunk(kind, value):
        return (
            struct.pack(">I", len(value))
            + kind
            + value
            + struct.pack(">I", zlib.crc32(kind + value))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(rows)))
        + chunk(b"IEND", b"")
    )


@router.get("/pwa/icon-{size}.png")
def icon(size: int):
    if size not in {180, 192, 512}:
        raise HTTPException(404)
    return Response(icon_png(size), media_type="image/png", headers={"Cache-Control": "no-cache"})


@router.get("/pwa/offline")
def offline():
    return HTMLResponse(
        """<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>연결을 기다리고 있어요</title>
<style>body{font:1.1rem/1.8 system-ui;background:#f7f3e9;color:#193e3a;margin:8vh auto;
padding:24px;max-width:620px}a{color:inherit}</style><main><h1>잠시 연결을 기다리고 있어요</h1>
<p>대화와 공식 자료 탐구는 인터넷 연결이 필요해요. 오프라인 입력은 전송하거나 저장하지 않아요.</p>
<p>서버와 다시 연결되면 학습을 이어갈 수 있어요.</p><a href="/learn">연결 후 다시 시작하기</a>
</main></html>""",
        headers={"Cache-Control": "no-cache"},
    )
