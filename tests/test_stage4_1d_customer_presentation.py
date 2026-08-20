"""Stage 4.1d — customer presentation model, learning layer, smart UI."""

from __future__ import annotations

from pathlib import Path

from carbon_ledger.applicability import (
    CompanyProfile,
    assess_applicability,
)
from carbon_ledger.ui.customer_presenters import (
    STATUS_APPLICABLE,
    STATUS_NEEDS_DATA,
    STATUS_NO_AUTO,
    STATUS_SYSTEM_REVIEW,
    STATUS_UNSUPPORTED,
    customer_copy_violations,
    present_assessment,
    present_obligation_card,
)
from carbon_ledger.ui.i18n import MESSAGES, t
from carbon_ledger.ui.tutorial import get_tutorial_copy

REPO_ROOT = Path(__file__).resolve().parents[1]
ZH = "zh-TW"
APL_PAGE = REPO_ROOT / "app_pages" / "applicability.py"
ENTERPRISE = REPO_ROOT / "src" / "carbon_ledger" / "ui" / "enterprise.py"
LEARNING = REPO_ROOT / "src" / "carbon_ledger" / "ui" / "learning.py"
CSS = REPO_ROOT / "src" / "carbon_ledger" / "ui" / "visual_system.css"


def _fresh_ok(repo_root=None, required_source_ids=None, **kwargs):
    return {
        "analysis_allowed": True,
        "state": "CURRENT",
        "overall_regulatory_freshness": "CURRENT",
        "last_successful_check_at": "2026-08-12T00:00:00Z",
        "last_global_check_at": "2026-08-12T00:00:00Z",
        "changes_pending_review": 0,
        "state_source": "durable_persisted_state",
        "required_source_ids": list(required_source_ids or []),
    }


def _listed_incomplete_taiwan() -> CompanyProfile:
    return CompanyProfile(
        company_name="presentation-co",
        reporting_year=2026,
        entity_type="general_listed_company",
        listing_status="TWSE",
        paid_in_capital_twd=12_000_000_000,
        jurisdiction="TW",
    )


def _assess(profile: CompanyProfile):
    return assess_applicability(
        profile,
        repo_root=REPO_ROOT,
        freshness_loader=_fresh_ok,
    )


def test_customer_missing_data_status() -> None:
    card = {
        "obligation_id": "ghg_inventory",
        "title": "台灣溫室氣體盤查",
        "status": "NEEDS_INFORMATION",
        "missing_field_ids": ["has_taiwan_facilities"],
        "official_authority": "",
        "official_document": "",
        "citations": [],
    }
    pres = present_obligation_card(card, ZH)
    assert pres.status_code == STATUS_NEEDS_DATA
    assert pres.short_status == "還需要一些資料"
    assert pres.customer_action_required is True
    assert pres.primary_action_label == "確認台灣廠場"


def test_system_review_pending_has_no_customer_cta() -> None:
    card = {
        "obligation_id": "ifrs_s1_s2",
        "title": "IFRS S1/S2",
        "status": "MANUAL_VERIFICATION_REQUIRED",
        "missing_field_ids": [],
        "official_authority": "金管會",
        "official_document": "roadmap",
        "citations": ["art-1"],
    }
    pres = present_obligation_card(card, ZH)
    assert pres.status_code == STATUS_SYSTEM_REVIEW
    assert pres.short_status == "正在確認中"
    assert pres.customer_action_required is False
    assert pres.primary_action_label == ""
    assert "管理員" not in pres.explanation
    assert "不需要操作" in pres.explanation


def test_product_unsupported_has_no_cta() -> None:
    card = {
        "obligation_id": "carbon_fee",
        "title": "碳費",
        "status": "OUT_OF_V1_SCOPE",
        "missing_field_ids": [],
        "official_authority": "",
        "official_document": "",
        "citations": [],
    }
    pres = present_obligation_card(card, ZH)
    assert pres.status_code == STATUS_UNSUPPORTED
    assert pres.short_status == "目前版本暫不支援"
    assert pres.primary_action_label == ""


