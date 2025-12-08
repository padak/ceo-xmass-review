# Questionnaire App

A Streamlit application for collecting feedback through configurable questionnaires. Designed to run as a Keboola Data App with OIDC authentication and stores responses in Keboola Storage for analysis.

## Keboola Environment

This app is built for the Keboola platform which provides:

- **OIDC Proxy** - authenticates company users via SSO (Google, Azure AD, etc.)
- **User identification** - the `X-Kbc-User-Email` header identifies who is responding
- **Trusted identity** - no need to ask users for email, it's provided by the proxy
- **Storage integration** - responses are saved to Keboola Storage Files with tags

When `oidc_identity: true` is set in the questionnaire config, the app shows the authenticated user's email and tags responses with it. Without OIDC, the questionnaire runs in anonymous mode.

## Features

- **16 question types** - from simple text to drag & drop ranking
- **Two display modes** - wizard (one question per screen) or all at once
- **Randomization** - shuffle questions and options for unbiased results
- **Admin dashboard** - overview of all responses for administrators
- **Keboola integration** - responses are saved with tags for easy filtering and analysis

## Question Types

| Type | When to use |
|------|-------------|
| `text_input` | Name, email, short answer |
| `text_area` | Longer feedback, comments |
| `compound` | Multiple related text questions grouped together |
| `radio` | Single choice (2-5 options) |
| `select` | Dropdown for longer lists (6+ options) |
| `checkbox` | Multiple selections ("check all that apply") |
| `yes_no` | Simple binary choice |
| `linear_scale` | 1-10 scale with labels (satisfaction, agreement) |
| `rating` | Stars or other icons (1-5) |
| `nps` | Net Promoter Score (0-10 with automatic labels) |
| `slider` | Draggable slider for percentages or ranges |
| `matrix` | Grid - rate multiple items on the same scale |
| `ranking` | Drag & drop priority ordering |
| `date` | Date picker |
| `time` | Time picker |
| `number` | Numeric input with min/max validation |

## How Responses End Up in Keboola

Responses are saved to Keboola Storage Files with tags:
- `{questionnaire_id}_v{version}` - e.g., `Employee_Survey_v1`
- Respondent's email

This enables you to:
- Filter responses by questionnaire and version
- Export to tables for analysis
- Connect to transformations and dashboards
- Automatically evaluate using AI/ML

## Creating a Custom Questionnaire with AI

### 1. Prepare your requirements

Write down what you want to learn. For example:
```
I need a questionnaire to evaluate new employee onboarding.
I want to know:
- How satisfied they were with their first week
- What was missing
- How they rate their mentor
- Whether they would recommend the company to a friend
```

### 2. Let AI generate the YAML

Open Claude Code in this repository and enter:

```
Create a new questionnaire based on this brief: [your requirements]

Use questionnaires/demo_questionnaire.yaml as a template
and questionnaires/questions.instructions.md as documentation
```

AI will create a file in the `questionnaires/` folder with:
- A unique `questionnaire_id`
- Appropriate question types for your needs
- Comments explaining the structure

### 3. Customize as needed

Review the generated YAML and adjust:
- Question texts
- Answer options
- Question order
- Settings (randomization, required answers, etc.)

### 4. Run and test

```bash
# With a specific questionnaire (required if multiple exist)
QUESTIONNAIRE=my_questionnaire.yaml streamlit run app.py

# Or export first
export QUESTIONNAIRE=my_questionnaire.yaml
streamlit run app.py

# Auto-detection works if only one .yaml file exists in questionnaires/
streamlit run app.py
```

## Project Structure

```
├── app.py                      # Main Streamlit application
├── requirements.txt            # Python dependencies
└── questionnaires/
    ├── demo_questionnaire.yaml  # Demo questionnaire (all 16 types)
    ├── questions.schema.json   # JSON schema for validation
    └── questions.instructions.md  # Documentation for AI
```

## Running the App

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

### Environment Variables

```bash
KBC_URL=https://connection.keboola.com  # Keboola API URL
KBC_TOKEN=xxx                            # Keboola Storage API token
CEO_EMAIL=admin@company.com             # Email for admin dashboard
```
