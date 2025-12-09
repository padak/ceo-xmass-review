# Questions Configuration Guide for LLMs

This document describes how to generate and modify questionnaire YAML files. Use this guide when creating questionnaires - it covers all available question types, configuration options, and best practices.

> **📋 Reference Implementation:** See `demo_questionnaire.yaml` in this folder for a complete demo questionnaire that showcases all 16 question types with detailed comments. Use it as a template!

## 🎯 Quick Reference: Demo Questionnaire

The `demo_questionnaire.yaml` file in this folder is a **live demo** you can run immediately. It demonstrates:

| Section | What it shows |
|---------|---------------|
| **Header comments** | How to document your questionnaire |
| **settings** | All available configuration options with explanations |
| **intro_questions** | 4 examples: text_input, select, number, date |
| **questions** | All 14 remaining types with realistic examples |

**To create your own questionnaire:**
1. Copy `demo_questionnaire.yaml` to a new file (e.g., `my_survey.yaml`)
2. Update `questionnaire_id`, `version`, and `title` in settings
3. Delete question types you don't need
4. Customize the remaining questions
5. Run with `QUESTIONNAIRE=my_survey.yaml streamlit run app.py`

## File Location & Multiple Questionnaires

All questionnaire files are stored in the `questionnaires/` folder. The app selects which questionnaire to load:

1. **ENV variable** `QUESTIONNAIRE=filename.yaml` - required if multiple files exist
2. **Auto-detect** - if only one `.yaml` file exists, it's used automatically
3. **Error page** - if multiple files exist and no ENV var is set, shows configuration help

**File structure:**
```
questionnaires/
├── demo_questionnaire.yaml   # Demo questionnaire (reference implementation)
├── questions.schema.json     # JSON schema for validation
├── questions.instructions.md # This documentation
├── employee_survey.yaml      # Your custom questionnaires...
└── customer_feedback.yaml
```

---

## Quick Start

A questionnaire YAML file has three main sections:

```yaml
settings:
  display_mode: one_by_one
  # ... other settings

intro_questions:  # Optional - never shuffled (demographics, name, etc.)
  - id: 1
    title: "What is your name?"
    type: text_input

questions:  # Main questions - can be shuffled if randomize_questions: true
  - id: 2
    title: "Rate your satisfaction"
    type: linear_scale
```

---

## Settings Configuration

### Required Settings

These three settings **MUST** be provided in every questionnaire:

```yaml
settings:
  # REQUIRED: Technical ID (letters, numbers, underscores only)
  # Must be unique per Keboola project!
  # Naming convention: {Team}_{Purpose}_{Year}
  questionnaire_id: HR_Onboarding_2024

  # REQUIRED: Version string - increment when making breaking changes
  version: "1"

  # REQUIRED: Display title shown to users
  title: "Employee Onboarding Survey"
```

**Naming convention for `questionnaire_id`:**
| Pattern | Example |
|---------|---------|
| `{Team}_{Purpose}_{Year}` | `HR_Onboarding_2024` |
| `{Department}_{Survey}_{Quarter}` | `Sales_Feedback_Q4` |
| `{Project}_{Type}` | `CEO_Assessment` |

**Important:** Answers are stored in Keboola with tag `{questionnaire_id}_v{version}`. If two questionnaires use the same ID, their answers will be mixed! Ensure your `questionnaire_id` is unique within your Keboola project.

### Custom Answer Tag (Backwards Compatibility)

If you need to load answers from an older questionnaire that used a different tag format, you can override the auto-generated tag:

```yaml
settings:
  questionnaire_id: CEO_Assessment
  version: "1"

  # Override the default tag ({questionnaire_id}_v{version})
  # Useful for loading legacy data with different tag format
  answers_tag: CEO_Assessment_Answers  # optional
```

**When to use `answers_tag`:**
- Migrating from an older version of the app that used different tagging
- Loading responses that were saved with a custom tag
- Backwards compatibility with existing Keboola Storage data

**Note:** If `answers_tag` is set, it completely replaces the auto-generated `{questionnaire_id}_v{version}` tag.

