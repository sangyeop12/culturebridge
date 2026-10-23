"""Optional voice transcription and presentation-only preferences."""

import json
from uuid import uuid4

from nicegui import ui

from culturebridge.services.learning_preferences import (
    LearningPreferences,
    get_preferences,
    save_preferences,
)


def voice_text(current, event):
    """Reject stale/oversized transcripts; a recording never submits a learning turn."""
    text, base = event.get("text"), event.get("base")
    if not isinstance(text, str) or not isinstance(base, str) or current != base:
        return None
    combined = base + ("\n" if base else "") + text.strip()
    return combined if text.strip() and len(combined) <= 1000 else None


def voice_controls(prompt):
    identity = uuid4().hex
    ui.label(
        "말로 입력한 내용은 확인한 뒤 직접 보내주세요. 음성은 이 서비스에 저장하지 않지만, "
        "브라우저 제공업체가 인식을 위해 처리할 수 있어요."
    ).classes("cb-muted text-sm")
    status = ui.label("마이크 사용은 선택이에요. 텍스트 입력은 언제든 가능해요.").props(
        "role=status aria-live=polite"
    )
    messages = {
        "listening": "듣고 있어요. 최대 30초 뒤 자동으로 멈춰요.",
        "unsupported": "이 브라우저는 음성 입력을 지원하지 않아요. 직접 입력해 주세요.",
        "insecure": "마이크는 보안 연결에서 사용할 수 있어요. 지금은 직접 입력해 주세요.",
        "not-allowed": "마이크가 허용되지 않았어요. 권한을 확인하거나 직접 입력해 주세요.",
        "service-not-allowed": "음성 인식을 사용할 수 없어요. 직접 입력해 주세요.",
        "audio-capture": "마이크를 찾지 못했어요. 연결을 확인하거나 직접 입력해 주세요.",
        "no-speech": "음성을 인식하지 못했어요. 다시 말하거나 직접 입력해 주세요.",
        "network": "음성 인식 연결이 끊겼어요. 직접 입력해도 괜찮아요.",
        "aborted": "음성 입력을 멈췄어요. 작성한 텍스트는 그대로예요.",
        "too-long": "입력 길이를 초과했거나 인식한 내용이 없어요. 짧게 다시 말해 주세요.",
        "edited": "입력 내용이 바뀌어 음성을 덮어쓰지 않았어요. 다시 말하거나 직접 입력해 주세요.",
        "failed": "음성 입력을 시작하지 못했어요. 직접 입력해 주세요.",
    }

    def received(event):
        data = event.args
        if not isinstance(data, dict) or data.get("target") != identity:
            return
        if data.get("code") == "result":
            if not button.enabled:
                return
            value = voice_text(prompt.value or "", data)
            if value is None:
                status.set_text(messages["edited"])
                return
            prompt.set_value(value)
            status.set_text("음성을 글로 옮겼어요. 내용을 확인하고 보내주세요.")
        else:
            status.set_text(messages.get(data.get("code"), messages["failed"]))

    ui.on("cb_voice", received)
    with ui.row().classes("gap-2 flex-wrap"):
        button = ui.button("말로 입력", icon="mic").props("outline")
        button.on(
            "click",
            js_handler=(
                f"() => window.CultureBridgeVoice?.start({json.dumps(identity)}, {prompt.id})"
            ),
        )
        ui.button("음성 입력 멈추기", icon="mic_off").props("flat").on(
            "click", js_handler="() => window.CultureBridgeVoice?.cancel()"
        )
    return button


def tone_controls(worker, on_saved=None, *, expanded=False):
    preferences = get_preferences()
    with ui.expansion("설명 스타일", icon="tune", value=expanded).classes("w-full"):
        ui.label(
            "설명의 말투와 풀이 깊이를 조절해요. 공식 원문과 이해도 판단 기준은 바꾸지 않아요."
        )
        tone = ui.select(
            {
                "friendly": "친근하게",
                "polite": "정중하게",
                "concise": "간결하게",
                "custom": "직접 선택",
            },
            value=preferences.tone,
            label="설명 문체",
        ).classes("w-full")
        depth = ui.select(
            {"auto": "대화에 맞춰 조절", "easy": "짧고 쉽게", "detailed": "근거까지 자세히"},
            value=preferences.explanation_depth,
            label="설명 깊이",
        ).classes("w-full")
        custom = (
            ui.input(label="원하는 안내 방식", value=preferences.custom_style)
            .props("maxlength=120")
            .classes("w-full")
        )
        ui.label(
            "직접 선택은 ‘존댓말’, ‘간결’, ‘짧게’를 인식해요. "
            "다음 설명부터 반영하며, 원문은 그대로 볼 수 있어요. "
            "AI 풀이를 확인하지 못하면 기존 읽기 도움말로 이어가요."
        ).classes("cb-muted text-sm")

        async def save():
            button.disable()
            try:
                await worker(
                    save_preferences,
                    LearningPreferences(
                        tone=tone.value,
                        custom_style=custom.value or "",
                        explanation_depth=depth.value,
                    ),
                )
                if on_saved:
                    on_saved()
                ui.notify("설명 방식을 저장했어요.")
            finally:
                button.enable()

        button = ui.button("설명 설정 저장", on_click=save).props("outline")
