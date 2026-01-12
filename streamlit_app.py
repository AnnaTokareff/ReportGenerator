"""
Streamlit web interface for Meeting Reporter

Simple interface for:
- Uploading audio/video files
- Tracking processing status
- Viewing results (transcript, topics, decisions, action items)
- Generating reports
- Asking questions to the support agent
"""

import streamlit as st
import httpx
import time
from pathlib import Path
from typing import Optional

# Configuration
API_BASE_URL = "http://127.0.0.1:8000"
TIMEOUT = 300.0  # 5 minutes for large files

# Session state initialization
if "token" not in st.session_state:
    st.session_state.token = None
if "username" not in st.session_state:
    st.session_state.username = None
if "password" not in st.session_state:
    st.session_state.password = None


def make_request(method: str, endpoint: str, **kwargs) -> Optional[dict]:
    """Generic helper for API requests."""
    url = f"{API_BASE_URL}{endpoint}"
    headers = kwargs.pop("headers", {})

    if st.session_state.token:
        headers["Authorization"] = f"Bearer {st.session_state.token}"

    try:
        with httpx.Client(timeout=TIMEOUT, verify=False) as client:
            if method == "GET":
                response = client.get(url, headers=headers)
            elif method == "POST":
                response = client.post(url, headers=headers, **kwargs)
            elif method == "DELETE":
                response = client.delete(url, headers=headers)
            else:
                return None

            if response.status_code in (200, 201):
                return response.json()

            try:
                error_data = response.json()
                error_detail = error_data.get("detail", response.text)
                st.error(f"Error: {error_detail}")
            except:
                st.error(f"API error {response.status_code}: {response.text}")
            return None

    except httpx.ConnectError as e:
        st.error(f"Couldn't connect to API. Make sure {API_BASE_URL} exists")
        st.error(f"Error: {e}")
        return None
    except Exception as e:
        st.error(f"Connection error: {e}")
        return None


def login_user(username: str, password: str) -> bool:
    """User login."""
    data = make_request(
        "POST",
        "/auth/login",
        json={"username": username, "password": password},
    )
    if data and "access_token" in data:
        st.session_state.token = data["access_token"]
        st.session_state.username = username
        st.session_state.password = password
        return True
    return False


def register_user(username: str, password: str) -> bool:
    """User registration."""
    data = make_request(
        "POST",
        "/auth/signup",
        json={"username": username, "password": password},
    )
    return data is not None


def upload_file(file, title: str) -> Optional[int]:
    """Upload audio or video file."""
    files = {"file": (file.name, file.read(), "application/octet-stream")}
    data = {"title": title}

    response = make_request(
        "POST",
        "/meetings/upload",
        files=files,
        data=data,
    )
    if response and "id" in response:
        return response["id"]
    return None


def get_meeting_status(meeting_id: int) -> Optional[dict]:
    """Get meeting processing status."""
    return make_request("GET", f"/meetings/{meeting_id}/status")


def get_meeting(meeting_id: int) -> Optional[dict]:
    """Get full meeting data."""
    return make_request("GET", f"/meetings/{meeting_id}")


def generate_report(meeting_id: int, include_transcription: bool = True) -> Optional[dict]:
    """Generate meeting report."""
    data = {
        "include_transcription": include_transcription,
        "include_timestamps": False,
    }
    return make_request("POST", f"/meetings/{meeting_id}/report", json=data)


def download_report_file(meeting_id: int) -> Optional[bytes]:
    """Download previously generated report file."""
    url = f"{API_BASE_URL}/meetings/{meeting_id}/report/download"
    headers = {"Authorization": f"Bearer {st.session_state.token}"}

    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(url, headers=headers)
            if response.status_code == 200:
                return response.content

            st.error(f"Download error {response.status_code}: {response.text}")
            return None

    except Exception as e:
        st.error(f"Connection error: {e}")
        return None


def query_support(question: str, meeting_ids: Optional[list] = None) -> Optional[dict]:
    """Query support agent."""
    data = {"question": question}
    if meeting_ids:
        data["meeting_ids"] = meeting_ids
    return make_request("POST", "/support/query", json=data)


def get_user_meetings() -> list:
    """Get current user's meetings."""
    response = make_request("GET", "/meetings")
    return response or []


# ============================================================================
# UI
# ============================================================================

st.set_page_config(
    page_title="Meeting Reporter",
    layout="wide",
)

st.title("Meeting Reporter")
st.markdown("Upload meeting recordings and get structured reports automatically.")

# Sidebar: authentication
with st.sidebar:
    st.header("Authentication")

    if not st.session_state.token:
        tab_login, tab_register = st.tabs(["Login", "Register"])

        with tab_login:
            username = st.text_input("Username", key="login_username")
            password = st.text_input("Password", type="password", key="login_password")

            if st.button("Log in"):
                if login_user(username, password):
                    st.success("Logged in successfully")
                    st.rerun()
                else:
                    st.error("Invalid username or password")

        with tab_register:
            reg_username = st.text_input("Username", key="reg_username")
            reg_password = st.text_input("Password", type="password", key="reg_password")

            if st.button("Register"):
                if register_user(reg_username, reg_password):
                    st.success("Registration successful. You can now log in.")
                else:
                    st.error("Registration failed")

    else:
        st.success(f"Logged in as {st.session_state.username}")
        if st.button("Log out"):
            st.session_state.token = None
            st.session_state.username = None
            st.rerun()


if not st.session_state.token:
    st.info("Please log in or register using the sidebar.")