### Display Mode

```yaml
settings:
  # "one_by_one" = wizard style, one question per screen (default)
  # "all_at_once" = all questions on single scrollable page
  display_mode: one_by_one
```

### Navigation & Progress

```yaml
settings:
  show_progress_bar: true        # Progress indicator (one_by_one mode only)
  allow_back_navigation: true    # Allow going back to previous questions
  show_question_numbers: true    # Show "Question 1 of 10" etc.
```

### Randomization

```yaml
settings:
  # Shuffle question order (only 'questions', not 'intro_questions')
  randomize_questions: false

  # Shuffle options in choice questions (radio, checkbox, select, ranking)
  randomize_options: false
```

**Important:** When `randomize_questions: true`, only the `questions` section is shuffled. The `intro_questions` section always stays at the beginning in original order - use it for demographics, name, department, etc.

### Auto-advance (Typeform-style)

```yaml
settings:
  # Automatically go to next question after selection
  # Works only for single-choice types: radio, yes_no, linear_scale, rating, nps
  auto_advance: false

  # Delay before advancing (milliseconds)
  auto_advance_delay: 600
```

### Validation

```yaml
settings:
  # Require all questions to be answered before submit
  require_all_answers: false
```

### Custom Messages

```yaml
settings:
  title: "CEO Assessment"

  # Shown at the start (inline HTML allowed)
  welcome_message: "<strong>Welcome!</strong><br><br>Please answer honestly."

  # Shown after submission
  thank_you_message: "Thank you for completing the assessment!"
```

**Important HTML guidelines:**
- Use **inline HTML only**: `<strong>`, `<em>`, `<br>`, `<a href="...">`
- Use `<br><br>` for paragraph breaks
- **Do NOT use block-level HTML**: `<h1>`-`<h6>`, `<p>`, `<div>` - these cause rendering issues
- **Do NOT use YAML multiline strings** (`|` or `>`). Always use single-line quoted strings.

**Good example:**
```yaml
welcome_message: "<strong>Hello!</strong><br><br>This survey is <em>anonymous</em>.<br><br>Be honest!"
```

**Bad example (will break):**
```yaml
# DON'T do this - block HTML and multiline string cause </div> to appear as text
welcome_message: |
  <h2>Hello!</h2>
  <p>This survey is anonymous.</p>
```

### Celebration

```yaml
settings:
  # Show balloons animation after submission
  show_balloons: true  # default: true, set to false for professional surveys
```

### Identity (OIDC)

```yaml
settings:
  # Enable OIDC-based identity
  oidc_identity: true  # default: false
```

**How it works:**
- When `oidc_identity: true` AND running behind Keboola OIDC proxy:
  - Shows identity box at the start: "Responding as: user@company.com"
  - Responses are tagged with user's email (trusted source)
  - No need to ask for name/email in questions

- When `oidc_identity: false` OR no OIDC proxy:
  - Anonymous questionnaire
  - No email tag saved (untrusted source)
  - Use `intro_questions` if you need to collect identity manually

**Important:** If you need verified user identity, you MUST use OIDC. Without it, any email entered by users is untrusted and should not be used for identification.

### All Settings Reference

```yaml
settings:
  # ── REQUIRED (no defaults) ──────────────────
  questionnaire_id: HR_Onboarding_2024  # REQUIRED
  version: "1"                           # REQUIRED
  title: "Employee Survey"               # REQUIRED

  # ── OPTIONAL (with defaults) ────────────────
  # Identity
  oidc_identity: false            # default: false (anonymous mode)

  # Storage (backwards compatibility)
  answers_tag: ""                 # default: "" (uses {questionnaire_id}_v{version})

  # Display
  display_mode: one_by_one        # default: one_by_one
  show_progress_bar: true         # default: true
  allow_back_navigation: true     # default: true
  show_question_numbers: true     # default: true

  # Behavior
  require_all_answers: false      # default: false
  randomize_questions: false      # default: false
  randomize_options: false        # default: false
  auto_advance: false             # default: false
  auto_advance_delay: 600         # default: 600 (ms)
  show_balloons: true             # default: true

  # Messages
  welcome_message: ""             # default: "" (empty)
  thank_you_message: "Thank you!" # default: "Thank you for completing the assessment!"
```

