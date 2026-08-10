"""Centralized Traditional Chinese / English UI strings for Phase 8B.

Default language is Traditional Chinese (zh-TW). Identifiers such as record_id
are never translated. Official standard names may stay in English.
"""

from __future__ import annotations

from typing import Any

LANG_ZH = "zh-TW"
LANG_EN = "en"
DEFAULT_LANG = LANG_ZH
LANG_OPTIONS = ("繁中", "EN")
LANG_OPTION_TO_CODE = {"繁中": LANG_ZH, "EN": LANG_EN}
LANG_CODE_TO_OPTION = {LANG_ZH: "繁中", LANG_EN: "EN"}

STATE_LANGUAGE = "ui_language"

MESSAGES: dict[str, dict[str, str]] = {
    # Navigation
    "nav.dashboard": {"zh-TW": "總覽", "en": "Dashboard"},
    "nav.intake": {"zh-TW": "資料匯入", "en": "Data Intake"},
    "nav.activity": {"zh-TW": "活動資料", "en": "Activity Data"},
    "nav.issues": {"zh-TW": "待處理問題", "en": "Issues & Actions"},
    "nav.frameworks": {"zh-TW": "準則分析", "en": "Frameworks"},
    "nav.audit": {"zh-TW": "稽核與匯出", "en": "Audit & Export"},
    # Brand / header
    "brand.name": {
        "zh-TW": "Carbon Evidence Ledger",
        "en": "Carbon Evidence Ledger",
    },
    "brand.descriptor": {
        "zh-TW": "台灣出口企業碳資料準備與證據追蹤",
        "en": "Carbon data readiness for Taiwanese exporters",
    },
    "header.tutorial": {"zh-TW": "? 操作教學", "en": "? Tutorial"},
    "header.language_aria": {"zh-TW": "語言", "en": "Language"},
    # Sidebar
    "sidebar.current_analysis": {"zh-TW": "目前分析", "en": "Current analysis"},
    "sidebar.workspace_name": {
        "zh-TW": "虛構台灣扣件公司",
        "en": "Synthetic Taiwan Fastener Co.",
    },
    "sidebar.reporting_context": {
        "zh-TW": "2024 示範資料",
        "en": "2024 synthetic demonstration",
    },
    "sidebar.analysis_contents": {"zh-TW": "分析內容", "en": "Analysis modules"},
    "sidebar.ghg_title": {"zh-TW": "公司碳盤查", "en": "Corporate GHG inventory"},
    "sidebar.ghg_help": {
        "zh-TW": "判斷公司活動屬於 Scope 1、2 或 3。",
        "en": "Classify activities as Scope 1, 2, or 3.",
    },
    "sidebar.cbam_title": {"zh-TW": "歐盟出口", "en": "EU export"},
    "sidebar.cbam_help": {
        "zh-TW": "判斷出口產品需要哪些碳資料，以及目前缺什麼。",
        "en": "See which carbon data an EU export product needs, and what is missing.",
    },
    "sidebar.ifrs_title": {"zh-TW": "氣候揭露", "en": "Climate disclosure"},
    "sidebar.ifrs_help": {
        "zh-TW": "判斷現有碳資料是否足以支援氣候資訊揭露準備。",
        "en": "See whether current carbon data can support climate disclosure prep.",
    },
    "sidebar.ifrs_note": {
        "zh-TW": "IFRS S2 會自動使用 GHG Protocol 分類結果作為來源證據。",
        "en": (
            "IFRS S2 automatically uses GHG Protocol classifications "
            "as source evidence."
        ),
    },
    "sidebar.run": {"zh-TW": "開始分析", "en": "Start analysis"},
    "sidebar.need_help": {"zh-TW": "需要協助？", "en": "Need help?"},
    "sidebar.tutorial_link": {
        "zh-TW": "操作教學 →",
        "en": "Tutorial →",
    },
    "sidebar.running": {"zh-TW": "正在分析…", "en": "Running analysis…"},
    "sidebar.loading": {
        "zh-TW": "正在整理內建示範資料…",
        "en": "Loading bundled synthetic evidence…",
    },
    "sidebar.complete": {"zh-TW": "分析完成", "en": "Analysis complete"},
    "sidebar.pipeline_done": {
        "zh-TW": "管線已完成。",
        "en": "Pipeline complete.",
    },
    "error.analysis_failed": {
        "zh-TW": "分析暫時無法完成。",
        "en": "Analysis could not be completed.",
    },
    "error.export_failed": {
        "zh-TW": "下載檔案建立失敗。",
        "en": "Export bundle could not be generated.",
    },
    # Common
    "common.demo_badge": {"zh-TW": "示範資料", "en": "Demo data"},
    "common.partial_result": {"zh-TW": "部分結果", "en": "Partial result"},
    "common.not_run": {"zh-TW": "尚未執行", "en": "Not run"},
    "common.how_to_use": {"zh-TW": "這頁怎麼用？", "en": "How to use this page"},
    "common.view_missing": {
        "zh-TW": "查看資料 →",
        "en": "View data →",
    },
    "common.high_priority": {"zh-TW": "高優先", "en": "High priority"},
    "common.critical": {"zh-TW": "重大", "en": "Critical"},
    "common.glossary": {"zh-TW": "名詞小幫手 →", "en": "Glossary →"},
    "common.advanced": {"zh-TW": "進階技術資訊", "en": "Advanced technical details"},
    # Status labels
    "status.calculated": {"zh-TW": "已完成計算", "en": "Calculated"},
    "status.blocked_missing_conversion": {
        "zh-TW": "無法計算－缺少轉換資料",
        "en": "Blocked — missing conversion",
    },
    "status.no_factor_configured": {
        "zh-TW": "缺少排放係數",
        "en": "Emission factor needed",
    },
    "status.not_emissions_activity": {
        "zh-TW": "輔助資料",
        "en": "Supporting data",
    },
    "status.unsupported_activity_type": {
        "zh-TW": "尚不支援的活動類型",
        "en": "Unsupported activity",
    },
    "status.invalid_normalized_input": {
        "zh-TW": "標準化輸入無效",
        "en": "Invalid normalized input",
    },
    "status.factor_match_inconsistent": {
        "zh-TW": "係數比對不一致",
        "en": "Factor match inconsistent",
    },
    "status.ready": {"zh-TW": "資料完整", "en": "Ready"},
    "status.partial_evidence": {
        "zh-TW": "部分資料可用",
        "en": "Partial evidence",
    },
    "status.data_gap": {"zh-TW": "資料不足", "en": "Data gap"},
    "status.supporting_only": {"zh-TW": "僅作輔助", "en": "Supporting only"},
    "status.excluded": {"zh-TW": "不納入", "en": "Excluded"},
    "status.needs_review": {"zh-TW": "需要確認", "en": "Needs review"},
    "status.not_applicable": {"zh-TW": "不適用", "en": "Not applicable"},
    "status.mapped": {"zh-TW": "已對應", "en": "Mapped"},
    "status.unknown": {"zh-TW": "未知", "en": "Unknown"},
    "status.no_open_issue": {
        "zh-TW": "無待處理問題",
        "en": "No open issue",
    },
    "status.attention_blocked": {
        "zh-TW": "缺少熱值轉換資料",
        "en": "Missing heating-value conversion",
    },
    "status.attention_factor": {
        "zh-TW": "缺少適用排放係數",
        "en": "Missing applicable emission factor",
    },
    # Activity names
    "activity.grid_electricity": {
        "zh-TW": "外購電力",
        "en": "Purchased electricity",
    },
    "activity.natural_gas": {
        "zh-TW": "熱處理天然氣",
        "en": "Heat-treatment natural gas",
    },
    "activity.diesel": {
        "zh-TW": "公司車柴油",
        "en": "Company-vehicle diesel",
    },
    "activity.purchased_steel": {
        "zh-TW": "採購鋼材",
        "en": "Purchased steel wire rod",
    },
    "activity.finished_goods_output": {
        "zh-TW": "成品產出",
        "en": "Finished-goods output",
    },
    "activity.third_party_transport": {
        "zh-TW": "第三方運輸",
        "en": "Third-party transport",
    },
    "activity.scrap_output": {"zh-TW": "廢料產出", "en": "Scrap output"},
    "activity.other": {"zh-TW": "其他", "en": "Other"},
    "activity.unknown": {"zh-TW": "未知", "en": "Unknown"},
    # GHG / CBAM roles
    "ghg.scope_1": {"zh-TW": "Scope 1", "en": "Scope 1"},
    "ghg.scope_2": {"zh-TW": "Scope 2", "en": "Scope 2"},
    "ghg.scope_3": {"zh-TW": "Scope 3", "en": "Scope 3"},
    "ghg.scope_3_cat1": {
        "zh-TW": "Scope 3 Category 1",
        "en": "Scope 3 Category 1",
    },
    "cbam.role.supporting_energy": {
        "zh-TW": "佐證用能源資料／不納入直接排放",
        "en": "Supporting evidence / excluded from direct emissions",
    },
    "cbam.role.direct_candidate": {
        "zh-TW": "直接排放活動候選",
        "en": "Direct-emissions activity candidate",
    },
    "cbam.role.outside": {
        "zh-TW": "製程邊界外",
        "en": "Outside process boundary",
    },
    "cbam.role.precursor": {
        "zh-TW": "可能的前驅物資料缺口",
        "en": "Possible precursor data gap",
    },
    "cbam.role.product_qty": {
        "zh-TW": "產品數量證據",
        "en": "Product quantity evidence",
    },
    # Dashboard
    "dash.page_title": {"zh-TW": "碳資料總覽", "en": "Carbon data overview"},
    "dash.page_subtitle": {
        "zh-TW": "查看目前能計算的排放、資料缺口，以及下一步需要處理的項目。",
        "en": (
            "See currently calculable emissions, data gaps, and what needs "
            "attention next."
        ),
    },
    "dash.tutorial_hint": {
        "zh-TW": "第一次使用？查看 3 分鐘操作教學 →",
        "en": "First time here? Open the 3-minute tutorial →",
    },
    "dash.hero_kicker": {
        "zh-TW": "Carbon Evidence Ledger",
        "en": "Carbon Evidence Ledger",
    },
    "dash.hero_title": {
        "zh-TW": "讓碳資料變得\n可計算、可追溯、可行動",
        "en": "Make carbon data\ncalculable, traceable, and actionable",
    },
    "dash.hero_support": {
        "zh-TW": (
            "從原始活動資料到 Scope 1 / 2 / 3、CBAM 與 IFRS S2，"
            "清楚知道目前能算什麼、缺什麼，以及下一步該做什麼。"
        ),
        "en": (
            "From source activity data to Scope 1 / 2 / 3, CBAM, and IFRS S2 — "
            "see what can be calculated, what is missing, and what to do next."
        ),
    },
    "dash.hero_cta": {"zh-TW": "開始分析", "en": "Start analysis"},
    "dash.hero_help_link": {
        "zh-TW": "不知道怎麼開始？請使用左側的「開始分析」。",
        "en": "Not sure how to start? Use Start analysis in the sidebar.",
    },
    "dash.hero_help_cta": {
        "zh-TW": "查看操作教學",
        "en": "Open tutorial",
    },
    "dash.flow_evidence": {"zh-TW": "來源證據", "en": "Source evidence"},
    "dash.flow_activity": {"zh-TW": "活動資料", "en": "Activity data"},
    "dash.flow_calc": {"zh-TW": "排放計算", "en": "Emissions calculation"},
    "dash.flow_framework": {"zh-TW": "準則分析", "en": "Framework analysis"},
    "dash.flow_frameworks_short": {
        "zh-TW": "準則對應",
        "en": "Frameworks",
    },
    "dash.flow_action": {"zh-TW": "下一步行動", "en": "Next action"},
    "dash.how_title": {"zh-TW": "如何使用", "en": "How it works"},
    "dash.how_1": {"zh-TW": "選擇分析項目", "en": "Choose modules"},
    "dash.how_2": {"zh-TW": "開始分析", "en": "Run analysis"},
    "dash.how_3": {"zh-TW": "處理缺少資料", "en": "Resolve data gaps"},
    "dash.how_4": {"zh-TW": "查看準則結果", "en": "Review frameworks"},
    "dash.how_5": {"zh-TW": "下載成果", "en": "Export results"},
    "dash.kpi_activities": {"zh-TW": "活動資料", "en": "Activities"},
    "dash.kpi_calculated": {"zh-TW": "已完成計算", "en": "Calculated"},
    "dash.kpi_issues": {"zh-TW": "待處理問題", "en": "Open issues"},
    "dash.kpi_docs": {"zh-TW": "來源文件", "en": "Source documents"},
    "dash.emissions_title": {
        "zh-TW": "目前已能計算的排放量",
        "en": "Currently calculable emissions",
    },
    "dash.emissions_label": {
        "zh-TW": "目前已能計算",
        "en": "Currently calculable",
    },
    "dash.emissions_ratio": {
        "zh-TW": "{done} / {total} 筆活動已完成計算",
        "en": "{done} / {total} activities calculated",
    },
    "dash.emissions_ratio_short": {
        "zh-TW": "{done} / {total} 筆活動",
        "en": "{done} / {total} activities",
    },
    "dash.emissions_notice": {
        "zh-TW": (
            "這不是公司的總排放量。"
            "缺少資料的活動不會被當成 0。"
        ),
        "en": (
            "This is not total company emissions. "
            "Missing activities are not treated as zero."
        ),
    },
    "dash.attention_title": {
        "zh-TW": "你現在需要處理",
        "en": "Needs your attention",
    },
    "dash.attention_sub": {
        "zh-TW": "以下資料缺口會阻止完整計算。",
        "en": "These data gaps currently prevent complete calculation.",
    },
    "dash.attention_empty": {
        "zh-TW": "目前沒有待處理的核心資料問題。",
        "en": "No open core data-quality issues right now.",
    },
    "dash.attention_gas_action": {
        "zh-TW": "取得適用的低位熱值後，即可繼續排放計算。",
        "en": "Register an applicable lower heating value to continue calculation.",
    },
    "dash.attention_diesel_action": {
        "zh-TW": "取得適用的低位熱值後，即可繼續排放計算。",
        "en": "Register an applicable lower heating value to continue calculation.",
    },
    "dash.attention_steel_action": {
        "zh-TW": "選定並登錄適用排放係數後，即可繼續計算。",
        "en": "Select and document an applicable emission factor to continue.",
    },
    "dash.activities_title": {
        "zh-TW": "所有活動資料",
        "en": "All activity data",
    },
    "dash.activities_sub": {
        "zh-TW": "快速查看每筆資料目前的計算與準則狀態。",
        "en": "Quickly review calculation and framework status for each record.",
    },
    "dash.activities_explore": {
        "zh-TW": "查看完整活動資料 →",
        "en": "Open full activity explorer →",
    },
    "dash.col.activity": {"zh-TW": "活動", "en": "Activity"},
    "dash.col.amount": {"zh-TW": "數量", "en": "Amount"},
    "dash.col.calc": {"zh-TW": "計算", "en": "Calculation"},
    "dash.col.ghg": {"zh-TW": "GHG Protocol", "en": "GHG Protocol"},
    "dash.col.cbam": {"zh-TW": "EU CBAM", "en": "EU CBAM"},
    "dash.col.ifrs": {"zh-TW": "IFRS S2", "en": "IFRS S2"},
    "dash.col.qa": {"zh-TW": "資料檢查", "en": "Data check"},
    "dash.framework_title": {
        "zh-TW": "準則涵蓋範圍",
        "en": "Framework coverage",
    },
    "dash.enabled": {"zh-TW": "已啟用", "en": "Enabled"},
    "dash.disabled": {"zh-TW": "未啟用", "en": "Not enabled"},
    "dash.rows": {"zh-TW": "{n} 筆評估", "en": "{n} evaluation rows"},
    # Activity page
    "act.title": {"zh-TW": "活動資料", "en": "Activity Data"},
    "act.subtitle": {
        "zh-TW": "從來源證據一路追蹤到排放計算與準則用途。",
        "en": "Trace each activity from evidence to calculation and framework use.",
    },
    "act.help": {
        "zh-TW": (
            "1. 先選一筆活動。\n"
            "2. 查看它目前能不能計算。\n"
            "3. 如果不能算，系統會告訴你缺什麼。\n"
            "4. 再查看來源證據及各準則如何使用它。"
        ),
        "en": (
            "1. Select an activity.\n"
            "2. See whether it can be calculated.\n"
            "3. If not, the app explains what is missing.\n"
            "4. Then review evidence and framework use."
        ),
    },
    "act.select_hint": {
        "zh-TW": "請先點選一筆活動，下方會顯示完整資料。",
        "en": "Select an activity row to see full details below.",
    },
    "act.filter_search": {"zh-TW": "搜尋", "en": "Search"},
    "act.filter_type": {"zh-TW": "活動類型", "en": "Activity type"},
    "act.filter_status": {"zh-TW": "計算狀態", "en": "Calculation status"},
    "act.filter_attention": {"zh-TW": "需要處理", "en": "Attention required"},
    "act.filter_all": {"zh-TW": "全部", "en": "All"},
    "act.filter_yes": {"zh-TW": "是", "en": "Yes"},
    "act.filter_no": {"zh-TW": "否", "en": "No"},
    "act.tab.summary": {"zh-TW": "總覽", "en": "Summary"},
    "act.tab.calc": {"zh-TW": "計算", "en": "Calculation"},
    "act.tab.evidence": {"zh-TW": "來源證據", "en": "Evidence"},
    "act.tab.frameworks": {"zh-TW": "準則分析", "en": "Frameworks"},
    "act.tab.tech": {"zh-TW": "進階技術資料", "en": "Technical details"},
    "act.can_calculate": {"zh-TW": "可以計算", "en": "Can calculate"},
    "act.cannot_calculate": {"zh-TW": "目前無法計算", "en": "Cannot calculate yet"},
    "act.why_blocked": {
        "zh-TW": "為什麼現在不能算？",
        "en": "Why this cannot be calculated yet",
    },
    "act.what_next": {
        "zh-TW": "下一步需要什麼？",
        "en": "What is needed next",
    },
    "act.no_zero": {
        "zh-TW": "排放量：未回報（缺少資料不會顯示為 0）",
        "en": "Emissions: not reported (gaps are not shown as zero)",
    },
    # Issues
    "iss.title": {"zh-TW": "待處理問題", "en": "Issues & Actions"},
    "iss.subtitle": {
        "zh-TW": "系統不會猜測缺少的資料；這裡告訴你下一步該補什麼。",
        "en": (
            "The system does not guess missing data; this list tells you "
            "what to collect next."
        ),
    },
    "iss.help": {
        "zh-TW": "這裡就是你的待辦清單。先處理高優先問題，再重新執行分析。",
        "en": (
            "This is your task list. Resolve high-priority issues, "
            "then run analysis again."
        ),
    },
    "iss.metric_open": {"zh-TW": "待處理", "en": "Open issues"},
    "iss.metric_critical": {"zh-TW": "重大", "en": "Critical"},
    "iss.metric_high": {"zh-TW": "高優先", "en": "High priority"},
    "iss.metric_affected": {"zh-TW": "受影響活動", "en": "Affected activities"},
    "iss.filter_severity": {"zh-TW": "優先程度", "en": "Severity"},
    "iss.filter_type": {"zh-TW": "問題類型", "en": "Issue type"},
    "iss.filter_activity": {"zh-TW": "活動", "en": "Activity"},
    "iss.col.priority": {"zh-TW": "優先程度", "en": "Priority"},
    "iss.col.activity": {"zh-TW": "活動", "en": "Activity"},
    "iss.col.issue": {"zh-TW": "問題", "en": "Issue"},
    "iss.col.why": {"zh-TW": "原因", "en": "Why it matters"},
    "iss.col.next": {"zh-TW": "下一步", "en": "Recommended action"},
    "iss.detail.problem": {"zh-TW": "問題", "en": "Problem"},
    "iss.detail.why": {"zh-TW": "為什麼重要", "en": "Why it matters"},
    "iss.detail.next": {"zh-TW": "下一步怎麼做", "en": "What to do next"},
    "iss.detail.allowed": {
        "zh-TW": "目前仍可以怎麼使用",
        "en": "Allowed use",
    },
    "iss.detail.prohibited": {
        "zh-TW": "目前不可怎麼使用",
        "en": "Do not use for",
    },
    "iss.detail.related": {"zh-TW": "相關資料", "en": "Related evidence"},
    "iss.empty": {
        "zh-TW": "目前沒有待處理的核心資料問題。",
        "en": "No open core data-quality issues.",
    },
    # Frameworks
    "fw.title": {"zh-TW": "準則分析", "en": "Frameworks"},
    "fw.subtitle": {
        "zh-TW": "同一筆碳資料，可以回答三種不同的問題。",
        "en": "One evidence ledger, three different questions.",
    },
    "fw.help": {
        "zh-TW": "這三個準則在回答不同問題，不要把它們當成同一套計算。",
        "en": (
            "These frameworks answer different questions — do not merge "
            "them into one calculation."
        ),
    },
    "fw.ghg_card_title": {"zh-TW": "公司碳盤查", "en": "Corporate GHG inventory"},
    "fw.ghg_question": {
        "zh-TW": "「這筆排放在公司盤查裡屬於哪個 Scope？」",
        "en": "“Which Scope does this belong to in the corporate inventory?”",
    },
    "fw.ghg_examples": {
        "zh-TW": (
            "天然氣 → Scope 1｜公司車柴油 → Scope 1｜"
            "外購電力 → Scope 2｜採購鋼材 → Scope 3"
        ),
        "en": (
            "Natural gas → Scope 1 · Fleet diesel → Scope 1 · "
            "Electricity → Scope 2 · Steel → Scope 3"
        ),
    },
    "fw.cbam_card_title": {
        "zh-TW": "歐盟出口產品碳資料",
        "en": "EU export product carbon data",
    },
    "fw.cbam_question": {
        "zh-TW": "「這筆資料跟出口歐盟的產品有什麼關係？」",
        "en": "“How does this record relate to an EU-exported product?”",
    },
    "fw.cbam_note": {
        "zh-TW": "不是把 Scope 1、2、3 直接搬過來使用。",
        "en": "This is not a direct copy of Scope 1 / 2 / 3.",
    },
    "fw.ifrs_card_title": {
        "zh-TW": "氣候資訊揭露準備",
        "en": "Climate disclosure readiness",
    },
    "fw.ifrs_question": {
        "zh-TW": "「目前的碳資料是否足以支援氣候相關揭露？」",
        "en": "“Is current carbon evidence enough to support climate disclosure prep?”",
    },
    "fw.ifrs_note": {
        "zh-TW": "不是重新計算一次排放。",
        "en": "This does not recalculate emissions.",
    },
    "fw.cbam_warning": {
        "zh-TW": "CN 7318 為示範假設，不是正式海關分類判定。",
        "en": "CN 7318 is a demo assumption — not a formal customs classification.",
    },
    "fw.ifrs_warning": {
        "zh-TW": "這是資料準備度判斷，不是 IFRS S2 合規判定。",
        "en": (
            "This is a data-readiness assessment, not an IFRS S2 "
            "compliance judgment."
        ),
    },
    "fw.disabled": {
        "zh-TW": "尚未執行這項分析。請在左側勾選此項目後，重新按「開始分析」。",
        "en": (
            "Not run for this analysis. Enable it in the sidebar and "
            "run analysis again."
        ),
    },
    "fw.disabled_title": {
        "zh-TW": "尚未執行此分析",
        "en": "Not run for this analysis",
    },
    "fw.col.activity": {"zh-TW": "活動", "en": "Activity"},
    "fw.col.scope": {"zh-TW": "Scope", "en": "Scope"},
    "fw.col.type": {"zh-TW": "類型", "en": "Category / type"},
    "fw.col.status": {"zh-TW": "狀態", "en": "Status"},
    "fw.col.reason": {"zh-TW": "說明", "en": "Reason"},
    "fw.col.role": {"zh-TW": "CBAM 用途", "en": "CBAM role"},
    "fw.col.relevance": {"zh-TW": "相關性", "en": "Relevance"},
    "fw.col.missing": {"zh-TW": "缺少資料", "en": "What is missing"},
    "fw.col.evidence_role": {"zh-TW": "資料角色", "en": "Evidence role"},
    "fw.col.readiness": {"zh-TW": "準備狀態", "en": "Readiness"},
    # Audit
    "aud.title": {"zh-TW": "稽核與匯出", "en": "Audit & Export"},
    "aud.hero": {
        "zh-TW": "下載你的分析成果",
        "en": "Download your analysis results",
    },
    "aud.subtitle": {
        "zh-TW": "取得完整分析資料，或只下載需要補充的問題清單。",
        "en": "Download the full analysis bundle, or only the open-issue list.",
    },
    "aud.help": {
        "zh-TW": "一般使用者只需要下載成果。進階技術資訊主要提供稽核與工程追蹤。",
        "en": (
            "Most users only need the downloads. Advanced details are for "
            "audit and engineering traceability."
        ),
    },
    "aud.zip_title": {"zh-TW": "完整分析資料", "en": "Full analysis bundle"},
    "aud.zip_desc": {
        "zh-TW": "包含活動資料、排放計算、待處理問題、準則分析與證據追蹤資訊。",
        "en": (
            "Includes activities, calculations, open issues, framework "
            "outputs, and evidence trail files."
        ),
    },
    "aud.zip_button": {
        "zh-TW": "下載完整分析資料 (.zip)",
        "en": "Download full analysis (.zip)",
    },
    "aud.csv_title": {"zh-TW": "待處理問題", "en": "Open issues"},
    "aud.csv_desc": {
        "zh-TW": "可直接使用 Excel 開啟，方便整理需要補充的資料。",
        "en": "Open in Excel to track the data you still need to collect.",
    },
    "aud.csv_button": {
        "zh-TW": "下載待處理問題 (.csv)",
        "en": "Download open issues (.csv)",
    },
    "aud.info_title": {"zh-TW": "分析資訊", "en": "Analysis information"},
    "aud.evidence_title": {"zh-TW": "來源證據", "en": "Source evidence"},
    "aud.advanced": {"zh-TW": "進階技術資訊", "en": "Advanced technical details"},
    "aud.run_id": {"zh-TW": "Run ID", "en": "Run ID"},
    "aud.activities": {"zh-TW": "活動資料", "en": "Activities"},
    "aud.calculations": {"zh-TW": "排放計算", "en": "Calculations"},
    "aud.issues": {"zh-TW": "待處理問題", "en": "Open issues"},
    "aud.enabled": {"zh-TW": "已啟用分析", "en": "Enabled adapters"},
    # Tutorial
    "tut.title": {
        "zh-TW": "第一次使用 Carbon Evidence Ledger？",
        "en": "Using Carbon Evidence Ledger for the first time?",
    },
    "tut.subtitle": {
        "zh-TW": "不用先懂碳盤查，照下面四步就可以開始。",
        "en": (
            "You do not need carbon-accounting expertise — "
            "follow these four steps."
        ),
    },
    "tut.step1_title": {"zh-TW": "選擇分析內容", "en": "Choose what to analyze"},
    "tut.step1_body": {
        "zh-TW": (
            "公司碳盤查 / GHG Protocol：查看活動屬於 Scope 1、Scope 2 或 Scope 3。\n"
            "歐盟出口 / EU CBAM：查看出口歐盟產品需要哪些碳資料，以及目前還缺什麼。\n"
            "氣候揭露 / IFRS S2：查看目前碳資料是否足以支援氣候揭露準備。"
        ),
        "en": (
            "Corporate GHG / GHG Protocol: see Scope 1, 2, or 3.\n"
            "EU export / EU CBAM: see required product data and gaps.\n"
            "Climate disclosure / IFRS S2: see whether evidence supports "
            "disclosure prep."
        ),
    },
    "tut.step2_title": {
        "zh-TW": "按「開始分析」",
        "en": "Click Start analysis",
    },
    "tut.step2_body": {
        "zh-TW": (
            "系統會：整理活動資料；檢查資料品質；計算目前可以計算的排放；"
            "執行你選擇的準則分析。"
        ),
        "en": (
            "The app will organize activity data, check data quality, "
            "calculate what is currently calculable, and run selected frameworks."
        ),
    },
    "tut.step3_title": {
        "zh-TW": "先處理「待處理問題」",
        "en": "Start with open issues",
    },
    "tut.step3_body": {
        "zh-TW": (
            "黃色或紅色並不表示排放量是零。它表示資料不足，因此系統拒絕猜測。"
            "你會看到：缺什麼、為什麼需要、下一步應該取得什麼資料。"
        ),
        "en": (
            "Yellow or red does not mean emissions are zero. "
            "It means data is incomplete, so the system refuses to guess. "
            "You will see what is missing, why it matters, "
            "and what to collect next."
        ),
    },
    "tut.step4_title": {
        "zh-TW": "查看結果與下載",
        "en": "Review results and download",
    },
    "tut.step4_body": {
        "zh-TW": (
            "你可以查看：每筆活動、排放計算、來源證據、Scope 1 / 2 / 3、"
            "CBAM 用途、IFRS S2 資料準備度。最後下載完整結果。"
        ),
        "en": (
            "Review each activity, calculations, evidence, "
            "Scope 1 / 2 / 3, CBAM roles, and IFRS S2 readiness — "
            "then download the full bundle."
        ),
    },
    "tut.footer": {
        "zh-TW": (
            "目前是示範版本，使用內建的虛構公司資料。"
            "尚未支援自行上傳公司的真實檔案。"
        ),
        "en": (
            "This is a synthetic demonstration. Real company file upload "
            "is not available yet."
        ),
    },
    "tut.start": {"zh-TW": "開始使用", "en": "Get started"},
    # Explanations used in view models
    "explain.calculated": {
        "zh-TW": "已用已驗證輸入與對應排放係數完成計算。",
        "en": "Emissions were calculated from verified inputs and a matched factor.",
    },
    "explain.blocked_missing_conversion": {
        "zh-TW": "缺少已驗證的轉換資料，因此目前無法計算。",
        "en": (
            "Calculation is blocked until verified conversion evidence "
            "is registered."
        ),
    },
    "explain.no_factor_configured": {
        "zh-TW": "尚未設定適用的排放係數。",
        "en": "No suitable emission factor is configured for this activity.",
    },
    "explain.not_emissions_activity": {
        "zh-TW": "這筆是輔助營運資料，不是排放來源本身。",
        "en": "This record is supporting operational data, not an emissions source.",
    },
    "next.blocked_missing_conversion": {
        "zh-TW": "取得並登錄所需的已驗證轉換證據。",
        "en": "Obtain and register the required verified conversion evidence.",
    },
    "next.no_factor_configured": {
        "zh-TW": "選定並文件化適用的排放係數後再計算。",
        "en": "Select and document an appropriate emission factor before calculation.",
    },
    "next.calculated": {
        "zh-TW": "此筆計算無需額外動作。",
        "en": "No calculation action required for this record.",
    },
    "next.not_emissions_activity": {
        "zh-TW": "保留作為輔助或分母證據即可。",
        "en": "Keep as supporting operational or denominator evidence.",
    },
    "severity.critical": {"zh-TW": "重大", "en": "Critical"},
    "severity.high": {"zh-TW": "高優先", "en": "High"},
    "severity.medium": {"zh-TW": "中", "en": "Medium"},
    "severity.low": {"zh-TW": "低", "en": "Low"},
    "severity.info": {"zh-TW": "資訊", "en": "Info"},
    # Charts (Phase 8E)
    "chart.calc_status.title": {
        "zh-TW": "活動計算狀態",
        "en": "Calculation status",
    },
    "chart.calc_status.help": {
        "zh-TW": "顯示目前 {n} 筆活動資料中，哪些已能計算、哪些仍缺資料。",
        "en": (
            "Shows which of the {n} activities can be calculated "
            "and which still have gaps."
        ),
    },
    "chart.activity_status.title": {
        "zh-TW": "各活動目前狀態",
        "en": "Activity status breakdown",
    },
    "chart.activity_status.help": {
        "zh-TW": "快速看出哪一筆活動已完成計算，哪一筆需要處理。",
        "en": "See at a glance which activities are calculated and which need action.",
    },
    "chart.emissions_contrib.help": {
        "zh-TW": "目前已計算排放量的來源活動（缺少資料的活動不會以 0 呈現）。",
        "en": (
            "Activities contributing to currently calculated emissions "
            "(gaps are not shown as zero)."
        ),
    },
    "chart.emissions_contrib.empty": {
        "zh-TW": "目前尚無已完成計算的活動排放量。",
        "en": "No calculated activity emissions yet.",
    },
    "chart.ghg_scope.title": {
        "zh-TW": "活動分類筆數",
        "en": "Activity classification count",
    },
    "chart.ghg_scope.help": {
        "zh-TW": "此圖顯示活動分類筆數，不代表各 Scope 的排放量占比。",
        "en": (
            "This chart shows activity classification counts, "
            "not emissions share by Scope."
        ),
    },
    "chart.cbam_roles.title": {
        "zh-TW": "CBAM 資料角色筆數",
        "en": "CBAM data-role counts",
    },
    "chart.cbam_roles.help": {
        "zh-TW": "依目前評估結果統計各 CBAM 資料角色出現次數。",
        "en": "Counts of CBAM data roles from the current evaluation.",
    },
    "chart.ifrs_ready.title": {
        "zh-TW": "IFRS S2 準備狀態筆數",
        "en": "IFRS S2 readiness counts",
    },
    "chart.ifrs_ready.help": {
        "zh-TW": "依目前評估結果統計準備狀態筆數，不是合規分數。",
        "en": (
            "Counts of readiness statuses from the current evaluation "
            "— not a compliance score."
        ),
    },
    "chart.issue_gaps.title": {
        "zh-TW": "缺少資料類型",
        "en": "Missing-data types",
    },
    "chart.issue_gaps.help": {
        "zh-TW": "目前待處理問題主要屬於哪些資料缺口類型。",
        "en": "Which kinds of data gaps appear in the open issues list.",
    },
    "chart.issue.missing_conversion": {
        "zh-TW": "缺少熱值 / 轉換資料",
        "en": "Missing heating-value / conversion data",
    },
    "chart.issue.missing_factor": {
        "zh-TW": "缺少排放係數",
        "en": "Missing emission factor",
    },
    "act.status_strip": {
        "zh-TW": "目前狀態",
        "en": "Current status",
    },
    # Phase 9A Data Intake
    "intake.title": {"zh-TW": "匯入公司資料", "en": "Import company data"},
    "intake.subtitle": {
        "zh-TW": "上傳 CSV 或 Excel，確認欄位後再進行碳資料分析。",
        "en": (
            "Upload a CSV or Excel file, confirm columns, "
            "then prepare data for carbon analysis."
        ),
    },
    "intake.intro": {
        "zh-TW": (
            "不需要先修改原本 Excel 欄位名稱。\n"
            "系統會先嘗試辨識你的欄位，再請你確認是否正確。\n\n"
            "第一次使用？\n\n"
            "你只需要準備一份表格，每一列代表一筆活動資料，例如：\n"
            "- 外購電力\n"
            "- 天然氣\n"
            "- 柴油\n"
            "- 採購鋼材\n"
            "- 生產數量"
        ),
        "en": (
            "You do not need to rename your Excel columns first.\n"
            "The system will try to recognize your columns, "
            "then ask you to confirm.\n\n"
            "First time here?\n\n"
            "Prepare one table where each row is an activity, for example:\n"
            "- Purchased electricity\n"
            "- Natural gas\n"
            "- Diesel\n"
            "- Purchased steel\n"
            "- Production quantity"
        ),
    },
    "intake.no_rename": {
        "zh-TW": (
            "不需要先修改原本 Excel 欄位名稱。\n"
            "系統會先嘗試辨識你的欄位，再請你確認是否正確。"
        ),
        "en": (
            "You do not need to rename your Excel columns first.\n"
            "The system will try to recognize your columns, then ask you to confirm."
        ),
    },
    "intake.suggest_sheet_title": {
        "zh-TW": "建議使用工作表",
        "en": "Suggested worksheet",
    },
    "intake.detect_result": {"zh-TW": "偵測結果：", "en": "Detection result:"},
    "intake.use_suggested_sheet": {
        "zh-TW": "使用建議工作表",
        "en": "Use suggested worksheet",
    },
    "intake.choose_other_sheet": {
        "zh-TW": "選擇其他工作表",
        "en": "Choose another worksheet",
    },
    "intake.header_ask": {
        "zh-TW": "哪一列是欄位名稱？",
        "en": "Which row contains the column names?",
    },
    "intake.header_confirm": {
        "zh-TW": "確認欄位名稱列",
        "en": "Confirm header row",
    },
    "intake.header_row_label": {
        "zh-TW": "第 {row} 列",
        "en": "Row {row}",
    },
    "intake.confidence_high": {
        "zh-TW": "系統已辨識",
        "en": "Recognized by the system",
    },
    "intake.confidence_medium": {
        "zh-TW": "請確認",
        "en": "Please confirm",
    },
    "intake.confidence_low": {
        "zh-TW": "需要你選擇",
        "en": "Needs your choice",
    },
    "intake.mapping_unknown": {
        "zh-TW": "我們無法確定這一欄代表什麼。請從下方選擇它的用途。",
        "en": (
            "We could not determine what this column means. "
            "Please choose its purpose below."
        ),
    },
    "intake.map_site": {"zh-TW": "廠區／場址欄位", "en": "Site / plant column"},
    "intake.field.activity_type": {"zh-TW": "活動類型", "en": "Activity type"},
    "intake.field.activity_value": {"zh-TW": "活動數量", "en": "Activity amount"},
    "intake.field.unit": {"zh-TW": "單位", "en": "Unit"},
    "intake.field.site_id": {"zh-TW": "廠區／場址", "en": "Site / plant"},
    "intake.field.start": {"zh-TW": "開始日期", "en": "Start date"},
    "intake.field.end": {"zh-TW": "結束日期", "en": "End date"},
    "intake.field.year_month": {
        "zh-TW": "年月（月報期間）",
        "en": "Year-month (monthly period)",
    },
    "intake.dates_year_month": {
        "zh-TW": "使用檔案中的年月欄位",
        "en": "Use a year-month column in the file",
    },
    "intake.map_year_month": {
        "zh-TW": "年月欄位",
        "en": "Year-month column",
    },
    "intake.year_month_preview_title": {
        "zh-TW": "系統將轉換為：",
        "en": "The system will convert this to:",
    },
    "intake.year_month_confirm": {
        "zh-TW": "確認此年月轉換",
        "en": "Confirm this year-month conversion",
    },
    "intake.reference_only_note": {
        "zh-TW": (
            "檔案中的「排放係數／排放量／計算結果」欄位僅供參考，"
            "不會當作本系統的計算依據。"
        ),
        "en": (
            "Uploaded emission-factor / emission-result columns are reference only "
            "and are not used as this system's calculation truth."
        ),
    },
    "intake.mapping_preview": {
        "zh-TW": "欄位對應建議",
        "en": "Suggested column mappings",
    },
    "intake.interpret.title": {
        "zh-TW": "我們看懂這份 Excel 了 ✓",
        "en": "We understand this Excel file ✓",
    },
    "intake.interpret.intro": {
        "zh-TW": "我們會這樣讀取你的資料：",
        "en": "Here is how we will read your data:",
    },
    "intake.interpret.activity_type": {
        "zh-TW": (
            "用來判斷每筆資料是外購電力、天然氣、柴油或其他活動。"
        ),
        "en": (
            "Used to tell whether each row is purchased electricity, "
            "natural gas, diesel, or another activity."
        ),
    },
    "intake.interpret.activity_value": {
        "zh-TW": "作為每筆活動的實際數量。",
        "en": "Used as the actual quantity for each activity.",
    },
    "intake.interpret.unit": {
        "zh-TW": "作為 kWh、m³、L、kg、t 等計量單位。",
        "en": "Used as the unit of measure, such as kWh, m³, L, kg, or t.",
    },
    "intake.interpret.site_id": {
        "zh-TW": "用來區分資料所屬的場址。",
        "en": "Used to tell which site each row belongs to.",
    },
    "intake.interpret.year_month": {
        "zh-TW": (
            "用來建立每筆活動的資料期間。\n"
            "例如 {example} 會轉成 {start} ～ {end}。"
        ),
        "en": (
            "Used to build the reporting period for each activity.\n"
            "For example, {example} becomes {start} – {end}."
        ),
    },
    "intake.interpret.start": {
        "zh-TW": "作為每筆活動的開始日期。",
        "en": "Used as the start date for each activity.",
    },
    "intake.interpret.end": {
        "zh-TW": "作為每筆活動的結束日期。",
        "en": "Used as the end date for each activity.",
    },
    "intake.interpret.ask": {
        "zh-TW": "這和你的 Excel 內容相符嗎？",
        "en": "Does this match your Excel content?",
    },
    "intake.interpret.need_help": {
        "zh-TW": (
            "有些欄位我們還不確定，需要你幫忙確認後才能繼續。"
        ),
        "en": (
            "Some columns are still unclear. "
            "Please adjust them before continuing."
        ),
    },
    "intake.btn.accept": {
        "zh-TW": "正確，繼續",
        "en": "Looks right, continue",
    },
    "intake.btn.accept_help": {
        "zh-TW": "接受目前的資料辨識結果，前往資料檢查。",
        "en": "Accept the current reading and continue to data checks.",
    },
    "intake.btn.fix": {
        "zh-TW": "有地方不對",
        "en": "Something is wrong",
    },
    "intake.btn.fix_help": {
        "zh-TW": "修改系統對 Excel 欄位的理解。",
        "en": "Change how the system reads your Excel columns.",
    },
    "intake.btn.validate_help": {
        "zh-TW": "只檢查資料能否轉成系統格式，不會開始計算碳排。",
        "en": (
            "Only checks whether the data can become the system format. "
            "It will not start carbon calculation."
        ),
    },
    "intake.btn.continue_help": {
        "zh-TW": "查看系統如何讀取你的 Excel 欄位。",
        "en": "See how the system will read your Excel columns.",
    },
    "intake.btn.use_sheet_help": {
        "zh-TW": "使用建議的工作表繼續讀取資料。",
        "en": "Continue using the suggested worksheet.",
    },
    "intake.btn.other_sheet_help": {
        "zh-TW": "改選其他工作表。",
        "en": "Pick a different worksheet instead.",
    },
    "intake.btn.header_help": {
        "zh-TW": "確認哪一列是欄位名稱，然後繼續。",
        "en": "Confirm which row has the column names, then continue.",
    },
    "intake.btn.show_advanced": {
        "zh-TW": "顯示進階設定",
        "en": "Show advanced settings",
    },
    "intake.btn.show_advanced_help": {
        "zh-TW": "檢視系統內部欄位名稱與其他進階選項。",
        "en": "View internal field names and other advanced options.",
    },
    "intake.advanced_canonical": {
        "zh-TW": "進階：系統內部欄位名稱",
        "en": "Advanced: internal field names",
    },
    "intake.step1": {"zh-TW": "01 上傳檔案", "en": "01 Upload file"},
    "intake.step2": {"zh-TW": "02 對應欄位", "en": "02 Map columns"},
    "intake.step3": {"zh-TW": "03 確認資料", "en": "03 Confirm data"},
    "intake.step4": {"zh-TW": "04 檢查結果", "en": "04 Validation result"},
    "intake.upload_label": {
        "zh-TW": "選擇公司資料檔案",
        "en": "Choose a company data file",
    },
    "intake.upload_help": {
        "zh-TW": "目前支援 CSV 與 XLSX。PDF 帳單與掃描文件將在後續版本支援。",
        "en": (
            "CSV and XLSX are supported now. "
            "PDF invoices and scanned documents come later."
        ),
    },
    "intake.template_button": {
        "zh-TW": "下載空白範本 (.csv)",
        "en": "Download blank template (.csv)",
    },
    "intake.example_button": {
        "zh-TW": "下載範例檔 (.csv)",
        "en": "Download example file (.csv)",
    },
    "intake.example_label": {
        "zh-TW": "範例資料，不會自動匯入",
        "en": "Example data only; it is not imported automatically.",
    },
    "intake.col_help_activity_type": {
        "zh-TW": "activity_type：活動類型，例如外購電力、天然氣、柴油、採購鋼材",
        "en": (
            "activity_type: activity type, e.g. purchased electricity, "
            "natural gas, diesel, purchased steel"
        ),
    },
    "intake.col_help_activity_value": {
        "zh-TW": "activity_value：實際數量或用量",
        "en": "activity_value: the actual quantity or usage amount",
    },
    "intake.col_help_unit": {
        "zh-TW": "unit：單位，例如 kWh、m3、L、t",
        "en": "unit: unit of measure, e.g. kWh, m3, L, t",
    },
    "intake.col_help_start": {
        "zh-TW": "activity_start_date：資料期間開始日",
        "en": "activity_start_date: reporting period start date",
    },
    "intake.col_help_end": {
        "zh-TW": "activity_end_date：資料期間結束日",
        "en": "activity_end_date: reporting period end date",
    },
    "intake.preview_title": {"zh-TW": "檔案預覽", "en": "File preview"},
    "intake.file_name": {"zh-TW": "檔名", "en": "File name"},
    "intake.file_type": {"zh-TW": "檔案類型", "en": "File type"},
    "intake.row_count": {"zh-TW": "列數", "en": "Rows"},
    "intake.col_count": {"zh-TW": "欄數", "en": "Columns"},
    "intake.sheet_label": {"zh-TW": "選擇工作表", "en": "Choose worksheet"},
    "intake.sheet_name": {"zh-TW": "工作表", "en": "Worksheet"},
    "intake.err_too_large": {
        "zh-TW": "檔案太大。\n目前單一檔案上限為 10 MB。",
        "en": "The file is too large.\nThe current limit is 10 MB per file.",
    },
    "intake.err_encoding": {
        "zh-TW": "請將 CSV 另存為 UTF-8 編碼後再上傳。",
        "en": "Please re-save the CSV as UTF-8 and upload again.",
    },
    "intake.err_unsupported": {
        "zh-TW": "目前僅支援 CSV 與 XLSX 檔案。",
        "en": "Only CSV and XLSX files are supported right now.",
    },
    "intake.map_activity_type": {
        "zh-TW": "活動類型欄位",
        "en": "Activity type column",
    },
    "intake.map_activity_value": {
        "zh-TW": "活動數量欄位",
        "en": "Activity amount column",
    },
    "intake.map_unit": {"zh-TW": "單位欄位", "en": "Unit column"},
    "intake.dates_in_file": {
        "zh-TW": "日期在檔案欄位中",
        "en": "Dates are in file columns",
    },
    "intake.dates_period": {
        "zh-TW": "使用同一資料期間",
        "en": "Use one reporting period",
    },
    "intake.map_start": {"zh-TW": "開始日期欄位", "en": "Start date column"},
    "intake.map_end": {"zh-TW": "結束日期欄位", "en": "End date column"},
    "intake.period_start": {"zh-TW": "開始日期", "en": "Start date"},
    "intake.period_end": {"zh-TW": "結束日期", "en": "End date"},
    "intake.value_map_activity": {
        "zh-TW": "活動類型對應",
        "en": "Activity type mapping",
    },
    "intake.value_map_unit": {"zh-TW": "單位對應", "en": "Unit mapping"},
    "intake.choose": {"zh-TW": "請選擇", "en": "Please choose"},
    "intake.source_name": {"zh-TW": "資料來源名稱", "en": "Source name"},
    "intake.site_id": {"zh-TW": "場址 ID", "en": "Site ID"},
    "intake.document_date": {"zh-TW": "文件日期", "en": "Document date"},
    "intake.data_quality": {"zh-TW": "資料品質", "en": "Data quality"},
    "intake.quality.primary": {
        "zh-TW": "公司原始紀錄",
        "en": "Primary company record",
    },
    "intake.quality.secondary": {"zh-TW": "二級資料", "en": "Secondary data"},
    "intake.quality.estimated": {"zh-TW": "估算資料", "en": "Estimated data"},
    "intake.quality.unknown": {"zh-TW": "不確定", "en": "Unknown"},
    "intake.confirm_title": {
        "zh-TW": "確認匯入資料",
        "en": "Confirm imported data",
    },
    "intake.advanced": {"zh-TW": "進階欄位", "en": "Advanced fields"},
    "intake.col.activity": {"zh-TW": "活動", "en": "Activity"},
    "intake.col.amount": {"zh-TW": "數量", "en": "Amount"},
    "intake.col.unit": {"zh-TW": "單位", "en": "Unit"},
    "intake.col.start": {"zh-TW": "開始日期", "en": "Start date"},
    "intake.col.end": {"zh-TW": "結束日期", "en": "End date"},
    "intake.col.quality": {"zh-TW": "資料品質", "en": "Data quality"},
    "intake.col.review": {
        "zh-TW": "需要人工確認",
        "en": "Needs human review",
    },
    "intake.result_accepted": {"zh-TW": "可接受", "en": "Accepted"},
    "intake.result_rejected": {"zh-TW": "需要修正", "en": "Needs correction"},
    "intake.result_total": {"zh-TW": "總筆數", "en": "Total rows"},
    "intake.success": {
        "zh-TW": "資料格式檢查完成。",
        "en": "Data-format checks completed.",
    },
    "intake.partial": {
        "zh-TW": "有部分資料需要修正。",
        "en": "Some rows need correction.",
    },
    "intake.rejected_title": {
        "zh-TW": "需要修正的資料",
        "en": "Rows that need correction",
    },
    "intake.rej.row": {"zh-TW": "原始列", "en": "Source row"},
    "intake.rej.field": {"zh-TW": "欄位", "en": "Field"},
    "intake.rej.issue": {"zh-TW": "問題", "en": "Issue"},
    "intake.rej.value": {"zh-TW": "目前值", "en": "Current value"},
    "intake.next_phase": {
        "zh-TW": (
            "資料格式已準備完成。\n"
            "下一階段會將通過驗證的資料接入排放計算與準則分析。"
        ),
        "en": (
            "Data format is ready.\n"
            "A later phase will connect accepted rows to emissions "
            "calculation and framework analysis."
        ),
    },
    "intake.demo_notice": {
        "zh-TW": "目前匯入資料尚未取代示範分析結果。",
        "en": (
            "Uploaded data does not replace the demo analysis results yet."
        ),
    },
    "intake.run_validation": {
        "zh-TW": "資料格式檢查",
        "en": "Check data format",
    },
    "intake.continue_mapping": {
        "zh-TW": "繼續",
        "en": "Continue",
    },
    "fw.purpose_ghg": {
        "zh-TW": "把公司活動分類到 Scope 1、2、3 或不適用。",
        "en": "Classifies corporate activities into Scope 1, 2, 3, or not applicable.",
    },
    "fw.purpose_cbam": {
        "zh-TW": "對合成 CN 7318 情境對應資料角色與缺口。",
        "en": "Maps activities to data roles for the synthetic CN 7318 scenario.",
    },
    "fw.purpose_ifrs": {
        "zh-TW": "只評估氣候指標相關證據的技術準備度。",
        "en": "Assesses technical climate-metrics evidence readiness only.",
    },
}


def normalize_lang(lang: str | None) -> str:
    """Return a supported language code."""
    if lang in (LANG_ZH, LANG_EN):
        return lang
    if lang in LANG_OPTION_TO_CODE:
        return LANG_OPTION_TO_CODE[lang]
    return DEFAULT_LANG


def t(key: str, lang: str | None = None, **kwargs: Any) -> str:
    """Translate a UI key for the active language."""
    code = normalize_lang(lang)
    entry = MESSAGES.get(key)
    if entry is None:
        return key
    text = entry.get(code) or entry.get(LANG_EN) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text


def status_label(code: str, lang: str | None = None) -> str:
    """Map an internal status code to a beginner-facing label."""
    key = f"status.{code}"
    if key in MESSAGES:
        return t(key, lang)
    cleaned = str(code or "").strip()
    if not cleaned:
        return t("status.unknown", lang)
    return cleaned.replace("_", " ")
