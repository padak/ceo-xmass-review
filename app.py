import streamlit as st
import json
import os
import tempfile
import logging
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file (for local development)
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Keboola OIDC header for user email
KEBOOLA_USER_HEADER = "X-Kbc-User-Email"

# Keboola Storage configuration
KBC_URL = os.environ.get("KBC_URL") or os.environ.get("KBC_API_URL", "https://connection.keboola.com")
KBC_TOKEN = os.environ.get("KBC_TOKEN") or os.environ.get("KBC_API_TOKEN", "")

# Tag for CEO Assessment answers
ANSWERS_TAG = "CEO_Assessment_Answers"


def get_keboola_files_client():
    """Get Keboola Storage Files client."""
    if not KBC_TOKEN:
        logger.warning("KBC_TOKEN not set - Keboola Storage integration disabled")
        return None
    try:
        from kbcstorage.files import Files
        return Files(KBC_URL, KBC_TOKEN)
    except ImportError:
        logger.warning("kbcstorage not installed - Keboola Storage integration disabled")
        return None
    except Exception as e:
        logger.error(f"Failed to initialize Keboola Files client: {e}")
        return None


def email_to_filename(email: str) -> str:
    """Convert email to safe filename. e.g., petr@keboola.com -> petr_keboola.com.json"""
    if not email:
        return "anonymous.json"
    # Replace @ with _ and keep the rest
    safe_name = email.replace("@", "_")
    return f"{safe_name}.json"


def filename_to_email(filename: str) -> str:
    """Convert filename back to email. e.g., petr_keboola.com.json -> petr@keboola.com"""
    if not filename:
        return ""
    # Remove .json extension
    name = filename.replace(".json", "")
    # Find the first underscore and replace with @
    parts = name.split("_", 1)
    if len(parts) == 2:
        return f"{parts[0]}@{parts[1]}"
    return name


def load_answers_from_keboola(email: str) -> dict | None:
    """Load existing answers for a user from Keboola Storage."""
    files_client = get_keboola_files_client()
    if not files_client:
        return None

    target_filename = email_to_filename(email)
    logger.info(f"Looking for file: {target_filename} with tag: {ANSWERS_TAG}")

    try:
        # List files with our tag
        files_list = files_client.list(tags=[ANSWERS_TAG], limit=1000)
        logger.info(f"Found {len(files_list)} files with tag {ANSWERS_TAG}")

        # Find file for this user
        for file_info in files_list:
            if file_info.get("name") == target_filename:
                file_id = file_info.get("id")
                logger.info(f"Found matching file: {file_id}")

                # Download to temp file
                with tempfile.TemporaryDirectory() as tmp_dir:
                    local_path = os.path.join(tmp_dir, target_filename)
                    files_client.download(file_id, local_path)

                    # Read and parse JSON
                    with open(local_path, "r") as f:
                        data = json.load(f)
                        logger.info(f"Loaded answers for {email}")
                        return data

        logger.info(f"No existing answers found for {email}")
        return None

    except Exception as e:
        logger.error(f"Error loading answers from Keboola: {e}")
        return None


