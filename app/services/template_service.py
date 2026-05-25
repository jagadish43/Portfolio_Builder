from __future__ import annotations

from app.utils.portfolio_defaults import THEME_SLUGS, default_theme_config


TEMPLATE_REGISTRY = {
    "modern": {
        "slug": "modern",
        "label": "Modern",
        "template_path": "Templates/modern.html",
        "description": "Split hero with elevated content cards and bold CTAs.",
    },
    "minimal": {
        "slug": "minimal",
        "label": "Minimal",
        "template_path": "Templates/minimal.html",
        "description": "Editorial single-column resume-style layout.",
    },
    "developer": {
        "slug": "developer",
        "label": "Developer",
        "template_path": "Templates/developer.html",
        "description": "Terminal-inspired developer portfolio with metrics and code accents.",
    },
    "creative": {
        "slug": "creative",
        "label": "Creative",
        "template_path": "Templates/creative.html",
        "description": "Magazine-like showcase with colorful section treatment.",
    },
}


def get_template_options() -> list[dict]:
    return [TEMPLATE_REGISTRY[slug] for slug in THEME_SLUGS]


def resolve_template(theme_slug: str | None) -> str:
    return TEMPLATE_REGISTRY.get(theme_slug or "", TEMPLATE_REGISTRY["modern"])["template_path"]


def build_template_preview(theme_slug: str) -> dict:
    data = dict(TEMPLATE_REGISTRY.get(theme_slug, TEMPLATE_REGISTRY["modern"]))
    data["default_theme_config"] = default_theme_config()
    return data
