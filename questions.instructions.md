# Questions Configuration Guide for LLMs

This document describes how to generate and modify `questions.yaml` for the CEO Assessment application.

## Schema Reference

See `questions.schema.json` for the formal JSON Schema definition.

## Question Types

### 1. `text_input` - Single Line Text
Short text answers (one line).

```yaml
- id: 1
  title: "What is your name?"
  type: text_input
  placeholder: "Enter your full name"  # optional
```

### 2. `text_area` - Multi-line Text
Long-form text answers (multiple lines, ~200px height).

```yaml
- id: 2
  title: "Describe your biggest achievement this quarter"
  subtitle: "Be specific about impact and outcomes"  # optional
  type: text_area
  placeholder: "Start typing..."  # optional
```

### 3. `compound` - Multiple Sub-questions
Groups related sub-questions under one main question. Each sub-question gets its own text area.

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

**Rules for `compound`:**
- `subquestions` is required
- Each sub-question needs `key` (single lowercase letter: a, b, c...) and `label`
- Keys must be sequential and unique within the question

### 4. `radio` - Single Choice
Select exactly one option from a list.

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

**Rules for `radio`:**
- `options` is required (array of strings)
- Minimum 2 options
- User must select exactly one

### 5. `checkbox` - Multiple Choice
Select zero or more options from a list.

```yaml
- id: 5
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

**Rules for `checkbox`:**
- `options` is required (array of strings)
- Minimum 2 options
- User can select multiple (or none)
- Stored as comma-separated string

### 6. `select` - Dropdown
Single selection from a dropdown menu.

```yaml
- id: 6
  title: "Select your department"
  type: select
  options:
    - "Engineering"
    - "Product"
    - "Design"
    - "Sales"
    - "Marketing"
    - "Operations"
```

**Rules for `select`:**
- `options` is required (array of strings)
- Minimum 2 options
- A placeholder "-- Select an option --" is added automatically

## General Rules

### Question IDs
- Must be sequential integers starting from 1
- Must be unique across all questions
- No gaps allowed (1, 2, 3... not 1, 3, 5)

### Required Fields
Every question MUST have:
- `id` (integer)
- `title` (string, non-empty)
- `type` (one of the 6 types above)

### Optional Fields
- `subtitle` - helper text below title (any type)
- `placeholder` - placeholder text (text_input, text_area only)
- `options` - list of choices (radio, checkbox, select - REQUIRED for these types)
- `subquestions` - list of sub-questions (compound - REQUIRED)

## File Structure

```yaml
# CEO Assessment Questions Configuration
# Supported types: text_input, text_area, compound, radio, checkbox, select

questions:
  - id: 1
    title: "First question"
    type: text_area

  - id: 2
    title: "Second question"
    type: radio
    options:
      - "Option A"
      - "Option B"

  # ... more questions
```

## Best Practices

1. **Clear titles**: Questions should be self-explanatory
2. **Use subtitles** for additional context or instructions
3. **Consistent tone**: Keep language style consistent across questions
4. **Logical order**: Group related questions together
5. **Appropriate types**:
   - Use `text_area` for open-ended reflective questions
   - Use `radio` for mutually exclusive choices
   - Use `checkbox` for "select all that apply"
   - Use `compound` when you need structured sub-questions
6. **Placeholder hints**: Use placeholders to show expected format

## Answer Storage

Answers are stored with keys derived from question structure:
- Simple questions: `q{id}` → `q1`, `q2`, etc.
- Compound sub-questions: `q{id}_{key}` → `q3_a`, `q3_b`, etc.

## Validation

To validate your YAML against the schema:

```bash
# Using ajv-cli (npm install -g ajv-cli)
ajv validate -s questions.schema.json -d questions.yaml

# Using yq + jsonschema (Python)
yq -o=json questions.yaml | jsonschema -i /dev/stdin questions.schema.json
```

## Example: Complete Questionnaire

```yaml
questions:
  - id: 1
    title: "What's your biggest win this month?"
    type: text_area
    placeholder: "Describe a specific achievement..."

  - id: 2
    title: "Rate your work-life balance"
    type: radio
    options:
      - "Excellent"
      - "Good"
      - "Needs improvement"
      - "Poor"

  - id: 3
    title: "Team collaboration"
    subtitle: "Reflect on how you work with others"
    type: compound
    subquestions:
      - key: a
        label: "Who helped you most this month?"
      - key: b
        label: "How did you help others?"

  - id: 4
    title: "Which areas need more resources?"
    subtitle: "Select all that apply"
    type: checkbox
    options:
      - "Headcount"
      - "Budget"
      - "Tools"
      - "Training"
      - "Time"

  - id: 5
    title: "Your primary focus area"
    type: select
    options:
      - "Product development"
      - "Customer success"
      - "Team building"
      - "Process improvement"
```
