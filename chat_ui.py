import json

import streamlit as st
import vertexai
from vertexai.preview import reasoning_engines

# --- CONFIGURATION ---
try:
    with open("ui_secrets.json") as f:
        _cfg = json.load(f)
    PROJECT_ID = _cfg["PROJECT_ID"]
    LOCATION = _cfg["LOCATION"]
    AGENT_ID = _cfg["AGENT_ID"]
except FileNotFoundError:
    st.error("Missing ui_secrets.json configuration file. Please create it.")
    st.stop()

st.set_page_config(page_title="Scrum Team Orchestrator", page_icon="🚀", layout="wide")


# Initialize Vertex AI connection only once
@st.cache_resource
def init_agent():
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    agent = reasoning_engines.ReasoningEngine(
        f"projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines/{AGENT_ID}"
    )
    return agent


try:
    agent = init_agent()
except Exception as e:
    st.error(f"Failed to connect to Vertex AI: {e}")
    st.stop()

# --- UI LAYOUT ---
st.title("🚀 Multi-Agent Scrum Team")
st.markdown(
    "Submit a ticket to your autonomous multi-agent team running in Google Cloud Vertex AI."
)

with st.sidebar:
    st.header("Ticket Configuration")
    ticket_id = st.text_input("Ticket ID", value="TICKET-101")
    ticket_type = st.selectbox("Ticket Type", options=["BACKEND", "FRONTEND", "FULLSTACK"])
    repo_name = st.text_input("Repository", value="oliverconstance/webapp-scrum-team")
    branch_name = st.text_input("Target Branch", value="feature/new-api")

st.subheader("Ticket Description")
description = st.text_area(
    "Describe the feature, bug, or architecture change:",
    value="Create a simple Python CRUD API using FastAPI to manage user profiles.",
    height=150,
)

if st.button("Submit to Scrum Team", type="primary"):
    if not description:
        st.warning("Please provide a ticket description.")
    else:
        with st.spinner(
            "🤖 The multi-agent team is working on your ticket... "
            "This may take a few minutes as they write code, review, and iterate."
        ):
            try:
                # Call the remote agent via the Python SDK
                response = agent.query(
                    ticket_id=ticket_id,
                    ticket_type=ticket_type,
                    description=description,
                    repo_name=repo_name,
                    branch_name=branch_name,
                )

                st.success(f"Pipeline Completed! Final Status: {response.get('status', 'UNKNOWN')}")

                # Display Results in Tabs
                tab1, tab2, tab3 = st.tabs(
                    ["Architecture Summary", "QA Feedback", "Raw JSON State"]
                )

                with tab1:
                    st.markdown(response.get("architecture_summary", "*No summary provided.*"))

                with tab2:
                    st.markdown(response.get("feedback", "*No QA feedback available.*"))
                    if response.get("failed_criteria"):
                        st.error(f"Failed Criteria:\n{response.get('failed_criteria')}")
                    st.info(f"Total iterations/retries: {response.get('retry_count', 0)}")

                with tab3:
                    st.json(response)

            except Exception as e:
                st.error(f"An error occurred during execution: {e}")
