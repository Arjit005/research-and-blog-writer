"""Accessible UI Theme, WCAG AA compliant contrast tokens, and focus styling."""

from __future__ import annotations

import streamlit as st


ACCESSIBLE_CSS = """
<style>
  /* -------------------------------------------------------------------------
     ACCESSIBLE THEME & WCAG AA TYPOGRAPHY (4.5:1 Contrast Ratio Verified)
     ------------------------------------------------------------------------- */
  
  /* Focus rings for keyboard navigation accessibility */
  button:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible {
    outline: 2px solid #4f46e5 !important;
    outline-offset: 2px !important;
  }

  /* Main Title with high-contrast gradient */
  .main-title {
    font-size: 2.2rem;
    font-weight: 800;
    margin-bottom: 0.15rem;
    background: linear-gradient(135deg, #1e1b4b 0%, #4338ca 50%, #4f46e5 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    letter-spacing: -0.02em;
  }

  .subtitle {
    color: #475569;
    font-size: 1.05rem;
    margin-bottom: 1.2rem;
    line-height: 1.5;
  }

  /* Solid card container (replaces low-contrast glassmorphism) */
  .solid-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 16px 18px;
    margin-bottom: 14px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  }

  /* Metric cards */
  .metric-box {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 12px 14px;
    text-align: center;
  }

  .metric-value {
    font-size: 1.5rem;
    font-weight: 800;
    color: #0f172a;
  }

  .metric-label {
    font-size: 0.8rem;
    font-weight: 600;
    color: #475569;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-top: 2px;
  }

  /* Respect prefers-reduced-motion */
  @media (prefers-reduced-motion: reduce) {
    *, ::before, ::after {
      animation-duration: 0.01ms !important;
      animation-iteration-count: 1 !important;
      transition-duration: 0.01ms !important;
      scroll-behavior: auto !important;
    }
  }

  /* Responsive adjustments for mobile screens */
  @media (max-width: 768px) {
    .main-title {
      font-size: 1.65rem;
    }
    .metric-value {
      font-size: 1.25rem;
    }
  }
</style>
"""


def apply_accessible_theme() -> None:
    """Inject accessible CSS rules into the Streamlit page."""
    st.markdown(ACCESSIBLE_CSS, unsafe_allow_html=True)
