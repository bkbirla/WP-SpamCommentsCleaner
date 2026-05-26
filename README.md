# WordPress Comment Spam Detector

A powerful, high-performance Python tool designed to automate the detection and cleanup of comment spam on WordPress websites using the WordPress REST API. It supports rule-based heuristics, Akismet API, and Google Gemini LLM for classification, and handles extremely large spam comments without crashing the server.

---

## Features

- **Robust Connection Handling**: Uses a two-stage parallel retrieval process (metadata first, then content via `context=view`) to bypass Nginx server buffer overflows and prevent `IncompleteRead` errors caused by huge spam payloads.
- **Three Spam Classifiers**:
  - **Heuristics (Rule-based)**: Analyzes spam keywords, suspicious TLDs, disposable emails, mixed character scripts, all-caps shouting, repetitive phrases, excessive links, SEO anchor stuffing, and applies trust discounts for registered users.
  - **Akismet API**: Integrates with the official Akismet spam checking service.
  - **Google Gemini LLM**: Uses advanced generative AI via the Google Gemini API to analyze comment context and metadata for precise classification.
- **Concurrent Processing**: Fetches and classifies comments in parallel using multithreading for maximum throughput.
- **Flexible Actions**: Can run in interactive mode (prompting you for verification) or automated mode (automatically marking detected comments as spam).

---

## Installation

1. **Clone or download** this repository to your machine.
2. **Create and activate a virtual environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

---

## Configuration

Copy `.env.example` to `.env` and fill in your details:
```bash
cp .env.example .env
```

Open `.env` and configure the following variables:

```ini
# WordPress REST API Settings
WP_URL=https://your-site.com
WP_USERNAME=your_username
# Generate this in WP-Admin -> Users -> Profile -> Application Passwords (24 chars)
WP_APP_PASSWORD=xxxx xxxx xxxx xxxx xxxx xxxx

# Spam Classifier Type (options: heuristic, llm, akismet)
CLASSIFIER_TYPE=heuristic

# LLM Classifier (Required if CLASSIFIER_TYPE=llm)
GEMINI_API_KEY=your_gemini_api_key

# Akismet Classifier (Required if CLASSIFIER_TYPE=akismet)
AKISMET_API_KEY=your_akismet_api_key
```

---

## Usage

Run the detector using the command line:

```bash
python main.py
```

### CLI Arguments

Customize the run using the following flags:

| Argument | Description | Default |
| :--- | :--- | :--- |
| `--classifier` | Classifier to use: `heuristic`, `llm`, or `akismet` | Configured in `.env` |
| `--status` | WordPress comment status to fetch (e.g. `hold`, `approve`, `spam`) | `hold` |
| `--limit` | Maximum number of comments to retrieve | All pending comments |
| `--action` | Action to take: `prompt` (interactive), `mark-spam` (auto), `none` | `prompt` |
| `--url` | WordPress URL (overrides `.env`) | Configured in `.env` |
| `--username` | WordPress username (overrides `.env`) | Configured in `.env` |
| `--password`| WordPress Application Password (overrides `.env`) | Configured in `.env` |

#### Examples

**Fetch all pending comments and prompt for confirmation before marking spam:**
```bash
python main.py --action prompt
```

**Fetch the last 50 pending comments and automatically mark spam using the Gemini LLM:**
```bash
python main.py --classifier llm --limit 50 --action mark-spam
```

---

## Verification & Testing

This project includes a comprehensive suite of 28 unit tests validating all heuristic criteria, Akismet verification, and client fetching logic.

Run the tests using `unittest`:
```bash
python verify_detector.py
```