else:
    tab_upload, tab_meetings, tab_support, tab_about = st.tabs(
        ["Upload", "My Meetings", "Support Agent", "About"]
    )

    # Upload tab
    with tab_upload:
        st.header("Upload audio or video file")

        uploaded_file = st.file_uploader(
            "Choose file",
            type=[
                "mp3", "wav", "ogg", "m4a",
                "mp4", "mov", "avi", "webm", "mkv", "3gp",
            ],
        )

        if uploaded_file:
            size_mb = len(uploaded_file.getvalue()) / (1024 * 1024)
            st.info(f"File: {uploaded_file.name} ({size_mb:.2f} MB)")

            if size_mb > 25:
                st.info("File exceeds 25 MB. It will be automatically compressed before processing.")
            elif size_mb > 20:
                st.info("File is large. It may be compressed automatically if needed.")

            title = st.text_input(
                "Meeting title",
                value=uploaded_file.name.rsplit(".", 1)[0],
            )

            if st.button("Upload and process"):
                with st.spinner("Uploading file..."):
                    meeting_id = upload_file(uploaded_file, title)

                if meeting_id:
                    st.success(f"File uploaded. Meeting ID: {meeting_id}")

                    progress = st.progress(0)
                    status_text = st.empty()
                    status = "unknown"

                    while True:
                        status_data = get_meeting_status(meeting_id)
                        if not status_data:
                            break

                        status = status_data.get("status", "unknown")
                        message = status_data.get("message", "")
                        status_text.text(f"Status: {status} {message}")

                        if status == "completed":
                            progress.progress(100)
                            st.success("Processing completed")
                            break
                        elif status == "failed":
                            st.error(status_data.get("error_message", "Processing failed"))
                            break
                        elif status == "processing":
                            progress.progress(50)
                        else:
                            progress.progress(10)

                        time.sleep(2)

                    if status == "completed":
                        st.info("See results in the 'My Meetings' tab")

    # My meetings tab
    with tab_meetings:
        st.header("My meetings")

        if st.button("Refresh list"):
            st.rerun()

        meetings = get_user_meetings()

        if not meetings:
            st.info("No meetings yet")
        else:
            for meeting in meetings:
                with st.expander(
                    f"{meeting.get('title', 'Untitled')} (ID: {meeting.get('id')})"
                ):
                    st.write(f"Status: {meeting.get('status')}")
                    st.write(f"Created at: {meeting.get('created_at')}")

                    if meeting.get("status") == "completed":
                        if st.button("Show details", key=f"details_{meeting['id']}"):
                            data = get_meeting(meeting["id"])

                            if not data:
                                continue

                            if data.get("transcription", {}).get("summary"):
                                st.subheader("Summary")
                                st.write(data["transcription"]["summary"])

                            if data.get("topics"):
                                st.subheader("Topics")
                                for t in data["topics"]:
                                    st.write(
                                        f"- {t.get('topic_name')} "
                                        f"({t.get('relevance_score', 0):.2f})"
                                    )

                            if data.get("decisions"):
                                st.subheader("Decisions")
                                for d in data["decisions"]:
                                    st.write(d.get("decision_text"))

                            if data.get("action_items"):
                                st.subheader("Action items")
                                for a in data["action_items"]:
                                    st.write(a.get("task_description"))

    # Support agent tab
    with tab_support:
        st.header("Support agent")
        st.markdown("Ask questions about your processed meetings.")

        meetings = [
            m for m in get_user_meetings() if m.get("status") == "completed"
        ]

        if not meetings:
            st.info("No completed meetings available")
        else:
            if "chat_history" not in st.session_state:
                st.session_state.chat_history = []
            
            #  chat history
            if st.session_state.chat_history:
                st.subheader("Conversation")
                for i, (q, a, conf) in enumerate(st.session_state.chat_history):
                    with st.expander(f"Q: {q[:50]}..." if len(q) > 50 else f"Q: {q}", expanded=(i == len(st.session_state.chat_history) - 1)):
                        st.markdown(f"**Question:** {q}")
                        st.markdown(f"**Answer:** {a}")
                        if conf is not None:
                            st.caption(f"Confidence: {conf:.1%}")
                
                if st.button("Clear conversation"):
                    st.session_state.chat_history = []
                    st.rerun()
            
            st.divider()
            
            # Question input
            question = st.text_area(
                "Your question",
                placeholder="e.g., Who attended the meeting? What decisions were made? When is the deadline?",
                key="question_input"
            )

            meeting_map = {
                f"{m['title']} (ID {m['id']})": m["id"] for m in meetings
            }
            selected = st.multiselect(
                "Limit search to meetings (optional)",
                options=list(meeting_map.keys()),
                help="Leave empty to search all meetings"
            )
            meeting_ids = [meeting_map[k] for k in selected] if selected else None

            search_button = st.button("Search", type="primary")

            if search_button:
                if question and question.strip():
                    with st.spinner("Searching through meetings..."):
                        result = query_support(question.strip(), meeting_ids)

                    if result:
                        answer = result.get("answer", "")
                        confidence = result.get("confidence", 0.0)
                        
                        #  to chat history
                        st.session_state.chat_history.append((question.strip(), answer, confidence))
                        
                        st.success("Answer found!")
                        st.rerun()
                    else:
                        st.error("Failed to get answer. Please try again.")
                else:
                    st.warning("Please enter a question")

    with tab_about:
        st.header("About")
        st.markdown(
            """
**Meeting Reporter** is a system for automatic meeting analysis.

Features:
- Speech-to-text transcription
- Topic, decision and action item extraction
- Markdown report generation
- Semantic search via support agent

Tech stack:
- FastAPI
- OpenAI Whisper
- OpenAI GPT
- Sentence Transformers
- Streamlit
"""
        )
