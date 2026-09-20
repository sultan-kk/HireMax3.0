# HireMatrix — AI-Assisted Resume Intelligence for HR Teams

A Final Year Project: upload CVs in almost any common format, extract
structured candidate data (Name, Email, Phone, Skills, Experience,
Education) using AI-powered vision OCR, review and correct it, and export
verified records to a multi-sheet Excel workbook with a full audit trail.
Includes multi-user HR login and is ready to deploy on Streamlit Community
Cloud straight from GitHub.

## 1. Supported file formats

| Format | How it's read |
|---|---|
| PDF | Native text layer extracted directly when present (fast, 100% accurate); scanned/image-only pages fall back to the image pipeline below |
| DOCX | Read directly via `python-docx` — no OCR at all |
| TXT | Read directly as plain text — no OCR at all |
| PNG / JPG / JPEG / BMP / TIFF / WEBP | **Gemini AI vision** transcribes the image (see §3); falls back to Tesseract OCR automatically if no Gemini API key is configured |

## 2. What's in this version

- **Gemini-powered image extraction** — photographed CVs, skewed scans,
  and unusual fonts are read far more reliably by a vision model than by
  classic character-matching OCR. Zero configuration required to keep
  working: no `GEMINI_API_KEY` set means the app automatically uses the
  original Tesseract pipeline instead, no crash, no missing feature.
- **Multi-user HR login** (`streamlit-authenticator`) — see §4.
- **Hybrid PDF extraction**, **DOCX/TXT native reading**, **section-aware
  classification** (Hobbies/References/Personal Info correctly excluded
  even without a keyword on every line), **worldwide phone validation**,
  **duplicate-candidate detection**, and a **Dashboard** with KPIs and a
  skills-frequency chart — all carried over and unchanged.
- **Streamlit Cloud ready**: `packages.txt` + `requirements.txt` install
  Tesseract, Poppler, and the spaCy English model automatically on
  deploy — no manual server setup.

## 3. Setting up Gemini (for the most accurate image extraction)

1. Get a free API key from Google AI Studio: https://aistudio.google.com/apikey
2. **Local development**: copy `.streamlit/secrets.toml.example` to
   `.streamlit/secrets.toml` and paste your key in:
   ```toml
   GEMINI_API_KEY = "your-key-here"
   ```
   This file is already in `.gitignore` — never commit your real key.
3. **Streamlit Community Cloud**: don't upload a secrets file at all.
   Open your deployed app's Settings then Secrets in the Streamlit Cloud
   dashboard and paste the same `GEMINI_API_KEY = "..."` line there —
   Streamlit injects it automatically, no code changes needed.
4. That's it. `config.get_gemini_api_key()` checks Streamlit secrets
   first, then the `GEMINI_API_KEY` environment variable, so the exact
   same code works locally and on Cloud.

**Don't want to use Gemini at all?** Just don't set the key — every image
upload will silently use the Tesseract OCR pipeline instead, exactly like
before.

## 4. Setting up HR team login

1. `pip install -r requirements.txt` (installs `streamlit-authenticator` + `bcrypt`)
2. Run `python generate_password_hash.py`, type a password, and copy the
   printed hash.
3. Open `auth_config.yaml` and paste that hash in place of
   `REPLACE_WITH_GENERATED_HASH` for the `hr_admin` user (or add more
   user blocks — copy the example, give each person their own username
   and their own generated hash).
4. Change `cookie.key` in `auth_config.yaml` to any random string (this
   signs the login cookie).
5. Run the app — you'll see a login form before anything else loads.

`auth_config.yaml` only stores bcrypt hashes, never plain-text passwords,
so it's safe to commit to your repo. If you'd rather your HR team's
usernames weren't visible on GitHub, make the repo private.

## 5. Project Structure

```
hiremax/
├── app.py                      # Streamlit UI — login gate, sidebar nav, 4 pages
├── extraction_engine.py        # Multi-format extraction (Gemini/Tesseract images, hybrid PDF, DOCX, TXT)
├── parser.py                    # Section-aware classification + field extraction
├── excel_handler.py            # Multi-sheet Excel export, delete, duplicate check, formatting
├── theme.py                     # Indigo/coral design system (cards, KPIs, badges)
├── config.py                     # Branding, paths, Gemini/auth config, keyword banks, i18n
├── generate_icon.py               # Draws assets/icon.png + logo_banner.png
├── generate_password_hash.py      # One-off helper to create a login password hash
├── auth_config.yaml                # HR login credentials (bcrypt hashes)
├── assets/
│   ├── icon.png / icon.ico          # App icon
│   ├── logo_banner.png              # Header banner
│   └── fonts/                        # Bundled OFL-licensed fonts
├── packages.txt                  # APT packages for Streamlit Cloud (tesseract, poppler, ...)
├── requirements.txt              # Python packages, incl. google-genai + spaCy model wheel
├── .streamlit/
│   ├── config.toml                  # Theme colors + upload size limit
│   └── secrets.toml.example         # Template for your Gemini API key
├── .gitignore                    # Keeps secrets.toml (and other local junk) out of git
├── run_app.bat                   # Local Windows launcher (venv-aware)
├── column_labels.json            # Auto-created once you rename columns in the UI
├── exports/                      # Candidates_Master.xlsx is created here
└── sample_data/                  # put test CVs here
```

