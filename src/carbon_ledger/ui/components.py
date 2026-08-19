"""Reusable Streamlit presentation helpers for Carbon Evidence Ledger."""

from __future__ import annotations

import html
from typing import Any

import streamlit as st

from carbon_ledger.ui.glossary import render_glossary_popover
from carbon_ledger.ui.i18n import (
    LANG_CODE_TO_OPTION,
    LANG_OPTION_TO_CODE,
    LANG_OPTIONS,
    t,
)
from carbon_ledger.ui.state import set_language
from carbon_ledger.ui.tutorial import request_tutorial

DESIGN_CSS = """
<style>
@import url("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+TC:wght@400;500;600;700&display=swap");

html, body, [class*="css"],
.stApp, .stMarkdown, button, input, textarea, select {
  font-family: "Inter", "Noto Sans TC", "PingFang TC", "Microsoft JhengHei",
    "Segoe UI", system-ui, sans-serif !important;
}
:root {
  /* Color tokens */
  --color-primary: #0F766E;
  --color-primary-hover: #0D5F59;
  --color-info: #2563EB;
  --color-warning: #D97706;
  --color-danger: #B42318;
  --color-success: #047857;
  --color-neutral: #64748B;
  --cel-primary: #0F8A83;
  --cel-primary-hover: #0C726C;
  --cel-navy: #0D2238;
  --cel-navy-950: #081A2B;
  --cel-text: #0F172A;
  --cel-slate: var(--color-neutral);
  --cel-page: #F4F7FA;
  --cel-surface: #FFFFFF;
  --cel-soft: #F1F5F9;
  --cel-border: #E3E9EF;
  --cel-warning: var(--color-warning);
  --cel-critical: var(--color-danger);
  --cel-success: var(--color-success);
  --cel-info: var(--color-info);
  /* 8-point spacing scale */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;
  --space-7: 40px;
  --space-8: 48px;
  --space-9: 64px;
  /* Radius / elevation */
  --radius-card: 14px;
  --radius-sm: 10px;
  --cel-radius: var(--radius-card);
  --cel-radius-sm: var(--radius-sm);
  --shadow-card: 0 1px 2px rgba(15, 23, 42, 0.04),
    0 1px 3px rgba(15, 23, 42, 0.06);
  --shadow-card-hover: 0 4px 12px rgba(15, 23, 42, 0.08);
  --cel-shadow: var(--shadow-card);
  /* Motion (Phase 11C scroll reveal) */
  --motion-fast: 160ms;
  --motion-normal: 260ms;
  --motion-slow: 320ms;
  --motion-result: 360ms;
  --motion-count: 900ms;
  --motion-distance: 16px;
  --motion-ease: cubic-bezier(0.22, 1, 0.36, 1);
  --ease-out: var(--motion-ease);
}

.stApp {
  background: var(--cel-page);
}

/* Application shell: centered main content */
section[data-testid="stMain"] .block-container,
.main .block-container {
  max-width: 1280px !important;
  padding-top: 1.1rem !important;
  padding-bottom: 2.5rem !important;
  padding-left: var(--space-5) !important;
  padding-right: var(--space-5) !important;
}

/* Sidebar: dark navy rail (visual_system.css refines further) */
section[data-testid="stSidebar"] {
  min-width: 240px !important;
  max-width: 250px !important;
  background: linear-gradient(180deg, #081A2B 0%, #0D2238 100%) !important;
  border-right: 1px solid rgba(255, 255, 255, 0.06) !important;
}
section[data-testid="stSidebar"] > div {
  width: 240px !important;
  background: transparent !important;
}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] span {
  font-size: 0.875rem !important;
  color: rgba(226, 232, 240, 0.88) !important;
}
section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"] {
  border-radius: 10px !important;
  margin: 3px 8px !important;
  padding: 0.55rem 0.7rem !important;
  background: transparent !important;
}
section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"] span {
  color: rgba(203, 213, 225, 0.9) !important;
  font-weight: 500 !important;
}
section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] {
  background: rgba(20, 163, 154, 0.18) !important;
  box-shadow: inset 3px 0 0 #14A39A;
  border-left: none !important;
}
section[data-testid="stSidebar"]
  [data-testid="stSidebarNavLink"][aria-current="page"] span {
  color: #F0FDFA !important;
  font-weight: 650 !important;
}

div[data-testid="stButton"] > button[kind="primary"] {
  background: var(--cel-primary) !important;
  border: 1px solid var(--cel-primary) !important;
  color: #fff !important;
  border-radius: var(--cel-radius-sm) !important;
  font-weight: 600 !important;
  min-height: 2.4rem !important;
  transition: background var(--motion-fast) var(--ease-out),
    border-color var(--motion-fast) var(--ease-out),
    transform var(--motion-fast) var(--ease-out),
    box-shadow var(--motion-fast) var(--ease-out) !important;
}
div[data-testid="stButton"] > button[kind="primary"]:hover {
  background: var(--cel-primary-hover) !important;
  border-color: var(--cel-primary-hover) !important;
  box-shadow: 0 2px 8px rgba(15, 118, 110, 0.22) !important;
}
div[data-testid="stButton"] > button[kind="primary"]:active {
  transform: translateY(1px) !important;
}
div[data-testid="stButton"] > button[kind="secondary"] {
  border: 1px solid var(--cel-border) !important;
  color: var(--cel-navy) !important;
  border-radius: var(--cel-radius-sm) !important;
  background: var(--cel-surface) !important;
  transition: border-color var(--motion-fast) var(--ease-out),
    box-shadow var(--motion-fast) var(--ease-out) !important;
}
div[data-testid="stButton"] > button[kind="secondary"]:hover {
  border-color: #CBD5E1 !important;
  box-shadow: var(--shadow-card) !important;
}
div[data-testid="stButton"] > button[kind="tertiary"] {
  color: var(--cel-primary) !important;
  font-weight: 600 !important;
}

div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div,
div[data-baseweb="textarea"] > div {
  border-radius: var(--cel-radius-sm) !important;
}
div[data-baseweb="tab-list"] {
  border-bottom: 1px solid var(--cel-border);
  gap: 4px;
}
button[data-baseweb="tab"] {
  border-radius: 8px 8px 0 0 !important;
}
button[aria-selected="true"][data-baseweb="tab"] {
  color: var(--cel-primary) !important;
  font-weight: 650 !important;
}

.cel-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 56px;
  padding: 4px 0 2px 0;
  border-bottom: 1px solid transparent;
  background: transparent;
}
.cel-brand-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.cel-mark {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: linear-gradient(145deg, #0F766E 0%, #14B8A6 100%);
  position: relative;
  flex-shrink: 0;
}
.cel-mark::before {
  content: "";
  position: absolute;
  inset: 7px 7px 7px 7px;
  border: 2px solid rgba(255,255,255,0.85);
  border-radius: 4px;
}
.cel-mark::after {
  content: "";
  position: absolute;
  width: 6px;
  height: 6px;
  right: 5px;
  bottom: 5px;
  background: #fff;
  border-radius: 50%;
}
.cel-brand-name {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--cel-navy);
  letter-spacing: -0.01em;
}

.cel-page-header {
  margin: 0 0 16px 0;
}
.cel-page-title {
  margin: 0 0 6px 0;
  font-size: clamp(2rem, 2.4vw, 2.5rem);
  line-height: 1.2;
  font-weight: 700;
  color: var(--cel-navy);
  letter-spacing: -0.02em;
}
.cel-page-sub {
  margin: 0 0 10px 0;
  font-size: 0.95rem;
  color: var(--cel-slate);
  line-height: 1.5;
  max-width: 52rem;
}
.cel-page-hint {
  margin: 8px 0 0 0;
  font-size: 0.82rem;
  color: var(--cel-slate);
}
.cel-badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border: 1px solid var(--cel-border);
  border-radius: 999px;
  background: var(--cel-soft);
  color: var(--cel-slate);
  font-size: 0.75rem;
  font-weight: 600;
}
.cel-badge-teal {
  background: #ECFDF8;
  border-color: #99F6E4;
  color: #0F766E;
}

.cel-meta-strip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 16px;
  margin: 0 0 20px 0;
  padding: 12px 16px;
  background: var(--cel-surface);
  border: 1px solid var(--cel-border);
  border-radius: var(--cel-radius);
  box-shadow: var(--cel-shadow);
}
.cel-meta-file {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 650;
  color: var(--cel-navy);
  word-break: break-word;
}
.cel-meta-period {
  margin: 0;
  font-size: 0.88rem;
  color: var(--cel-slate);
  font-weight: 500;
}
.cel-meta-sep {
  color: #CBD5E1;
  font-size: 0.85rem;
}

.cel-section {
  margin: var(--space-6) 0 var(--space-3) 0;
}
.cel-section-title {
  margin: 0;
  font-size: clamp(1.35rem, 1.8vw, 1.75rem);
  line-height: 1.3;
  font-weight: 700;
  color: var(--cel-navy);
  letter-spacing: -0.01em;
}
.cel-section-help {
  margin: 4px 0 0 0;
  font-size: 0.86rem;
  color: var(--cel-slate);
  line-height: 1.5;
}
.cel-page-help {
  color: var(--cel-slate);
  font-size: 0.86rem;
  margin: 0 0 12px 0;
}

.cel-kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-4);
  margin: 0 0 var(--space-5) 0;
}
.cel-kpi-grid-hero {
  grid-template-columns: 1.35fr 1fr 1fr 1fr;
}
.cel-kpi-grid-hero-1 {
  grid-template-columns: minmax(16rem, 28rem);
}
.cel-kpi-grid-hero-2 {
  grid-template-columns: 1.6fr 1fr;
}
.cel-kpi-grid-hero-3 {
  grid-template-columns: 1.4fr 1fr 1fr;
}
.cel-kpi-grid-compact {
  grid-template-columns: repeat(4, minmax(140px, 1fr));
}
.cel-kpi-card {
  background: var(--cel-surface);
  border: 1px solid var(--cel-border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
  padding: 18px 20px 18px 20px;
  border-top: 3px solid #CBD5E1;
  min-height: 156px;
  min-width: 0;
  display: flex;
  flex-direction: column;
  writing-mode: horizontal-tb;
  transition: box-shadow var(--motion-fast) var(--ease-out),
    border-color var(--motion-fast) var(--ease-out),
    transform var(--motion-fast) var(--ease-out);
}
.cel-kpi-card:hover {
  box-shadow: var(--shadow-card-hover);
  border-color: #CBD5E1;
}
.cel-kpi-card-primary {
  border-top-color: var(--color-primary);
  background: linear-gradient(180deg, #F0FDFA 0%, #FFFFFF 42%);
}
.cel-kpi-card.cel-accent-teal { border-top-color: #14B8A6; }
.cel-kpi-card.cel-accent-amber { border-top-color: #F59E0B; }
.cel-kpi-card.cel-accent-blue { border-top-color: #3B82F6; }
.cel-kpi-card.cel-accent-slate { border-top-color: #64748B; }
.cel-kpi-card.cel-accent-coral { border-top-color: #F97316; }
.cel-kpi-label {
  margin: 0;
  color: #64748B;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  white-space: normal;
  writing-mode: horizontal-tb;
  line-height: 1.3;
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 1.3em;
}
.cel-kpi-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.05em;
  flex-shrink: 0;
  opacity: 0.8;
  line-height: 1;
  font-size: 0.95em;
}
.cel-kpi-metric {
  margin: 12px 0 0 0;
  display: flex;
  flex-wrap: nowrap;
  align-items: baseline;
  gap: 0.35em;
  min-height: 3.1rem;
  line-height: 1;
}
.cel-kpi-value {
  margin: 0;
  color: var(--cel-navy);
  font-size: clamp(1.9rem, 2.35vw, 2.35rem);
  font-weight: 700;
  letter-spacing: -0.035em;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  font-feature-settings: "tnum" 1, "lnum" 1;
  word-break: normal;
  overflow-wrap: normal;
  white-space: nowrap;
}
.cel-kpi-value-primary {
  margin: 0;
  color: var(--cel-navy);
  font-size: clamp(2.85rem, 4vw, 3.55rem);
  font-weight: 760;
  letter-spacing: -0.05em;
  line-height: 0.95;
  font-variant-numeric: tabular-nums;
  font-feature-settings: "tnum" 1, "lnum" 1;
  white-space: nowrap;
}
.cel-kpi-unit-inline {
  color: #64748B;
  font-size: clamp(1rem, 1.15vw, 1.15rem);
  font-weight: 650;
  letter-spacing: 0.01em;
  line-height: 1.15;
  white-space: nowrap;
  flex-shrink: 0;
  transform: translateY(-0.08em);
}
.cel-kpi-unit {
  /* Legacy block unit — prefer .cel-kpi-unit-inline on same line as value */
  margin: 2px 0 0 0;
  color: var(--cel-slate);
  font-size: 0.92rem;
  font-weight: 600;
  letter-spacing: 0.01em;
}
.cel-kpi-sub {
  margin: 10px 0 0 0;
  color: #94A3B8;
  font-size: 0.72rem;
  line-height: 1.4;
  flex: 1 1 auto;
}
.cel-stat-stack {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  padding: 4px 0 8px 0;
}
.cel-stat-note {
  margin: 0;
  color: var(--cel-slate);
  font-size: 0.78rem;
  line-height: 1.45;
}
.cel-stat-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.cel-stat-label {
  margin: 0;
  color: var(--cel-slate);
  font-size: 0.88rem;
  font-weight: 600;
  line-height: 1.3;
}
.cel-stat-value {
  margin: 0;
  color: var(--cel-navy);
  font-size: clamp(2.1rem, 2.6vw, 2.6rem);
  font-weight: 750;
  letter-spacing: -0.04em;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  font-feature-settings: "tnum" 1, "lnum" 1;
}
.cel-progress {
  margin-top: var(--space-3);
  height: 6px;
  border-radius: 999px;
  background: #E2E8F0;
  overflow: hidden;
}
.cel-progress > span {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #0F766E, #14B8A6);
  border-radius: 999px;
  transition: width var(--motion-result) var(--ease-out);
}
.cel-success-banner {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  margin: 0 0 var(--space-5) 0;
  padding: var(--space-4) var(--space-5);
  background: #ECFDF8;
  border: 1px solid #99F6E4;
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
}
.cel-success-banner-title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--cel-navy);
}
.cel-success-banner-body {
  margin: 4px 0 0 0;
  font-size: 0.88rem;
  color: var(--cel-slate);
  line-height: 1.45;
}
.cel-check {
  width: 22px;
  height: 22px;
  border-radius: 999px;
  background: var(--color-primary);
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 0.75rem;
  font-weight: 700;
  flex-shrink: 0;
  margin-top: 2px;
}
.cel-skeleton {
  background: linear-gradient(90deg, #E2E8F0 0%, #F1F5F9 45%, #E2E8F0 90%);
  background-size: 200% 100%;
  animation: cel-shimmer 1.2s ease-in-out infinite;
  border-radius: var(--radius-card);
}
.cel-skeleton-kpi { height: 128px; }
.cel-skeleton-primary { height: 148px; }
.cel-skeleton-chart { height: 280px; margin-bottom: var(--space-4); }
@keyframes cel-shimmer {
  0% { background-position: 100% 0; }
  100% { background-position: -100% 0; }
}
/* Immediate load animations (top-of-page only; prefer data-cel-reveal) */
.cel-reveal {
  animation: cel-fade-up var(--motion-normal) var(--motion-ease) both;
}
.cel-reveal-1 { animation-delay: 0ms; }
.cel-reveal-2 { animation-delay: 60ms; }
.cel-reveal-3 { animation-delay: 120ms; }
.cel-reveal-4 { animation-delay: 180ms; }
.cel-reveal-5 { animation-delay: 240ms; }
@keyframes cel-fade-up {
  from { opacity: 0; transform: translateY(var(--motion-distance)); }
  to { opacity: 1; transform: translateY(0); }
}

/*
 * FAIL-OPEN scroll reveal:
 * Default state is VISIBLE. Hide rules apply ONLY after html.motion-ready
 * is added by a successfully initialized IntersectionObserver controller.
 * Never hide generic Streamlit containers / chart internals.
 */
html.motion-ready [data-cel-reveal]:not(.is-visible):not([data-cel-animated="1"]) {
  opacity: 0;
  transform: translateY(var(--motion-distance));
}
html.motion-ready [data-cel-reveal] {
  transition:
    opacity var(--motion-normal) var(--motion-ease),
    transform var(--motion-normal) var(--motion-ease);
}
[data-cel-reveal].is-visible,
[data-cel-reveal][data-cel-animated="1"] {
  opacity: 1 !important;
  transform: translateY(0) !important;
}
html.motion-ready
[data-cel-reveal][data-cel-stagger]:not(.is-visible):not([data-cel-animated="1"])
> [data-cel-stagger-item] {
  opacity: 0;
  transform: translateY(var(--motion-distance));
}
html.motion-ready [data-cel-reveal][data-cel-stagger] > [data-cel-stagger-item] {
  transition:
    opacity var(--motion-normal) var(--motion-ease),
    transform var(--motion-normal) var(--motion-ease);
}
html.motion-ready
[data-cel-reveal][data-cel-stagger].is-visible
> [data-cel-stagger-item]:nth-child(1),
html.motion-ready
[data-cel-reveal][data-cel-stagger][data-cel-animated="1"]
> [data-cel-stagger-item]:nth-child(1) {
  transition-delay: 0ms;
}
html.motion-ready
[data-cel-reveal][data-cel-stagger].is-visible
> [data-cel-stagger-item]:nth-child(2),
html.motion-ready
[data-cel-reveal][data-cel-stagger][data-cel-animated="1"]
> [data-cel-stagger-item]:nth-child(2) {
  transition-delay: 60ms;
}
html.motion-ready
[data-cel-reveal][data-cel-stagger].is-visible
> [data-cel-stagger-item]:nth-child(3),
html.motion-ready
[data-cel-reveal][data-cel-stagger][data-cel-animated="1"]
> [data-cel-stagger-item]:nth-child(3) {
  transition-delay: 120ms;
}
html.motion-ready
[data-cel-reveal][data-cel-stagger].is-visible
> [data-cel-stagger-item]:nth-child(4),
html.motion-ready
[data-cel-reveal][data-cel-stagger][data-cel-animated="1"]
> [data-cel-stagger-item]:nth-child(4) {
  transition-delay: 180ms;
}
html.motion-ready
[data-cel-reveal][data-cel-stagger].is-visible
> [data-cel-stagger-item],
html.motion-ready
[data-cel-reveal][data-cel-stagger][data-cel-animated="1"]
> [data-cel-stagger-item] {
  opacity: 1;
  transform: translateY(0);
}
html.motion-ready
[data-cel-reveal]:not(.is-visible):not([data-cel-animated="1"])
.cel-progress > span {
  width: 0 !important;
}
html.motion-ready [data-cel-reveal] .cel-progress > span {
  transition: width var(--motion-slow) var(--motion-ease);
}
[data-cel-reveal].is-visible .cel-progress > span,
[data-cel-reveal][data-cel-animated="1"] .cel-progress > span {
  width: var(--cel-progress-target, 0%) !important;
}
/* Trace staged reveal — only our wrapper, never chart hosts */
html.motion-ready
[data-cel-reveal="trace"]:not(.is-visible):not([data-cel-animated="1"])
.cel-trace-stage {
  opacity: 0;
  transform: translateY(10px);
}
[data-cel-reveal="trace"] .cel-trace-stage {
  transition:
    opacity var(--motion-normal) var(--motion-ease),
    transform var(--motion-normal) var(--motion-ease);
}
[data-cel-reveal="trace"].is-visible .cel-trace-stage-1,
[data-cel-reveal="trace"][data-cel-animated="1"] .cel-trace-stage-1 {
  opacity: 1;
  transform: none;
  transition-delay: 0ms;
}
[data-cel-reveal="trace"].is-visible .cel-trace-stage-2,
[data-cel-reveal="trace"][data-cel-animated="1"] .cel-trace-stage-2 {
  opacity: 1;
  transform: none;
  transition-delay: 80ms;
}
[data-cel-reveal="trace"].is-visible .cel-trace-stage-3,
[data-cel-reveal="trace"][data-cel-animated="1"] .cel-trace-stage-3 {
  opacity: 1;
  transform: none;
  transition-delay: 160ms;
}
[data-cel-reveal="trace"].is-visible .cel-trace-stage-4,
[data-cel-reveal="trace"][data-cel-animated="1"] .cel-trace-stage-4 {
  opacity: 1;
  transform: none;
  transition-delay: 240ms;
}
.cel-sr-only {
  position: absolute !important;
  width: 1px !important;
  height: 1px !important;
  padding: 0 !important;
  margin: -1px !important;
  overflow: hidden !important;
  clip: rect(0, 0, 0, 0) !important;
  white-space: nowrap !important;
  border: 0 !important;
}
.cel-journey {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-3);
  margin: var(--space-4) 0 var(--space-5) 0;
}
.cel-journey-step {
  background: var(--cel-surface);
  border: 1px solid var(--cel-border);
  border-radius: var(--radius-card);
  padding: var(--space-4);
  box-shadow: var(--shadow-card);
}
.cel-journey-num {
  margin: 0 0 var(--space-2) 0;
  color: var(--color-primary);
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.04em;
}
.cel-journey-title {
  margin: 0;
  color: var(--cel-navy);
  font-size: 0.95rem;
  font-weight: 700;
}
.cel-understood {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: var(--space-3) 0;
  padding: 10px 14px;
  background: #ECFDF8;
  border: 1px solid #99F6E4;
  border-radius: 999px;
  color: var(--cel-navy);
  font-size: 0.9rem;
  font-weight: 650;
}
@media (prefers-reduced-motion: reduce) {
  .cel-skeleton { animation: none !important; background: #E2E8F0; }
  .cel-reveal,
  [data-cel-reveal],
  [data-cel-reveal] > [data-cel-stagger-item],
  [data-cel-reveal="trace"] .cel-trace-stage,
  html.motion-ready [data-cel-reveal],
  html.motion-ready [data-cel-reveal] > [data-cel-stagger-item],
  html.motion-ready [data-cel-reveal="trace"] .cel-trace-stage {
    animation: none !important;
    opacity: 1 !important;
    transform: none !important;
    clip-path: none !important;
    transition: none !important;
  }
  [data-cel-reveal] .cel-progress > span,
  html.motion-ready [data-cel-reveal] .cel-progress > span {
    width: var(--cel-progress-target, 0%) !important;
    transition: none !important;
  }
  .cel-progress > span { transition: none !important; }
  div[data-testid="stButton"] > button[kind="primary"],
  div[data-testid="stButton"] > button[kind="secondary"],
  .cel-kpi-card {
    transition: none !important;
  }
}

.cel-viz-panel {
  background: var(--cel-surface);
  border: 1px solid var(--cel-border);
  border-radius: var(--cel-radius);
  box-shadow: var(--cel-shadow);
  padding: 14px 16px 8px 16px;
  margin-bottom: 12px;
  min-height: 0;
}
.cel-viz-panel-soft {
  background: var(--cel-surface);
  border: 1px solid var(--cel-border);
  border-radius: var(--cel-radius);
  box-shadow: var(--cel-shadow);
  padding: 14px 16px 8px 16px;
}
.cel-viz-title {
  margin: 0 0 2px 0;
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--cel-navy);
}
.cel-viz-caption {
  margin: 0 0 8px 0;
  font-size: 0.78rem;
  color: var(--cel-slate);
}

.cel-panel {
  background: var(--cel-surface);
  border: 1px solid var(--cel-border);
  border-radius: var(--cel-radius);
  box-shadow: var(--cel-shadow);
  padding: 16px 18px;
}
.cel-panel-title {
  margin: 0 0 4px 0;
  font-size: 0.9rem;
  font-weight: 650;
  color: var(--cel-navy);
}
.cel-emissions-value {
  margin: 4px 0;
  font-size: 1.85rem;
  font-weight: 700;
  color: var(--cel-navy);
  letter-spacing: -0.02em;
}
.cel-emissions-meta {
  margin: 0;
  color: var(--cel-slate);
  font-size: 0.85rem;
}
.cel-emissions-note {
  margin: 10px 0 0 0;
  padding-top: 10px;
  border-top: 1px solid var(--cel-border);
  color: var(--cel-slate);
  font-size: 0.8rem;
  line-height: 1.5;
}

.cel-trace-card {
  background: var(--cel-surface);
  border: 1px solid var(--cel-border);
  border-radius: var(--cel-radius);
  box-shadow: var(--cel-shadow);
  padding: 18px 20px;
  max-width: 520px;
}
.cel-trace-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px 20px;
  margin: 12px 0;
}
.cel-trace-label {
  margin: 0;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--cel-slate);
}
.cel-trace-value {
  margin: 2px 0 0 0;
  font-size: 1rem;
  font-weight: 650;
  color: var(--cel-navy);
}
.cel-trace-result {
  margin: 8px 0 0 0;
  padding: 12px 14px;
  background: #F0FDFA;
  border: 1px solid #99F6E4;
  border-radius: 10px;
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--cel-navy);
}
.cel-trace-formula {
  margin: 8px 0 0 0;
  font-size: 0.85rem;
  color: var(--cel-slate);
  font-family: "Inter", ui-monospace, monospace;
}

.cel-status {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid var(--cel-border);
  font-size: 0.72rem;
  font-weight: 650;
  color: var(--cel-text);
}
.cel-status-success {
  color: var(--cel-success);
  border-color: #A7F3D0;
  background: #ECFDF5;
}
.cel-status-warning {
  color: var(--cel-warning);
  border-color: #FDE68A;
  background: #FFFBEB;
}
.cel-status-critical {
  color: var(--cel-critical);
  border-color: #FECACA;
  background: #FEF2F2;
}
.cel-status-info {
  color: var(--cel-info);
  border-color: #BFDBFE;
  background: #EFF6FF;
}
.cel-status-attention {
  color: #C2410C;
  border-color: #FDBA74;
  background: #FFF7ED;
}
.cel-status-muted { color: var(--cel-slate); }

.cel-issue-card {
  background: var(--cel-surface);
  border: 1px solid var(--cel-border);
  border-radius: var(--cel-radius);
  box-shadow: var(--cel-shadow);
  padding: 14px 14px 10px 14px;
  height: 100%;
  min-height: 0;
  border-left: 3px solid var(--cel-warning);
}
.cel-issue-card.cel-issue-critical {
  border-left-color: var(--cel-critical);
}
.cel-issue-title {
  margin: 8px 0 4px 0;
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--cel-navy);
}
.cel-issue-meta {
  margin: 0;
  color: var(--cel-slate);
  font-size: 0.82rem;
  line-height: 1.45;
}
.cel-issue-body {
  margin: 8px 0 0 0;
  color: var(--cel-text);
  font-size: 0.84rem;
  line-height: 1.5;
}

.cel-framework-notice {
  background: var(--cel-surface);
  border: 1px solid var(--cel-border);
  border-radius: var(--cel-radius);
  box-shadow: var(--cel-shadow);
  padding: 16px 18px;
  color: var(--cel-text);
  font-size: 0.9rem;
  margin-bottom: 8px;
  line-height: 1.55;
}
.cel-empty {
  background: var(--cel-soft);
  border: 1px dashed var(--cel-border);
  border-radius: var(--cel-radius);
  padding: 18px;
}
.cel-empty-title {
  margin: 0;
  font-weight: 700;
  color: var(--cel-navy);
}
.cel-empty-body {
  margin: 6px 0 0 0;
  color: var(--cel-slate);
  font-size: 0.88rem;
  line-height: 1.55;
}

.cel-sidebar-title {
  margin: 4px 0 8px 0;
  font-size: 0.7rem;
  font-weight: 700;
  color: var(--cel-slate);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.cel-sidebar-meta {
  margin: 0 0 2px 0;
  color: var(--cel-navy);
  font-size: 0.84rem;
  font-weight: 700;
  word-break: break-word;
  line-height: 1.35;
}
.cel-sidebar-muted {
  margin: 0 0 12px 0;
  color: var(--cel-slate);
  font-size: 0.75rem;
  line-height: 1.4;
}
.cel-module-sub {
  margin: -6px 0 10px 1.55rem;
  color: var(--cel-slate);
  font-size: 0.72rem;
  font-weight: 500;
}
.cel-card {
  background: var(--cel-surface);
  border: 1px solid var(--cel-border);
  border-radius: var(--cel-radius);
  box-shadow: var(--cel-shadow);
  padding: 16px 18px;
  height: 100%;
}
.cel-download-title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--cel-navy);
}
.cel-download-tag {
  margin: 4px 0 6px 0;
  color: var(--cel-primary);
  font-size: 0.74rem;
  font-weight: 700;
  letter-spacing: 0.03em;
}

@media (max-width: 1100px) {
  .cel-kpi-grid,
  .cel-kpi-grid-hero,
  .cel-kpi-grid-compact { grid-template-columns: 1fr 1fr; }
  .cel-journey { grid-template-columns: 1fr; }
  .cel-page-title { font-size: 1.7rem; }
  .cel-trace-grid { grid-template-columns: 1fr; }
}
@media (max-width: 720px) {
  .cel-kpi-grid,
  .cel-kpi-grid-hero,
  .cel-kpi-grid-compact { grid-template-columns: 1fr; }
}
</style>
"""

