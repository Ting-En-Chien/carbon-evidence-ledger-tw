"""Stage 4.2G guided-tour asset manifest.

Production screenshots live beside this module. Coordinates are normalized
percentages so the spotlight stays aligned when the image scales.

The tour is a three-step desktop orientation. Mobile guided-tour layout
is deferred.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

TOUR_VERSION = "stage4-2g-3step-20260820"
TOUR_STEP_COUNT = 3
ASSET_DIR = Path(__file__).with_name("assets") / "tutorial"

STEP_IDS: tuple[str, ...] = (
    "company",
    "upload",
    "results",
)

# Highlight boxes are fractions of the cropped screenshot (left, top, width, height).
# Callout anchors are the point the label sits relative to the image.
TOUR_STEPS: tuple[dict[str, Any], ...] = (
    {
        "id": "company",
        "index": 1,
        "image": "step1_company.png",
        "images": {
            "zh-TW": "step1_company.png",
            "en": "step1_company.en.png",
        },
        "source_screen": "applicability.facilities",
        "language": "zh-TW",
        "capture_version": TOUR_VERSION,
        "title_key": "tut.s1.title",
        "why_key": "tut.s1.why",
        "action_key": "tut.s1.action",
        "next_key": "tut.s1.next",
        "alt_key": "tut.s1.alt",
        "highlight": {"left": 0.05, "top": 0.28, "width": 0.94, "height": 0.68},
        "highlights": {
            "zh-TW": {"left": 0.05, "top": 0.28, "width": 0.94, "height": 0.68},
            "en": {"left": 0.05, "top": 0.28, "width": 0.94, "height": 0.68},
        },
        "callouts": (
            {"left": 0.68, "top": 0.12, "key": "tut.s1.callout1"},
        ),
    },
    {
        "id": "upload",
        "index": 2,
        "image": "step2_upload.png",
        "images": {
            "zh-TW": "step2_upload.png",
            "en": "step2_upload.en.png",
        },
        "source_screen": "intake.upload",
        "language": "zh-TW",
        "capture_version": TOUR_VERSION,
        "title_key": "tut.s2.title",
        "why_key": "tut.s2.why",
        "action_key": "tut.s2.action",
        "next_key": "tut.s2.next",
        "alt_key": "tut.s2.alt",
        "highlight": {"left": 0.06, "top": 0.42, "width": 0.88, "height": 0.36},
        "highlights": {
            "zh-TW": {"left": 0.06, "top": 0.42, "width": 0.88, "height": 0.36},
            "en": {"left": 0.02, "top": 0.44, "width": 0.96, "height": 0.49},
        },
        "callouts": (
            {"left": 0.62, "top": 0.22, "key": "tut.s2.callout1"},
        ),
    },
    {
        "id": "results",
        "index": 3,
        "image": "step3_results.png",
        "images": {
            "zh-TW": "step3_results.png",
            "en": "step3_results.en.png",
        },
        "source_screen": "dashboard.results",
        "language": "zh-TW",
        "capture_version": TOUR_VERSION,
        "title_key": "tut.s3.title",
        "why_key": "tut.s3.why",
        "action_key": "tut.s3.action",
        "next_key": "tut.s3.next",
        "alt_key": "tut.s3.alt",
        "highlight": {"left": 0.18, "top": 0.51, "width": 0.33, "height": 0.42},
        "highlights": {
            "zh-TW": {"left": 0.18, "top": 0.51, "width": 0.33, "height": 0.42},
            "en": {"left": 0.18, "top": 0.51, "width": 0.33, "height": 0.42},
        },
        "callouts": (
            {"left": 0.62, "top": 0.36, "key": "tut.s3.callout1"},
        ),
    },
)


def normalize_tour_lang(lang: str) -> str:
    return "en" if str(lang).lower().startswith("en") else "zh-TW"


def tour_step_visual(spec: dict[str, Any], lang: str) -> dict[str, Any]:
    """Return the language-matched image, highlight, and resolved path."""
    key = normalize_tour_lang(lang)
    images = spec.get("images") or {spec.get("language") or "zh-TW": spec["image"]}
    highlights = spec.get("highlights") or {
        spec.get("language") or "zh-TW": spec["highlight"]
    }
    filename = str(images.get(key) or spec["image"])
    highlight = dict(highlights.get(key) or spec["highlight"])
    return {
        "lang": key,
        "image": filename,
        "highlight": highlight,
        "path": asset_path(filename),
    }


def asset_path(filename: str) -> Path:
    return ASSET_DIR / filename


def production_asset_paths() -> tuple[Path, ...]:
    paths: list[Path] = []
    seen: set[str] = set()
    for step in TOUR_STEPS:
        names = [str(step["image"])]
        images = step.get("images") or {}
        names.extend(str(name) for name in images.values())
        for name in names:
            if name in seen:
                continue
            seen.add(name)
            paths.append(asset_path(name))
    return tuple(paths)


def missing_or_empty_assets() -> tuple[str, ...]:
    missing: list[str] = []
    for path in production_asset_paths():
        if not path.is_file() or path.stat().st_size <= 0:
            missing.append(path.name)
    return tuple(missing)


def iter_tour_steps() -> tuple[dict[str, Any], ...]:
    return TOUR_STEPS


def step_by_index(index: int) -> dict[str, Any]:
    if index < 1 or index > TOUR_STEP_COUNT:
        raise ValueError(f"tutorial step out of range: {index}")
    return TOUR_STEPS[index - 1]
