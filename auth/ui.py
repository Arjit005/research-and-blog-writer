"""Streamlit Authentication UI & Gateway.

Renders responsive, accessible email OTP authentication steps and sidebar controls.
Enforces fail-closed authentication gating before any studio features are executed.
"""

from __future__ import annotations

import time
from typing import Optional, Dict, Any
import streamlit as st

from auth.config import load_auth_config
from auth.otp import mask_email
from auth.service import request_otp, verify_otp_and_login, validate_session, logout_user, logout_all_sessions
import database as db


def init_auth_session_state():
    """Ensure authentication keys are initialized in Streamlit session state."""
    if "auth_token" not in st.session_state:
        st.session_state.auth_token = None
    if "user" not in st.session_state:
        st.session_state.user = None
    if "auth_step" not in st.session_state:
        st.session_state.auth_step = "email"  # 'email' or 'verify'
    if "auth_email" not in st.session_state:
        st.session_state.auth_email = ""
    if "cooldown_until" not in st.session_state:
        st.session_state.cooldown_until = 0.0
    if "dev_mode_otp" not in st.session_state:
        st.session_state.dev_mode_otp = None


def render_login_screen():
    """Render high-contrast accessible authentication screens."""
    cfg = load_auth_config()

    st.markdown("""
        <style>
        .auth-container {
            max-width: 480px;
            margin: 40px auto;
            padding: 32px;
            background: #ffffff;
            border-radius: 12px;
            border: 1px solid #e2e8f0;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        }
        .auth-header {
            font-size: 24px;
            font-weight: 700;
            color: #0f172a;
            margin-bottom: 8px;
        }
        .auth-sub {
            font-size: 14px;
            color: #475569;
            margin-bottom: 24px;
        }
        .dev-badge {
            background-color: #fef3c7;
            border: 1px solid #f59e0b;
            color: #92400e;
            padding: 12px;
            border-radius: 8px;
            font-size: 14px;
            margin-bottom: 20px;
        }
        </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.markdown('<div class="auth-container">', unsafe_allow_html=True)
        st.markdown('<div class="auth-header">✍️ AI Research & Visual Blog Studio</div>', unsafe_allow_html=True)

        if cfg.auth_dev_mode:
            st.markdown(
                '<div class="dev-badge"><strong>🛠️ Dev Mode Active:</strong> External SMTP is bypassed. Verification codes are displayed directly on screen.</div>',
                unsafe_allow_html=True
            )

        if st.session_state.auth_step == "email":
            st.markdown('<div class="auth-sub">Enter your email address to receive a secure 6-digit sign-in code:</div>', unsafe_allow_html=True)

            with st.form("email_auth_form", clear_on_submit=False):
                email_input = st.text_input(
                    "Work or Personal Email",
                    value=st.session_state.auth_email,
                    placeholder="name@company.com",
                    key="login_email_input",
                    help="We will send a single-use 6-digit verification code to this address.",
                )
                submit_button = st.form_submit_button("Send Sign-In Code", use_container_width=True, type="primary")

            if submit_button:
                if not email_input.strip():
                    st.error("Please enter a valid email address.")
                else:
                    success, msg, dev_code = request_otp(email_input.strip())
                    if success:
                        st.session_state.auth_email = email_input.strip()
                        st.session_state.auth_step = "verify"
                        st.session_state.cooldown_until = time.time() + cfg.otp_resend_cooldown_seconds
                        st.session_state.dev_mode_otp = dev_code
                        st.success(msg)
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(msg)

        elif st.session_state.auth_step == "verify":
            masked = mask_email(st.session_state.auth_email)
            st.markdown(f'<div class="auth-sub">A 6-digit code was sent to <strong>{masked}</strong>. It expires in 5 minutes.</div>', unsafe_allow_html=True)

            if cfg.auth_dev_mode and st.session_state.dev_mode_otp:
                st.info(f"🔑 **Dev Mode Code:** `{st.session_state.dev_mode_otp}`")

            with st.form("verify_auth_form", clear_on_submit=False):
                code_input = st.text_input(
                    "6-Digit Verification Code",
                    max_chars=6,
                    placeholder="123456",
                    key="login_code_input",
                    help="Enter the 6-digit code without spaces or dashes.",
                )
                verify_btn = st.form_submit_button("Verify & Sign In", use_container_width=True, type="primary")

            if verify_btn:
                if not code_input.strip() or len(code_input.strip()) != 6:
                    st.error("Please enter the complete 6-digit code.")
                else:
                    valid, err_msg, raw_token, user = verify_otp_and_login(st.session_state.auth_email, code_input.strip())
                    if valid and raw_token and user:
                        st.session_state.auth_token = raw_token
                        st.session_state.user = user
                        st.session_state.auth_step = "email"
                        st.session_state.dev_mode_otp = None
                        st.success("Verification successful! Loading studio...")
                        time.sleep(0.3)
                        st.rerun()
                    else:
                        st.error(err_msg)

            # Resend & Email Change Controls
            now = time.time()
            remaining_cooldown = max(0, int(st.session_state.cooldown_until - now))

            resend_cols = st.columns([1, 1])
            with resend_cols[0]:
                if remaining_cooldown > 0:
                    st.button(f"Resend in {remaining_cooldown}s", disabled=True, use_container_width=True)
                else:
                    if st.button("Resend Code", use_container_width=True):
                        success, msg, dev_code = request_otp(st.session_state.auth_email)
                        if success:
                            st.session_state.cooldown_until = time.time() + cfg.otp_resend_cooldown_seconds
                            st.session_state.dev_mode_otp = dev_code
                            st.success("New code sent.")
                            st.rerun()
                        else:
                            st.error(msg)

            with resend_cols[1]:
                if st.button("Change Email", use_container_width=True):
                    st.session_state.auth_step = "email"
                    st.session_state.dev_mode_otp = None
                    st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)


def render_user_auth_sidebar(user: Dict[str, Any]):
    """Render user profile and session controls in sidebar."""
    with st.sidebar:
        st.markdown("---")
        st.markdown("### 👤 User Account")
        st.markdown(f"**Signed in as:** `{mask_email(user['email'])}`")

        col_out, col_all = st.columns([1, 1])
        with col_out:
            if st.button("Log Out", key="sidebar_logout_btn", use_container_width=True):
                token = st.session_state.get("auth_token")
                if token:
                    logout_user(token, user["id"])
                st.session_state.auth_token = None
                st.session_state.user = None
                st.session_state.auth_step = "email"
                st.rerun()

        with col_all:
            with st.expander("Security", expanded=False):
                if st.button("Log Out Everywhere", key="sidebar_logout_all_btn", use_container_width=True):
                    logout_all_sessions(user["id"])
                    st.session_state.auth_token = None
                    st.session_state.user = None
                    st.session_state.auth_step = "email"
                    st.rerun()

        # Legacy Data Claim Button (only shown if unowned legacy data exists)
        unowned_count = db.count_unclaimed_legacy_articles()
        if unowned_count > 0:
            st.markdown(f"""
                <div style="background-color: #f1f5f9; border-left: 3px solid #6366f1; padding: 8px 12px; margin-top: 12px; font-size: 13px; color: #334155;">
                    Found <strong>{unowned_count}</strong> legacy unassigned article(s) created before authentication was enabled.
                </div>
            """, unsafe_allow_html=True)
            if st.button("Claim Legacy Articles", key="claim_legacy_btn", use_container_width=True):
                claimed = db.claim_legacy_data(user["id"])
                st.success(f"Claimed {claimed} legacy articles into your personal studio!")
                time.sleep(0.8)
                st.rerun()


def require_login() -> Dict[str, Any]:
    """Top-level authentication gateway.

    Must be called before rendering any studio functionality.
    Halts execution via st.stop() if client is unauthenticated.
    """
    init_auth_session_state()

    raw_token = st.session_state.get("auth_token")
    if raw_token:
        user = validate_session(raw_token)
        if user:
            st.session_state.user = user
            render_user_auth_sidebar(user)
            return user
        else:
            # Token expired or revoked
            st.session_state.auth_token = None
            st.session_state.user = None

    # Render login interface and halt downstream app code
    render_login_screen()
    st.stop()
