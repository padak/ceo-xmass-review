import streamlit as st
import streamlit.components.v1 as components
import json
import os
import tempfile
import logging
import io
import random
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import yaml
from streamlit_sortables import sort_items

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

# CEO email for admin view (shows all responses)
CEO_EMAIL = os.environ.get("CEO_EMAIL", "")


def get_answers_tag() -> str:
    """Get the tag for storing answers based on questionnaire_id and version from settings."""
    q_id = SETTINGS.get("questionnaire_id", "Assessment")
    version = SETTINGS.get("version", "1")
    return f"{q_id}_v{version}"


# Questionnaires folder path
QUESTIONNAIRES_DIR = Path(__file__).parent / "questionnaires"

# Default settings for questionnaires
# Note: questionnaire_id, version, and title are REQUIRED (no defaults)
DEFAULT_SETTINGS = {
    # questionnaire_id: REQUIRED - no default
    # version: REQUIRED - no default
    # title: REQUIRED - no default
    "display_mode": "one_by_one",  # "one_by_one" or "all_at_once"
    "show_progress_bar": True,
    "allow_back_navigation": True,
    "show_question_numbers": True,
    "require_all_answers": False,
    "randomize_questions": False,
    "randomize_options": False,
    "auto_advance": False,
    "auto_advance_delay": 600,
    "show_balloons": True,  # Show balloons animation after submit
    "welcome_message": "",
    "thank_you_message": "Thank you for completing the assessment!",
}

# Required settings that must be provided in YAML
REQUIRED_SETTINGS = ["questionnaire_id", "version", "title"]


def get_questionnaire_path() -> Path | None:
    """Determine which questionnaire file to load.

    Priority:
    1. ENV var QUESTIONNAIRE (filename without path, e.g., "questions.yaml")
    2. If only one .yaml file exists in questionnaires/, use it automatically
    3. If multiple files exist and no ENV var set, return None (error state)

    Returns:
        Path to questionnaire file, or None if configuration is required.
    """
    # Get all YAML files in questionnaires folder
    yaml_files = list(QUESTIONNAIRES_DIR.glob("*.yaml")) + list(QUESTIONNAIRES_DIR.glob("*.yml"))

    # Priority 1: ENV var
    env_questionnaire = os.environ.get("QUESTIONNAIRE")
    if env_questionnaire:
        path = QUESTIONNAIRES_DIR / env_questionnaire
        if path.exists():
            logger.info(f"Using questionnaire from ENV: {env_questionnaire}")
            return path
        else:
            logger.error(f"ENV QUESTIONNAIRE '{env_questionnaire}' not found in {QUESTIONNAIRES_DIR}")
            return None

    # Priority 2: Single file auto-detection
    if len(yaml_files) == 1:
        logger.info(f"Auto-detected single questionnaire: {yaml_files[0].name}")
        return yaml_files[0]

    # Priority 3: Multiple files without ENV var = error
    if len(yaml_files) > 1:
        logger.error(f"Multiple questionnaires found but QUESTIONNAIRE env var not set")
        return None

    # No files found
    if not yaml_files:
        logger.error(f"No questionnaire files found in {QUESTIONNAIRES_DIR}")
        return None

    return None