### Environment Variable Overrides

Any setting can be overridden via environment variables. This is useful for:
- Changing behavior per deployment without editing YAML
- A/B testing different configurations
- Quick adjustments in Keboola Data App Secrets

**Environment variable names** (uppercase with underscores):

| Setting | Environment Variable |
|---------|---------------------|
| `display_mode` | `DISPLAY_MODE` |
| `show_progress_bar` | `SHOW_PROGRESS_BAR` |
| `allow_back_navigation` | `ALLOW_BACK_NAVIGATION` |
| `show_question_numbers` | `SHOW_QUESTION_NUMBERS` |
| `require_all_answers` | `REQUIRE_ALL_ANSWERS` |
| `randomize_questions` | `RANDOMIZE_QUESTIONS` |
| `randomize_options` | `RANDOMIZE_OPTIONS` |
| `auto_advance` | `AUTO_ADVANCE` |
| `auto_advance_delay` | `AUTO_ADVANCE_DELAY` |
| `show_balloons` | `SHOW_BALLOONS` |
| `oidc_identity` | `OIDC_IDENTITY` |
| `welcome_message` | `WELCOME_MESSAGE` |
| `thank_you_message` | `THANK_YOU_MESSAGE` |
| `title` | `TITLE` |

**Boolean values:** Use `true`, `1`, `yes` (case-insensitive) for true, anything else for false.

**Example:** Override display mode in Keboola Secrets:
```
DISPLAY_MODE = all_at_once
```

---

## Question Types

### Text Input Types

#### `text_input` - Single Line Text
Short text answers (name, email, short phrase).

```yaml
- id: 1
  title: "What is your name?"
  type: text_input
  placeholder: "Enter your full name"  # optional
  subtitle: "As it appears on your badge"  # optional
```

#### `text_area` - Multi-line Text
Long-form text answers (feedback, descriptions, reflections).

```yaml
- id: 2
  title: "What was your biggest achievement this quarter?"
  type: text_area
  placeholder: "Describe the impact and outcomes..."
  subtitle: "Be specific about what you accomplished"
```

#### `compound` - Multiple Sub-questions
Groups related text questions under one heading. Each sub-question gets its own text area.

```yaml
- id: 3
  title: "Self-evaluation"
  subtitle: "Reflect on your performance"
  type: compound
  subquestions:
    - key: a
      label: "What are your strengths?"
    - key: b
      label: "What areas need improvement?"
    - key: c
      label: "What support do you need?"
```

**Rules:**
- `subquestions` is required
- Each needs `key` (single lowercase letter: a, b, c...) and `label`
- Keys must be unique within the question

---

### Single Choice Types

#### `radio` - Radio Buttons
Select exactly one option. Good for 2-5 options.

```yaml
- id: 4
  title: "How satisfied are you with your role?"
  type: radio
  options:
    - "Very satisfied"
    - "Satisfied"
    - "Neutral"
    - "Dissatisfied"
    - "Very dissatisfied"
```

#### `select` - Dropdown
Single selection from dropdown. Good for longer lists (6+ options).

```yaml
- id: 5
  title: "Which department do you work in?"
  type: select
  options:
    - "Engineering"
    - "Product"
    - "Design"
    - "Sales"
    - "Marketing"
    - "Operations"
    - "Finance"
    - "HR"
```

#### `yes_no` - Binary Choice
Simple yes/no with large buttons. Good for quick binary questions.

```yaml
- id: 6
  title: "Would you recommend working here to a friend?"
  type: yes_no
  yes_label: "Yes"   # optional, default "Yes"
  no_label: "No"     # optional, default "No"
```

---

### Multiple Choice Types

#### `checkbox` - Multiple Selection
Select zero or more options.

```yaml
- id: 7
  title: "Which tools do you use daily?"
  subtitle: "Select all that apply"
  type: checkbox
  options:
    - "Slack"
    - "Jira"
    - "GitHub"
    - "Notion"
    - "Figma"
```

