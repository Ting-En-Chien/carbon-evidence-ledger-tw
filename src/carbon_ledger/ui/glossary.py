"""Beginner glossary for Carbon Evidence Ledger UI."""

from __future__ import annotations

import streamlit as st

from carbon_ledger.ui.i18n import t

# (lookup_key, zh_title, zh_body, en_body)
GLOSSARY_ENTRIES: tuple[tuple[str, str, str, str], ...] = (
    (
        "Activity",
        "活動資料 / Activity",
        (
            "公司營運中會影響碳排計算或準則判斷的資料，例如用電量、天然氣量、"
            "柴油用量、採購鋼材。"
        ),
        (
            "Operational data that affects emissions calculation or framework "
            "decisions — for example electricity, natural gas, diesel, or "
            "purchased steel."
        ),
    ),
    (
        "Emission factor",
        "排放係數 / Emission factor",
        "把活動量換算成溫室氣體排放量時使用的係數。",
        (
            "A factor used to convert an activity quantity into "
            "greenhouse-gas emissions."
        ),
    ),
    (
        "tCO2e",
        "tCO₂e",
        "公噸二氧化碳當量。不同溫室氣體會換算成同一單位，方便比較與加總。",
        (
            "Tonnes of carbon dioxide equivalent — a common unit for "
            "comparing greenhouse gases."
        ),
    ),
    (
        "Scope 1",
        "Scope 1",
        "公司自己直接產生的排放。例如公司設備燃燒天然氣、公司車使用柴油。",
        (
            "Direct emissions from sources owned or controlled by the company, "
            "such as on-site fuel or fleet diesel."
        ),
    ),
    (
        "Scope 2",
        "Scope 2",
        "公司購買能源造成的間接排放。例如向電力公司購買電力。",
        "Indirect emissions from purchased energy, such as grid electricity.",
    ),
    (
        "Scope 3",
        "Scope 3",
        "公司價值鏈中其他間接排放。例如採購鋼材所產生的上游排放。",
        (
            "Other indirect value-chain emissions, such as upstream emissions "
            "from purchased steel."
        ),
    ),
    (
        "Evidence",
        "來源證據 / Evidence",
        "支持活動量、係數、計算或判斷的原始來源。",
        (
            "Source records that support quantities, factors, calculations, "
            "or judgments."
        ),
    ),
    (
        "QA",
        "資料品質檢查 / QA",
        "檢查資料是不是缺漏、互相矛盾、無法計算或需要人工確認。",
        (
            "Checks for missing, conflicting, non-calculable, or "
            "review-required data."
        ),
    ),
    (
        "CBAM",
        "CBAM",
        "歐盟碳邊境調整機制。本產品目前用它判斷出口產品資料用途與資料缺口。",
        (
            "EU Carbon Border Adjustment Mechanism. This product uses it to "
            "map export-product data roles and gaps."
        ),
    ),
    (
        "IFRS S2",
        "IFRS S2",
        "氣候相關財務資訊揭露標準。本產品目前只判斷碳資料準備度，不做合規判定。",
        (
            "Climate-related disclosure standard. This product assesses data "
            "readiness only — not compliance."
        ),
    ),
)


def glossary_pairs(lang: str) -> list[tuple[str, str]]:
    """Return (title, body) pairs for the active language."""
    pairs: list[tuple[str, str]] = []
    for _key, zh_title, zh_body, en_body in GLOSSARY_ENTRIES:
        if lang == "en":
            title = zh_title.split(" / ")[-1] if " / " in zh_title else zh_title
            pairs.append((title, en_body))
        else:
            pairs.append((zh_title, zh_body))
    return pairs


def glossary_contains(term: str) -> bool:
    """Return True when a glossary term exists (for tests)."""
    needle = term.lower().replace("₂", "2")
    for key, title, zh_body, en_body in GLOSSARY_ENTRIES:
        blob = f"{key} {title} {zh_body} {en_body}".lower()
        blob = blob.replace("₂", "2")
        if needle in blob:
            return True
    return False


def render_glossary_popover(lang: str) -> None:
    """Render glossary as a compact popover."""
    with st.popover(t("common.glossary", lang)):
        for title, body in glossary_pairs(lang):
            st.markdown(f"**{title}**")
            st.caption(body)


def render_glossary_inline(lang: str) -> None:
    """Render glossary entries inside tutorial or help areas."""
    st.markdown(f"**{t('common.glossary', lang)}**")
    for title, body in glossary_pairs(lang):
        st.markdown(f"**{title}**  \n{body}")