def test_applicable_ifrs_concise_summary() -> None:
    assessment = _assess(_listed_incomplete_taiwan())
    presented = present_assessment(assessment, ZH)
    ifrs = next(item for item in presented.presentations if item.domain == "ifrs")
    assert ifrs.status_code == STATUS_APPLICABLE
    assert ifrs.short_status == "適用"
    assert "第一階段" in ifrs.explanation
    assert ifrs.timing_items
    assert "適用報導年度" not in ifrs.explanation


def test_empty_timing_fields_omitted() -> None:
    card = {
        "obligation_id": "carbon_fee",
        "title": "碳費",
        "status": "NEEDS_INFORMATION",
        "effective_reporting_year": None,
        "first_filing_year": None,
        "missing_field_ids": ["has_taiwan_facilities"],
        "official_authority": "",
        "official_document": "",
        "citations": [],
    }
    pres = present_obligation_card(card, ZH)
    assert pres.timing_items == ()
    assert pres.domain == "carbon_fee"


def test_official_basis_omitted_when_unavailable() -> None:
    card = {
        "obligation_id": "ghg_inventory",
        "title": "台灣溫室氣體盤查",
        "status": "NEEDS_INFORMATION",
        "missing_field_ids": ["has_taiwan_facilities"],
        "official_authority": "",
        "official_document": "",
        "citations": [],
        "applied_rule_ids": ["rule_internal_only"],
    }
    pres = present_obligation_card(card, ZH)
    assert pres.show_official_basis is False


def test_duplicated_missing_facts_merged() -> None:
    assessment = _assess(_listed_incomplete_taiwan())
    presented = present_assessment(assessment, ZH)
    summary = presented.action_summary
    assert summary.customer_action_required is True
    assert summary.facts
    assert len(summary.facts) == len(set(summary.facts))
    assert summary.affected_count >= 2
    assert "還差" in summary.headline
    assert "tut.glossary_hint" not in get_tutorial_copy(ZH)["glossary_hint"]
    assert get_tutorial_copy(ZH)["glossary_hint"] == ""
    assert presented.finish_label_key == "apl.wizard.view_current"
    assert t(presented.finish_label_key, ZH) != "完成判定"


def test_no_admin_language_in_customer_copy() -> None:
    hits = customer_copy_violations(MESSAGES)
    assert hits == []
    tutorial = get_tutorial_copy(ZH)
    blob = " ".join(
        [
            tutorial["title"],
            tutorial["subtitle"],
            tutorial["helps"],
            *[step["title"] for step in tutorial["steps"]],
        ]
    )
    assert "管理員" not in blob
    assert "系統不會把空白當成 0" not in blob


def test_no_zero_blank_implementation_copy() -> None:
    assert "系統不會把空白當成 0" not in t("apl.money.unknown_help", ZH)
    assert "系統不會把空白當成 0" not in t("apl.money.blank_is_unknown", ZH)
    enterprise = ENTERPRISE.read_text(encoding="utf-8")
    assert "apl.money.blank_is_unknown" not in enterprise


def test_carbon_fee_uses_carbon_fee_presentation() -> None:
    assessment = _assess(_listed_incomplete_taiwan())
    presented = present_assessment(assessment, ZH)
    fee_cards = [
        item for item in presented.presentations if item.domain == "carbon_fee"
    ]
    assert fee_cards == []
    assert presented.action_summary.customer_action_required is True
    card = {
        "obligation_id": "carbon_fee",
        "title": "碳費",
        "status": "APPLICABLE",
        "official_authority": "環境部",
        "official_document": "碳費徵收辦法",
        "citations": ["art-1"],
        "missing_field_ids": [],
    }
    pres = present_obligation_card(card, ZH)
    assert pres.title == "公司可能需要繳碳費嗎？"
    assert pres.timing_items == ()
    assert "首次申報" not in pres.explanation