def inject_design_system() -> None:
    """Inject application-owned CSS and scroll-reveal runtime once per page."""
    st.markdown(DESIGN_CSS, unsafe_allow_html=True)
    from carbon_ledger.ui.enterprise import inject_enterprise_styles
    from carbon_ledger.ui.motion import inject_scroll_reveal_runtime

    inject_enterprise_styles()
    inject_scroll_reveal_runtime()


def render_global_header(lang: str) -> None:
    """Compact single-baseline top bar: context left, controls right."""
    from carbon_ledger.ui.glossary import render_glossary_popover
    from carbon_ledger.ui.state import (
        REPO_ROOT,
        get_company_master_mapping,
        get_company_profile_mapping,
    )
    from carbon_ledger.ui.view_models_compliance import regulatory_freshness_banner

    profile = get_company_profile_mapping(st.session_state)
    master = get_company_master_mapping(st.session_state)
    confirmed = bool(str(master.get("customer_confirmed_at") or "").strip())
    confirmed_name = (
        str(master.get("company_name") or "").strip() if confirmed else ""
    )
    confirmed_ubn = (
        str(master.get("unified_business_number") or "").strip()
        if confirmed
        else ""
    )
    company = html.escape(
        confirmed_name
        or str(profile.get("company_name") or "")
        or t("sidebar.company_unset", lang)
    )
    year = html.escape(str(profile.get("reporting_year") or "—"))
    context_detail = f"FY{year}"
    if confirmed_ubn:
        context_detail = (
            f"{t('sidebar.company_ubn', lang, ubn=confirmed_ubn)} · "
            f"{context_detail}"
        )
    freshness = regulatory_freshness_banner(REPO_ROOT, lang=lang)
    state = html.escape(str(freshness.get("state_label") or ""))
    checked = html.escape(str(freshness.get("last_successful_check_at") or "—"))

    ctx, meta, help_col, gloss_col, lang_col = st.columns(
        [1.7, 1.5, 0.65, 0.9, 1.05],
        gap="small",
        vertical_alignment="center",
    )
    with ctx:
        st.markdown(
            f"""
            <div class="cel-topbar-marker" aria-hidden="true"></div>
            <p class="cel-appbar-title">{company}</p>
            <p class="cel-appbar-sub">{html.escape(context_detail)}</p>
            """,
            unsafe_allow_html=True,
        )
    with meta:
        st.markdown(
            f"""
            <div class="cel-appbar-meta">
              <span class="cel-freshness-chip">
                <span class="cel-freshness-dot" aria-hidden="true"></span>
                {state}
              </span>
              <span style="font-size:0.75rem;white-space:nowrap;">{checked}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with help_col:
        if st.button(
            t("header.help", lang),
            key="header_tutorial_btn",
            type="tertiary",
        ):
            request_tutorial(st.session_state)
            st.rerun()
    with gloss_col:
        render_glossary_popover(lang)
    with lang_col:
        current = LANG_CODE_TO_OPTION.get(lang, "繁中")
        selected = st.segmented_control(
            t("header.language_aria", lang),
            options=list(LANG_OPTIONS),
            default=current,
            key="ui_language_control",
            label_visibility="collapsed",
        )
        if selected and selected != current:
            set_language(st.session_state, LANG_OPTION_TO_CODE[selected])
            st.rerun()


def render_page_header(
    title: str,
    subtitle: str,
    *,
    badge: str | None = None,
    hint: str | None = None,
) -> None:
    """Render a compact SaaS page header."""
    badge_html = f'<span class="cel-badge">{badge}</span>' if badge else ""
    hint_html = f'<p class="cel-page-hint">{hint}</p>' if hint else ""
    st.markdown(
        f"""
        <div class="cel-page-header">
          <h1 class="cel-page-title">{title}</h1>
          <p class="cel-page-sub">{subtitle}</p>
          {badge_html}
          {hint_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section_header(
    title: str,
    help_text: str | None = None,
    *,
    scroll_key: str | None = None,
) -> None:
    """Render a restrained section title (optionally scroll-revealed)."""
    help_html = (
        f'<p class="cel-section-help">{help_text}</p>' if help_text else ""
    )
    attrs = ""
    if scroll_key:
        attrs = (
            f' data-cel-reveal="section" data-cel-key="{scroll_key}" '
            f'data-cel-animation-type="section"'
        )
    st.markdown(
        f'<div class="cel-section"{attrs}>'
        f'<h2 class="cel-section-title">{title}</h2>'
        f"{help_html}</div>",
        unsafe_allow_html=True,
    )


def render_page_help(text: str) -> None:
    """Render compact page-level how-to guidance."""
    st.markdown(
        f'<p class="cel-page-help">{text}</p>',
        unsafe_allow_html=True,
    )


def render_result_meta_strip(
    *,
    file_name: str,
    period_text: str,
    badge: str,
) -> None:
    """Compact metadata line — never put long names inside KPI cards."""
    st.markdown(
        f"""
        <div class="cel-meta-strip">
          <p class="cel-meta-file">{file_name}</p>
          <span class="cel-meta-sep">·</span>
          <p class="cel-meta-period">{period_text}</p>
          <span class="cel-badge cel-badge-teal">{badge}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _zero_count_text(decimals: int) -> str:
    """Visible start value for a playing count-up (before rAF)."""
    if int(decimals) > 0:
        return f"{0:.{int(decimals)}f}"
    return "0"


def _count_span(
    display: str,
    *,
    target: float,
    decimals: int = 0,
    delay_ms: int = 0,
    ratio_total: int | None = None,
    css_class: str = "",
    hero_emissions: bool = False,
    hero_play: bool = False,
    hero_run: str = "",
    kpi_metric: bool = False,
    kpi_play: bool = False,
    kpi_run: str = "",
    kpi_key: str = "",
) -> str:
    """Build a count-up span. Playing nodes start at 0; final is in data-cel-final."""
    final = html.escape(str(display))
    playing = (hero_emissions and hero_play) or (kpi_metric and kpi_play)
    hold_zero = playing
    try:
        from carbon_ledger.ui.state import STATE_COUNTUP_RUNTIME_READY

        if playing and bool(st.session_state.get(STATE_COUNTUP_RUNTIME_READY)):
            hold_zero = False
    except Exception:  # noqa: BLE001 - AppTest session proxies vary
        pass
    visible = _zero_count_text(int(decimals)) if hold_zero else final
    cls = f' class="{html.escape(css_class)}"' if css_class else ""
    if hero_emissions:
        # Dedicated primary emissions KPI — not driven by scroll-reveal.
        play = "1" if hero_play else "0"
        run = html.escape(str(hero_run))
        node_id = html.escape(f"cel-hero-emissions-{hero_run or 'idle'}")
        return (
            f"<span{cls} id=\"{node_id}\" "
            f'data-cel-hero-emissions="1" data-cel-hero-play="{play}" '
            f'data-cel-hero-run="{run}" data-cel-final="{final}" '
            f'data-cel-target="{float(target)}" '
            f'data-cel-decimals="{int(decimals)}">{visible}</span>'
        )
    if kpi_metric:
        play = "1" if kpi_play else "0"
        run = html.escape(str(kpi_run))
        key = html.escape(str(kpi_key or "metric"))
        node_id = html.escape(f"cel-kpi-{kpi_key or 'metric'}-{kpi_run or 'idle'}")
        return (
            f"<span{cls} id=\"{node_id}\" data-cel-kpi-metric=\"1\" "
            f'data-cel-kpi-key="{key}" data-cel-kpi-play="{play}" '
            f'data-cel-kpi-run="{run}" data-cel-final="{final}" '
            f'data-cel-target="{float(target)}" '
            f'data-cel-decimals="{int(decimals)}">{visible}</span>'
        )
    attrs = (
        f'data-cel-count="1" data-cel-final="{final}" '
        f'data-cel-target="{float(target)}" data-cel-decimals="{int(decimals)}"'
    )
    if ratio_total is not None:
        attrs += f' data-cel-ratio="1" data-cel-ratio-total="{int(ratio_total)}"'
    if delay_ms:
        attrs += f' data-cel-delay="{int(delay_ms)}"'
    return f"<span{cls} {attrs}>{final}</span>"


def render_saas_kpi_row(
    cards: list[dict[str, Any]],
    *,
    variant: str = "default",
    reveal: bool = False,
    reveal_on_scroll: bool = False,
    scroll_key: str = "kpi",
) -> None:
    """Render compact SaaS KPI cards with optional subtitle and progress.

    Each card dict may include:
    label, value, accent, subtitle, progress (0-100), unit, primary, icon, count.
    Primary metrics put unit on the same line as the number (e.g. ``5,311 tCO₂e``).
    """
    grid_class = "cel-kpi-grid"
    if variant == "hero":
        grid_class = "cel-kpi-grid cel-kpi-grid-hero"
        if len(cards) == 1:
            grid_class += " cel-kpi-grid-hero-1"
        elif len(cards) == 2:
            grid_class += " cel-kpi-grid-hero-2"
        elif len(cards) == 3:
            grid_class += " cel-kpi-grid-hero-3"
    elif variant == "compact":
        grid_class = "cel-kpi-grid cel-kpi-grid-compact"

    html_parts: list[str] = []
    for index, card in enumerate(cards):
        accent = str(card.get("accent") or "slate")
        label = html.escape(str(card.get("label") or ""))
        value = card.get("value")
        unit = card.get("unit")
        subtitle = card.get("subtitle")
        progress = card.get("progress")
        icon = card.get("icon")
        count = card.get("count") if isinstance(card.get("count"), dict) else None
        is_primary = bool(card.get("primary")) or (
            variant == "hero" and index == 0
        )
        reveal_class = f" cel-reveal cel-reveal-{min(index + 1, 5)}" if reveal else ""
        card_class = "cel-kpi-card"
        if is_primary:
            card_class += " cel-kpi-card-primary"
        else:
            card_class += f" cel-accent-{accent}"
        card_class += reveal_class
        icon_html = (
            f'<span class="cel-kpi-icon" aria-hidden="true">'
            f"{html.escape(str(icon))}</span>"
            if icon
            else ""
        )
        value_class = "cel-kpi-value-primary" if is_primary else "cel-kpi-value"
        delay_ms = int(count.get("delay_ms") or (index * 70)) if count else 0
        if count is not None:
            value_html = _count_span(
                str(count.get("final", value)),
                target=float(count.get("target") or 0),
                decimals=int(count.get("decimals") or 0),
                delay_ms=delay_ms,
                ratio_total=(
                    int(count["ratio_total"])
                    if count.get("ratio_total") is not None
                    else None
                ),
                css_class=value_class,
                hero_emissions=bool(count.get("hero_emissions")),
                hero_play=bool(count.get("hero_play")),
                hero_run=str(count.get("hero_run") or ""),
                kpi_metric=bool(count.get("kpi_metric")),
                kpi_play=bool(count.get("kpi_play")),
                kpi_run=str(count.get("kpi_run") or ""),
                kpi_key=str(count.get("kpi_key") or ""),
            )
        else:
            value_html = (
                f'<span class="{value_class}">{html.escape(str(value))}</span>'
            )
        unit_html = (
            f'<span class="cel-kpi-unit-inline">{html.escape(str(unit))}</span>'
            if unit
            else ""
        )
        metric_html = (
            f'<p class="cel-kpi-metric">{value_html}{unit_html}</p>'
        )
        sub_html = (
            f'<p class="cel-kpi-sub">{html.escape(str(subtitle))}</p>'
            if subtitle
            else ""
        )
        progress_html = ""
        if progress is not None:
            try:
                pct = max(0.0, min(100.0, float(progress)))
            except (TypeError, ValueError):
                pct = 0.0
            progress_html = (
                f'<div class="cel-progress" role="progressbar" '
                f'aria-valuenow="{pct:.0f}" aria-valuemin="0" aria-valuemax="100">'
                f'<span style="--cel-progress-target:{pct:.1f}%;width:{pct:.1f}%;">'
                f"</span></div>"
            )
        stagger_attr = ' data-cel-stagger-item="1"' if reveal_on_scroll else ""
        html_parts.append(
            f"<div class='{card_class}'{stagger_attr}>"
            f"<p class='cel-kpi-label'>{icon_html}{label}</p>"
            f"{metric_html}{sub_html}{progress_html}"
            "</div>"
        )
    wrap_attrs = ""
    if reveal_on_scroll:
        wrap_attrs = (
            f' data-cel-reveal="kpi" data-cel-key="{scroll_key}" '
            f'data-cel-stagger="1" data-cel-animation-type="stagger"'
        )
    st.markdown(
        f"<div class='{grid_class}'{wrap_attrs}>{''.join(html_parts)}</div>",
        unsafe_allow_html=True,
    )


def render_success_banner(*, title: str, body: str, reveal: bool = False) -> None:
    """Restrained analysis-complete confirmation."""
    attrs = (
        ' data-cel-reveal="banner" data-cel-key="success-banner" '
        'data-cel-animation-type="section"'
        if reveal
        else ""
    )
    st.markdown(
        f"""
        <div class="cel-success-banner" role="status"{attrs}>
          <span class="cel-check" aria-hidden="true">✓</span>
          <div>
            <p class="cel-success-banner-title">{title}</p>
            <p class="cel-success-banner-body">{body}</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_upload_journey(steps: list[tuple[str, str]]) -> None:
    """Simple 3-step beginner journey for data intake."""
    parts = []
    for number, title in steps:
        parts.append(
            "<div class='cel-journey-step'>"
            f"<p class='cel-journey-num'>{number}</p>"
            f"<p class='cel-journey-title'>{title}</p>"
            "</div>"
        )
    st.markdown(
        f"<div class='cel-journey'>{''.join(parts)}</div>",
        unsafe_allow_html=True,
    )


def render_viz_panel_start(
    title: str,
    caption: str | None = None,
    *,
    scroll_key: str | None = None,
    chart_kind: str | None = None,
) -> None:
    """Open a bounded chart panel header (optionally scroll-revealed)."""
    caption_html = (
        f'<p class="cel-viz-caption">{caption}</p>' if caption else ""
    )
    attrs = ""
    if scroll_key:
        chart_attr = f' data-cel-chart="{chart_kind}"' if chart_kind else ""
        attrs = (
            f' data-cel-reveal="chart" data-cel-key="{scroll_key}" '
            f'data-cel-animation-type="chart"{chart_attr}'
        )
    st.markdown(
        f"""
        <div class="cel-viz-panel"{attrs}>
          <p class="cel-viz-title">{title}</p>
          {caption_html}
        """,
        unsafe_allow_html=True,
    )


def render_viz_panel_end() -> None:
    """Close a chart panel wrapper."""
    st.markdown("</div>", unsafe_allow_html=True)


def render_trace_card(
    *,
    title: str,
    activity_label: str,
    activity_value: str,
    factor_label: str,
    factor_value: str,
    year_label: str,
    year_value: str,
    emissions_label: str,
    emissions_value: str,
    formula: str,
    source_label: str,
    source_value: str,
    activity_amount: float | None = None,
    activity_amount_display: str | None = None,
    activity_unit: str = "",
    factor_num: float | None = None,
    factor_display: str | None = None,
    kg_num: float | None = None,
    kg_display: str | None = None,
    tco2e_num: float | None = None,
    tco2e_display: str | None = None,
) -> None:
    """Polished calculation-trace card with staged scroll reveal + count-up."""
    # Activity / factor cells — animate numeric portions when provided.
    if activity_amount is not None and activity_amount_display is not None:
        amount_span = _count_span(
            activity_amount_display,
            target=float(activity_amount),
            decimals=0 if abs(float(activity_amount)) >= 100 else 2,
            delay_ms=40,
        )
        unit_bit = f" {html.escape(activity_unit)}" if activity_unit else ""
        activity_value_html = f"{amount_span}{unit_bit}"
    else:
        activity_value_html = html.escape(activity_value)

    if factor_num is not None and factor_display is not None:
        factor_span = _count_span(
            factor_display,
            target=float(factor_num),
            decimals=3 if float(factor_num) < 10 else 0,
            delay_ms=100,
        )
        # Keep unit suffix from original factor_value when present.
        suffix = ""
        raw = str(factor_value)
        if " " in raw:
            suffix = html.escape(raw.split(" ", 1)[1])
            factor_value_html = f"{factor_span} {suffix}"
        else:
            factor_value_html = factor_span
    else:
        factor_value_html = html.escape(factor_value)

    if (
        activity_amount is not None
        and activity_amount_display is not None
        and factor_num is not None
        and factor_display is not None
        and kg_num is not None
        and kg_display is not None
    ):
        factor_decimals = 3 if float(factor_num) < 10 else 0
        amt_span = _count_span(
            activity_amount_display,
            target=float(activity_amount),
            delay_ms=120,
        )
        fac_span = _count_span(
            factor_display,
            target=float(factor_num),
            decimals=factor_decimals,
            delay_ms=200,
        )
        kg_span = _count_span(
            kg_display,
            target=float(kg_num),
            delay_ms=280,
        )
        formula_html = f"{amt_span} × {fac_span} = {kg_span} kgCO2e"
    else:
        formula_html = html.escape(formula)

    if tco2e_num is not None and tco2e_display is not None:
        # emissions_value may be "55.9 tCO₂e"; animate amount, keep unit inline.
        unit = "tCO₂e"
        if " " in str(emissions_value):
            unit = str(emissions_value).split(" ", 1)[1]
        abs_t = abs(float(tco2e_num))
        t_decimals = 0 if abs_t >= 100 else (1 if abs_t >= 10 else 2)
        t_span = _count_span(
            tco2e_display,
            target=float(tco2e_num),
            decimals=t_decimals,
            delay_ms=360,
        )
        emissions_html = (
            f"{html.escape(emissions_label)}　{t_span} {html.escape(unit)}"
        )
    else:
        emissions_html = (
            f"{html.escape(emissions_label)}　{html.escape(emissions_value)}"
        )

    title_html = html.escape(title)
    st.markdown(
        f"""
        <div class="cel-trace-card" data-cel-reveal="trace"
             data-cel-key="calc-trace" data-cel-animation-type="trace">
          <p class="cel-panel-title cel-trace-stage cel-trace-stage-1">
            {title_html}
          </p>
          <div class="cel-trace-grid cel-trace-stage cel-trace-stage-2">
            <div>
              <p class="cel-trace-label">{html.escape(activity_label)}</p>
              <p class="cel-trace-value">{activity_value_html}</p>
            </div>
            <div>
              <p class="cel-trace-label">{html.escape(factor_label)}</p>
              <p class="cel-trace-value">{factor_value_html}</p>
            </div>
            <div>
              <p class="cel-trace-label">{html.escape(year_label)}</p>
              <p class="cel-trace-value">{html.escape(year_value)}</p>
            </div>
            <div>
              <p class="cel-trace-label">{html.escape(source_label)}</p>
              <p class="cel-trace-value">{html.escape(source_value)}</p>
            </div>
          </div>
          <p class="cel-trace-formula cel-trace-stage cel-trace-stage-3">
            {formula_html}
          </p>
          <p class="cel-trace-result cel-trace-stage cel-trace-stage-4">
            {emissions_html}
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_completeness_stats(
    *,
    note: str,
    calculated_label: str,
    calculated_value: int,
    needs_work_label: str,
    needs_work_value: int,
    scroll_key: str = "completeness-metrics",
    play: bool = False,
    run: str = "",
) -> None:
    """Side-stack metrics for data completeness (analysis-result count-up)."""
    from carbon_ledger.ui.formatting import format_int

    calc_display = format_int(calculated_value)
    need_display = format_int(needs_work_value)
    calc_span = _count_span(
        calc_display,
        target=float(calculated_value),
        delay_ms=60,
        kpi_metric=True,
        kpi_play=play,
        kpi_run=run,
        kpi_key="completeness-calculated",
    )
    need_span = _count_span(
        need_display,
        target=float(needs_work_value),
        delay_ms=140,
        kpi_metric=True,
        kpi_play=play,
        kpi_run=run,
        kpi_key="completeness-unresolved",
    )
    st.markdown(
        f"""
        <div class="cel-stat-stack" data-cel-reveal="section"
             data-cel-key="{html.escape(scroll_key)}"
             data-cel-animation-type="section">
          <p class="cel-stat-note">{html.escape(note)}</p>
          <div class="cel-stat-item">
            <p class="cel-stat-label">{html.escape(calculated_label)}</p>
            <p class="cel-stat-value">{calc_span}</p>
          </div>
          <div class="cel-stat-item">
            <p class="cel-stat-label">{html.escape(needs_work_label)}</p>
            <p class="cel-stat-value">{need_span}</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_kpi_row(items: list[tuple[Any, str] | tuple[Any, str, str]]) -> None:
    """Render four equal SaaS KPI cards with optional accent class."""
    cards = []
    for item in items:
        value = item[0]
        label = item[1]
        accent = item[2] if len(item) >= 3 else "slate"
        cards.append(
            {
                "label": label,
                "value": value,
                "accent": accent,
            }
        )
    render_saas_kpi_row(cards)


def render_kpi_card(
    value: Any,
    label: str,
    *,
    help_text: str | None = None,
) -> None:
    """Render one KPI card (compatibility helper).

    Uses a single full-width card — never nest inside st.columns(4), which
    previously caused Chinese labels to collapse into vertical one-character text.
    """
    sub_html = (
        f'<p class="cel-kpi-sub">{html.escape(str(help_text))}</p>'
        if help_text
        else ""
    )
    st.markdown(
        "<div class='cel-kpi-card cel-accent-slate' style='max-width:100%'>"
        f"<p class='cel-kpi-label'>{html.escape(str(label))}</p>"
        f'<p class="cel-kpi-metric">'
        f'<span class="cel-kpi-value">{html.escape(str(value))}</span></p>'
        f"{sub_html}</div>",
        unsafe_allow_html=True,
    )


def _status_class(kind: str) -> str:
    mapping = {
        "success": "cel-status-success",
        "warning": "cel-status-warning",
        "critical": "cel-status-critical",
        "attention": "cel-status-attention",
        "info": "cel-status-info",
        "muted": "cel-status-muted",
    }
    return mapping.get(kind, "cel-status-muted")


def render_status_badge(label: str, *, kind: str = "muted") -> None:
    """Render a text status badge that does not rely on color alone."""
    st.markdown(
        f'<span class="cel-status {_status_class(kind)}">{label}</span>',
        unsafe_allow_html=True,
    )


def render_issue_card(
    *,
    activity_name: str,
    title: str,
    severity: str,
    action_hint: str,
    scroll_key: str | None = None,
) -> None:
    """Render a compact dashboard attention card."""
    is_critical = "重大" in severity or "Critical" in severity
    severity_kind = "critical" if is_critical else "warning"
    tone = "cel-issue-critical" if is_critical else ""
    attrs = ""
    if scroll_key:
        attrs = (
            f' data-cel-reveal="card" data-cel-key="{scroll_key}" '
            f'data-cel-animation-type="section"'
        )
    st.markdown(
        f"""
        <div class="cel-issue-card {tone}"{attrs}>
          <span class="cel-status {_status_class(severity_kind)}">{severity}</span>
          <p class="cel-issue-title">{activity_name}</p>
          <p class="cel-issue-meta">{title}</p>
          <p class="cel-issue-body">{action_hint}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_empty_state(title: str, body: str) -> None:
    """Render a professional empty or success state."""
    st.markdown(
        f"""
        <div class="cel-empty">
          <p class="cel-empty-title">{title}</p>
          <p class="cel-empty-body">{body}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_framework_notice(text: str) -> None:
    """Render a restrained framework information notice."""
    st.markdown(
        f'<div class="cel-framework-notice">{text}</div>',
        unsafe_allow_html=True,
    )


def render_disabled_adapter_state(lang: str, framework_name: str) -> None:
    """Explain that an optional adapter was not run."""
    render_empty_state(
        t("fw.disabled_title", lang),
        f"{framework_name}\n\n{t('fw.disabled', lang)}",
    )


def render_emissions_panel(
    *,
    title: str,
    value_display: str,
    ratio: str,
    status_label: str,
    notice: str,
) -> None:
    """Render one cohesive calculated-emissions summary panel."""
    st.markdown(
        f"""
        <div class="cel-panel">
          <p class="cel-panel-title">{title}</p>
          <p class="cel-emissions-value">{value_display}</p>
          <p class="cel-emissions-meta">{ratio}</p>
          <div style="margin-top:10px;">
            <span class="cel-status cel-status-info">{status_label}</span>
          </div>
          <p class="cel-emissions-note">{notice}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_source(
    lang: str,
    *,
    source_label: str | None = None,
    source_detail: str | None = None,
    is_demo: bool = True,
) -> None:
    """Render compact current-source context without framework checkboxes."""
    source_heading = t("sidebar.current_source", lang)
    if source_label:
        primary = source_label
    elif is_demo:
        primary = t("sidebar.source_demo", lang)
    else:
        primary = t("sidebar.source_uploaded", lang)
    detail = source_detail or (
        t("sidebar.reporting_context", lang) if is_demo else ""
    )
    st.markdown(
        f"""
        <p class="cel-sidebar-title">{source_heading}</p>
        <p class="cel-sidebar-meta">{primary}</p>
        <p class="cel-sidebar-muted">{detail}</p>
        """,
        unsafe_allow_html=True,
    )


def render_analysis_settings(lang: str) -> dict[str, bool]:
    """Framework toggles under progressive disclosure (分析設定).

    V1 does not expose CBAM in the sidebar. Backend ``include_cbam`` remains
    available for tests / future V2 and is forced off for the active UI.
    """
    with st.expander(t("sidebar.settings", lang), expanded=False):
        st.caption(t("sidebar.settings_help", lang))
        include_ghg = st.checkbox(
            t("sidebar.ghg_title", lang),
            key="ui_checkbox_ghg",
            help=t("sidebar.ghg_help", lang),
        )
        st.markdown(
            '<p class="cel-module-sub">GHG Protocol</p>',
            unsafe_allow_html=True,
        )
        include_ifrs = st.checkbox(
            t("sidebar.ifrs_title", lang),
            key="ui_checkbox_ifrs",
            help=t("sidebar.ifrs_help", lang),
        )
        st.markdown(
            '<p class="cel-module-sub">IFRS S1 / S2</p>',
            unsafe_allow_html=True,
        )
    # Keep checkbox key stable for session migrations, but do not render CBAM.
    if "ui_checkbox_cbam" not in st.session_state:
        st.session_state["ui_checkbox_cbam"] = False
    else:
        st.session_state["ui_checkbox_cbam"] = False
    return {
        "include_ghg": bool(include_ghg),
        "include_cbam": False,
        "include_ifrs": bool(include_ifrs),
    }


def render_sidebar_controls(
    lang: str,
    *,
    source_label: str | None = None,
    source_detail: str | None = None,
    is_demo: bool = True,
    show_framework_toggles: bool = False,
) -> dict[str, bool]:
    """Render sidebar source context; framework toggles optional (settings)."""
    render_sidebar_source(
        lang,
        source_label=source_label,
        source_detail=source_detail,
        is_demo=is_demo,
    )
    if show_framework_toggles:
        return render_analysis_settings(lang)
    # Preserve prior checkbox keys when settings expander is used elsewhere.
    return {
        "include_ghg": bool(st.session_state.get("ui_checkbox_ghg", True)),
        "include_cbam": False,
        "include_ifrs": bool(st.session_state.get("ui_checkbox_ifrs", True)),
    }


def render_sidebar_help(lang: str) -> None:
    """Render compact sidebar help with glossary access."""
    st.markdown(
        f'<p class="cel-sidebar-title">{t("sidebar.need_help", lang)}</p>',
        unsafe_allow_html=True,
    )
    if st.button(
        t("sidebar.tutorial_link", lang),
        key="sidebar_tutorial_link",
        type="tertiary",
    ):
        request_tutorial(st.session_state)
        st.rerun()
    render_glossary_popover(lang)
