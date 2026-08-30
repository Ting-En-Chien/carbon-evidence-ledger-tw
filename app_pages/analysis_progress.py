"""Blocking analysis transition page.

Dashboard, hero KPIs, and prior results are not mounted while this page runs.
The pipeline reports real progress here; the next navigation is Dashboard.
"""

from __future__ import annotations

import streamlit as st

from carbon_ledger.ui.components import inject_design_system
from carbon_ledger.ui.enterprise import inject_enterprise_styles
from carbon_ledger.ui.motion import (
    ANALYSIS_PHASE_CLOSING,
    ANALYSIS_PHASE_REVEAL,
    analysis_phase,
    render_analysis_transition_view,
)
from carbon_ledger.ui.state import (
    STATE_ANALYSIS_UPLOADED_MODE,
    STATE_INCLUDE_GHG,
    STATE_INCLUDE_IFRS,
    get_language,
)

inject_design_system()
inject_enterprise_styles()

_phase = analysis_phase(st.session_state)
if _phase in {ANALYSIS_PHASE_CLOSING, ANALYSIS_PHASE_REVEAL}:
    # Parent navigates to Dashboard on this run. Do not remount progress or results.
    st.stop()

lang = get_language(st.session_state)
uploaded_mode = bool(st.session_state.get(STATE_ANALYSIS_UPLOADED_MODE, False))
render_analysis_transition_view(
    st.session_state,
    lang=lang,
    uploaded_mode=uploaded_mode,
    include_ghg=bool(st.session_state.get(STATE_INCLUDE_GHG, True)),
    include_cbam=False,
    include_ifrs_s2=bool(st.session_state.get(STATE_INCLUDE_IFRS, True)),
)