def test_environmental_verification_uses_verification_presentation() -> None:
    assessment = _assess(_listed_incomplete_taiwan())
    presented = present_assessment(assessment, ZH)
    env_cards = [
        item for item in presented.presentations if item.domain == "env_verification"
    ]
    assert env_cards == []
    received = present_obligation_card(
        {
            "obligation_id": "taiwan_environmental_verification",
            "title": "環境部溫室氣體查驗",
            "status": "NEEDS_REVIEW",
            "missing_field_ids": [],
            "official_authority": "",
            "official_document": "",
            "citations": [],
        },
        ZH,
    )
    assert received.title == "公司需要第三方查驗溫室氣體資料嗎？"
    assert received.status_code == STATUS_NO_AUTO
    assert received.customer_action_required is False
    applicable = present_obligation_card(
        {
            "obligation_id": "taiwan_environmental_verification",
            "title": "環境部溫室氣體查驗",
            "status": "APPLICABLE",
            "missing_field_ids": [],
            "official_authority": "",
            "official_document": "",
            "citations": [],
        },
        ZH,
    )
    assert applicable.status_code == STATUS_APPLICABLE
    assert "管理員" not in applicable.explanation
    missing = present_obligation_card(
        {
            "obligation_id": "taiwan_environmental_verification",
            "title": "環境部溫室氣體查驗",
            "status": "NEEDS_REVIEW",
            "missing_field_ids": ["received_verification_requirement"],
            "official_authority": "",
            "official_document": "",
            "citations": [],
        },
        ZH,
    )
    assert missing.status_code == STATUS_NEEDS_DATA
    assert missing.primary_action_label == "確認主管機關通知"


def test_ghg_inventory_uses_inventory_presentation() -> None:
    assessment = _assess(_listed_incomplete_taiwan())
    presented = present_assessment(assessment, ZH)
    inventory_cards = [
        item for item in presented.presentations if item.domain == "ghg_inventory"
    ]
    assert inventory_cards == []
    assert presented.action_summary.customer_action_required is True
    inventory = present_obligation_card(
        {
            "obligation_id": "ghg_inventory",
            "title": "台灣溫室氣體盤查",
            "status": "APPLICABLE",
            "missing_field_ids": [],
            "official_authority": "環境部",
            "official_document": "溫室氣體減量及管理法",
            "citations": ["art-1"],
        },
        ZH,
    )
    assert inventory.title == "公司需要向環境部盤查／登錄溫室氣體嗎？"
    assert inventory.timing_items == ()
    assert "整理年度排放資料" in inventory.explanation


def test_no_automatic_result_is_not_customer_todo() -> None:
    pres = present_obligation_card(
        {
            "obligation_id": "ghg_inventory",
            "title": "台灣溫室氣體盤查",
            "status": "NEEDS_REVIEW",
            "missing_field_ids": [],
            "official_authority": "",
            "official_document": "",
            "citations": [],
        },
        ZH,
    )
    assert pres.status_code == STATUS_NO_AUTO
    assert pres.short_status == "目前尚未提供自動判定"
    assert pres.primary_action_label == ""
    assert pres.customer_action_required is False


def test_step1_has_no_permanent_learning_sidebar() -> None:
    source = APL_PAGE.read_text(encoding="utf-8")
    assert "render_learning_panel" not in source
    assert "learn_col" not in source
    assert "apl.why_title" not in source
    assert "render_micro_help" in source


def test_step2_does_not_duplicate_explanation() -> None:
    source = APL_PAGE.read_text(encoding="utf-8")
    assert "render_field_hint" not in source
    assert "render_why_we_ask" not in source
    assert 2 <= source.count("render_money_field(") <= 3
    learning = LEARNING.read_text(encoding="utf-8")
    assert "def render_micro_help" in learning


