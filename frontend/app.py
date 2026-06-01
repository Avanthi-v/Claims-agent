import json
import urllib.request
from urllib.error import HTTPError, URLError

import streamlit as st

st.set_page_config(page_title="Claims Dashboard", page_icon="🧾")

API_BASE_URL = "http://127.0.0.1:8000"


def post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code}: {error_body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Connection error: {exc.reason}") from exc


def initialize_session_state() -> None:
    defaults = {
        "member_id": "",
        "claim_id": "",
        "estimated_cost": 0.0,
        "claim_response": None,
        "approve_response": None,
        "transaction_status": None,
        "error_message": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def submit_claim(member_id: str, claim_id: str, estimated_cost: float) -> dict:
    payload = {
        "member_id": member_id,
        "claim_id": claim_id,
        "estimated_cost": estimated_cost,
    }
    return post_json(f"{API_BASE_URL}/submit", payload)


def approve_claim(thread_id: str, approved: bool) -> dict:
    payload = {"thread_id": thread_id, "approved": approved}
    return post_json(f"{API_BASE_URL}/approve", payload)


def render_sidebar() -> None:
    st.sidebar.header("Submit a New Claim")
    with st.sidebar.form("claim_form"):
        member_id = st.text_input("Member ID", value=st.session_state.get("member_id", ""))
        claim_id = st.text_input("Claim ID", value=st.session_state.get("claim_id", ""))
        estimated_cost = st.number_input(
            "Estimated Cost",
            min_value=0.0,
            value=float(st.session_state.get("estimated_cost", 0.0)),
            step=100.0,
            format="%.2f",
        )
        submit_button = st.form_submit_button("Submit Claim")

        if submit_button:
            st.session_state.member_id = member_id
            st.session_state.claim_id = claim_id
            st.session_state.estimated_cost = estimated_cost
            st.session_state.error_message = None
            st.session_state.transaction_status = None
            st.session_state.approve_response = None

            try:
                response = submit_claim(member_id, claim_id, estimated_cost)
                state = response.get("state", {})
                st.session_state.claim_response = {
                    "thread_id": response.get("thread_id"),
                    "status": state.get("status"),
                    "underwriting_score": state.get("underwriting_score"),
                    "pending_human_review": bool(response.get("interrupted", False)),
                }
            except Exception as exc:
                st.session_state.claim_response = None
                st.session_state.error_message = str(exc)


def render_main_area() -> None:
    st.title("Claims Dashboard")
    st.caption("Use the sidebar to submit a claim and handle any human review decisions.")

    if st.session_state.error_message:
        st.error(st.session_state.error_message)

    if not st.session_state.claim_response:
        st.info("Submit a claim in the sidebar to begin. If the claim requires review, the approval actions will appear here.")
        return

    claim_response = st.session_state.claim_response
    st.subheader("Latest Claim Result")
    st.write(
        {
            "thread_id": claim_response.get("thread_id"),
            "status": claim_response.get("status"),
            "underwriting_score": claim_response.get("underwriting_score"),
            "pending_human_review": claim_response.get("pending_human_review"),
        }
    )

    if claim_response.get("pending_human_review"):
        st.warning(
            f"⚠️ Manual review required: underwriting score is {claim_response.get('underwriting_score')}"
        )
        cols = st.columns(2)
        with cols[0]:
            approve_click = st.button("Approve Payout")
        with cols[1]:
            reject_click = st.button("Reject Claim")

        if approve_click or reject_click:
            try:
                approval_result = approve_claim(claim_response["thread_id"], approved=approve_click)
                final_state = approval_result.get("state", {})
                status_text = final_state.get("status", "unknown")
                st.session_state.approve_response = approval_result
                st.session_state.transaction_status = (
                    f"Transaction completed successfully: {status_text}"
                )
                st.success(st.session_state.transaction_status)
                st.session_state.claim_response["status"] = status_text
                st.session_state.claim_response["pending_human_review"] = False
                st.session_state.claim_response["underwriting_score"] = final_state.get("underwriting_score", claim_response.get("underwriting_score"))
            except Exception as exc:
                st.session_state.error_message = str(exc)
                st.error(st.session_state.error_message)
    else:
        st.success(f"Claim status: {claim_response.get('status')}")
        st.write(f"Underwriting score: {claim_response.get('underwriting_score')}")

    if st.session_state.transaction_status and not claim_response.get("pending_human_review"):
        st.info(st.session_state.transaction_status)


def main() -> None:
    initialize_session_state()
    render_sidebar()
    render_main_area()


if __name__ == "__main__":
    main()
