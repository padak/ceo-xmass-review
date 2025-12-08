# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CEO Assessment is a Streamlit-based questionnaire application designed to run as a Keboola Data App. It collects employee feedback through configurable questionnaires and stores responses in Keboola Storage.

## Development Commands

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run locally
streamlit run app.py

# Run with specific port
streamlit run app.py --server.port 8501
```

## Architecture

### Core Files

- **app.py** - Main Streamlit application (~2000 lines)
  - Question rendering for 16+ question types
  - Keboola Storage integration for saving/loading answers
  - CEO dashboard for viewing all responses
  - Session state management for wizard-style navigation

- **questions.yaml** - Questionnaire configuration
  - `settings:` - Display mode, randomization, versioning
  - `intro_questions:` - Never shuffled (demographics)
  - `questions:` - Main questions (can be shuffled)

- **questions.instructions.md** - LLM guide for generating questionnaires

### Key Patterns

**Question Types**: text_input, text_area, compound, radio, checkbox, select, yes_no, linear_scale, rating, nps, slider, matrix, ranking, date, time, number

**Answer Storage**: Answers stored in Keboola Storage Files with tags:
- Tag format: `{questionnaire_id}_v{version}` (e.g., `CEO_Assessment_v1`)
- Additional tag: user's email for lookup

**Two Rendering Modes**:
1. `one_by_one` - Wizard style, one question per screen
2. `all_at_once` - All questions on single page

**Randomization**:
- `intro_questions` are NEVER shuffled
- `questions` can be shuffled via `randomize_questions: true`
- Options within questions via `randomize_options: true`

### Environment Variables

```bash
KBC_URL=https://connection.keboola.com  # Keboola API URL
KBC_TOKEN=xxx                            # Keboola Storage API token
SURVEY_EVALUATORS=jan@company.com,petra@company.com  # Comma-separated emails for dashboard access
QUESTIONS_CONFIG_FILE=questions.yaml     # Config file path (optional)
AGGRID_LICENSE_KEY=xxx                   # AG Grid Enterprise license (enables charts, pivoting, Excel export)
```

### Keboola Integration

When running as a Keboola Data App:
- User email comes from `X-Kbc-User-Email` header (OIDC)
- Answers saved to Keboola Storage Files (not tables)
- CEO sees dashboard with all responses instead of questionnaire

### Dashboard & Visualizations

The evaluator dashboard has three tabs:
- **Summary** - Smart visualizations per question type (Altair charts)
- **All Data** - Interactive AgGrid table with filtering, grouping, export
- **Respondents** - List of all respondents with timestamps

**Visualization Config** (`config/visualizations.yaml`):
- Maps each of 16 question types to optimal chart type
- Configures colors, thresholds, aggregation methods
- Special handling for NPS (promoters/passives/detractors calculation)

**AgGrid Enterprise** (requires `AGGRID_LICENSE_KEY`):
- Use `enable_enterprise_modules="enterprise+AgCharts"` to enable integrated charts
- Right-click on selected cells → "Chart Range..." for ad-hoc charting
- Row grouping, pivoting, Excel export

## Configuration Schema

See `questions.instructions.md` for complete documentation of all question types and settings. Key settings:

```yaml
settings:
  questionnaire_id: CEO_Assessment  # Used in Keboola tags
  version: "1"                       # Increment for new versions
  display_mode: one_by_one
  randomize_questions: false
  auto_advance: false               # Typeform-style auto-next
```