def test_first_tutorial_is_concise() -> None:
    copy = get_tutorial_copy(ZH)
    assert copy["title"] == "歡迎使用 Carbon Evidence Ledger"
    assert "第一次使用" not in copy["title"]
    assert "用 3 個步驟了解如何確認公司" in copy["subtitle"]
    assert "不需要先懂碳盤查" not in copy["subtitle"]
    titles = [step["title"] for step in copy["steps"]]
    assert titles == [
        "確認公司與目前營運據點",
        "使用公司既有的資料檔",
        "檢視分析結果與可下載資料",
    ]
    assert "排放量" not in copy["helps"]
    assert "哪些資料有問題" not in copy["helps"]
    assert copy["glossary_hint"] == ""
    assert "tut." not in copy["glossary_hint"]
    assert "？" in copy["helps"] or "?" in copy["helps"]
    en = get_tutorial_copy("en")
    assert "welcome" in en["title"].lower()
    assert "first time" not in en["title"].lower()


def test_beginner_terms_before_professional() -> None:
    assert t("apl.field.reporting_year", ZH) == "要評估哪一年度？"
    assert "報導年度" in t("apl.field.reporting_year_professional", ZH)
    assert t("apl.field.listing_status", ZH) == "公司是否上市／上櫃？"
    known = t("apl.field.reporting_entities_known", ZH)
    assert known == "這次報告包含哪些公司？"
    assert "報導邊界" in t("apl.field.reporting_entities_known_help", ZH)
    assert t("apl.wizard.step3", ZH) == "確認台灣廠場"
    assert t("nav.applicability", ZH) == "我的適用要求"
    assert t("apl.entity.unresolved", ZH) == "不知道／不確定"
    assert t("apl.money.unknown", ZH) == "我不知道"


def test_none_timing_absent_from_card_source_contract() -> None:
    source = ENTERPRISE.read_text(encoding="utf-8")
    card_fn = source.split("def render_obligation_result_card", 1)[1]
    card_fn = card_fn.split("def render_customer_action_summary", 1)[0]
    assert "or \"—\"" not in card_fn
    assert "apl.effective_year" not in card_fn


def test_no_cta_when_no_customer_action() -> None:
    pres = present_obligation_card(
        {
            "obligation_id": "ifrs_s1_s2",
            "title": "IFRS S1/S2",
            "status": "NOT_APPLICABLE",
            "missing_field_ids": [],
            "official_authority": "FSC",
            "official_document": "doc",
            "citations": ["1"],
        },
        ZH,
    )
    assert pres.customer_action_required is False
    assert pres.primary_action_label == ""
    assert pres.show_official_basis is True


def test_finish_label_not_complete_when_unresolved() -> None:
    presented = present_assessment(_assess(_listed_incomplete_taiwan()), ZH)
    assert t(presented.finish_label_key, ZH) in {
        "查看目前結果",
        "儲存並查看結果",
    }
    assert "完成判定" not in t(presented.finish_label_key, ZH)
    assert "完成判定" not in APL_PAGE.read_text(encoding="utf-8")


def test_no_static_checkbox_glyph_for_missing_info() -> None:
    css = CSS.read_text(encoding="utf-8")
    assert 'content: "□ ' not in css
    enterprise = ENTERPRISE.read_text(encoding="utf-8")
    card_body = enterprise.split("def render_obligation_result_card", 1)[1].split(
        "def render_customer_action_summary", 1
    )[0]
    assert "cel-checklist" not in card_body
    assert "□" not in card_body


def test_wizard_step_names_are_beginner_facing() -> None:
    assert t("apl.wizard.step1", ZH) == "確認公司"
    assert t("apl.wizard.step2", ZH) == "補充必要資訊"
    assert t("apl.wizard.step4", ZH) == "你的結果"
    assert t("apl.title", ZH) == "你的公司適用哪些要求？"
    assert "IFRS" in t("apl.subtitle", ZH)
