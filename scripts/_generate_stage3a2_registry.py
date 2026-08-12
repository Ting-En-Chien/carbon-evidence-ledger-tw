"""One-shot Stage 3A.2 registry generator. Not part of the runtime package."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

TODAY = "2026-08-12"
ROOT = Path(__file__).resolve().parents[1]

SOURCE_FIELDS = [
    "source_id",
    "jurisdiction",
    "authority",
    "source_class",
    "source_type",
    "document_title",
    "official_url",
    "publication_date",
    "effective_date",
    "retrieved_date",
    "version",
    "language",
    "authority_level",
    "authority_rank",
    "status",
    "notes",
    "monitor_enabled",
    "monitor_frequency",
    "last_checked_at",
    "last_successful_fetch_at",
    "last_changed_at",
    "http_etag",
    "http_last_modified",
    "content_hash",
    "fetch_status",
    "fetch_error",
    "consecutive_failures",
    "freshness_status",
    "next_check_at",
    "current_source_version",
    "previous_source_version",
]

RULE_FIELDS = [
    "rule_id",
    "jurisdiction",
    "framework",
    "authority",
    "source_id",
    "official_document",
    "citation",
    "paragraph",
    "content_area",
    "requirement_type",
    "requirement_title",
    "requirement_summary",
    "entity_type",
    "applicability_condition",
    "applicability_condition_machine",
    "required_action",
    "required_data",
    "required_evidence",
    "reporting_period_rule",
    "deadline_rule",
    "assurance_requirement",
    "transition_relief",
    "concept_layer",
    "international_standard_version",
    "taiwan_recognised_version",
    "international_effective_date",
    "taiwan_recognition_date",
    "taiwan_status",
    "publication_date",
    "source_version",
    "rule_effective_from",
    "rule_effective_to",
    "rule_status",
    "supersedes_rule_id",
    "superseded_by_rule_id",
    "last_verified_at",
    "product_support_status",
    "verification_status",
    "version",
    "notes",
]

GEN = "general_listed_company|general_otc_company"
sources: list[dict[str, str]] = []
rules: list[dict[str, str]] = []


def S(**kw: str) -> dict[str, str]:
    base = {k: "" for k in SOURCE_FIELDS}
    base.update(
        {
            "monitor_enabled": "true",
            "monitor_frequency": "normal_regulatory_source",
            "freshness_status": "CHECK_DUE",
            "consecutive_failures": "0",
            "language": "zh-TW",
            "status": "ACTIVE",
            "retrieved_date": TODAY,
        }
    )
    base.update(kw)
    if not base["current_source_version"]:
        base["current_source_version"] = base.get("version", "")
    return base


def R(**kw: str) -> dict[str, str]:
    base = {k: "" for k in RULE_FIELDS}
    base.update(
        {
            "taiwan_status": "N/A",
            "version": "3A.2",
            "last_verified_at": TODAY,
            "product_support_status": "IN_V1_SCOPE",
            "entity_type": "unresolved",
            "rule_status": "ACTIVE",
        }
    )
    base.update(kw)
    return base


def add_s(**kw: str) -> None:
    sources.append(S(**kw))


def add_r(**kw: str) -> None:
    rules.append(R(**kw))


def build_sources() -> None:
    add_s(
        source_id="src_tw_fsc_law_portal",
        jurisdiction="TW",
        authority="FSC",
        source_class="LAW_REGULATION",
        source_type="official_legal_portal",
        document_title="金融監督管理委員會主管法規共用系統",
        official_url="https://law.fsc.gov.tw/",
        authority_level="AUTHORITATIVE",
        authority_rank="10",
        version="portal_live",
        monitor_frequency="high_change_source",
    )
    add_s(
        source_id="src_tw_annual_report_rules_fl007032",
        jurisdiction="TW",
        authority="FSC",
        source_class="LAW_REGULATION",
        source_type="regulation",
        document_title="公開發行公司年報應行記載事項準則",
        official_url="https://law.fsc.gov.tw/LawContent.aspx?id=FL007032",
        publication_date="2025-11-07",
        effective_date="2025-11-07",
        version="2025-12-19_amended",
        authority_level="AUTHORITATIVE",
        authority_rank="10",
    )
    add_s(
        source_id="src_tw_order_11403851756",
        jurisdiction="TW",
        authority="FSC",
        source_class="FSC_ORDER",
        source_type="fsc_order",
        document_title="金管證審字第11403851756號令",
        official_url="https://law.fsc.gov.tw/LawContent.aspx?id=GL004194",
        publication_date="2025-11-12",
        effective_date="2025-11-12",
        version="金管證審字第11403851756號",
        authority_level="AUTHORITATIVE",
        authority_rank="20",
    )
    add_s(
        source_id="src_tw_order_11403851755",
        jurisdiction="TW",
        authority="FSC",
        source_class="FSC_ORDER",
        source_type="fsc_order",
        document_title="金管證審字第11403851755號令",
        official_url=(
            "https://www.fsc.gov.tw/ch/home.jsp?dataserno=202511120001"
            "&dtable=NewsLaw&id=128&mcustomize=lawnew_view.jsp&parentpath=0%2C3"
        ),
        publication_date="2025-11-12",
        effective_date="2025-11-12",
        version="金管證審字第11403851755號",
        authority_level="AUTHORITATIVE",
        authority_rank="20",
    )
    add_s(
        source_id="src_tw_sfb_ifrs_download_area",
        jurisdiction="TW",
        authority="SFB/FSC",
        source_class="OFFICIAL_GUIDANCE",
        source_type="official_portal",
        document_title="國際財務報導準則（IFRS）下載專區",
        official_url="https://ifrs.sfb.gov.tw/ifrs/index.cfm",
        version="portal_live",
        authority_level="AUTHORITATIVE",
        authority_rank="20",
        monitor_frequency="high_change_source",
    )
    add_s(
        source_id="src_tw_order_11402739247_fi",
        jurisdiction="TW",
        authority="FSC Banking Bureau",
        source_class="FSC_ORDER",
        source_type="fsc_order",
        document_title="金管銀法字第11402739247號令",
        official_url=(
            "https://www.banking.gov.tw/ch/home.jsp?dataserno=202512160003"
            "&id=579&mcustomize=lawnew_view.jsp&parentpath=0%2C525"
        ),
        publication_date="2025-12-16",
        effective_date="2025-12-18",
        version="金管銀法字第11402739247號",
        authority_level="AUTHORITATIVE",
        authority_rank="20",
    )
    add_s(
        source_id="src_tw_bank_annual_report_fl006611",
        jurisdiction="TW",
        authority="FSC",
        source_class="LAW_REGULATION",
        source_type="regulation",
        document_title="銀行年報應行記載事項準則",
        official_url="https://law.fsc.gov.tw/LawContent.aspx?id=FL006611",
        publication_date="2025-12-16",
        version="2025-12_amended",
        authority_level="AUTHORITATIVE",
        authority_rank="10",
    )
    add_s(
        source_id="src_tw_fhc_annual_report_fl006626",
        jurisdiction="TW",
        authority="FSC",
        source_class="LAW_REGULATION",
        source_type="regulation",
        document_title="金融控股公司年報應行記載事項準則",
        official_url="https://law.fsc.gov.tw/LawContent.aspx?id=FL006626",
        publication_date="2025-12-16",
        version="2025-12_amended",
        authority_level="AUTHORITATIVE",
        authority_rank="10",
    )
    add_s(
        source_id="src_tw_bills_annual_report_fl006628",
        jurisdiction="TW",
        authority="FSC",
        source_class="LAW_REGULATION",
        source_type="regulation",
        document_title="票券金融公司年報應行記載事項準則",
        official_url="https://law.fsc.gov.tw/LawContent.aspx?id=FL006628",
        publication_date="2025-12-16",
        version="2025-12_amended",
        authority_level="AUTHORITATIVE",
        authority_rank="10",
    )
    add_s(
        source_id="src_tw_securities_fin_report_fl007040",
        jurisdiction="TW",
        authority="FSC",
        source_class="LAW_REGULATION",
        source_type="regulation",
        document_title="證券商財務報告編製準則",
        official_url="https://law.fsc.gov.tw/LawContent.aspx?id=FL007040",
        publication_date="2025-12-24",
        effective_date="2025-12-24",
        version="2025-12-24_Art32-1",
        authority_level="AUTHORITATIVE",
        authority_rank="10",
        notes="Art.32-1 sustainability family for securities firms.",
    )
    add_s(
        source_id="src_tw_order_11403856095_securities",
        jurisdiction="TW",
        authority="FSC",
        source_class="FSC_ORDER",
        source_type="fsc_order",
        document_title="金管證券字第11403856095號令",
        official_url=(
            "https://www.sfb.gov.tw/ch/home.jsp?dataserno=202512260004"
            "&id=88&mcustomize=lawnews_view.jsp&parentpath=0%2C3"
        ),
        publication_date="2025-12-26",
        effective_date="2025-12-26",
        version="金管證券字第11403856095號",
        authority_level="AUTHORITATIVE",
        authority_rank="20",
    )
    add_s(
        source_id="src_tw_order_11403856094_recognised",
        jurisdiction="TW",
        authority="FSC",
        source_class="FSC_ORDER",
        source_type="fsc_order",
        document_title="金管證券字第11403856094號令",
        official_url=(
            "https://www.fsc.gov.tw/ch/home.jsp?dataserno=202512260005"
            "&dtable=NewsLaw&id=3&mcustomize=lawnew_view.jsp&parentpath=0"
        ),
        publication_date="2025-12-26",
        effective_date="2025-12-26",
        version="金管證券字第11403856094號",
        authority_level="AUTHORITATIVE",
        authority_rank="20",
    )
    add_s(
        source_id="src_tw_fcm_fin_report_fl021990",
        jurisdiction="TW",
        authority="FSC",
        source_class="LAW_REGULATION",
        source_type="regulation",
        document_title="期貨商財務報告編製準則",
        official_url="https://law.fsc.gov.tw/LawContent.aspx?id=FL021990",
        publication_date="2025-12-24",
        effective_date="2025-12-24",
        version="2025-12-24_Art34-1",
        authority_level="AUTHORITATIVE",
        authority_rank="10",
    )
    add_s(
        source_id="src_tw_order_11403856096_fcm",
        jurisdiction="TW",
        authority="FSC",
        source_class="FSC_ORDER",
        source_type="fsc_order",
        document_title="金管證券字第11403856096號令",
        official_url=(
            "https://www.fsc.gov.tw/ch/home.jsp?dataserno=202512260003"
            "&dtable=NewsLaw&id=3&mcustomize=lawnew_view.jsp&parentpath=0"
        ),
        publication_date="2025-12-26",
        effective_date="2025-12-26",
        version="金管證券字第11403856096號",
        authority_level="AUTHORITATIVE",
        authority_rank="20",
    )
    for sid, title, url, rank, freq, level, sclass in [
        (
            "src_tw_tpex_isds_portal",
            "接軌 IFRS 永續揭露準則專區（ISDS）",
            "https://isds.tpex.org.tw/IFRS/front/#/main/home",
            "40",
            "normal_regulatory_source",
            "OFFICIAL_GUIDANCE",
            "OFFICIAL_GUIDANCE",
        ),
        (
            "src_tw_twse_impl_plan_example",
            "IFRS 永續揭露準則導入計畫參考範例",
            "https://www.twse.com.tw/market_insights/zh/detail/8a8216d69236c2e30192db1f6c6902fb",
            "50",
            "normal_regulatory_source",
            "OFFICIAL_EXAMPLE",
            "OFFICIAL_EXAMPLE",
        ),
        (
            "src_tw_twse_impl_plan_progress_template",
            "導入 IFRS 永續揭露準則執行情形進度表",
            "https://twse-regulation.twse.com.tw/TW/GetFile.ashx?FILEID=0000371549",
            "30",
            "normal_regulatory_source",
            "AUTHORITATIVE",
            "TWSE_TPEX_OFFICIAL_RULE_OR_ANNOUNCEMENT",
        ),
        (
            "src_tw_sfb_press_20251028",
            "金管會年報準則修正新聞稿（2025-10-28）",
            "https://www.sfb.gov.tw/ch/home.jsp?dataserno=202510280004&dtable=News&id=95&mcustomize=news_view.jsp&parentpath=0%2C2",
            "60",
            "normal_regulatory_source",
            "EXPLANATORY",
            "EXPLANATORY_MATERIAL",
        ),
        (
            "src_tw_fsc_roadmap_press_20230817",
            "金管會接軌 IFRS 永續揭露準則藍圖新聞稿（2023-08-17）",
            "https://www.fsc.gov.tw/ch/home.jsp?dataserno=202308170002&dtable=News&id=96&mcustomize=news_view.jsp&parentpath=0%2C2",
            "60",
            "normal_regulatory_source",
            "EXPLANATORY",
            "EXPLANATORY_MATERIAL",
        ),
        (
            "src_tw_tpex_qa_20250402",
            "IFRS 永續揭露準則問答集（2025.4.2）",
            "https://isds.tpex.org.tw/download/20250402IFRS%E6%B0%B8%E7%BA%8C%E6%BA%96%E5%89%87%E5%95%8F%E7%AD%94%E9%9B%86.pdf",
            "40",
            "normal_regulatory_source",
            "OFFICIAL_GUIDANCE",
            "OFFICIAL_GUIDANCE",
        ),
        (
            "src_tw_fsc_portal",
            "金融監督管理委員會全球資訊網",
            "https://www.fsc.gov.tw/",
            "60",
            "high_change_source",
            "EXPLANATORY",
            "EXPLANATORY_MATERIAL",
        ),
        (
            "src_tw_sfb_portal",
            "證券期貨局全球資訊網",
            "https://www.sfb.gov.tw/",
            "60",
            "high_change_source",
            "EXPLANATORY",
            "EXPLANATORY_MATERIAL",
        ),
        (
            "src_tw_twse_portal",
            "臺灣證券交易所",
            "https://www.twse.com.tw/",
            "30",
            "normal_regulatory_source",
            "AUTHORITATIVE",
            "TWSE_TPEX_OFFICIAL_RULE_OR_ANNOUNCEMENT",
        ),
        (
            "src_tw_tpex_portal",
            "證券櫃檯買賣中心",
            "https://www.tpex.org.tw/",
            "30",
            "normal_regulatory_source",
            "AUTHORITATIVE",
            "TWSE_TPEX_OFFICIAL_RULE_OR_ANNOUNCEMENT",
        ),
        (
            "src_tw_moenv_ghg_registry",
            "環境部溫室氣體排放量盤查登錄及查驗管理資訊平台",
            "https://ghgregistry.moenv.gov.tw/",
            "40",
            "normal_regulatory_source",
            "OFFICIAL_GUIDANCE",
            "OFFICIAL_GUIDANCE",
        ),
        (
            "src_tw_moenv_oaout",
            "環境部氣候變遷署公開資訊入口",
            "https://oaout.moenv.gov.tw/",
            "40",
            "normal_regulatory_source",
            "OFFICIAL_GUIDANCE",
            "OFFICIAL_GUIDANCE",
        ),
    ]:
        add_s(
            source_id=sid,
            jurisdiction="TW",
            authority="TW official",
            source_class=sclass,
            source_type="official_portal",
            document_title=title,
            official_url=url,
            version="portal_or_doc",
            authority_level=level,
            authority_rank=rank,
            monitor_frequency=freq,
        )
    add_s(
        source_id="src_issb_ifrs_s1_2023",
        jurisdiction="INTL",
        authority="ISSB/IFRS Foundation",
        source_class="LAW_REGULATION",
        source_type="international_standard_page",
        document_title="IFRS S1 General Requirements",
        official_url=(
            "https://www.ifrs.org/issued-standards/"
            "ifrs-sustainability-standards-navigator/ifrs-s1-general-requirements/"
        ),
        publication_date="2023-06-26",
        effective_date="2024-01-01",
        version="2023-06",
        language="en",
        authority_level="AUTHORITATIVE",
        authority_rank="10",
        monitor_frequency="stable_standard_reference",
    )
    add_s(
        source_id="src_issb_ifrs_s2_2023",
        jurisdiction="INTL",
        authority="ISSB/IFRS Foundation",
        source_class="LAW_REGULATION",
        source_type="international_standard_page",
        document_title="IFRS S2 Climate-related Disclosures",
        official_url=(
            "https://www.ifrs.org/issued-standards/"
            "ifrs-sustainability-standards-navigator/ifrs-s2-climate-related-disclosures/"
        ),
        publication_date="2023-06-26",
        effective_date="2024-01-01",
        version="2023-06",
        language="en",
        authority_level="AUTHORITATIVE",
        authority_rank="10",
        monitor_frequency="stable_standard_reference",
    )
    add_s(
        source_id="src_issb_ifrs_s2_ghg_amendments_2025",
        jurisdiction="INTL",
        authority="ISSB/IFRS Foundation",
        source_class="LAW_REGULATION",
        source_type="amendment_page",
        document_title="Amendments to Greenhouse Gas Emissions Disclosures (IFRS S2)",
        official_url=(
            "https://www.ifrs.org/projects/completed-projects/2025/"
            "amendments-to-disclosure-of-greenhouse-gas-emissions-s2/"
        ),
        publication_date="2025-12-01",
        effective_date="2027-01-01",
        version="2025-12",
        language="en",
        authority_level="AUTHORITATIVE",
        authority_rank="10",
        monitor_frequency="stable_standard_reference",
    )
    add_s(
        source_id="src_issb_s1_s2_mapping_education",
        jurisdiction="INTL",
        authority="ISSB/IFRS Foundation",
        source_class="OFFICIAL_GUIDANCE",
        source_type="official_education_pdf",
        document_title=(
            "Education material—Applying IFRS S1 when reporting only "
            "climate-related disclosures in accordance with IFRS S2"
        ),
        official_url=(
            "https://www.ifrs.org/content/dam/ifrs/supporting-implementation/"
            "issb-standards/applying-ifrs-s1-reporting-only-climate-related-"
            "disclosures-accordance-ifrs-s2.pdf"
        ),
        version="education_mapping",
        language="en",
        authority_level="OFFICIAL_GUIDANCE",
        authority_rank="40",
        monitor_frequency="stable_standard_reference",
        notes="Public paragraph anchors only; not full Standard text.",
    )
    add_s(
        source_id="src_issb_knowledge_hub",
        jurisdiction="INTL",
        authority="ISSB/IFRS Foundation",
        source_class="OFFICIAL_GUIDANCE",
        source_type="official_portal",
        document_title="IFRS Sustainability Knowledge Hub / resources",
        official_url="https://www.ifrs.org/sustainability/knowledge-hub/ifrs-resources/",
        version="portal_live",
        language="en",
        authority_level="OFFICIAL_GUIDANCE",
        authority_rank="40",
        monitor_frequency="stable_standard_reference",
    )
    add_s(
        source_id="src_issb_sasb_hub",
        jurisdiction="INTL",
        authority="ISSB/IFRS Foundation",
        source_class="OFFICIAL_GUIDANCE",
        source_type="official_portal",
        document_title="SASB Standards portal",
        official_url="https://www.ifrs.org/issued-standards/sasb-standards/",
        version="portal_live",
        language="en",
        authority_level="AUTHORITATIVE",
        authority_rank="40",
        monitor_frequency="stable_standard_reference",
    )
    add_s(
        source_id="src_ifrs_org_portal",
        jurisdiction="INTL",
        authority="IFRS Foundation",
        source_class="OFFICIAL_GUIDANCE",
        source_type="official_portal",
        document_title="IFRS Foundation",
        official_url="https://www.ifrs.org/",
        version="portal_live",
        language="en",
        authority_level="AUTHORITATIVE",
        authority_rank="10",
        monitor_frequency="stable_standard_reference",
    )


def _tw_rule(**kw: str) -> None:
    add_r(jurisdiction="TW", concept_layer="TAIWAN_ADOPTION", **kw)


def build_taiwan_general_and_fi() -> None:
    _tw_rule(
        rule_id="tw_ar_art7_2_sustainability_chapter",
        framework="TW_IFRS_S1_S2",
        authority="FSC",
        source_id="src_tw_annual_report_rules_fl007032",
        official_document="公開發行公司年報應行記載事項準則",
        citation="第7條第2項",
        paragraph="Art.7(2)",
        content_area="Annual report",
        requirement_type="disclosure_location",
        requirement_title="Sustainability chapter for general listed/OTC companies",
        requirement_summary=(
            "Companies meeting FSC-prescribed conditions must include a "
            "board-approved sustainability-related financial information chapter."
        ),
        entity_type=GEN,
        applicability_condition="General listed/OTC under FL007032",
        applicability_condition_machine=(
            "entity_type in {general_listed_company,general_otc_company} "
            "AND art7_2_condition_met=true"
        ),
        required_action="Prepare board-approved sustainability chapter",
        required_data="board approval",
        required_evidence="annual report chapter",
        publication_date="2025-11-07",
        source_version="FL007032_2025-12",
        rule_effective_from="2026-01-01",
        rule_status="FUTURE",
        verification_status="VERIFIED_AUTHORITATIVE",
    )
    for rid, para, title, area in [
        (
            "tw_ar_art10_1_risk_opportunity_identification",
            "1",
            "風險與機會及重大資訊",
            "Strategy",
        ),
        (
            "tw_ar_art10_1_materiality_definition",
            "1",
            "重大資訊定義",
            "Materiality",
        ),
        (
            "tw_ar_art10_1_reporting_entity_period",
            "2",
            "報導個體與期間",
            "Reporting entity",
        ),
        (
            "tw_ar_art10_1_comparative_information",
            "2",
            "比較資訊",
            "Comparative information",
        ),
        (
            "tw_ar_art10_1_compliance_statement_fair_presentation",
            "3",
            "認可準則聲明與允當表達",
            "Statement of compliance",
        ),
        (
            "tw_ar_art10_1_connected_information",
            "4",
            "連結資訊",
            "Connected information",
        ),
        ("tw_ar_art10_1_governance", "5", "治理", "Governance"),
        ("tw_ar_art10_1_strategy", "5", "策略", "Strategy"),
        ("tw_ar_art10_1_risk_management", "5", "風險管理", "Risk Management"),
        ("tw_ar_art10_1_metrics_targets", "5", "指標與目標", "Metrics & Targets"),
        (
            "tw_ar_art10_1_first_year_climate_only",
            "6",
            "首年得僅揭露氣候",
            "Transition",
        ),
        ("tw_ar_art10_1_ghg_measurement_method", "7", "GHG 衡量方法", "GHG emissions"),
        (
            "tw_ar_art10_1_scope12_assurance_hook",
            "8",
            "範疇一／二確信及範疇三時程",
            "Assurance / GHG",
        ),
    ]:
        _tw_rule(
            rule_id=rid,
            framework="TW_IFRS_S1_S2",
            authority="FSC",
            source_id="src_tw_annual_report_rules_fl007032",
            official_document="公開發行公司年報應行記載事項準則",
            citation=f"第10條之1第{para}款",
            paragraph=f"Art.10-1({para})",
            content_area=area,
            requirement_type="statutory_requirement",
            requirement_title=title,
            requirement_summary=f"FL007032 Art.10-1({para}): {title}.",
            entity_type=GEN,
            applicability_condition="General companies with Art.7(2) chapter",
            applicability_condition_machine=(
                "entity_type in {general_listed_company,general_otc_company} "
                "AND tw_ar_sustainability_chapter_required=true"
            ),
            required_action="Comply with Art.10-1 item",
            required_data="as specified",
            required_evidence="annual report disclosures",
            publication_date="2025-11-07",
            source_version="FL007032_2025-12",
            rule_effective_from="2026-01-01",
            rule_status="FUTURE",
            verification_status="VERIFIED_AUTHORITATIVE",
            transition_relief=(
                "first_year_climate_only" if "first_year" in rid else ""
            ),
        )
    _tw_rule(
        rule_id="tw_ar_art2_excludes_bank_fhc_bills",
        framework="TW_IFRS_S1_S2",
        authority="FSC",
        source_id="src_tw_annual_report_rules_fl007032",
        official_document="公開發行公司年報應行記載事項準則",
        citation="第2條",
        paragraph="Art.2",
        content_area="Applicability",
        requirement_type="entity_family_boundary",
        requirement_title="Banks/FHCs/bills use special annual-report rules",
        requirement_summary=(
            "Banks, bills finance companies and FHCs are carved out of the "
            "general public-company annual-report rules for covered matters."
        ),
        entity_type="other",
        applicability_condition="Bank / bills / FHC",
        applicability_condition_machine=(
            "entity_type in {bank,bills_finance_company,"
            "financial_holding_company} => use_fi_rule_family=true"
        ),
        required_action="Select FI-specific family",
        required_data="entity_type",
        required_evidence="license type",
        publication_date="2025-11-07",
        source_version="FL007032",
        rule_effective_from="2025-11-07",
        rule_status="ACTIVE",
        verification_status="VERIFIED_AUTHORITATIVE",
    )
    _tw_rule(
        rule_id="tw_ar_not_securities_or_fcm_family",
        framework="TW_IFRS_S1_S2",
        authority="FSC",
        source_id="src_tw_annual_report_rules_fl007032",
        official_document="公開發行公司年報應行記載事項準則",
        citation="體系邊界說明",
        paragraph="",
        content_area="Applicability",
        requirement_type="entity_family_boundary",
        requirement_title="Securities firms and FCMs are not under FL007032 family",
        requirement_summary=(
            "Securities firms use FL007040 Art.32-1 + Orders 11403856095/56094; "
            "FCMs use FL021990 Art.34-1 + Orders 11403856096/56094."
        ),
        entity_type="other",
        applicability_condition="securities_firm or futures_commission_merchant",
        applicability_condition_machine=(
            "entity_type in {securities_firm,futures_commission_merchant} "
            "=> use_dedicated_family=true"
        ),
        required_action="Select dedicated family",
        required_data="entity_type",
        required_evidence="license type",
        publication_date="2025-12-26",
        source_version="3A.2_boundary",
        rule_effective_from="2025-12-26",
        rule_status="ACTIVE",
        verification_status="VERIFIED_AUTHORITATIVE",
        notes=(
            "PREVIOUS STATUS: securities mapped to FL007032. "
            "NEW STATUS: dedicated families. "
            "SOURCE THAT RESOLVED IT: FL007040/FL021990 + 56094/56095/56096. "
            "DATE VERIFIED: 2026-08-12."
        ),
    )
    for rid, cite, title, machine, ef in [
        (
            "tw_order_51756_phase1_ge_10bn",
            "二(一)",
            "Phase I >= NT$10bn: FY2026 / file 2027",
            (
                "entity_type in {general_listed_company,general_otc_company} "
                "AND paid_in_capital_twd >= 10000000000"
            ),
            "2026-01-01",
        ),
        (
            "tw_order_51756_phase2_5_to_10bn",
            "二(二)",
            "Phase II >= NT$5bn < NT$10bn: FY2027 / file 2028",
            (
                "entity_type in {general_listed_company,general_otc_company} "
                "AND 5000000000 <= paid_in_capital_twd < 10000000000"
            ),
            "2027-01-01",
        ),
        (
            "tw_order_51756_phase3_lt_5bn",
            "二(三)",
            "Phase III < NT$5bn: FY2028 / file 2029",
            (
                "entity_type in {general_listed_company,general_otc_company} "
                "AND paid_in_capital_twd < 5000000000"
            ),
            "2028-01-01",
        ),
    ]:
        _tw_rule(
            rule_id=rid,
            framework="TW_IFRS_S1_S2",
            authority="FSC",
            source_id="src_tw_order_11403851756",
            official_document="金管證審字第11403851756號令",
            citation=f"令第{cite}點",
            paragraph=cite,
            content_area="Applicability",
            requirement_type="phased_applicability",
            requirement_title=title,
            requirement_summary=title + ".",
            entity_type=GEN,
            applicability_condition="General listed/OTC capital band",
            applicability_condition_machine=machine,
            required_action="Apply/file per schedule",
            required_data="capital/net worth",
            required_evidence="filed AR",
            publication_date="2025-11-12",
            source_version="11403851756",
            rule_effective_from=ef,
            rule_status="FUTURE",
            verification_status="VERIFIED_AUTHORITATIVE",
        )
    for rid, cite, title, rtype, area, machine, ef, status in [
        (
            "tw_order_51756_early_adoption",
            "3",
            "Early adoption permitted",
            "early_adoption",
            "Applicability",
            "early_adopt=true",
            "2025-11-12",
            "ACTIVE",
        ),
        (
            "tw_order_51756_replace_prior_climate_table",
            "4",
            "Prior climate table replaced after adoption",
            "supersession",
            "Transition",
            "tw_ifrs_sustainability_applied=true",
            "2026-01-01",
            "FUTURE",
        ),
        (
            "tw_order_51756_scope12_consolidated_assurance",
            "4",
            "Consolidated Scope 1/2 independent assurance",
            "assurance",
            "Assurance / GHG",
            "tw_ifrs_sustainability_applied=true",
            "2026-01-01",
            "FUTURE",
        ),
        (
            "tw_order_51756_assurance_october_mops_fallback",
            "4",
            "October MOPS fallback if assurance late",
            "deadline",
            "Assurance / Filing",
            "assurance_ready_at_ar_filing=false",
            "2026-01-01",
            "FUTURE",
        ),
        (
            "tw_order_51756_assurance_difference_correction",
            "4",
            "Correct filings when assured figures differ",
            "correction",
            "Assurance / Correction",
            "assured_ghg != ar_ghg",
            "2026-01-01",
            "FUTURE",
        ),
        (
            "tw_order_51756_material_difference_board_reapproval",
            "4",
            "Material differences require board re-approval",
            "board_approval",
            "Governance / Assurance",
            "ghg_difference_material=true",
            "2026-01-01",
            "FUTURE",
        ),
        (
            "tw_order_51756_assurance_provider_qualification",
            "5",
            "Assurance providers must meet TWSE/TPEx rules",
            "assurance_provider",
            "Assurance",
            "engages_ghg_assurance=true",
            "2026-01-01",
            "FUTURE",
        ),
        (
            "tw_order_51756_scope3_from_fourth_year",
            "6",
            "Scope 3 from fourth FY after first application",
            "transition_relief",
            "GHG transition",
            "years_since_first_tw_ifrs_application >= 4",
            "2026-01-01",
            "FUTURE",
        ),
        (
            "tw_order_51756_net_worth_substitute_thresholds",
            "7",
            "Net-worth substitutes for no-par / non-NT$10",
            "threshold_substitute",
            "Applicability",
            "share_par in {no_par, not_10}",
            "2025-11-12",
            "ACTIVE",
        ),
    ]:
        _tw_rule(
            rule_id=rid,
            framework="TW_IFRS_S1_S2",
            authority="FSC",
            source_id="src_tw_order_11403851756",
            official_document="金管證審字第11403851756號令",
            citation=f"令第{cite}點",
            paragraph=cite,
            content_area=area,
            requirement_type=rtype,
            requirement_title=title,
            requirement_summary=title + ".",
            entity_type=GEN,
            applicability_condition=title,
            applicability_condition_machine=machine,
            required_action=title,
            required_data="as applicable",
            required_evidence="filings",
            assurance_requirement=(
                "independent_third_party_assurance_scope1_scope2_consolidated"
                if "scope12" in rid
                else ""
            ),
            deadline_rule=(
                "same_year_october_31_mops" if "october" in rid else ""
            ),
            transition_relief=(
                "scope3_starts_fourth_financial_year_after_first_application"
                if "scope3" in rid
                else ""
            ),
            publication_date="2025-11-12",
            source_version="11403851756",
            rule_effective_from=ef,
            rule_status=status,
            verification_status="VERIFIED_AUTHORITATIVE",
        )
    _tw_rule(
        rule_id="tw_order_51755_recognised_ifrs_version_locus",
        framework="TW_IFRS_S1_S2",
        authority="FSC",
        source_id="src_tw_order_11403851755",
        official_document="金管證審字第11403851755號令",
        citation="令第二點",
        paragraph="2",
        content_area="Taiwan-recognised version",
        requirement_type="version_recognition",
        requirement_title="Taiwan-recognised IFRS = SFB download-area versions",
        requirement_summary=(
            "Recognised standards are those announced in the SFB IFRS download "
            "area — distinct from the latest IFRS Foundation publication."
        ),
        entity_type=GEN,
        applicability_condition="General-company Taiwan disclosures",
        applicability_condition_machine=(
            "entity_type in {general_listed_company,general_otc_company}"
        ),
        required_action="Use Taiwan-recognised version",
        required_data="recognised version id",
        required_evidence="SFB recognition notice",
        international_standard_version=(
            "IFRS_Foundation_latest_not_automatically_applicable"
        ),
        taiwan_recognised_version=(
            "SFB_IFRS_download_area_announced_recognised_version"
        ),
        taiwan_recognition_date="2025-11-12",
        taiwan_status="RECOGNISED_VIA_ORDER_11403851755",
        publication_date="2025-11-12",
        source_version="11403851755",
        rule_effective_from="2025-11-12",
        rule_status="ACTIVE",
        verification_status="VERIFIED_AUTHORITATIVE",
    )
    _tw_rule(
        rule_id="tw_order_51756_not_covering_securities_or_fcm",
        framework="TW_IFRS_S1_S2",
        authority="FSC",
        source_id="src_tw_order_11403851756",
        official_document="金管證審字第11403851756號令",
        citation="令文適用對象",
        paragraph="2",
        content_area="Applicability",
        requirement_type="coverage_boundary",
        requirement_title="Order 51756 does not cover securities firms / FCMs",
        requirement_summary=(
            "After full review, securities firms and FCMs are outside this "
            "general-company order and use dedicated orders 56095/56096."
        ),
        entity_type="securities_firm|futures_commission_merchant",
        applicability_condition="securities_firm or FCM",
        applicability_condition_machine=(
            "entity_type in {securities_firm,futures_commission_merchant}"
        ),
        required_action="Use dedicated orders",
        required_data="entity_type",
        required_evidence="license",
        publication_date="2025-11-12",
        source_version="11403851756",
        rule_effective_from="2025-11-12",
        rule_status="ACTIVE",
        verification_status="NOT_COVERED_BY_CURRENT_ORDER",
        notes="Legal silence relative to this order — not research failure.",
    )
    for rid, title, superseded_by in [
        (
            "tw_ifrs_phase1_capital_10bn_news_legacy",
            "LEGACY news Phase I",
            "tw_order_51756_phase1_ge_10bn",
        ),
        (
            "tw_scope3_transition_first_three_years_news_legacy",
            "LEGACY news Scope3",
            "tw_order_51756_scope3_from_fourth_year",
        ),
    ]:
        _tw_rule(
            rule_id=rid,
            framework="TW_IFRS_S1_S2",
            authority="FSC",
            source_id="src_tw_sfb_press_20251028",
            official_document="SFB press 2025-10-28",
            citation="press (historical)",
            paragraph="",
            content_area="Applicability",
            requirement_type="legacy_explanatory",
            requirement_title=title,
            requirement_summary="Historical news-based record retained for audit.",
            entity_type=GEN,
            applicability_condition="n/a",
            applicability_condition_machine="deprecated=true",
            required_action="Use formal order",
            required_data="",
            required_evidence="",
            publication_date="2025-10-28",
            source_version="press",
            rule_effective_from="",
            rule_effective_to="2025-11-12",
            rule_status="SUPERSEDED",
            verification_status="SUPERSEDED",
            superseded_by_rule_id=superseded_by,
        )
    _tw_rule(
        rule_id="tw_securities_firm_uses_general_ar_if_public_company",
        framework="TW_IFRS_S1_S2",
        authority="FSC",
        source_id="src_tw_annual_report_rules_fl007032",
        official_document="公開發行公司年報應行記載事項準則",
        citation="第2條（3A.1 incorrect mapping）",
        paragraph="Art.2",
        content_area="Applicability",
        requirement_type="entity_family_boundary",
        requirement_title="SUPERSEDED incorrect securities mapping to FL007032",
        requirement_summary=(
            "Stage 3A.1 incorrectly mapped securities firms to FL007032. "
            "Correct family is FL007040 Art.32-1 + Order 11403856095."
        ),
        entity_type="securities_firm",
        applicability_condition="n/a — superseded",
        applicability_condition_machine="deprecated=true",
        required_action="Use securities_firm family",
        required_data="entity_type",
        required_evidence="",
        publication_date="2025-11-07",
        source_version="3A.1_incorrect",
        rule_effective_from="",
        rule_effective_to="2025-12-26",
        rule_status="SUPERSEDED",
        verification_status="SUPERSEDED",
        superseded_by_rule_id="tw_sf_art32_1_family",
        notes=(
            "PREVIOUS STATUS: VERIFIED_AUTHORITATIVE (incorrect family). "
            "NEW STATUS: SUPERSEDED. "
            "SOURCE THAT RESOLVED IT: FL007040 Art.32-1 + 11403856095/56094. "
            "DATE VERIFIED: 2026-08-12."
        ),
    )
    for rid, sid, doc, cite, para, et, title, machine, ef in [
        (
            "tw_fi_fhc_apply_fy2026",
            "src_tw_order_11402739247_fi",
            "金管銀法字第11402739247號令",
            "令第二點(一)",
            "2(1)",
            "financial_holding_company",
            "FHC: FY2026 apply / file from 2027",
            "entity_type==financial_holding_company",
            "2026-01-01",
        ),
        (
            "tw_fi_bank_listed_or_fhc_sub_fy2026",
            "src_tw_order_11402739247_fi",
            "金管銀法字第11402739247號令",
            "令第二點(二)",
            "2(2)",
            "bank",
            "Listed/OTC or FHC-sub banks: FY2026",
            "entity_type==bank AND (listing in {TWSE,TPEx} OR is_fhc_subsidiary=true)",
            "2026-01-01",
        ),
        (
            "tw_fi_bank_nonlisted_non_fhc_sub_fy2027",
            "src_tw_order_11402739247_fi",
            "金管銀法字第11402739247號令",
            "令第二點(三)",
            "2(3)",
            "bank",
            "Non-listed non-FHC-sub banks: FY2027",
            (
                "entity_type==bank AND listing not in {TWSE,TPEx} "
                "AND is_fhc_subsidiary=false"
            ),
            "2027-01-01",
        ),
        (
            "tw_fi_bills_listed_or_fhc_sub_fy2026",
            "src_tw_order_11402739247_fi",
            "金管銀法字第11402739247號令",
            "令第二點(二)",
            "2(2)",
            "bills_finance_company",
            "Listed or FHC-sub bills: FY2026",
            (
                "entity_type==bills_finance_company "
                "AND (listing==TWSE OR is_fhc_subsidiary=true)"
            ),
            "2026-01-01",
        ),
        (
            "tw_fi_scope3_from_fourth_year",
            "src_tw_order_11402739247_fi",
            "金管銀法字第11402739247號令",
            "令第六點",
            "6",
            "financial_holding_company|bank|bills_finance_company",
            "FI Scope 3 from fourth FY",
            (
                "entity_type in "
                "{financial_holding_company,bank,bills_finance_company} "
                "AND years_since_first_tw_ifrs_application >= 4"
            ),
            "2026-01-01",
        ),
        (
            "tw_fi_scope12_assurance",
            "src_tw_order_11402739247_fi",
            "金管銀法字第11402739247號令",
            "令第四點",
            "4",
            "financial_holding_company|bank|bills_finance_company",
            "FI Scope 1/2 assurance + Oct fallback",
            "fi_tw_ifrs_applied=true",
            "2026-01-01",
        ),
        (
            "tw_fi_bank_regulation_family",
            "src_tw_bank_annual_report_fl006611",
            "銀行年報應行記載事項準則",
            "第7條第2項／第10條之1",
            "Art.7(2)/10-1",
            "bank",
            "Banks use bank AR family",
            "entity_type==bank",
            "2025-12-16",
        ),
        (
            "tw_fi_fhc_regulation_family",
            "src_tw_fhc_annual_report_fl006626",
            "金融控股公司年報應行記載事項準則",
            "第7條第2項／第10條之1",
            "Art.7(2)/10-1",
            "financial_holding_company",
            "FHCs use FHC AR family",
            "entity_type==financial_holding_company",
            "2025-12-16",
        ),
        (
            "tw_fi_bills_regulation_family",
            "src_tw_bills_annual_report_fl006628",
            "票券金融公司年報應行記載事項準則",
            "第7條第2項／第10條之1",
            "Art.7(2)/10-1",
            "bills_finance_company",
            "Bills use bills AR family",
            "entity_type==bills_finance_company",
            "2025-12-16",
        ),
    ]:
        _tw_rule(
            rule_id=rid,
            framework="TW_IFRS_S1_S2_FI",
            authority="FSC",
            source_id=sid,
            official_document=doc,
            citation=cite,
            paragraph=para,
            content_area="Applicability",
            requirement_type="phased_applicability",
            requirement_title=title,
            requirement_summary=title + ".",
            entity_type=et,
            applicability_condition=title,
            applicability_condition_machine=machine,
            required_action=title,
            required_data="entity_type",
            required_evidence="filings",
            publication_date="2025-12-16",
            source_version="FI_2025-12",
            rule_effective_from=ef,
            rule_status="FUTURE" if ef >= "2026" else "ACTIVE",
            verification_status="VERIFIED_AUTHORITATIVE",
        )


def build_securities_and_fcm() -> None:
    _tw_rule(
        rule_id="tw_sf_art32_1_family",
        framework="TW_IFRS_S1_S2_SF",
        authority="FSC",
        source_id="src_tw_securities_fin_report_fl007040",
        official_document="證券商財務報告編製準則",
        citation="第32條之1",
        paragraph="Art.32-1",
        content_area="Financial report sustainability disclosures",
        requirement_type="rule_family",
        requirement_title="Securities firms use Art.32-1 family",
        requirement_summary=(
            "Securities firms meeting Art.11(3) conditions prepare "
            "sustainability-related financial information under Art.32-1 — "
            "not under FL007032."
        ),
        entity_type="securities_firm",
        applicability_condition="Securities firm under FL007040",
        applicability_condition_machine="entity_type==securities_firm",
        required_action="Apply FL007040 + Orders 56095/56094",
        required_data="securities license; capital",
        required_evidence="financial report disclosures",
        publication_date="2025-12-24",
        source_version="FL007040_2025-12-24",
        rule_effective_from="2025-12-24",
        rule_status="ACTIVE",
        verification_status="VERIFIED_AUTHORITATIVE",
        supersedes_rule_id="tw_securities_firm_uses_general_ar_if_public_company",
        notes=(
            "PREVIOUS STATUS: mapped to general AR family. "
            "NEW STATUS: VERIFIED_AUTHORITATIVE dedicated family. "
            "SOURCE THAT RESOLVED IT: FL007040 Art.32-1. "
            "DATE VERIFIED: 2026-08-12."
        ),
    )
    for rid, cite, title, machine, ef in [
        (
            "tw_sf_order_56095_phase1_ge_10bn",
            "二(一)",
            "SF Phase I >= NT$10bn: FY2026 / file 2027",
            (
                "entity_type==securities_firm "
                "AND paid_in_capital_twd >= 10000000000 "
                "AND (is_listed_otc_securities_firm "
                "OR is_listed_parent_integrated_sf_sub)"
            ),
            "2026-01-01",
        ),
        (
            "tw_sf_order_56095_phase2_5_to_10bn",
            "二(二)",
            "SF Phase II >= NT$5bn < NT$10bn: FY2027 / file 2028",
            (
                "entity_type==securities_firm "
                "AND 5000000000 <= paid_in_capital_twd < 10000000000 "
                "AND (is_listed_otc_securities_firm "
                "OR is_listed_parent_integrated_sf_sub)"
            ),
            "2027-01-01",
        ),
        (
            "tw_sf_order_56095_phase3_lt_5bn",
            "二(三)",
            "SF Phase III < NT$5bn: FY2028 / file 2029",
            (
                "entity_type==securities_firm "
                "AND paid_in_capital_twd < 5000000000 "
                "AND (is_listed_otc_securities_firm "
                "OR is_listed_parent_integrated_sf_sub)"
            ),
            "2028-01-01",
        ),
    ]:
        _tw_rule(
            rule_id=rid,
            framework="TW_IFRS_S1_S2_SF",
            authority="FSC",
            source_id="src_tw_order_11403856095_securities",
            official_document="金管證券字第11403856095號令",
            citation=f"令第{cite}點",
            paragraph=cite,
            content_area="Applicability",
            requirement_type="phased_applicability",
            requirement_title=title,
            requirement_summary=title + ".",
            entity_type="securities_firm",
            applicability_condition="Listed/OTC SF or listed-parent integrated SF sub",
            applicability_condition_machine=machine,
            required_action="Apply/file per schedule with financial reports",
            required_data="paid-in capital from FS under Admin Rules Art.21",
            required_evidence="financial report",
            publication_date="2025-12-26",
            source_version="11403856095",
            rule_effective_from=ef,
            rule_status="FUTURE",
            verification_status="VERIFIED_AUTHORITATIVE",
        )
    for rid, cite, title, rtype, area, machine, ef, status in [
        (
            "tw_sf_order_56095_early_adoption",
            "3",
            "SF early adoption permitted",
            "early_adoption",
            "Applicability",
            "entity_type==securities_firm AND early_adopt=true",
            "2025-12-26",
            "ACTIVE",
        ),
        (
            "tw_sf_order_56095_scope12_assurance",
            "4",
            "SF consolidated Scope 1/2 assurance + Oct MOPS fallback",
            "assurance",
            "Assurance / GHG",
            "sf_tw_ifrs_applied=true",
            "2026-01-01",
            "FUTURE",
        ),
        (
            "tw_sf_order_56095_scope3_from_fourth_year",
            "6",
            "SF Scope 3 from fourth FY after first application",
            "transition_relief",
            "GHG transition",
            (
                "entity_type==securities_firm "
                "AND years_since_first_tw_ifrs_application >= 4"
            ),
            "2026-01-01",
            "FUTURE",
        ),
        (
            "tw_sf_order_56095_capital_basis",
            "7",
            "SF capital measured from latest FS under Admin Rules Art.21",
            "threshold_basis",
            "Applicability",
            "entity_type==securities_firm",
            "2025-12-26",
            "ACTIVE",
        ),
    ]:
        _tw_rule(
            rule_id=rid,
            framework="TW_IFRS_S1_S2_SF",
            authority="FSC",
            source_id="src_tw_order_11403856095_securities",
            official_document="金管證券字第11403856095號令",
            citation=f"令第{cite}點",
            paragraph=cite,
            content_area=area,
            requirement_type=rtype,
            requirement_title=title,
            requirement_summary=title + ".",
            entity_type="securities_firm",
            applicability_condition=title,
            applicability_condition_machine=machine,
            required_action=title,
            required_data="as applicable",
            required_evidence="filings",
            assurance_requirement=(
                "independent_third_party_assurance_scope1_scope2_consolidated"
                if "scope12" in rid
                else ""
            ),
            deadline_rule=(
                "same_year_october_31_mops" if "scope12" in rid else ""
            ),
            transition_relief=(
                "scope3_starts_fourth_financial_year_after_first_application"
                if "scope3" in rid
                else ""
            ),
            publication_date="2025-12-26",
            source_version="11403856095",
            rule_effective_from=ef,
            rule_status=status,
            verification_status="VERIFIED_AUTHORITATIVE",
        )
    _tw_rule(
        rule_id="tw_sf_order_56094_recognised_version",
        framework="TW_IFRS_S1_S2_SF",
        authority="FSC",
        source_id="src_tw_order_11403856094_recognised",
        official_document="金管證券字第11403856094號令",
        citation="令第二點",
        paragraph="2",
        content_area="Taiwan-recognised version",
        requirement_type="version_recognition",
        requirement_title="SF/FCM recognised IFRS version = SFB download area",
        requirement_summary=(
            "Recognised IFRS Sustainability Disclosure Standards are those "
            "announced in the SFB IFRS download area."
        ),
        entity_type="securities_firm|futures_commission_merchant",
        applicability_condition="SF or FCM disclosures",
        applicability_condition_machine=(
            "entity_type in {securities_firm,futures_commission_merchant}"
        ),
        required_action="Use SFB-announced recognised version",
        required_data="recognised version id",
        required_evidence="SFB notice",
        international_standard_version=(
            "IFRS_Foundation_latest_not_automatically_applicable"
        ),
        taiwan_recognised_version=(
            "SFB_IFRS_download_area_announced_recognised_version"
        ),
        taiwan_recognition_date="2025-12-26",
        taiwan_status="RECOGNISED_VIA_ORDER_11403856094",
        publication_date="2025-12-26",
        source_version="11403856094",
        rule_effective_from="2025-12-26",
        rule_status="ACTIVE",
        verification_status="VERIFIED_AUTHORITATIVE",
    )
    _tw_rule(
        rule_id="tw_sf_nonlisted_not_in_56095",
        framework="TW_IFRS_S1_S2_SF",
        authority="FSC",
        source_id="src_tw_order_11403856095_securities",
        official_document="金管證券字第11403856095號令",
        citation="令第二點適用對象",
        paragraph="2",
        content_area="Applicability",
        requirement_type="coverage_boundary",
        requirement_title="Non-listed securities firms not in Order 56095",
        requirement_summary=(
            "Order 56095 covers listed/OTC securities firms and listed "
            "companies' integrated securities-firm subsidiaries only."
        ),
        entity_type="securities_firm",
        applicability_condition="SF outside covered population",
        applicability_condition_machine=(
            "entity_type==securities_firm AND not "
            "(is_listed_otc_securities_firm OR is_listed_parent_integrated_sf_sub)"
        ),
        required_action="Do not apply 56095 schedule",
        required_data="listing/subsidiary status",
        required_evidence="registration",
        publication_date="2025-12-26",
        source_version="11403856095",
        rule_effective_from="2025-12-26",
        rule_status="ACTIVE",
        verification_status="NOT_COVERED_BY_CURRENT_ORDER",
    )

    _tw_rule(
        rule_id="tw_fcm_art34_1_family",
        framework="TW_IFRS_S1_S2_FCM",
        authority="FSC",
        source_id="src_tw_fcm_fin_report_fl021990",
        official_document="期貨商財務報告編製準則",
        citation="第34條之1",
        paragraph="Art.34-1",
        content_area="Financial report sustainability disclosures",
        requirement_type="rule_family",
        requirement_title="Futures commission merchants use Art.34-1 family",
        requirement_summary=(
            "FCMs meeting Art.12(3) conditions prepare sustainability-related "
            "financial information under Art.34-1."
        ),
        entity_type="futures_commission_merchant",
        applicability_condition="FCM under FL021990",
        applicability_condition_machine="entity_type==futures_commission_merchant",
        required_action="Apply FL021990 + Orders 56096/56094",
        required_data="FCM license; capital",
        required_evidence="financial report disclosures",
        publication_date="2025-12-24",
        source_version="FL021990_2025-12-24",
        rule_effective_from="2025-12-24",
        rule_status="ACTIVE",
        verification_status="VERIFIED_AUTHORITATIVE",
        product_support_status="OUT_OF_V1_SCOPE",
        notes="Regulatory family registered; V1 product support OUT_OF_V1_SCOPE.",
    )
    for rid, cite, title, machine, ef in [
        (
            "tw_fcm_order_56096_phase1_ge_10bn",
            "二(一)",
            "FCM Phase I >= NT$10bn: FY2026 / file 2027",
            (
                "entity_type==futures_commission_merchant "
                "AND paid_in_capital_twd >= 10000000000 "
                "AND (is_listed_otc_fcm OR is_listed_parent_dedicated_fcm_sub)"
            ),
            "2026-01-01",
        ),
        (
            "tw_fcm_order_56096_phase2_5_to_10bn",
            "二(二)",
            "FCM Phase II >= NT$5bn < NT$10bn: FY2027 / file 2028",
            (
                "entity_type==futures_commission_merchant "
                "AND 5000000000 <= paid_in_capital_twd < 10000000000 "
                "AND (is_listed_otc_fcm OR is_listed_parent_dedicated_fcm_sub)"
            ),
            "2027-01-01",
        ),
        (
            "tw_fcm_order_56096_phase3_lt_5bn",
            "二(三)",
            "FCM Phase III < NT$5bn: FY2028 / file 2029",
            (
                "entity_type==futures_commission_merchant "
                "AND paid_in_capital_twd < 5000000000 "
                "AND (is_listed_otc_fcm OR is_listed_parent_dedicated_fcm_sub)"
            ),
            "2028-01-01",
        ),
    ]:
        _tw_rule(
            rule_id=rid,
            framework="TW_IFRS_S1_S2_FCM",
            authority="FSC",
            source_id="src_tw_order_11403856096_fcm",
            official_document="金管證券字第11403856096號令",
            citation=f"令第{cite}點",
            paragraph=cite,
            content_area="Applicability",
            requirement_type="phased_applicability",
            requirement_title=title,
            requirement_summary=title + ".",
            entity_type="futures_commission_merchant",
            applicability_condition="Listed/OTC FCM or listed-parent dedicated FCM sub",
            applicability_condition_machine=machine,
            required_action="Apply/file per schedule",
            required_data="paid-in capital from FS under Admin Rules Art.24",
            required_evidence="financial report",
            publication_date="2025-12-26",
            source_version="11403856096",
            rule_effective_from=ef,
            rule_status="FUTURE",
            verification_status="VERIFIED_AUTHORITATIVE",
            product_support_status="OUT_OF_V1_SCOPE",
        )
    for rid, cite, title, rtype, area, machine, ef, status in [
        (
            "tw_fcm_order_56096_scope12_assurance",
            "4",
            "FCM consolidated Scope 1/2 assurance + Oct MOPS fallback",
            "assurance",
            "Assurance / GHG",
            "fcm_tw_ifrs_applied=true",
            "2026-01-01",
            "FUTURE",
        ),
        (
            "tw_fcm_order_56096_scope3_from_fourth_year",
            "6",
            "FCM Scope 3 from fourth FY after first application",
            "transition_relief",
            "GHG transition",
            (
                "entity_type==futures_commission_merchant "
                "AND years_since_first_tw_ifrs_application >= 4"
            ),
            "2026-01-01",
            "FUTURE",
        ),
        (
            "tw_fcm_order_56096_capital_basis",
            "7",
            "FCM capital from latest FS under Admin Rules Art.24",
            "threshold_basis",
            "Applicability",
            "entity_type==futures_commission_merchant",
            "2025-12-26",
            "ACTIVE",
        ),
    ]:
        _tw_rule(
            rule_id=rid,
            framework="TW_IFRS_S1_S2_FCM",
            authority="FSC",
            source_id="src_tw_order_11403856096_fcm",
            official_document="金管證券字第11403856096號令",
            citation=f"令第{cite}點",
            paragraph=cite,
            content_area=area,
            requirement_type=rtype,
            requirement_title=title,
            requirement_summary=title + ".",
            entity_type="futures_commission_merchant",
            applicability_condition=title,
            applicability_condition_machine=machine,
            required_action=title,
            required_data="as applicable",
            required_evidence="filings",
            assurance_requirement=(
                "independent_third_party_assurance_scope1_scope2_consolidated"
                if "scope12" in rid
                else ""
            ),
            deadline_rule=(
                "same_year_october_31_mops" if "scope12" in rid else ""
            ),
            transition_relief=(
                "scope3_starts_fourth_financial_year_after_first_application"
                if "scope3" in rid
                else ""
            ),
            publication_date="2025-12-26",
            source_version="11403856096",
            rule_effective_from=ef,
            rule_status=status,
            verification_status="VERIFIED_AUTHORITATIVE",
            product_support_status="OUT_OF_V1_SCOPE",
        )
    _tw_rule(
        rule_id="tw_fcm_other_articles_fy2028_package_note",
        framework="TW_IFRS_S1_S2_FCM",
        authority="FSC",
        source_id="src_tw_fcm_fin_report_fl021990",
        official_document="期貨商財務報告編製準則",
        citation="2026-04-27 修正（非永續專章；自117會計年度施行）",
        paragraph="",
        content_area="Versioning",
        requirement_type="version_note",
        requirement_title=(
            "Later FCM amendments may have FY2028 effective dates "
            "distinct from Art.34-1"
        ),
        requirement_summary=(
            "Document-level amendment date is not identical to every "
            "provision's effective date. Art.34-1 package (2025-12) is "
            "tracked separately from later 2026-04-27 amendments effective FY2028."
        ),
        entity_type="futures_commission_merchant",
        applicability_condition="Version-awareness for FCM rules",
        applicability_condition_machine="entity_type==futures_commission_merchant",
        required_action="Apply provision-level effective dates",
        required_data="source_version; rule_effective_from",
        required_evidence="gazette/order",
        publication_date="2026-04-27",
        source_version="FL021990_2026-04-27_other_articles",
        rule_effective_from="2028-01-01",
        rule_status="FUTURE",
        verification_status="PARTIAL",
        product_support_status="OUT_OF_V1_SCOPE",
    )
    for rid, sid, title, vstatus in [
        (
            "tw_twse_impl_plan_reference_example",
            "src_tw_twse_impl_plan_example",
            "Reference implementation plan (required vs recommended)",
            "VERIFIED_OFFICIAL_GUIDANCE",
        ),
        (
            "tw_twse_impl_plan_quarterly_board_and_15day_filing",
            "src_tw_twse_impl_plan_progress_template",
            "Quarterly board progress + file within 15 days after quarter-end",
            "VERIFIED_AUTHORITATIVE",
        ),
    ]:
        add_r(
            rule_id=rid,
            jurisdiction="TW",
            framework="TW_IFRS_S1_S2",
            authority="TWSE",
            source_id=sid,
            official_document="TWSE implementation materials",
            citation="implementation plan",
            paragraph="",
            content_area="Implementation plan",
            requirement_type="exchange_filing",
            requirement_title=title,
            requirement_summary=title + ".",
            entity_type=GEN,
            applicability_condition="Implementation planning / reporting",
            applicability_condition_machine="twse_impl_plan_reporting_required=true",
            required_action=title,
            required_data="progress schedule",
            required_evidence="system filing",
            concept_layer="IMPLEMENTATION_GUIDANCE",
            publication_date="2024-07-01",
            source_version="2024-07",
            rule_effective_from="2024-07-01",
            rule_status="ACTIVE",
            verification_status=vstatus,
        )


def build_ifrs() -> None:
    for rid, area, para, title in [
        ("ifrs_s1_governance", "Governance", "26–27", "Governance (S1.26–27)"),
        ("ifrs_s1_strategy", "Strategy", "28–42", "Strategy (S1.28–42)"),
        (
            "ifrs_s1_risk_management",
            "Risk Management",
            "43–44",
            "Risk Management (S1.43–44)",
        ),
        (
            "ifrs_s1_metrics_targets",
            "Metrics & Targets",
            "45–53",
            "Metrics & Targets (S1.45–53)",
        ),
    ]:
        add_r(
            rule_id=rid,
            jurisdiction="INTL",
            framework="IFRS_S1",
            authority="ISSB",
            source_id="src_issb_s1_s2_mapping_education",
            official_document="IFRS S1 (official education mapping anchors)",
            citation=f"IFRS S1.{para}",
            paragraph=para,
            content_area=area,
            requirement_type="core_content",
            requirement_title=title,
            requirement_summary=(
                f"Official public mapping identifies paragraph range {para}. "
                "Full Standard text not stored."
            ),
            entity_type="other",
            applicability_condition="Entities applying IFRS S1",
            applicability_condition_machine="applies_ifrs_s1=true",
            required_action="Verify against licensed IFRS S1 text",
            required_data="topic data",
            required_evidence="disclosures",
            international_standard_version="IFRS_S1_2023",
            taiwan_recognised_version="only_if_announced_on_SFB_download_area",
            international_effective_date="2024-01-01",
            taiwan_status="RECOGNITION_VIA_TAIWAN_ORDERS_PORTAL",
            concept_layer="INTERNATIONAL_IFRS",
            publication_date="2023-06-26",
            source_version="IFRS_S1_2023",
            rule_effective_from="2024-01-01",
            rule_status="ACTIVE",
            verification_status="REQUIRES_MANUAL_IFRS_ACCESS",
            notes=(
                "Paragraph anchors from official education/mapping materials; "
                "not upgraded to VERIFIED_AUTHORITATIVE solely from mapping."
            ),
        )
    for rid, area, title, status in [
        ("ifrs_s1_objective", "Objective", "Objective", "PARTIAL"),
        ("ifrs_s1_scope", "Scope", "Scope", "PARTIAL"),
        (
            "ifrs_s1_conceptual_foundations",
            "Conceptual foundations",
            "Conceptual foundations",
            "REQUIRES_MANUAL_IFRS_ACCESS",
        ),
        (
            "ifrs_s1_reporting_entity",
            "Reporting entity",
            "Reporting entity",
            "REQUIRES_MANUAL_IFRS_ACCESS",
        ),
        (
            "ifrs_s1_materiality",
            "Materiality",
            "Materiality",
            "REQUIRES_MANUAL_IFRS_ACCESS",
        ),
        (
            "ifrs_s1_fair_presentation",
            "Fair presentation",
            "Fair presentation",
            "REQUIRES_MANUAL_IFRS_ACCESS",
        ),
        (
            "ifrs_s1_connected_information",
            "Connected information",
            "Connected information",
            "REQUIRES_MANUAL_IFRS_ACCESS",
        ),
        (
            "ifrs_s1_timing",
            "Reporting timing",
            "Reporting timing / location",
            "REQUIRES_MANUAL_IFRS_ACCESS",
        ),
        (
            "ifrs_s1_comparative",
            "Comparative information",
            "Comparative information",
            "REQUIRES_MANUAL_IFRS_ACCESS",
        ),
        (
            "ifrs_s1_compliance_statement",
            "Statement of compliance",
            "Statement of compliance",
            "REQUIRES_MANUAL_IFRS_ACCESS",
        ),
        (
            "ifrs_s1_judgements",
            "Judgements",
            "Judgements",
            "REQUIRES_MANUAL_IFRS_ACCESS",
        ),
        (
            "ifrs_s1_measurement_uncertainty",
            "Measurement uncertainty",
            "Measurement uncertainty",
            "REQUIRES_MANUAL_IFRS_ACCESS",
        ),
        ("ifrs_s1_errors", "Errors", "Errors", "REQUIRES_MANUAL_IFRS_ACCESS"),
        (
            "ifrs_s1_commercial_sensitivity",
            "Commercially sensitive information",
            "Commercially sensitive information",
            "REQUIRES_MANUAL_IFRS_ACCESS",
        ),
        (
            "ifrs_s1_transition",
            "Transition",
            "Transition provisions",
            "REQUIRES_MANUAL_IFRS_ACCESS",
        ),
    ]:
        add_r(
            rule_id=rid,
            jurisdiction="INTL",
            framework="IFRS_S1",
            authority="ISSB",
            source_id="src_issb_ifrs_s1_2023",
            official_document="IFRS S1",
            citation="IFRS S1 official page / standard",
            paragraph="TBD",
            content_area=area,
            requirement_type="standard_requirement",
            requirement_title=title,
            requirement_summary=f"IFRS S1 topic '{title}' registered for coverage.",
            entity_type="other",
            applicability_condition="Entities applying IFRS S1",
            applicability_condition_machine="applies_ifrs_s1=true",
            required_action="Manual verification if access-limited",
            required_data="TBD",
            required_evidence="TBD",
            international_standard_version="IFRS_S1_2023",
            taiwan_recognised_version="only_if_announced_on_SFB_download_area",
            international_effective_date="2024-01-01",
            taiwan_status="RECOGNITION_VIA_TAIWAN_ORDERS_PORTAL",
            concept_layer="INTERNATIONAL_IFRS",
            publication_date="2023-06-26",
            source_version="IFRS_S1_2023",
            rule_effective_from="2024-01-01",
            rule_status="ACTIVE" if status == "PARTIAL" else "UNVERIFIED",
            verification_status=status,
        )
    for rid, area, para, title in [
        ("ifrs_s2_governance", "Governance", "5–6", "Governance (S2.5–6)"),
        ("ifrs_s2_strategy", "Strategy", "8–9+", "Strategy (S2.8–9+)"),
        (
            "ifrs_s2_risk_management",
            "Risk Management",
            "24–25",
            "Risk Management (S2.24–25)",
        ),
        (
            "ifrs_s2_metrics_targets",
            "Metrics & Targets",
            "27+",
            "Metrics & Targets (S2.27+)",
        ),
    ]:
        add_r(
            rule_id=rid,
            jurisdiction="INTL",
            framework="IFRS_S2",
            authority="ISSB",
            source_id="src_issb_s1_s2_mapping_education",
            official_document="IFRS S2 (official education mapping anchors)",
            citation=f"IFRS S2.{para}",
            paragraph=para,
            content_area=area,
            requirement_type="core_content",
            requirement_title=title,
            requirement_summary=(
                f"Official public mapping identifies IFRS S2 anchors around {para}. "
                "Full Standard text not stored."
            ),
            entity_type="other",
            applicability_condition="Entities applying IFRS S2",
            applicability_condition_machine="applies_ifrs_s2=true",
            required_action="Verify against licensed IFRS S2 text",
            required_data="climate information",
            required_evidence="climate disclosures",
            international_standard_version="IFRS_S2_2023",
            taiwan_recognised_version="only_if_announced_on_SFB_download_area",
            international_effective_date="2024-01-01",
            taiwan_status="RECOGNITION_VIA_TAIWAN_ORDERS_PORTAL",
            concept_layer="INTERNATIONAL_IFRS",
            publication_date="2023-06-26",
            source_version="IFRS_S2_2023",
            rule_effective_from="2024-01-01",
            rule_status="ACTIVE",
            verification_status="REQUIRES_MANUAL_IFRS_ACCESS",
        )
    for rid, area, title, status in [
        ("ifrs_s2_objective", "Objective", "Objective / scope", "PARTIAL"),
        (
            "ifrs_s2_physical_risks",
            "Physical risks",
            "Climate-related physical risks",
            "PARTIAL",
        ),
        (
            "ifrs_s2_transition_risks",
            "Transition risks",
            "Climate-related transition risks",
            "PARTIAL",
        ),
        (
            "ifrs_s2_opportunities",
            "Opportunities",
            "Climate-related opportunities",
            "PARTIAL",
        ),
        ("ifrs_s2_scope1", "GHG emissions", "Scope 1", "PARTIAL"),
        ("ifrs_s2_scope2", "GHG emissions", "Scope 2", "PARTIAL"),
        ("ifrs_s2_scope3", "GHG emissions", "Scope 3", "PARTIAL"),
        (
            "ifrs_s2_business_model_value_chain",
            "Strategy",
            "Business model and value chain",
            "REQUIRES_MANUAL_IFRS_ACCESS",
        ),
        (
            "ifrs_s2_strategy_decision_making",
            "Strategy",
            "Strategy and decision-making",
            "REQUIRES_MANUAL_IFRS_ACCESS",
        ),
        (
            "ifrs_s2_transition_plan",
            "Strategy",
            "Transition plans",
            "REQUIRES_MANUAL_IFRS_ACCESS",
        ),
        (
            "ifrs_s2_current_financial_effects",
            "Financial effects",
            "Current financial effects",
            "REQUIRES_MANUAL_IFRS_ACCESS",
        ),
        (
            "ifrs_s2_anticipated_financial_effects",
            "Financial effects",
            "Anticipated financial effects",
            "REQUIRES_MANUAL_IFRS_ACCESS",
        ),
        (
            "ifrs_s2_climate_resilience",
            "Climate resilience",
            "Climate resilience",
            "REQUIRES_MANUAL_IFRS_ACCESS",
        ),
        (
            "ifrs_s2_scenario_analysis",
            "Climate resilience",
            "Scenario analysis",
            "REQUIRES_MANUAL_IFRS_ACCESS",
        ),
        (
            "ifrs_s2_cross_industry_metrics",
            "Metrics & Targets",
            "Cross-industry metrics",
            "REQUIRES_MANUAL_IFRS_ACCESS",
        ),
        (
            "ifrs_s2_industry_metrics",
            "Industry-based metrics",
            "Industry-based metrics",
            "REQUIRES_MANUAL_IFRS_ACCESS",
        ),
        (
            "ifrs_s2_climate_targets",
            "Metrics & Targets",
            "Climate targets",
            "REQUIRES_MANUAL_IFRS_ACCESS",
        ),
        (
            "ifrs_s2_capital_deployment",
            "Metrics & Targets",
            "Capital deployment",
            "REQUIRES_MANUAL_IFRS_ACCESS",
        ),
        (
            "ifrs_s2_internal_carbon_price",
            "Metrics & Targets",
            "Internal carbon price",
            "REQUIRES_MANUAL_IFRS_ACCESS",
        ),
        (
            "ifrs_s2_executive_remuneration",
            "Metrics & Targets",
            "Executive remuneration",
            "REQUIRES_MANUAL_IFRS_ACCESS",
        ),
        (
            "ifrs_s2_transition_provisions",
            "Transition",
            "Transition provisions",
            "REQUIRES_MANUAL_IFRS_ACCESS",
        ),
    ]:
        add_r(
            rule_id=rid,
            jurisdiction="INTL",
            framework="IFRS_S2",
            authority="ISSB",
            source_id="src_issb_ifrs_s2_2023",
            official_document="IFRS S2",
            citation="IFRS S2 official page / standard",
            paragraph="TBD" if status != "PARTIAL" else "public_locator",
            content_area=area,
            requirement_type="standard_requirement",
            requirement_title=title,
            requirement_summary=f"IFRS S2 topic '{title}' registered for coverage.",
            entity_type="other",
            applicability_condition="Entities applying IFRS S2",
            applicability_condition_machine="applies_ifrs_s2=true",
            required_action="Manual verification if access-limited",
            required_data="TBD",
            required_evidence="TBD",
            international_standard_version="IFRS_S2_2023",
            taiwan_recognised_version="only_if_announced_on_SFB_download_area",
            international_effective_date="2024-01-01",
            taiwan_status="RECOGNITION_VIA_TAIWAN_ORDERS_PORTAL",
            concept_layer="INTERNATIONAL_IFRS",
            publication_date="2023-06-26",
            source_version="IFRS_S2_2023",
            rule_effective_from="2024-01-01",
            rule_status="ACTIVE" if status == "PARTIAL" else "UNVERIFIED",
            verification_status=status,
        )
    add_r(
        rule_id="ifrs_s2_ghg_amendments_2025_international",
        jurisdiction="INTL",
        framework="IFRS_S2",
        authority="ISSB",
        source_id="src_issb_ifrs_s2_ghg_amendments_2025",
        official_document=(
            "Amendments to Greenhouse Gas Emissions Disclosures (Amendments to IFRS S2)"
        ),
        citation="ISSB project page — issued Dec 2025",
        paragraph="TBD",
        content_area="GHG emissions",
        requirement_type="amendment",
        requirement_title="2025 Amendments to GHG emissions disclosures in IFRS S2",
        requirement_summary=(
            "International amendment supporting application of specific GHG "
            "disclosure requirements in IFRS S2; effective for annual reporting "
            "periods beginning on or after 1 January 2027; early application "
            "permitted. Consequential SASB alignment amendments also issued."
        ),
        entity_type="other",
        applicability_condition=(
            "International IFRS S2 applicants from 2027 (or earlier if elected)"
        ),
        applicability_condition_machine=(
            "report_period_start >= 2027-01-01 OR early_apply_s2_ghg_amendments=true"
        ),
        required_action="Assess internationally; do not assume Taiwan recognition",
        required_data="current GHG disclosure approach",
        required_evidence="impact assessment",
        international_standard_version="IFRS_S2_2025_GHG_Amendments",
        taiwan_recognised_version="",
        international_effective_date="2027-01-01",
        taiwan_recognition_date="",
        taiwan_status="NOT_YET_VERIFIED",
        concept_layer="INTERNATIONAL_IFRS",
        publication_date="2025-12-01",
        source_version="2025-12",
        rule_effective_from="2027-01-01",
        rule_status="FUTURE",
        verification_status="PARTIAL",
        notes=(
            "International version verified at project-page level. "
            "taiwan_status=NOT_YET_VERIFIED — do not auto-activate for Taiwan."
        ),
    )


def main() -> None:
    build_sources()
    build_taiwan_general_and_fi()
    build_securities_and_fcm()
    build_ifrs()
    src_path = ROOT / "data/reference/regulatory_sources.csv"
    rule_path = ROOT / "config/regulatory_rules.csv"
    with src_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SOURCE_FIELDS)
        w.writeheader()
        w.writerows(sources)
    with rule_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=RULE_FIELDS)
        w.writeheader()
        for r in rules:
            w.writerow({k: r.get(k, "") for k in RULE_FIELDS})
    change_path = ROOT / "data/regulatory/regulatory_change_log.csv"
    with change_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "change_id",
                "source_id",
                "detected_at",
                "previous_hash",
                "new_hash",
                "change_type",
                "previous_version",
                "new_version",
                "affected_rule_ids",
                "review_status",
                "reviewed_by",
                "reviewed_at",
                "activation_status",
                "notes",
            ],
        )
        w.writeheader()
    conflict_path = ROOT / "data/regulatory/regulatory_conflict_log.csv"
    with conflict_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "conflict_id",
                "detected_at",
                "source_id_a",
                "source_id_b",
                "requirement_a",
                "requirement_b",
                "publication_date_a",
                "publication_date_b",
                "effective_date_a",
                "effective_date_b",
                "affected_rule_ids",
                "review_status",
                "notes",
            ],
        )
        w.writeheader()
    freshness_path = ROOT / "data/regulatory/source_freshness_state.csv"
    with freshness_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "source_id",
                "last_checked_at",
                "last_successful_fetch_at",
                "last_changed_at",
                "http_etag",
                "http_last_modified",
                "content_hash",
                "fetch_status",
                "fetch_error",
                "consecutive_failures",
                "freshness_status",
                "next_check_at",
                "current_source_version",
                "previous_source_version",
            ],
        )
        w.writeheader()
        for s in sources:
            if s.get("monitor_enabled", "true").lower() == "true":
                w.writerow(
                    {
                        "source_id": s["source_id"],
                        "last_checked_at": "",
                        "last_successful_fetch_at": "",
                        "last_changed_at": "",
                        "http_etag": "",
                        "http_last_modified": "",
                        "content_hash": "",
                        "fetch_status": "",
                        "fetch_error": "",
                        "consecutive_failures": "0",
                        "freshness_status": "CHECK_DUE",
                        "next_check_at": "",
                        "current_source_version": s.get("current_source_version", ""),
                        "previous_source_version": "",
                    }
                )
    print("sources", len(sources))
    print("rules", len(rules))
    print("verification", Counter(r["verification_status"] for r in rules))
    print("rule_status", Counter(r["rule_status"] for r in rules))


if __name__ == "__main__":
    main()
