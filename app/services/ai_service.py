from __future__ import annotations

from typing import Final

import httpx

from app.config import get_settings


PROMPT_TEMPLATES: Final[dict[str, str]] = {
    "project_description": (
        "Rewrite this project description for a professional software portfolio. "
        "Improve grammar, make impact clear, keep it ATS-friendly, and avoid hype."
    ),
    "resume_summary": (
        "Rewrite this summary for an ATS-friendly software resume. "
        "Keep it concrete, polished, and recruiter-friendly."
    ),
    "experience_description": (
        "Rewrite this experience bullet or paragraph to emphasize ownership, scope, and measurable impact."
    ),
    "skill_highlights": (
        "Rewrite this skills text into concise professional highlights grouped for a portfolio."
    ),
}


def _fallback_enhancement(content_type: str, text: str, concise: bool) -> str:
    cleaned = " ".join(part.strip() for part in text.splitlines() if part.strip())
    if not cleaned:
        return ""

    prefix_map = {
        "project_description": "Built and delivered",
        "resume_summary": "Results-driven engineer with experience in",
        "experience_description": "Led execution across",
        "skill_highlights": "Core strengths include",
    }
    prefix = prefix_map.get(content_type, "Professional summary:")
    if concise:
        return f"{prefix} {cleaned.rstrip('.')}."
    return (
        f"{prefix} {cleaned.rstrip('.')} with a focus on scalable delivery, clear communication, "
        "and measurable outcomes."
    )


async def enhance_text(content_type: str, text: str, concise: bool) -> dict:
    settings = get_settings()
    if not settings.openai_api_key:
        return {
            "enhanced_text": _fallback_enhancement(content_type, text, concise),
            "provider": "fallback",
            "used_fallback": True,
        }

    system_prompt = PROMPT_TEMPLATES.get(content_type, PROMPT_TEMPLATES["resume_summary"])
    brevity = "Keep it under 60 words." if concise else "Keep it under 120 words."
    payload = {
        "model": settings.openai_model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": f"{system_prompt} {brevity}"}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/responses",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
    except Exception:
        return {
            "enhanced_text": _fallback_enhancement(content_type, text, concise),
            "provider": "fallback",
            "used_fallback": True,
        }

    output = data.get("output", [])
    chunks: list[str] = []
    for item in output:
        for content in item.get("content", []):
            text_value = content.get("text")
            if isinstance(text_value, str) and text_value.strip():
                chunks.append(text_value.strip())

    enhanced = "\n".join(chunks).strip() or _fallback_enhancement(content_type, text, concise)
    return {
        "enhanced_text": enhanced,
        "provider": "openai",
        "used_fallback": not bool(chunks),
    }
