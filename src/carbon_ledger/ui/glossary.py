"""Beginner glossary for Carbon Evidence Ledger UI."""

from __future__ import annotations

import streamlit as st

from carbon_ledger.ui.i18n import t

# (lookup_key, zh_title, zh_body, en_title, en_body)
GLOSSARY_ENTRIES: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "ifrs_s1",
        "IFRS S1",
        "永續相關財務資訊揭露的一般要求，說明公司如何治理、策略與風險管理永續議題。",
        "IFRS S1",
        "General requirements for sustainability-related financial disclosures.",
    ),
    (
        "ifrs_s2",
        "IFRS S2",
        "氣候相關財務資訊揭露標準，聚焦氣候風險、機會與相關指標。",
        "IFRS S2",
        "Climate-related disclosure standard focusing on risks, opportunities, and metrics.",  # noqa: E501
    ),
    (
        "scope_1",
        "Scope 1",
        "公司直接產生的排放，例如自有設備燃燒燃料或公務車用油。",
        "Scope 1",
        "Direct emissions from sources the company owns or controls, such as on-site fuel.",  # noqa: E501
    ),
    (
        "scope_2",
        "Scope 2",
        "購買能源造成的間接排放，例如外購電力。",
        "Scope 2",
        "Indirect emissions from purchased energy, such as grid electricity.",
    ),
    (
        "scope_3",
        "Scope 3",
        "價值鏈其他間接排放，例如採購原料的上游排放。",
        "Scope 3",
        "Other value-chain indirect emissions, such as upstream purchased goods.",
    ),
    (
        "ghg_inventory",
        "溫室氣體盤查",
        "依官方方法盤點組織邊界內溫室氣體排放來源與數量。",
        "GHG Inventory",
        "A structured inventory of greenhouse-gas sources and quantities.",
    ),
    (
        "assurance",
        "確信（Assurance）",
        "由獨立第三方對永續／溫室氣體資訊提供確信意見，常見於 IFRS 相關要求。",
        "Assurance",
        "Independent third-party assurance over sustainability or GHG information.",
    ),
    (
        "verification",
        "查驗（Verification）",
        "台灣環境主管機關脈絡下的溫室氣體查驗，與 IFRS 確信是不同概念。",
        "Verification",
        "Taiwan environmental GHG verification — distinct from IFRS assurance.",
    ),
    (
        "carbon_fee",
        "碳費",
        "台灣依氣候法規對特定排放源課徵的費用制度；是否適用需依官方條件判定。",
        "Carbon Fee",
        "Taiwan carbon-fee regime for certain emitters under climate law.",
    ),
    (
        "reporting_boundary",
        "報導邊界",
        "本次評估要涵蓋哪些公司／據點／營運活動的範圍。",
        "Reporting Boundary",
        "Which entities, sites, and activities are included in the assessment.",
    ),
    (
        "consolidated_fs",
        "合併財務報表",
        "把母公司與子公司視為一個經濟個體編製的財務報表。",
        "Consolidated Financial Statements",
        "Financial statements presenting a parent and subsidiaries as one entity.",
    ),
    (
        "paid_in_capital",
        "實收資本額",
        "股東實際繳納的資本；常見於公司登記或財務資訊。",
        "Paid-in Capital",
        "Capital actually paid in by shareholders.",
    ),
    (
        "net_worth",
        "淨值",
        "通常對應資產負債表的權益總額。",
        "Net Worth",
        "Usually corresponds to total equity on the balance sheet.",
    ),
    (
        "evidence",
        "證據",
        "支持活動量、係數、計算或判斷的原始來源文件。",
        "Evidence",
        "Source records that support quantities, factors, or judgments.",
    ),
    (
        "emission_factor",
        "排放係數",
        "把活動量換算成溫室氣體排放量時使用的係數。",
        "Emission Factor",
        "A factor converting activity quantity into greenhouse-gas emissions.",
    ),
    (
        "activity",
        "活動資料",
        "影響碳排計算的營運資料，例如用電量、燃料用量。",
        "Activity",
        "Operational data that drives emissions calculation.",
    ),
    (
        "tco2e",
        "tCO₂e",
        "公噸二氧化碳當量，方便比較不同溫室氣體。",
        "tCO₂e",
        "Tonnes of carbon dioxide equivalent.",
    ),
)


def glossary_pairs(lang: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for _key, zh_title, zh_body, en_title, en_body in GLOSSARY_ENTRIES:
        if lang == "en":
            pairs.append((en_title, en_body))
        else:
            pairs.append((zh_title, zh_body))
    return pairs


def glossary_entry(term_key: str, lang: str) -> tuple[str, str] | None:
    needle = term_key.lower().replace(" ", "_")
    for key, zh_title, zh_body, en_title, en_body in GLOSSARY_ENTRIES:
        if key == needle or key.replace("_", "") == needle.replace("_", ""):
            return (en_title, en_body) if lang == "en" else (zh_title, zh_body)
    return None


def glossary_contains(term: str) -> bool:
    needle = term.lower().replace("₂", "2")
    for key, zh_title, zh_body, en_title, en_body in GLOSSARY_ENTRIES:
        blob = f"{key} {zh_title} {zh_body} {en_title} {en_body}".lower()
        blob = blob.replace("₂", "2")
        if needle in blob:
            return True
    return False


def render_glossary_popover(lang: str) -> None:
    """Render glossary as a compact popover."""
    label = t("header.glossary", lang)
    if label == "header.glossary":
        label = t("common.glossary", lang)
    with st.popover(label):
        intro = t("glossary.intro", lang)
        if intro != "glossary.intro":
            st.caption(intro)
        for title, body in glossary_pairs(lang):
            st.markdown(f"**{title}**")
            st.caption(body)


def render_glossary_inline(lang: str) -> None:
    """Render glossary entries inside tutorial or help areas."""
    st.markdown(f"**{t('common.glossary', lang)}**")
    for title, body in glossary_pairs(lang):
        st.markdown(f"**{title}**  \n{body}")