---

### Scale & Rating Types

#### `linear_scale` - Numeric Scale
Rating scale with labeled endpoints. Good for satisfaction, agreement, likelihood.

```yaml
- id: 8
  title: "How would you rate your work-life balance?"
  subtitle: "Select a number on the scale"
  type: linear_scale
  min: 1           # default: 1
  max: 10          # default: 10
  min_label: "Very poor"
  max_label: "Excellent"
```

#### `rating` - Visual Rating
Star/emoji rating. Good for quick quality assessments.

```yaml
- id: 9
  title: "How would you rate your team collaboration?"
  type: rating
  max: 5           # default: 5
  icon: star       # Options: star, heart, thumb, fire, smile
```

#### `nps` - Net Promoter Score
Standard NPS question (0-10 scale with Detractor/Passive/Promoter labels).

```yaml
- id: 10
  title: "How likely are you to recommend our company as a workplace?"
  subtitle: "On a scale of 0-10"
  type: nps
```

**Note:** NPS is always 0-10 with fixed labels. For custom scales, use `linear_scale`.

#### `slider` - Draggable Slider
Continuous value selection within a range.

```yaml
- id: 11
  title: "What percentage of your time do you spend in meetings?"
  type: slider
  min: 0
  max: 100
  step: 5          # increment step
  default: 25      # initial value
```

---

### Matrix & Ranking Types

#### `matrix` - Grid Question
Rate multiple items on the same scale. Like Google Forms multiple choice grid.

```yaml
- id: 12
  title: "Rate these aspects of your work environment"
  subtitle: "Select one rating per row"
  type: matrix
  multiple: false  # false = radio (one per row), true = checkbox (multiple per row)
  rows:
    - key: office
      label: "Office space"
    - key: equipment
      label: "Equipment & tools"
    - key: culture
      label: "Company culture"
    - key: growth
      label: "Growth opportunities"
  columns:
    - "Poor"
    - "Fair"
    - "Good"
    - "Excellent"
```

#### `ranking` - Drag & Drop Ordering
Order items by preference using drag & drop.

```yaml
- id: 13
  title: "Rank these company values by importance to you"
  subtitle: "Drag items to reorder (top = most important)"
  type: ranking
  options:
    - "Innovation"
    - "Customer focus"
    - "Teamwork"
    - "Integrity"
    - "Excellence"
```

---

### Date & Time Types

#### `date` - Date Picker

```yaml
- id: 14
  title: "When did you join the company?"
  type: date
```

#### `time` - Time Picker

```yaml
- id: 15
  title: "What time do you usually start work?"
  type: time
```

#### `number` - Numeric Input

```yaml
- id: 16
  title: "How many years have you been with the company?"
  type: number
  min: 0
  max: 50
  step: 1
```

---

## File Structure

```yaml
# yaml-language-server: $schema=questions.schema.json
# Assessment Configuration

settings:
  display_mode: one_by_one
  randomize_questions: true
  # ... other settings

# Intro questions - NEVER shuffled (demographics, identification)
intro_questions:
  - id: 1
    title: "What is your name?"
    type: text_input

  - id: 2
    title: "Which department do you work in?"
    type: select
    options:
      - "Engineering"
      - "Product"
      - "Design"

# Main questions - shuffled if randomize_questions: true
questions:
  - id: 3
    title: "First main question"
    type: text_area

  - id: 4
    title: "Second main question"
    type: rating
    max: 5
```

---

## Question IDs

- Must be **unique integers** across all questions (intro + main)
- Should be **sequential** starting from 1
- No gaps allowed (1, 2, 3... not 1, 3, 5)

---

## Answer Storage

Answers are stored with keys derived from question structure:
- Simple questions: `q{id}` → `q1`, `q2`
- Compound sub-questions: `q{id}_{key}` → `q3_a`, `q3_b`
- Matrix rows: `q{id}_{row_key}` → `q12_office`, `q12_culture`
- Ranking: JSON array of ordered items
- Checkbox: comma-separated string