def save_answers_to_keboola(email: str, answers: dict) -> bool:
    """Save answers to Keboola Storage as a file with tag."""
    files_client = get_keboola_files_client()
    if not files_client:
        # Fallback to local file
        save_answers_locally(email, answers)
        return False

    filename = email_to_filename(email)

    try:
        # Create temp file with answers
        with tempfile.TemporaryDirectory() as tmp_dir:
            local_path = os.path.join(tmp_dir, filename)

            # Prepare data
            data = {
                "email": email,
                "submitted_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "answers": answers
            }

            # Write to temp file
            with open(local_path, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # Upload to Keboola with tag
            result = files_client.upload_file(
                file_path=local_path,
                tags=[ANSWERS_TAG],
                is_permanent=True,
                is_public=False
            )
            logger.info(f"Saved answers to Keboola: {result}")
            return True

    except Exception as e:
        logger.error(f"Error saving answers to Keboola: {e}")
        # Fallback to local file
        save_answers_locally(email, answers)
        return False


def save_answers_locally(email: str, answers: dict):
    """Fallback: save answers to local file."""
    output_dir = "data/out/files"
    os.makedirs(output_dir, exist_ok=True)

    filename = email_to_filename(email)
    filepath = os.path.join(output_dir, filename)

    data = {
        "email": email,
        "submitted_at": datetime.now().isoformat(),
        "answers": answers
    }

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved answers locally to {filepath}")


def get_authenticated_user():
    """
    Get authenticated user email from Keboola OIDC proxy header.
    Falls back to DEV_USER_EMAIL env variable for local development.
    Returns email string or None if not authenticated.
    """
    # First check for dev/local override
    dev_email = os.environ.get("DEV_USER_EMAIL")
    if dev_email:
        return dev_email

    # Then try Keboola OIDC header
    try:
        headers = st.context.headers
        return headers.get(KEBOOLA_USER_HEADER)
    except Exception:
        return None


def get_debug_headers():
    """Get all headers for debugging."""
    try:
        return dict(st.context.headers)
    except Exception as e:
        return {"error": str(e)}


# Page config
st.set_page_config(
    page_title="CEO Assessment",
    page_icon="📋",
    layout="centered"
)

# Custom CSS for better styling
st.markdown("""
<style>
    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* Progress bar styling */
    .stProgress > div > div > div > div {
        background-color: #4CAF50;
    }

    /* Card-like container */
    .question-card {
        background-color: #f8f9fa;
        padding: 2rem;
        border-radius: 10px;
        margin: 1rem 0;
    }

    /* Question number badge */
    .question-number {
        background-color: #4CAF50;
        color: white;
        padding: 0.3rem 0.8rem;
        border-radius: 20px;
        font-size: 0.9rem;
        margin-bottom: 1rem;
        display: inline-block;
    }

    /* Navigation buttons */
    .stButton > button {
        border-radius: 20px;
        padding: 0.5rem 2rem;
    }

    /* Center title */
    h1 {
        text-align: center;
        margin-bottom: 2rem;
    }

    /* Subtitle styling */
    .subtitle {
        color: #666;
        font-size: 0.95rem;
        margin-bottom: 1rem;
    }
</style>
<script>
    // Auto-focus the first Streamlit textarea/input on page load
    (function() {
        function focusFirstInput() {
            // Try multiple document contexts
            const docs = [document, window.parent.document];
            for (const doc of docs) {
                try {
                    // Look for Streamlit's textarea (id starts with text_area_) or text input
                    const textarea = doc.querySelector('textarea[id^="text_area_"]');
                    if (textarea) {
                        textarea.focus();
                        return true;
                    }
                    // Fallback to any visible textarea
                    const anyTextarea = doc.querySelector('textarea[aria-label="Your answer"]');
                    if (anyTextarea) {
                        anyTextarea.focus();
                        return true;
                    }
                } catch(e) {}
            }
            return false;
        }

        // Retry with increasing delays
        const delays = [50, 100, 200, 300, 500, 700, 1000];
        delays.forEach((delay, i) => {
            setTimeout(() => {
                focusFirstInput();
            }, delay);
        });
    })();
</script>
""", unsafe_allow_html=True)


# Questions definition (id starts at 1, user identified via OIDC)
QUESTIONS = [
    {
        "id": 1,
        "title": "What have you shipped in the last 3 weeks that made our customers' lives better?",
        "type": "text_area"
    },
    {
        "id": 2,
        "title": "In which areas do you support me so well that I don't have to think about them?",
        "type": "text_area"
    },
    {
        "id": 3,
        "title": "What do you excel at?",
        "type": "text_area"
    },
    {
        "id": 4,
        "title": "What do your colleagues excel at that you admire or learn from?",
        "type": "text_area"
    },
    {
        "id": 5,
        "title": "What bottlenecks with other departments, if cleared, would help you most?",
        "type": "text_area"
    },
    {
        "id": 6,
        "title": "If you could magically eliminate 3 activities that cause you the most pain, which would they be?",
        "type": "text_area",
        "placeholder": "1. \n2. \n3. "
    },
    {
        "id": 7,
        "title": "Self-evaluation",
        "subtitle": "Let's reflect on your strengths and growth areas",
        "type": "compound",
        "subquestions": [
            {"key": "a", "label": "What are you struggling with? Where could I (CEO) help you improve?"},
            {"key": "b", "label": "What are you great at that might be underutilized and could help the company more?"}
        ]
    },
    {
        "id": 8,
        "title": "What would you do if you were in my (CEO) role?",
        "subtitle": "Think about different time horizons",
        "type": "compound",
        "subquestions": [
            {"key": "a", "label": "Next 7 days?"},
            {"key": "b", "label": "Next 30 days?"},
            {"key": "c", "label": "Next 90 days?"}
        ]
    },
    {
        "id": 9,
        "title": "Pick any role(s) in the company - what would you do differently if you were in that role?",
        "subtitle": "You can comment on multiple roles",
        "type": "text_area",
        "placeholder": "Role: ...\nWhat I would do: ...\n\nRole: ...\nWhat I would do: ..."
    },
    {
        "id": 10,
        "title": "What are our top 3 priorities and why?",
        "subtitle": "What outcomes will they bring to customers and revenue?",
        "type": "text_area",
        "placeholder": "1. Priority: ... Why: ... Outcome: ...\n\n2. Priority: ... Why: ... Outcome: ...\n\n3. Priority: ... Why: ... Outcome: ..."
    },
    {
        "id": 11,
        "title": "What is THE single most important priority for the foreseeable future?",
        "subtitle": "The one thing that would have 50%+ impact",
        "type": "text_area"
    }
]

TOTAL_QUESTIONS = len(QUESTIONS)


def init_session_state(authenticated_user: str | None):
    """Initialize session state variables and load existing answers."""
    if "initialized" not in st.session_state:
        st.session_state.initialized = False

    if "current_step" not in st.session_state:
        st.session_state.current_step = 0

    if "answers" not in st.session_state:
        st.session_state.answers = {}

    if "submitted" not in st.session_state:
        st.session_state.submitted = False

    if "answers_loaded" not in st.session_state:
        st.session_state.answers_loaded = False

    # Load existing answers from Keboola (only once per session)
    if not st.session_state.answers_loaded and authenticated_user:
        existing_data = load_answers_from_keboola(authenticated_user)
        if existing_data and "answers" in existing_data:
            st.session_state.answers = existing_data["answers"]
            st.session_state.has_existing_answers = True
            logger.info(f"Loaded existing answers for {authenticated_user}")
        else:
            st.session_state.has_existing_answers = False
        st.session_state.answers_loaded = True


def get_answer_key(question_id, sub_key=None):
    """Generate a unique key for storing answers."""
    if sub_key:
        return f"q{question_id}_{sub_key}"
    return f"q{question_id}"


def init_widget_state(widget_key: str, answer_key: str):
    """Initialize widget state from answers if not already set."""
    if widget_key not in st.session_state:
        st.session_state[widget_key] = st.session_state.answers.get(answer_key, "")


def sync_answer(widget_key: str, answer_key: str):
    """Sync widget value back to answers."""
    st.session_state.answers[answer_key] = st.session_state.get(widget_key, "")


def render_question(question):
    """Render a single question based on its type."""
    q_id = question["id"]
    q_type = question["type"]

    # Question header
    st.markdown(f"<span class='question-number'>Question {q_id} of {TOTAL_QUESTIONS}</span>", unsafe_allow_html=True)
    st.markdown(f"## {question['title']}")

    if "subtitle" in question:
        st.markdown(f"<p class='subtitle'>{question['subtitle']}</p>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    placeholder = question.get("placeholder", "")

    if q_type == "text_input":
        answer_key = get_answer_key(q_id)
        widget_key = f"input_{q_id}"
        init_widget_state(widget_key, answer_key)

        st.text_input(
            label="Your answer",
            placeholder=placeholder,
            label_visibility="collapsed",
            key=widget_key,
            on_change=sync_answer,
            args=(widget_key, answer_key)
        )
        # Also sync immediately for current render
        sync_answer(widget_key, answer_key)
        return st.session_state.get(widget_key, "")

    elif q_type == "text_area":
        answer_key = get_answer_key(q_id)
        widget_key = f"input_{q_id}"
        init_widget_state(widget_key, answer_key)

        st.text_area(
            label="Your answer",
            placeholder=placeholder,
            label_visibility="collapsed",
            height=200,
            key=widget_key,
            on_change=sync_answer,
            args=(widget_key, answer_key)
        )
        sync_answer(widget_key, answer_key)
        return st.session_state.get(widget_key, "")

    elif q_type == "compound":
        responses = {}
        for sub in question["subquestions"]:
            sub_key = sub["key"]
            answer_key = get_answer_key(q_id, sub_key)
            widget_key = f"input_{q_id}_{sub_key}"
            init_widget_state(widget_key, answer_key)

            st.markdown(f"**{sub_key})** {sub['label']}")
            st.text_area(
                label=f"Answer for {sub_key}",
                label_visibility="collapsed",
                height=120,
                key=widget_key,
                on_change=sync_answer,
                args=(widget_key, answer_key)
            )
            sync_answer(widget_key, answer_key)
            responses[sub_key] = st.session_state.get(widget_key, "")
            st.markdown("<br>", unsafe_allow_html=True)
        return responses

    return None


def render_progress_bar():
    """Render progress bar at the top."""
    progress = (st.session_state.current_step + 1) / TOTAL_QUESTIONS
    st.progress(progress)
    st.markdown(f"<p style='text-align: center; color: #666;'>Step {st.session_state.current_step + 1} of {TOTAL_QUESTIONS}</p>", unsafe_allow_html=True)


def render_navigation(authenticated_user):
    """Render navigation buttons."""
    col1, col2, col3 = st.columns([1, 1, 1])

    current = st.session_state.current_step

    with col1:
        if current > 0:
            if st.button("← Previous", use_container_width=True):
                st.session_state.current_step -= 1
                st.rerun()

    with col3:
        if current < TOTAL_QUESTIONS - 1:
            if st.button("Next →", use_container_width=True, type="primary"):
                st.session_state.current_step += 1
                st.rerun()
        else:
            if st.button("Submit ✓", use_container_width=True, type="primary"):
                submit_assessment(authenticated_user)


def submit_assessment(authenticated_user):
    """Submit the assessment."""
    # Get user from OIDC or fallback
    user_email = authenticated_user or "anonymous"

    # Save to Keboola Storage
    save_answers_to_keboola(user_email, st.session_state.answers)

    st.session_state.submitted = True
    st.rerun()


def render_thank_you():
    """Render thank you page after submission."""
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("# 🎉 Thank You!")
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("""
    <div style='text-align: center; font-size: 1.2rem;'>
        Your assessment has been submitted successfully.<br><br>
        I really appreciate you taking the time to share your thoughts.<br>
        Your feedback is invaluable for our growth.
    </div>
    """, unsafe_allow_html=True)
    st.balloons()


def main():
    # Get authenticated user from Keboola OIDC
    authenticated_user = get_authenticated_user()

    # Initialize session state (and load existing answers)
    init_session_state(authenticated_user)

    # Header
    st.markdown("# 📋 CEO Assessment")

    # Debug mode - show headers and Keboola config (use query param ?debug=1)
    if st.query_params.get("debug"):
        with st.expander("🔧 Debug Info", expanded=True):
            st.write(f"**Authenticated user:** {authenticated_user}")
            st.write(f"**KBC_URL:** {KBC_URL}")
            st.write(f"**KBC_TOKEN:** {'***' + KBC_TOKEN[-4:] if KBC_TOKEN else 'Not set'}")
            st.write(f"**Has existing answers:** {st.session_state.get('has_existing_answers', False)}")
            st.json(get_debug_headers())

    # Check if already submitted
    if st.session_state.submitted:
        render_thank_you()
        return

    # Welcome message on first question
    if st.session_state.current_step == 0:
        user_display = authenticated_user or "there"
        existing_note = ""
        if st.session_state.get("has_existing_answers"):
            existing_note = "<br><em>📝 We found your previous answers - feel free to update them!</em>"

        st.markdown(f"""
        <div style='background-color: #e8f5e9; padding: 1rem; border-radius: 10px; margin-bottom: 2rem;'>
            <strong>Hi {user_display}!</strong><br><br>
            Thank you for taking the time to share your thoughts.
            Your honest feedback helps me understand how we can work better together.
            {existing_note}
        </div>
        """, unsafe_allow_html=True)

    # Progress bar
    render_progress_bar()

    st.markdown("---")

    # Current question
    current_question = QUESTIONS[st.session_state.current_step]
    render_question(current_question)

    st.markdown("<br><br>", unsafe_allow_html=True)

    # Navigation
    render_navigation(authenticated_user)

    # Question dots navigation
    st.markdown("<br>", unsafe_allow_html=True)
    cols = st.columns(TOTAL_QUESTIONS)
    for i, col in enumerate(cols):
        with col:
            q_id = QUESTIONS[i]["id"]
            if i == st.session_state.current_step:
                st.markdown("●")
            elif st.session_state.answers.get(f"q{q_id}") or any(
                st.session_state.answers.get(f"q{q_id}_{k}")
                for k in ["a", "b", "c"]
            ):
                st.markdown("○")
            else:
                st.markdown("·")


if __name__ == "__main__":
    main()