def load_questions_from_yaml(config_path: Path | str | None = None) -> tuple[list[dict], list[dict], dict] | None:
    """Load questions configuration and settings from YAML file.

    Args:
        config_path: Optional path to questionnaire file. If None, auto-detects.

    Returns:
        Tuple of (intro_questions, main_questions, settings), or None if not configured.
    """
    # Determine path if not provided
    if config_path is None:
        config_path = get_questionnaire_path()
        if config_path is None:
            return None  # Not configured - will show error page
    elif isinstance(config_path, str):
        config_path = Path(config_path)

    if not config_path.exists():
        logger.error(f"Questionnaire not found: {config_path}")
        return None

    logger.info(f"Loading questions from {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

        # intro_questions are never shuffled (demographics, name, etc.)
        intro_questions = config.get("intro_questions", [])
        questions = config.get("questions", [])

        # Get YAML settings
        yaml_settings = config.get("settings", {})

        # Validate required settings
        missing = [key for key in REQUIRED_SETTINGS if not yaml_settings.get(key)]
        if missing:
            raise ValueError(
                f"Missing required settings in {config_path.name}: {', '.join(missing)}. "
                f"Please add these to your YAML settings section."
            )

        # Merge settings with defaults
        settings = DEFAULT_SETTINGS.copy()
        settings.update(yaml_settings)

        total = len(intro_questions) + len(questions)
        logger.info(f"Loaded {total} questions ({len(intro_questions)} intro + {len(questions)} main), display_mode={settings['display_mode']}")
        return intro_questions, questions, settings


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
    answers_tag = get_answers_tag()
    logger.info(f"Looking for file with tags: {answers_tag} + {email}")

    try:
        # List files with assessment tag first
        files_list = files_client.list(tags=[answers_tag], limit=1000)
        logger.info(f"Found {len(files_list)} files with tag {answers_tag}")

        # Filter to find files that ALSO have the user's email tag
        for file_info in files_list:
            file_tags = file_info.get("tags", [])
            # Check if file has BOTH required tags
            tag_names = [t.get("name") if isinstance(t, dict) else t for t in file_tags]
            if email in tag_names:
                file_id = file_info.get("id")
                file_name = file_info.get("name", target_filename)
                logger.info(f"Found matching file with both tags: {file_id} ({file_name})")

                # Download to temp directory
                with tempfile.TemporaryDirectory() as tmp_dir:
                    files_client.download(file_id, tmp_dir)
                    local_path = os.path.join(tmp_dir, file_name)

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


def load_all_answers_from_keboola() -> list[dict]:
    """Load all answers from Keboola Storage for CEO dashboard."""
    files_client = get_keboola_files_client()
    if not files_client:
        return []

    logger.info("Loading all assessment answers for CEO dashboard")
    all_answers = []
    answers_tag = get_answers_tag()

    try:
        # List all files with assessment tag
        files_list = files_client.list(tags=[answers_tag], limit=1000)
        logger.info(f"Found {len(files_list)} files with tag {answers_tag}")

        for file_info in files_list:
            file_id = file_info.get("id")
            file_name = file_info.get("name", "unknown.json")

            # Extract email from tags (second tag should be the email)
            file_tags = file_info.get("tags", [])
            tag_names = [t.get("name") if isinstance(t, dict) else t for t in file_tags]
            # Find email tag (not the answers_tag)
            user_email = None
            for tag in tag_names:
                if tag != answers_tag and "@" in tag:
                    user_email = tag
                    break

            if not user_email:
                continue

            try:
                # Download to temp directory
                with tempfile.TemporaryDirectory() as tmp_dir:
                    files_client.download(file_id, tmp_dir)
                    local_path = os.path.join(tmp_dir, file_name)

                    with open(local_path, "r") as f:
                        data = json.load(f)
                        data["_user_email"] = user_email
                        all_answers.append(data)
                        logger.info(f"Loaded answers from {user_email}")
            except Exception as e:
                logger.error(f"Error loading file {file_id}: {e}")
                continue

        return all_answers

    except Exception as e:
        logger.error(f"Error loading all answers from Keboola: {e}")
        return []


def delete_existing_file_from_keboola(email: str) -> bool:
    """Delete existing answers file for a user from Keboola Storage."""
    files_client = get_keboola_files_client()
    if not files_client:
        return False

    answers_tag = get_answers_tag()
    try:
        # List files with assessment tag
        files_list = files_client.list(tags=[answers_tag], limit=1000)

        # Find and delete only files that ALSO have the user's email tag
        for file_info in files_list:
            file_tags = file_info.get("tags", [])
            tag_names = [t.get("name") if isinstance(t, dict) else t for t in file_tags]
            if email in tag_names:
                file_id = file_info.get("id")
                file_name = file_info.get("name")
                logger.info(f"Deleting old file: {file_id} ({file_name})")
                files_client.delete(file_id)

        return True

    except Exception as e:
        logger.error(f"Error deleting old file from Keboola: {e}")
        return False


def save_answers_to_keboola(email: str, answers: dict, save_email_tag: bool = True) -> bool:
    """
    Save answers to Keboola Storage as a file with tag.

    Args:
        email: User email (or "anonymous")
        answers: Dictionary of answers
        save_email_tag: If True, include email as a tag (for OIDC-authenticated users).
                       If False, only save with questionnaire tag (anonymous mode).
    """
    files_client = get_keboola_files_client()
    if not files_client:
        # Fallback to local file
        save_answers_locally(email, answers)
        return False

    filename = email_to_filename(email)
    answers_tag = get_answers_tag()

    try:
        # First, delete any existing file for this user (only if we have email tag)
        if save_email_tag and email != "anonymous":
            delete_existing_file_from_keboola(email)

        # Create temp file with answers
        with tempfile.TemporaryDirectory() as tmp_dir:
            local_path = os.path.join(tmp_dir, filename)

            # Prepare data - include questionnaire metadata
            data = {
                "email": email if save_email_tag else "anonymous",
                "questionnaire_id": SETTINGS.get("questionnaire_id", "Assessment"),
                "questionnaire_version": SETTINGS.get("version", "1"),
                "submitted_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "answers": answers
            }

            # Write to temp file
            with open(local_path, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # Build tags list
            # - Always include questionnaire tag
            # - Only include email tag if save_email_tag is True (OIDC authenticated)
            tags = [answers_tag]
            if save_email_tag and email != "anonymous":
                tags.append(email)

            # Upload to Keboola
            result = files_client.upload_file(
                file_path=local_path,
                tags=tags,
                is_permanent=True,
                is_public=False
            )
            logger.info(f"Saved answers to Keboola with tags {tags}: {result}")
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


def generate_csv_export(all_answers: list[dict]) -> str:
    """Generate CSV content from all answers."""
    output = io.StringIO()

    # Header row
    respondents = [a.get("_user_email", a.get("email", "Unknown")) for a in all_answers]
    header = ["Question"] + [r.split("@")[0] for r in respondents]
    output.write(",".join(f'"{h}"' for h in header) + "\n")

    # Data rows
    for question in QUESTIONS:
        q_id = question["id"]
        q_type = question["type"]

        if q_type == "compound":
            # Main question header
            row = [f"Q{q_id}: {question['title']}"] + [""] * len(respondents)
            output.write(",".join(f'"{cell}"' for cell in row) + "\n")

            # Sub-questions
            for sub in question["subquestions"]:
                sub_key = sub["key"]
                answer_key = f"q{q_id}_{sub_key}"
                row = [f"  {sub_key}) {sub['label']}"]
                for answer_data in all_answers:
                    answer = answer_data.get("answers", {}).get(answer_key, "")
                    # Escape quotes and newlines for CSV
                    answer = answer.replace('"', '""').replace('\n', ' ')
                    row.append(answer)
                output.write(",".join(f'"{cell}"' for cell in row) + "\n")
        else:
            answer_key = f"q{q_id}"
            row = [f"Q{q_id}: {question['title']}"]
            for answer_data in all_answers:
                answer = answer_data.get("answers", {}).get(answer_key, "")
                answer = answer.replace('"', '""').replace('\n', ' ')
                row.append(answer)
            output.write(",".join(f'"{cell}"' for cell in row) + "\n")

    return output.getvalue()


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


# Page config (title is generic since SETTINGS not loaded yet)
st.set_page_config(
    page_title="Questionnaire",
    page_icon="📋",
    layout="centered"
)

# Custom CSS for better styling
st.markdown("""
<style>
    /* Material Icons */
    @import url('https://fonts.googleapis.com/icon?family=Material+Icons+Outlined');

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

    /* CEO Dashboard question header */
    .question-header {
        background-color: #1a5f2a;
        color: white;
        padding: 12px 16px;
        border-radius: 8px;
        margin-top: 24px;
        margin-bottom: 12px;
        font-size: 1.1rem;
    }

    /* Sortable items styling for ranking */
    .sortable-item {
        background-color: #f8f9fa;
        border: 1px solid #dee2e6;
        border-radius: 8px;
        padding: 12px 16px;
        margin: 4px 0;
        cursor: grab;
        transition: all 0.2s ease;
    }

    .sortable-item:hover {
        background-color: #e9ecef;
        border-color: #4CAF50;
    }

    .sortable-item:active {
        cursor: grabbing;
        background-color: #d4edda;
    }

    /* Yes/No buttons styling */
    div[data-testid="column"] button {
        font-size: 1.1rem !important;
        padding: 1rem !important;
        min-height: 60px !important;
    }

    /* Stretch horizontal radio buttons to full width */
    div[data-testid="stRadio"] > div[role="radiogroup"] {
        display: flex !important;
        justify-content: space-between !important;
        width: 100% !important;
    }

    div[data-testid="stRadio"] > div[role="radiogroup"] > label {
        flex: 1 !important;
        text-align: center !important;
        white-space: nowrap !important;
    }
</style>
""", unsafe_allow_html=True)


# Load questions and settings from YAML configuration file
_load_result = load_questions_from_yaml()
if _load_result is None:
    # Not configured - will show error page in main()
    _INTRO_QUESTIONS, _MAIN_QUESTIONS, SETTINGS = [], [], {}
    QUESTIONNAIRE_NOT_CONFIGURED = True
else:
    _INTRO_QUESTIONS, _MAIN_QUESTIONS, SETTINGS = _load_result
    QUESTIONNAIRE_NOT_CONFIGURED = False


def render_configuration_error():
    """Render error page when questionnaire is not properly configured."""
    yaml_files = list(QUESTIONNAIRES_DIR.glob("*.yaml")) + list(QUESTIONNAIRES_DIR.glob("*.yml"))

    st.markdown("""
    <h1 style="text-align: center; color: #d32f2f;">
        Configuration Required
    </h1>
    """, unsafe_allow_html=True)

    if not yaml_files:
        st.error(f"No questionnaire files found in `{QUESTIONNAIRES_DIR}`")
        st.markdown("""
        ### How to fix:
        1. Create a questionnaire YAML file in the `questionnaires/` folder
        2. See `questionnaires/questions.instructions.md` for documentation
        """)
    else:
        st.warning("Multiple questionnaires found but none is selected.")
        st.markdown("### Available questionnaires:")

        for f in sorted(yaml_files):
            st.code(f.name)

        st.markdown("---")
        st.markdown("### How to select a questionnaire:")

        st.markdown("**Option 1: Keboola Data App** (production)")
        st.markdown("In Keboola Data App settings, go to **Secrets** section and add:")
        st.code(f"QUESTIONNAIRE = {yaml_files[0].name}", language="text")
        st.caption("The variable will be available as environment variable in the app.")

        st.markdown("**Option 2: Local development**")
        st.code(f"QUESTIONNAIRE={yaml_files[0].name} streamlit run app.py", language="bash")

        st.markdown("---")
        st.info("Tip: If you want automatic selection, keep only one `.yaml` file in the `questionnaires/` folder.")


def get_questions() -> list:
    """Get questions list (intro + main, with main optionally randomized per session)."""
    if not SETTINGS.get("randomize_questions", False):
        # No randomization - just combine intro + main
        return _INTRO_QUESTIONS + _MAIN_QUESTIONS

    # Randomize main questions once per session (intro stays at the beginning)
    if "randomized_main_questions" not in st.session_state:
        shuffled = _MAIN_QUESTIONS.copy()
        random.shuffle(shuffled)
        st.session_state.randomized_main_questions = shuffled

    return _INTRO_QUESTIONS + st.session_state.randomized_main_questions


# For backwards compatibility - will be set dynamically in main()
QUESTIONS = _INTRO_QUESTIONS + _MAIN_QUESTIONS
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

    if "show_review" not in st.session_state:
        st.session_state.show_review = False

    if "answers_loaded" not in st.session_state:
        st.session_state.answers_loaded = False

    if "existing_data" not in st.session_state:
        st.session_state.existing_data = None

    if "user_chose_action" not in st.session_state:
        st.session_state.user_chose_action = False

    if "editing_from_review" not in st.session_state:
        st.session_state.editing_from_review = False

    # Check for existing answers from Keboola (only once per session)
    if not st.session_state.answers_loaded and authenticated_user:
        logger.info(f"Checking for existing answers for {authenticated_user}...")
        existing_data = load_answers_from_keboola(authenticated_user)
        logger.info(f"Result: {existing_data}")
        if existing_data and "answers" in existing_data:
            st.session_state.existing_data = existing_data
            st.session_state.has_existing_answers = True
            logger.info(f"Found existing answers for {authenticated_user}")
        else:
            st.session_state.has_existing_answers = False
            st.session_state.user_chose_action = True  # No choice needed
            logger.info(f"No existing answers found for {authenticated_user}")
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


def get_randomized_options(question_id: int, options: list) -> list:
    """Get randomized options for a question (consistent within session)."""
    if not SETTINGS.get("randomize_options", False):
        return options

    # Use a consistent seed per question per session
    cache_key = f"randomized_options_{question_id}"
    if cache_key not in st.session_state:
        shuffled = options.copy()
        random.shuffle(shuffled)
        st.session_state[cache_key] = shuffled

    return st.session_state[cache_key]


def trigger_auto_advance():
    """Trigger auto-advance to next question after a delay."""
    if not SETTINGS.get("auto_advance", False):
        return
    if SETTINGS.get("display_mode") != "one_by_one":
        return

    delay_ms = SETTINGS.get("auto_advance_delay", 600)

    # JavaScript to auto-advance after delay
    js_code = f"""
    <script>
        setTimeout(function() {{
            try {{
                var doc = window.parent.document;
                var nextBtn = doc.querySelector('button[kind="primary"]');
                if (nextBtn && nextBtn.textContent.includes('Next')) {{
                    nextBtn.click();
                }}
            }} catch(e) {{}}
        }}, {delay_ms});
    </script>
    """
    components.html(js_code, height=0)


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

    elif q_type == "radio":
        answer_key = get_answer_key(q_id)
        widget_key = f"radio_{q_id}"
        options = get_randomized_options(q_id, question.get("options", []))

        # Get current value from answers
        current_value = st.session_state.answers.get(answer_key, None)
        # Find index of current value in options (None if not found)
        current_index = options.index(current_value) if current_value in options else None

        selected = st.radio(
            label="Select one option",
            options=options,
            index=current_index,
            label_visibility="collapsed",
            key=widget_key
        )
        st.session_state.answers[answer_key] = selected
        return selected

    elif q_type == "checkbox":
        answer_key = get_answer_key(q_id)
        options = get_randomized_options(q_id, question.get("options", []))

        # Get current selections from answers (stored as comma-separated string or list)
        current_value = st.session_state.answers.get(answer_key, "")
        if isinstance(current_value, str):
            selected_items = [x.strip() for x in current_value.split(",") if x.strip()]
        else:
            selected_items = current_value if current_value else []

        selections = []
        for option in options:
            widget_key = f"checkbox_{q_id}_{option}"
            checked = st.checkbox(
                label=option,
                value=option in selected_items,
                key=widget_key
            )
            if checked:
                selections.append(option)

        # Store as comma-separated string for consistency
        st.session_state.answers[answer_key] = ", ".join(selections)
        return selections

    elif q_type == "select":
        answer_key = get_answer_key(q_id)
        widget_key = f"select_{q_id}"
        options = get_randomized_options(q_id, question.get("options", []))

        # Get current value
        current_value = st.session_state.answers.get(answer_key, "")
        current_index = options.index(current_value) if current_value in options else 0

        # Add empty option at the beginning if needed
        options_with_placeholder = ["-- Select an option --"] + options

        selected = st.selectbox(
            label="Select an option",
            options=options_with_placeholder,
            index=current_index + 1 if current_value else 0,
            label_visibility="collapsed",
            key=widget_key
        )

        # Don't store the placeholder
        if selected != "-- Select an option --":
            st.session_state.answers[answer_key] = selected
        else:
            st.session_state.answers[answer_key] = ""
        return selected if selected != "-- Select an option --" else ""

    elif q_type == "yes_no":
        # Simple Yes/No choice (Typeform style)
        answer_key = get_answer_key(q_id)
        widget_key = f"yesno_{q_id}"

        yes_label = question.get("yes_label", "Yes")
        no_label = question.get("no_label", "No")

        # Get current value
        current_value = st.session_state.answers.get(answer_key, None)

        # Create two big buttons side by side
        col1, col2 = st.columns(2)

        with col1:
            yes_selected = current_value == "yes"
            if st.button(
                f"👍 {yes_label}",
                key=f"{widget_key}_yes",
                use_container_width=True,
                type="primary" if yes_selected else "secondary"
            ):
                st.session_state.answers[answer_key] = "yes"
                trigger_auto_advance()
                st.rerun()

        with col2:
            no_selected = current_value == "no"
            if st.button(
                f"👎 {no_label}",
                key=f"{widget_key}_no",
                use_container_width=True,
                type="primary" if no_selected else "secondary"
            ):
                st.session_state.answers[answer_key] = "no"
                trigger_auto_advance()
                st.rerun()

        return current_value

    elif q_type == "slider":
        # Numeric slider with customizable range
        answer_key = get_answer_key(q_id)
        widget_key = f"slider_{q_id}"

        min_val = question.get("min", 0)
        max_val = question.get("max", 100)
        step = question.get("step", 1)
        default = question.get("default", min_val)

        # Get current value from answers
        current_value = st.session_state.answers.get(answer_key)
        if current_value is not None and current_value != "":
            try:
                current_value = type(min_val)(current_value)
            except (ValueError, TypeError):
                current_value = default
        else:
            current_value = default

        value = st.slider(
            label="Select a value",
            min_value=min_val,
            max_value=max_val,
            value=current_value,
            step=step,
            label_visibility="collapsed",
            key=widget_key
        )
        st.session_state.answers[answer_key] = value
        return value

    elif q_type == "linear_scale":
        # Linear scale with labeled endpoints (like NPS or satisfaction)
        answer_key = get_answer_key(q_id)
        widget_key = f"scale_{q_id}"

        min_val = question.get("min", 1)
        max_val = question.get("max", 10)
        min_label = question.get("min_label", "")
        max_label = question.get("max_label", "")

        # Create scale options
        options = list(range(min_val, max_val + 1))

        # Get current value
        current_value = st.session_state.answers.get(answer_key)
        if current_value is not None and current_value != "":
            try:
                current_index = options.index(int(current_value))
            except (ValueError, IndexError):
                current_index = None
        else:
            current_index = None

        # Show labels if provided
        if min_label or max_label:
            col1, col2 = st.columns([1, 1])
            with col1:
                st.caption(f"← {min_label}" if min_label else "")
            with col2:
                if max_label:
                    st.markdown(f"<p style='text-align: right; color: #666; font-size: 0.85rem; margin: 0;'>{max_label} →</p>", unsafe_allow_html=True)

        selected = st.radio(
            label="Select a value",
            options=options,
            index=current_index,
            horizontal=True,
            label_visibility="collapsed",
            key=widget_key
        )
        st.session_state.answers[answer_key] = selected
        return selected

    elif q_type == "rating":
        # Star/emoji rating
        answer_key = get_answer_key(q_id)
        widget_key = f"rating_{q_id}"

        max_rating = question.get("max", 5)
        icon = question.get("icon", "star")  # star, heart, thumb

        # Map icon names to emojis
        icon_map = {
            "star": ("⭐", "☆"),
            "heart": ("❤️", "🤍"),
            "thumb": ("👍", "👎"),
            "fire": ("🔥", "💨"),
            "smile": ("😊", "😐"),
        }
        filled, empty = icon_map.get(icon, ("⭐", "☆"))

        # Get current value
        current_value = st.session_state.answers.get(answer_key, 0)
        if isinstance(current_value, str):
            try:
                current_value = int(current_value) if current_value else 0
            except ValueError:
                current_value = 0

        # Create clickable rating using columns
        cols = st.columns(max_rating)
        for i in range(max_rating):
            with cols[i]:
                rating_val = i + 1
                is_selected = rating_val <= current_value
                btn_label = filled if is_selected else empty
                if st.button(btn_label, key=f"{widget_key}_{i}", use_container_width=True):
                    st.session_state.answers[answer_key] = rating_val
                    trigger_auto_advance()
                    st.rerun()

        if current_value > 0:
            st.caption(f"Your rating: {current_value}/{max_rating}")

        return current_value

    elif q_type == "nps":
        # Net Promoter Score (0-10 scale with specific styling)
        answer_key = get_answer_key(q_id)
        widget_key = f"nps_{q_id}"

        # NPS is always 0-10
        options = list(range(0, 11))

        # Get current value
        current_value = st.session_state.answers.get(answer_key)
        if current_value is not None and current_value != "":
            try:
                current_index = options.index(int(current_value))
            except (ValueError, IndexError):
                current_index = None
        else:
            current_index = None

        # Show NPS labels
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            st.caption("← Not likely at all")
        with col3:
            st.caption("Extremely likely →")

        selected = st.radio(
            label="NPS Score",
            options=options,
            index=current_index,
            horizontal=True,
            label_visibility="collapsed",
            key=widget_key
        )

        # Show category based on score
        if selected is not None:
            if selected <= 6:
                st.caption("🔴 Detractor")
            elif selected <= 8:
                st.caption("🟡 Passive")
            else:
                st.caption("🟢 Promoter")

        st.session_state.answers[answer_key] = selected
        return selected

    elif q_type == "date":
        # Date picker
        answer_key = get_answer_key(q_id)
        widget_key = f"date_{q_id}"

        from datetime import date

        # Get current value and parse if string
        current_value = st.session_state.answers.get(answer_key)
        parsed_date = None
        if current_value and current_value != "":
            try:
                if isinstance(current_value, str):
                    parsed_date = date.fromisoformat(current_value)
                elif isinstance(current_value, date):
                    parsed_date = current_value
            except (ValueError, TypeError):
                parsed_date = None

        selected = st.date_input(
            label="Select a date",
            value=parsed_date,
            min_value=date(1900, 1, 1),
            max_value=date(2100, 12, 31),
            label_visibility="collapsed",
            key=widget_key
        )
        # Store as ISO string for JSON serialization
        st.session_state.answers[answer_key] = selected.isoformat() if selected else ""
        return selected

    elif q_type == "time":
        # Time picker
        answer_key = get_answer_key(q_id)
        widget_key = f"time_{q_id}"

        from datetime import time as dt_time

        # Get current value and parse if string
        current_value = st.session_state.answers.get(answer_key)
        parsed_time = None
        if current_value and current_value != "":
            try:
                if isinstance(current_value, str):
                    parts = current_value.split(":")
                    parsed_time = dt_time(int(parts[0]), int(parts[1]))
                elif isinstance(current_value, dt_time):
                    parsed_time = current_value
            except (ValueError, IndexError, TypeError):
                parsed_time = None

        selected = st.time_input(
            label="Select a time",
            value=parsed_time,
            label_visibility="collapsed",
            key=widget_key
        )
        # Store as string for JSON serialization
        st.session_state.answers[answer_key] = selected.strftime("%H:%M") if selected else ""
        return selected

    elif q_type == "number":
        # Number input with optional min/max/step
        answer_key = get_answer_key(q_id)
        widget_key = f"number_{q_id}"

        min_val = question.get("min", None)
        max_val = question.get("max", None)
        step = question.get("step", 1)

        # Get current value
        current_value = st.session_state.answers.get(answer_key)
        if current_value is not None and current_value != "":
            try:
                current_value = float(current_value) if "." in str(current_value) else int(current_value)
            except (ValueError, TypeError):
                current_value = min_val if min_val is not None else 0
        else:
            current_value = min_val if min_val is not None else 0

        value = st.number_input(
            label="Enter a number",
            min_value=min_val,
            max_value=max_val,
            value=current_value,
            step=step,
            label_visibility="collapsed",
            key=widget_key
        )
        st.session_state.answers[answer_key] = value
        return value

    elif q_type == "matrix":
        # Matrix/grid question with rows and columns
        answer_key = get_answer_key(q_id)

        rows = question.get("rows", [])
        columns = question.get("columns", [])
        multiple = question.get("multiple", False)  # Allow multiple selections per row

        responses = {}

        # Create header row
        header_cols = st.columns([2] + [1] * len(columns))
        with header_cols[0]:
            st.write("")  # Empty corner
        for i, col_label in enumerate(columns):
            with header_cols[i + 1]:
                st.markdown(f"**{col_label}**")

        # Create rows
        for row in rows:
            row_key = row.get("key", row.get("label", "").lower().replace(" ", "_"))
            row_label = row.get("label", row_key)
            row_answer_key = f"{answer_key}_{row_key}"

            row_cols = st.columns([2] + [1] * len(columns))
            with row_cols[0]:
                st.write(row_label)

            if multiple:
                # Checkbox mode - multiple selections per row
                current_value = st.session_state.answers.get(row_answer_key, "")
                if isinstance(current_value, str):
                    selected_cols = [x.strip() for x in current_value.split(",") if x.strip()]
                else:
                    selected_cols = current_value if current_value else []

                new_selections = []
                for i, col_label in enumerate(columns):
                    with row_cols[i + 1]:
                        widget_key = f"matrix_{q_id}_{row_key}_{i}"
                        checked = st.checkbox(
                            label=col_label,
                            value=col_label in selected_cols,
                            key=widget_key,
                            label_visibility="collapsed"
                        )
                        if checked:
                            new_selections.append(col_label)

                st.session_state.answers[row_answer_key] = ", ".join(new_selections)
                responses[row_key] = new_selections
            else:
                # Radio mode - single selection per row
                current_value = st.session_state.answers.get(row_answer_key, None)
                widget_key = f"matrix_{q_id}_{row_key}"

                for i, col_label in enumerate(columns):
                    with row_cols[i + 1]:
                        is_selected = current_value == col_label
                        if st.button(
                            "●" if is_selected else "○",
                            key=f"{widget_key}_{i}",
                            use_container_width=True
                        ):
                            st.session_state.answers[row_answer_key] = col_label
                            st.rerun()

                responses[row_key] = current_value

        return responses

    elif q_type == "ranking":
        # Ranking question - drag & drop reorder using streamlit-sortables
        answer_key = get_answer_key(q_id)
        widget_key = f"ranking_{q_id}"

        options = question.get("options", [])
        options = get_randomized_options(q_id, options)

        # Get current order from answers (stored as JSON list)
        current_order = st.session_state.answers.get(answer_key)
        if current_order:
            if isinstance(current_order, str):
                try:
                    current_order = json.loads(current_order)
                except json.JSONDecodeError:
                    current_order = options
            # Validate that all options are present
            if set(current_order) != set(options):
                current_order = options
        else:
            current_order = options

        st.caption("☰ Drag items up/down to reorder (top = most important)")

        # Use streamlit-sortables for drag & drop (vertical layout)
        sorted_items = sort_items(current_order, key=widget_key, direction="vertical")

        # Store as JSON list (ordered from most to least important)
        st.session_state.answers[answer_key] = json.dumps(sorted_items)

        return sorted_items

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
    editing_from_review = st.session_state.get("editing_from_review", False)

    with col1:
        if editing_from_review:
            # Show "Back to Review" when editing from review page
            if st.button("← Back to Review", use_container_width=True):
                st.session_state.show_review = True
                st.session_state.editing_from_review = False
                st.rerun()
        elif current > 0:
            if st.button("← Previous", use_container_width=True):
                st.session_state.current_step -= 1
                st.rerun()

    with col3:
        if editing_from_review:
            # When editing from review, primary action is to go back to review
            if st.button("Save & Back to Review →", use_container_width=True, type="primary"):
                st.session_state.show_review = True
                st.session_state.editing_from_review = False
                st.rerun()
        elif current < TOTAL_QUESTIONS - 1:
            if st.button("Next →", use_container_width=True, type="primary"):
                st.session_state.current_step += 1
                st.rerun()
        else:
            # Last question - go to review page
            if st.button("Review Answers →", use_container_width=True, type="primary"):
                st.session_state.show_review = True
                st.rerun()


def render_review_page(authenticated_user):
    """Render review page with all answers before final submit."""
    st.markdown("## Review Your Answers")
    st.markdown("Please review your answers before submitting. Click on any question to edit.")
    st.markdown("---")

    # Show all answers
    for i, question in enumerate(QUESTIONS):
        q_id = question["id"]
        q_type = question["type"]

        with st.expander(f"**Q{q_id}:** {question['title']}", expanded=True):
            if q_type == "compound":
                for sub in question["subquestions"]:
                    sub_key = sub["key"]
                    answer_key = get_answer_key(q_id, sub_key)
                    answer = st.session_state.answers.get(answer_key, "")
                    st.markdown(f"**{sub_key})** {sub['label']}")
                    if answer:
                        st.markdown(f"> {answer}")
                    else:
                        st.markdown("_No answer provided_")
            else:
                answer_key = get_answer_key(q_id)
                answer = st.session_state.answers.get(answer_key, "")
                if answer:
                    st.markdown(f"> {answer}")
                else:
                    st.markdown("_No answer provided_")

            # Edit button for this question
            if st.button(f"Edit Question {q_id}", key=f"edit_{q_id}"):
                st.session_state.current_step = i
                st.session_state.show_review = False
                st.session_state.editing_from_review = True
                st.rerun()

    st.markdown("---")
    st.markdown("<br>", unsafe_allow_html=True)

    # Navigation buttons
    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        if st.button("← Back to Questions", use_container_width=True):
            st.session_state.show_review = False
            st.rerun()

    with col3:
        if st.button("Submit ✓", use_container_width=True, type="primary"):
            submit_assessment(authenticated_user)


def submit_assessment(authenticated_user):
    """Submit the assessment."""
    oidc_identity = SETTINGS.get("oidc_identity", False)

    # Only save email tag if OIDC identity is enabled AND user is authenticated
    # Otherwise, save anonymously (no email tag = untrusted source)
    if oidc_identity and authenticated_user:
        save_answers_to_keboola(authenticated_user, st.session_state.answers, save_email_tag=True)
    else:
        save_answers_to_keboola("anonymous", st.session_state.answers, save_email_tag=False)

    st.session_state.submitted = True
    st.rerun()


def render_identity_box(authenticated_user: str | None) -> bool:
    """
    Render identity box showing user's email from OIDC.
    Returns True if OIDC identity is active and user is authenticated.
    """
    oidc_identity = SETTINGS.get("oidc_identity", False)

    if not oidc_identity:
        return False

    if authenticated_user:
        st.markdown(f"""
        <div style='background-color: #e3f2fd; padding: 1rem; border-radius: 10px; margin-bottom: 1.5rem; border-left: 4px solid #1976d2;'>
            <strong>Responding as:</strong> {authenticated_user}<br>
            <span style='color: #666; font-size: 0.9rem;'>Your answers will be saved under this email.</span>
        </div>
        """, unsafe_allow_html=True)
        return True
    else:
        st.markdown("""
        <div style='background-color: #fff3e0; padding: 1rem; border-radius: 10px; margin-bottom: 1.5rem; border-left: 4px solid #ff9800;'>
            <strong>Anonymous mode</strong><br>
            <span style='color: #666; font-size: 0.9rem;'>OIDC authentication not detected. Your answers will be saved anonymously.</span>
        </div>
        """, unsafe_allow_html=True)
        return False


def render_thank_you():
    """Render thank you page after submission."""
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("# 🎉 Thank You!")
    st.markdown("<br>", unsafe_allow_html=True)

    thank_you_msg = SETTINGS.get("thank_you_message", "Thank you for completing the assessment!")
    st.markdown(f"""
    <div style='text-align: center; font-size: 1.2rem;'>
        {thank_you_msg}
    </div>
    """, unsafe_allow_html=True)

    if SETTINGS.get("show_balloons", True):
        st.balloons()


def render_all_questions(authenticated_user):
    """Render all questions on a single page (all_at_once mode)."""
    user_display = authenticated_user or "there"

    # Identity box (if oidc_identity is enabled)
    render_identity_box(authenticated_user)

    # Welcome message
    welcome_msg = SETTINGS.get("welcome_message", "")
    if welcome_msg:
        st.markdown(f"""
        <div style='background-color: #e8f5e9; padding: 1rem; border-radius: 10px; margin-bottom: 2rem;'>
            {welcome_msg}
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style='background-color: #e8f5e9; padding: 1rem; border-radius: 10px; margin-bottom: 2rem;'>
            <strong>Hi {user_display}!</strong><br><br>
            Thank you for taking the time to share your thoughts.
        </div>
        """, unsafe_allow_html=True)

    # Render all questions
    for i, question in enumerate(QUESTIONS):
        q_id = question["id"]

        st.markdown("---")

        # Question header
        if SETTINGS.get("show_question_numbers", True):
            st.markdown(f"<span class='question-number'>Question {q_id} of {TOTAL_QUESTIONS}</span>", unsafe_allow_html=True)

        st.markdown(f"## {question['title']}")

        if "subtitle" in question:
            st.markdown(f"<p class='subtitle'>{question['subtitle']}</p>", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Render the question input
        render_question_input(question)

        st.markdown("<br>", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("<br>", unsafe_allow_html=True)

    # Submit button
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("Submit ✓", use_container_width=True, type="primary"):
            submit_assessment(authenticated_user)


def render_question_input(question):
    """Render just the input part of a question (without header)."""
    q_id = question["id"]
    q_type = question["type"]
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
        sync_answer(widget_key, answer_key)

    elif q_type == "text_area":
        answer_key = get_answer_key(q_id)
        widget_key = f"input_{q_id}"
        init_widget_state(widget_key, answer_key)

        st.text_area(
            label="Your answer",
            placeholder=placeholder,
            label_visibility="collapsed",
            height=150,
            key=widget_key,
            on_change=sync_answer,
            args=(widget_key, answer_key)
        )
        sync_answer(widget_key, answer_key)

    elif q_type == "compound":
        for sub in question["subquestions"]:
            sub_key = sub["key"]
            answer_key = get_answer_key(q_id, sub_key)
            widget_key = f"input_{q_id}_{sub_key}"
            init_widget_state(widget_key, answer_key)

            st.markdown(f"**{sub_key})** {sub['label']}")
            st.text_area(
                label=f"Answer for {sub_key}",
                label_visibility="collapsed",
                height=100,
                key=widget_key,
                on_change=sync_answer,
                args=(widget_key, answer_key)
            )
            sync_answer(widget_key, answer_key)

    else:
        # For other question types, call render_question which handles them
        # Note: In all_at_once mode, the header is rendered separately
        render_question_body(question)


def render_question_body(question):
    """Render just the body/input of a question (used in all_at_once mode)."""
    q_id = question["id"]
    q_type = question["type"]

    # Handle all the other question types (slider, linear_scale, rating, etc.)
    # This is a simplified version that just renders the input controls
    answer_key = get_answer_key(q_id)

    if q_type == "radio":
        widget_key = f"radio_{q_id}"
        options = get_randomized_options(q_id, question.get("options", []))
        current_value = st.session_state.answers.get(answer_key, None)
        current_index = options.index(current_value) if current_value in options else None

        selected = st.radio(
            label="Select one option",
            options=options,
            index=current_index,
            label_visibility="collapsed",
            key=widget_key
        )
        st.session_state.answers[answer_key] = selected

    elif q_type == "checkbox":
        options = get_randomized_options(q_id, question.get("options", []))
        current_value = st.session_state.answers.get(answer_key, "")
        if isinstance(current_value, str):
            selected_items = [x.strip() for x in current_value.split(",") if x.strip()]
        else:
            selected_items = current_value if current_value else []

        selections = []
        for option in options:
            widget_key = f"checkbox_{q_id}_{option}"
            checked = st.checkbox(label=option, value=option in selected_items, key=widget_key)
            if checked:
                selections.append(option)
        st.session_state.answers[answer_key] = ", ".join(selections)

    elif q_type == "select":
        widget_key = f"select_{q_id}"
        options = get_randomized_options(q_id, question.get("options", []))
        current_value = st.session_state.answers.get(answer_key, "")
        options_with_placeholder = ["-- Select an option --"] + options
        current_index = options.index(current_value) + 1 if current_value in options else 0

        selected = st.selectbox(
            label="Select an option",
            options=options_with_placeholder,
            index=current_index,
            label_visibility="collapsed",
            key=widget_key
        )
        if selected != "-- Select an option --":
            st.session_state.answers[answer_key] = selected
        else:
            st.session_state.answers[answer_key] = ""

    elif q_type == "yes_no":
        # Simple Yes/No choice (Typeform style)
        widget_key = f"yesno_{q_id}"
        yes_label = question.get("yes_label", "Yes")
        no_label = question.get("no_label", "No")
        current_value = st.session_state.answers.get(answer_key, None)

        col1, col2 = st.columns(2)
        with col1:
            yes_selected = current_value == "yes"
            if st.button(f"👍 {yes_label}", key=f"{widget_key}_yes", use_container_width=True,
                        type="primary" if yes_selected else "secondary"):
                st.session_state.answers[answer_key] = "yes"
                trigger_auto_advance()
                st.rerun()
        with col2:
            no_selected = current_value == "no"
            if st.button(f"👎 {no_label}", key=f"{widget_key}_no", use_container_width=True,
                        type="primary" if no_selected else "secondary"):
                st.session_state.answers[answer_key] = "no"
                trigger_auto_advance()
                st.rerun()

    elif q_type == "slider":
        widget_key = f"slider_{q_id}"
        min_val = question.get("min", 0)
        max_val = question.get("max", 100)
        step = question.get("step", 1)
        default = question.get("default", min_val)

        current_value = st.session_state.answers.get(answer_key)
        if current_value is not None and current_value != "":
            try:
                current_value = type(min_val)(current_value)
            except (ValueError, TypeError):
                current_value = default
        else:
            current_value = default

        value = st.slider(
            label="Select a value",
            min_value=min_val, max_value=max_val, value=current_value, step=step,
            label_visibility="collapsed", key=widget_key
        )
        st.session_state.answers[answer_key] = value

    elif q_type == "linear_scale":
        widget_key = f"scale_{q_id}"
        min_val = question.get("min", 1)
        max_val = question.get("max", 10)
        min_label = question.get("min_label", "")
        max_label = question.get("max_label", "")
        options = list(range(min_val, max_val + 1))

        current_value = st.session_state.answers.get(answer_key)
        if current_value is not None and current_value != "":
            try:
                current_index = options.index(int(current_value))
            except (ValueError, IndexError):
                current_index = None
        else:
            current_index = None

        if min_label or max_label:
            col1, col2 = st.columns([1, 1])
            with col1:
                st.caption(f"← {min_label}" if min_label else "")
            with col2:
                if max_label:
                    st.markdown(f"<p style='text-align: right; color: #666; font-size: 0.85rem; margin: 0;'>{max_label} →</p>", unsafe_allow_html=True)

        selected = st.radio(
            label="Select a value", options=options, index=current_index,
            horizontal=True, label_visibility="collapsed", key=widget_key
        )
        st.session_state.answers[answer_key] = selected

    elif q_type == "rating":
        widget_key = f"rating_{q_id}"
        max_rating = question.get("max", 5)
        icon = question.get("icon", "star")
        icon_map = {"star": ("⭐", "☆"), "heart": ("❤️", "🤍"), "thumb": ("👍", "👎"), "fire": ("🔥", "💨"), "smile": ("😊", "😐")}
        filled, empty = icon_map.get(icon, ("⭐", "☆"))

        current_value = st.session_state.answers.get(answer_key, 0)
        if isinstance(current_value, str):
            try:
                current_value = int(current_value) if current_value else 0
            except ValueError:
                current_value = 0

        cols = st.columns(max_rating)
        for i in range(max_rating):
            with cols[i]:
                rating_val = i + 1
                is_selected = rating_val <= current_value
                btn_label = filled if is_selected else empty
                if st.button(btn_label, key=f"{widget_key}_{i}", use_container_width=True):
                    st.session_state.answers[answer_key] = rating_val
                    trigger_auto_advance()
                    st.rerun()

        if current_value > 0:
            st.caption(f"Your rating: {current_value}/{max_rating}")

    elif q_type == "nps":
        widget_key = f"nps_{q_id}"
        options = list(range(0, 11))

        current_value = st.session_state.answers.get(answer_key)
        if current_value is not None and current_value != "":
            try:
                current_index = options.index(int(current_value))
            except (ValueError, IndexError):
                current_index = None
        else:
            current_index = None

        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            st.caption("← Not likely at all")
        with col3:
            st.caption("Extremely likely →")

        selected = st.radio(
            label="NPS Score", options=options, index=current_index,
            horizontal=True, label_visibility="collapsed", key=widget_key
        )

        if selected is not None:
            if selected <= 6:
                st.caption("🔴 Detractor")
            elif selected <= 8:
                st.caption("🟡 Passive")
            else:
                st.caption("🟢 Promoter")
        st.session_state.answers[answer_key] = selected

    elif q_type == "date":
        from datetime import date
        widget_key = f"date_{q_id}"
        current_value = st.session_state.answers.get(answer_key)
        parsed_date = None
        if current_value and current_value != "":
            try:
                if isinstance(current_value, str):
                    parsed_date = date.fromisoformat(current_value)
                elif isinstance(current_value, date):
                    parsed_date = current_value
            except (ValueError, TypeError):
                parsed_date = None

        selected = st.date_input(
            label="Select a date", value=parsed_date,
            min_value=date(1900, 1, 1), max_value=date(2100, 12, 31),
            label_visibility="collapsed", key=widget_key
        )
        st.session_state.answers[answer_key] = selected.isoformat() if selected else ""

    elif q_type == "time":
        from datetime import time as dt_time
        widget_key = f"time_{q_id}"
        current_value = st.session_state.answers.get(answer_key)
        parsed_time = None
        if current_value and current_value != "":
            try:
                if isinstance(current_value, str):
                    parts = current_value.split(":")
                    parsed_time = dt_time(int(parts[0]), int(parts[1]))
                elif isinstance(current_value, dt_time):
                    parsed_time = current_value
            except (ValueError, IndexError, TypeError):
                parsed_time = None

        selected = st.time_input(label="Select a time", value=parsed_time, label_visibility="collapsed", key=widget_key)
        st.session_state.answers[answer_key] = selected.strftime("%H:%M") if selected else ""

    elif q_type == "number":
        widget_key = f"number_{q_id}"
        min_val = question.get("min", None)
        max_val = question.get("max", None)
        step = question.get("step", 1)

        current_value = st.session_state.answers.get(answer_key)
        if current_value is not None and current_value != "":
            try:
                current_value = float(current_value) if "." in str(current_value) else int(current_value)
            except (ValueError, TypeError):
                current_value = min_val if min_val is not None else 0
        else:
            current_value = min_val if min_val is not None else 0

        value = st.number_input(
            label="Enter a number", min_value=min_val, max_value=max_val,
            value=current_value, step=step, label_visibility="collapsed", key=widget_key
        )
        st.session_state.answers[answer_key] = value

    elif q_type == "matrix":
        rows = question.get("rows", [])
        columns = question.get("columns", [])
        multiple = question.get("multiple", False)

        header_cols = st.columns([2] + [1] * len(columns))
        with header_cols[0]:
            st.write("")
        for i, col_label in enumerate(columns):
            with header_cols[i + 1]:
                st.markdown(f"**{col_label}**")

        for row in rows:
            row_key = row.get("key", row.get("label", "").lower().replace(" ", "_"))
            row_label = row.get("label", row_key)
            row_answer_key = f"{answer_key}_{row_key}"

            row_cols = st.columns([2] + [1] * len(columns))
            with row_cols[0]:
                st.write(row_label)

            if multiple:
                current_value = st.session_state.answers.get(row_answer_key, "")
                if isinstance(current_value, str):
                    selected_cols = [x.strip() for x in current_value.split(",") if x.strip()]
                else:
                    selected_cols = current_value if current_value else []

                new_selections = []
                for i, col_label in enumerate(columns):
                    with row_cols[i + 1]:
                        widget_key = f"matrix_{q_id}_{row_key}_{i}"
                        checked = st.checkbox(label=col_label, value=col_label in selected_cols, key=widget_key, label_visibility="collapsed")
                        if checked:
                            new_selections.append(col_label)
                st.session_state.answers[row_answer_key] = ", ".join(new_selections)
            else:
                current_value = st.session_state.answers.get(row_answer_key, None)
                widget_key = f"matrix_{q_id}_{row_key}"
                for i, col_label in enumerate(columns):
                    with row_cols[i + 1]:
                        is_selected = current_value == col_label
                        if st.button("●" if is_selected else "○", key=f"{widget_key}_{i}", use_container_width=True):
                            st.session_state.answers[row_answer_key] = col_label
                            st.rerun()

    elif q_type == "ranking":
        # Drag & drop ranking using streamlit-sortables
        widget_key = f"ranking_{q_id}"
        options = question.get("options", [])
        options = get_randomized_options(q_id, options)

        # Get current order from answers (stored as JSON list)
        current_order = st.session_state.answers.get(answer_key)
        if current_order:
            if isinstance(current_order, str):
                try:
                    current_order = json.loads(current_order)
                except json.JSONDecodeError:
                    current_order = options
            if set(current_order) != set(options):
                current_order = options
        else:
            current_order = options

        st.caption("☰ Drag items up/down to reorder (top = most important)")
        sorted_items = sort_items(current_order, key=widget_key, direction="vertical")
        st.session_state.answers[answer_key] = json.dumps(sorted_items)


def is_ceo(email: str) -> bool:
    """Check if the user is the CEO."""
    if not email or not CEO_EMAIL:
        return False
    return email.lower() == CEO_EMAIL.lower()


def render_ceo_dashboard():
    """Render CEO dashboard showing all employee answers."""
    st.markdown("## All Responses Dashboard")
    st.markdown("Compare answers from all team members for each question.")

    # Load all answers
    if "all_answers" not in st.session_state:
        with st.spinner("Loading all responses..."):
            st.session_state.all_answers = load_all_answers_from_keboola()

    all_answers = st.session_state.all_answers

    if not all_answers:
        st.warning("No responses found yet.")
        return

    # Export section
    st.markdown("---")

    col1, col2 = st.columns([1, 1])

    with col1:
        # CSV download
        csv_data = generate_csv_export(all_answers)
        st.download_button(
            label="Download CSV",
            data=csv_data,
            file_name=f"ceo_assessment_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True,
            type="primary"
        )

    with col2:
        # Refresh button
        if st.button("Refresh Data", use_container_width=True):
            if "all_answers" in st.session_state:
                del st.session_state.all_answers
            st.rerun()

    # Show respondents with timestamps
    st.markdown("---")
    st.markdown(f"### {len(all_answers)} Responses")
    for answer_data in all_answers:
        user = answer_data.get("_user_email", answer_data.get("email", "Unknown"))
        timestamp = answer_data.get("last_updated") or answer_data.get("submitted_at", "")
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp)
                formatted_date = dt.strftime("%b %d, %Y %H:%M")
            except:
                formatted_date = timestamp
        else:
            formatted_date = "unknown"
        st.markdown(f"- **{user}** — submitted {formatted_date}")
    st.markdown("---")

    # Show each question with all answers
    for question in QUESTIONS:
        q_id = question["id"]
        q_type = question["type"]

        # Question header with colored background
        st.markdown(f"""<div class="question-header"><strong>Q{q_id}:</strong> {question['title']}</div>""", unsafe_allow_html=True)

        if "subtitle" in question:
            st.markdown(f"*{question['subtitle']}*")

        if q_type == "compound":
            # For compound questions, show sub-questions
            for sub in question["subquestions"]:
                sub_key = sub["key"]
                answer_key = f"q{q_id}_{sub_key}"
                st.markdown(f"**{sub_key})** {sub['label']}")

                # Create columns for each respondent
                cols = st.columns(len(all_answers))
                for idx, answer_data in enumerate(all_answers):
                    user = answer_data.get("_user_email", "Unknown")
                    user_short = user.split("@")[0]
                    answer = answer_data.get("answers", {}).get(answer_key, "")
                    with cols[idx]:
                        st.markdown(f"**{user_short}**")
                        if answer:
                            st.markdown(f"> {answer}")
                        else:
                            st.markdown("_No answer_")
                st.markdown("")
        else:
            answer_key = f"q{q_id}"

            # Create columns for each respondent
            cols = st.columns(len(all_answers))
            for idx, answer_data in enumerate(all_answers):
                user = answer_data.get("_user_email", "Unknown")
                user_short = user.split("@")[0]
                answer = answer_data.get("answers", {}).get(answer_key, "")
                with cols[idx]:
                    st.markdown(f"**{user_short}**")
                    if answer:
                        st.markdown(f"> {answer}")
                    else:
                        st.markdown("_No answer_")



def render_existing_answers_choice(authenticated_user):
    """Render dialog to choose whether to load existing answers or start fresh."""
    existing_data = st.session_state.existing_data

    # Parse timestamp
    timestamp_str = existing_data.get("last_updated") or existing_data.get("submitted_at", "")
    if timestamp_str:
        try:
            dt = datetime.fromisoformat(timestamp_str)
            formatted_date = dt.strftime("%B %d, %Y at %H:%M")
        except:
            formatted_date = timestamp_str
    else:
        formatted_date = "unknown date"

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown(f"""
    <div style='background-color: #fff3cd; padding: 1.5rem; border-radius: 10px; margin-bottom: 2rem; border: 1px solid #ffc107;'>
        <h3 style='margin-top: 0;'>📋 Previous Answers Found</h3>
        <p>Hi <strong>{authenticated_user}</strong>!</p>
        <p>We found your previous assessment from <strong>{formatted_date}</strong>.</p>
        <p>Would you like to continue editing your previous answers or start fresh?</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        if st.button("📝 Load & Edit Previous Answers", use_container_width=True, type="primary"):
            # Load the existing answers
            st.session_state.answers = existing_data.get("answers", {})
            st.session_state.user_chose_action = True
            st.rerun()

    with col2:
        if st.button("🆕 Start Fresh", use_container_width=True):
            # Start with empty answers
            st.session_state.answers = {}
            st.session_state.user_chose_action = True
            st.rerun()


def main():
    global QUESTIONS, TOTAL_QUESTIONS

    # Check if questionnaire is configured
    if QUESTIONNAIRE_NOT_CONFIGURED:
        render_configuration_error()
        return

    # Get authenticated user from Keboola OIDC
    authenticated_user = get_authenticated_user()

    # Initialize session state (and load existing answers)
    init_session_state(authenticated_user)

    # Get questions (potentially randomized per session)
    QUESTIONS = get_questions()
    TOTAL_QUESTIONS = len(QUESTIONS)

    # Header with Material Icon - use title from settings
    questionnaire_title = SETTINGS.get("title", "Questionnaire")
    st.markdown(f"""
    <h1 style="text-align: center; display: flex; align-items: center; justify-content: center; gap: 12px;">
        <span class="material-icons-outlined" style="font-size: 42px; color: #4CAF50;">assignment</span>
        {questionnaire_title}
    </h1>
    """, unsafe_allow_html=True)

    # Debug mode - show headers and Keboola config (use query param ?debug=1)
    if st.query_params.get("debug"):
        with st.expander("🔧 Debug Info", expanded=True):
            st.write(f"**Authenticated user:** {authenticated_user}")
            st.write(f"**Is CEO:** {is_ceo(authenticated_user)}")
            st.write(f"**CEO_EMAIL:** {CEO_EMAIL or 'Not set'}")
            st.write(f"**KBC_URL:** {KBC_URL}")
            st.write(f"**KBC_TOKEN:** {'***' + KBC_TOKEN[-4:] if KBC_TOKEN else 'Not set'}")
            st.write(f"**Has existing answers:** {st.session_state.get('has_existing_answers', False)}")
            st.json(get_debug_headers())

    # CEO gets the dashboard view instead of the questionnaire
    if is_ceo(authenticated_user):
        render_ceo_dashboard()
        return

    # Check if already submitted
    if st.session_state.submitted:
        render_thank_you()
        return

    # Check if user needs to choose what to do with existing answers
    if st.session_state.has_existing_answers and not st.session_state.user_chose_action:
        render_existing_answers_choice(authenticated_user)
        return

    # Check if showing review page
    if st.session_state.show_review:
        render_review_page(authenticated_user)
        return

    # Check display mode from settings
    display_mode = SETTINGS.get("display_mode", "one_by_one")

    if display_mode == "all_at_once":
        # Render all questions on single page
        render_all_questions(authenticated_user)
        return

    # === ONE BY ONE MODE ===
    # Identity box and welcome message on first question
    if st.session_state.current_step == 0:
        # Identity box (if oidc_identity is enabled)
        render_identity_box(authenticated_user)

        user_display = authenticated_user or "there"

        st.markdown(f"""
        <div style='background-color: #e8f5e9; padding: 1rem; border-radius: 10px; margin-bottom: 2rem;'>
            <strong>Hi {user_display}!</strong><br><br>
            Thank you for taking the time to share your thoughts.
            Your honest feedback helps me understand how we can work better together.
        </div>
        """, unsafe_allow_html=True)

    # Progress bar
    render_progress_bar()

    st.markdown("---")

    # Current question
    current_question = QUESTIONS[st.session_state.current_step]
    render_question(current_question)

    # Auto-focus on textarea after navigation using iframe component
    focus_js = f"""
    <script>
        (function() {{
            var step = {st.session_state.current_step};
            function focusTextarea() {{
                try {{
                    var doc = window.parent.document;
                    var textarea = doc.querySelector('textarea[aria-label="Your answer"]');
                    if (textarea) {{
                        textarea.focus();
                        return true;
                    }}
                }} catch(e) {{}}
                return false;
            }}
            // Retry with delays to ensure DOM is ready
            [50, 100, 200, 400, 600].forEach(function(delay) {{
                setTimeout(focusTextarea, delay);
            }});
        }})();
    </script>
    """
    components.html(focus_js, height=0)

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