## 6. Deploying to Streamlit Community Cloud

`packages.txt` (already included) is what makes Tesseract/Poppler work on
the server:
```
tesseract-ocr
poppler-utils
libgl1
libglib2.0-0
```
Streamlit Cloud runs `apt-get install` on every line in this file
automatically — you never run this yourself.

1. Push this whole folder to a GitHub repo (`packages.txt` and
   `requirements.txt` must sit at the repo root, next to `app.py`).
2. Go to share.streamlit.io, click **New app**, and pick your repo,
   branch, and set the main file to `app.py`.
3. Before or after first deploy, add your `GEMINI_API_KEY` under
   Settings then Secrets (see §3).
4. Deploy. `packages.txt` installs the system OCR/PDF tools,
   `requirements.txt` installs Python packages including the spaCy model
   wheel directly (no separate `spacy download` command needed — that's
   what silently fails on Cloud since only `requirements.txt` and
   `packages.txt` run automatically).

## 7. Running locally

### System dependencies (only needed for the Tesseract fallback path)

**Windows:** Tesseract (https://github.com/UB-Mannheim/tesseract/wiki) and
Poppler (https://github.com/oschwartz10612/poppler-windows/releases). If
either isn't on PATH, set `TESSERACT_CMD` / `POPPLER_PATH` env vars —
`config.py` also auto-detects the standard Windows Tesseract install path.

**macOS:** `brew install tesseract poppler`

**Linux:** `sudo apt install tesseract-ocr poppler-utils`

### Python environment

```bash
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS/Linux

pip install -r requirements.txt
```

### Run it

```bash
streamlit run app.py
```
or double-click `run_app.bat` on Windows (activates `venv` automatically
if one exists next to it).

## 8. How the four pages work

- **Dashboard** — KPI tiles and a skills-frequency chart across every
  saved candidate.
- **Upload & Extract** — drop in any mix of supported formats, click
  **Process Uploaded Files**; each gets a format badge and a status
  badge (Pending/Saved).
- **Review & Edit** — original document/image on the left, editable
  fields on the right. A caption tells you exactly which extraction path
  was used (native text / Gemini / Tesseract OCR / mixed). The
  **Excluded / Low-Confidence Text** panel is collapsed by default —
  open it to delete genuine noise or move a wrongly-excluded item back
  into a field. A duplicate warning appears if the email/phone matches
  an already-saved candidate.
- **Records** — search, browse the audit log, download a formatted copy
  of the master workbook, delete a record, or rename Excel columns.

## 9. How classification works (for your viva / report)

- Every extractor (Gemini, Tesseract, native PDF/DOCX/TXT) produces the
  same shape: a list of lines with a confidence score. Native text gets
  confidence=100; Gemini-transcribed lines get a flat high confidence
  (it doesn't expose per-word scores like Tesseract does).
- **Section-zone tracking**: the parser tracks which resume section it's
  in (Education / Skills / Hobbies / References / Personal Information)
  as it scans top-to-bottom, so a hobbies list like "Cricket" / "Chess"
  is correctly excluded even without the word "hobby" on those lines.
- **Personal/demographic fields** (CNIC, date of birth, marital status,
  nationality, religion, ...) are their own category, separated from
  core hire-relevant fields.
- **Referee contact exclusion**: a referee's own email/phone under a
  "References" section can't accidentally overwrite the candidate's own
  contact info.
- **Symbol-aware noise filter**: `C++`, `C#`, `ASP.NET` are never
  mistaken for OCR garbage.
- **Precise "excluded" tracking**: extractors return the exact source
  line index they used, so a reformatted value (e.g. a normalized phone
  number) never causes its source line to wrongly reappear as noise.
- **Worldwide phone detection** via Google's `phonenumbers` library.

## 10. Extending the project further

- Add more skills/education keywords in `config.py`.
- Add more UI languages: add a key to `config.TRANSLATIONS` and
  `config.LANGUAGES` — missing keys fall back to English automatically.
- **Custom-trained NER for skills extraction**: the current skills
  extractor is a curated keyword list (fast, deterministic, easy to
  defend in a viva). Swapping it for a model fine-tuned specifically on
  labeled resume data would need a training dataset this project doesn't
  have — a good "future work" line for your report, but not something
  that can be responsibly bolted on without real training data to
  validate it against.