---

## Type Selection Guide

| Use Case | Recommended Type |
|----------|------------------|
| Name, email, short text | `text_input` |
| Feedback, comments | `text_area` |
| Multiple related text questions | `compound` |
| 2-5 mutually exclusive options | `radio` |
| 6+ options or long list | `select` |
| Simple yes/no | `yes_no` |
| "Select all that apply" | `checkbox` |
| Satisfaction/agreement scale | `linear_scale` |
| Quick quality rating | `rating` |
| NPS survey | `nps` |
| Percentage or continuous value | `slider` |
| Rate multiple items on same scale | `matrix` |
| Priority ordering | `ranking` |
| Date selection | `date` |
| Time selection | `time` |
| Numeric value with limits | `number` |

---

## Validation

Validate your YAML against the schema:

```bash
# Using ajv-cli
ajv validate -s questions.schema.json -d demo_questionnaire.yaml

# Using yq + jsonschema (Python)
yq -o=json demo_questionnaire.yaml | jsonschema -i /dev/stdin questions.schema.json
```

---

## Example: Complete Employee Survey

```yaml
settings:
  questionnaire_id: Employee_Survey
  version: "1"
  display_mode: one_by_one
  randomize_questions: true
  randomize_options: true
  auto_advance: false
  title: "Employee Satisfaction Survey"

intro_questions:
  - id: 1
    title: "What is your name?"
    type: text_input
    placeholder: "Your full name"

  - id: 2
    title: "Which department do you work in?"
    type: select
    options:
      - "Engineering"
      - "Product"
      - "Design"
      - "Sales"
      - "Operations"

  - id: 3
    title: "How long have you been with the company?"
    type: number
    min: 0
    max: 30
    step: 1

questions:
  - id: 4
    title: "How satisfied are you with your role?"
    type: linear_scale
    min: 1
    max: 10
    min_label: "Very dissatisfied"
    max_label: "Very satisfied"

  - id: 5
    title: "Would you recommend working here to a friend?"
    type: yes_no

  - id: 6
    title: "Rate these aspects of your workplace"
    type: matrix
    rows:
      - key: management
        label: "Management support"
      - key: growth
        label: "Career growth"
      - key: balance
        label: "Work-life balance"
    columns:
      - "Poor"
      - "Fair"
      - "Good"
      - "Excellent"

  - id: 7
    title: "Rank these benefits by importance"
    type: ranking
    options:
      - "Health insurance"
      - "Remote work"
      - "Learning budget"
      - "Flexible hours"

  - id: 8
    title: "What could we do better?"
    type: text_area
    placeholder: "Share your thoughts..."
```

---

## Demo Questionnaire Reference

The `demo_questionnaire.yaml` file contains all 16 question types. Here's the complete map:

### Intro Questions (IDs 1-4) — Never Shuffled

| ID | Type | Purpose |
|----|------|---------|
| 1 | `text_input` | Name collection |
| 2 | `select` | Role/department dropdown |
| 3 | `number` | Years of experience |
| 4 | `date` | Start date |

### Main Questions (IDs 5-18) — Can Be Shuffled

| ID | Type | Purpose |
|----|------|---------|
| 5 | `text_area` | Open-ended feedback |
| 6 | `compound` | Multi-part text (3 sub-questions) |
| 7 | `radio` | Single choice (work preference) |
| 8 | `yes_no` | Binary choice |
| 9 | `checkbox` | Multiple selection |
| 10 | `linear_scale` | 1-10 satisfaction scale |
| 11 | `slider` | Percentage slider |
| 12 | `rating` | Star rating (⭐) |
| 13 | `rating` | Fire icon rating (🔥) |
| 14 | `nps` | Net Promoter Score |
| 15 | `matrix` | Grid rating (4 rows × 4 columns) |
| 16 | `ranking` | Drag & drop ordering |
| 17 | `time` | Time picker |
| 18 | `text_area` | Final open feedback |

**Tip:** When creating your own questionnaire, use this demo as a starting point. Copy the question blocks you need and delete the rest.
