# CaseWeave AI

> **From fragmented evidence to connected intelligence.**
> An AI-powered investigation & evidence-analysis reasoning layer for modern investigative teams.

---

## What is CaseWeave?

CaseWeave is an AI reasoning and contradiction-analysis workspace designed for investigative workflows (tailored for the India/Tamil Nadu police context). 

It connects fragmented case materials—**CCTV & phone videos, photos, witness statements, forensic reports, and access logs**—into a unified, evidence-linked workspace.

> **Honest core principle:**  
> *"CaseWeave finds contradictions and gaps faster and more consistently than manual review, and cites its sources so you can verify everything — it does not replace investigation, verification, or judgment."*

---

## Key Features

1. **Multimodal Media Extraction (Stage 1):**
   - PDFs (text layer + scanned page OCR fallback).
   - Images & crime scene photos (deep visual inspection via Meta Vision + OCR for signage/stamps).
   - Audio recordings transcribed via Whisper.
   - Videos processed with audio extraction and sampled key-frame visual reasoning.

2. **Source-Grounded Observations & Timelines (Stages 2 & 3):**
   - Extracts structured factual claims classified into `observed`, `reported`, `inferred`, `disputed`, or `unknown`.
   - Chronological timeline construction linking directly to source citations and locators.

3. **3-Agent Adversarial Debate for Discrepancy Detection (Stage 4):**
   - Moves past unreliable single-prompt LLM evaluation.
   - **Prosecutor Agent** builds the argument for conflict and non-coincidence.
   - **Defender Agent** argues compatibility, temporal ambiguity, or separate events.
   - **Judge Agent** adjudicates using a strict shared decision rubric.
   - Reviewer workflow requires non-empty rationale with complete audit tracking.

4. **Entity Resolution & Interactive Graph (Stage 11):**
   - Resolves aliases and mentions into canonical people, devices, locations, and organizations.
   - Rendered using an interactive dependency-free SVG entity-relationship graph.

5. **Legal Retrieval RAG (Stage 5):**
   - Contextual RAG matching case facts against legal statutes (e.g., Bharatiya Sakshya Adhiniyam / BSA s.63 electronic evidence provisions, IEA s.65B).

6. **Interactive 3D Scene Shell (Stage 6):**
   - Procedural 3D scene approximation built with React Three Fiber (R3F) and runtime Babel compilation from investigator room dimensions and object states.

7. **Synthesized Incident Reconstruction (Stage 9a):**
   - Holistically synthesizes supported facts vs. unresolved gaps, providing confidence-rated best guesses with investigative rationale.

8. **Exportable Reports & Legal Artifacts (Stage 10):**
   - Comprehensive Markdown reports and styled, publication-ready PDF exports.
   - Draft BSA s.63 Electronic Evidence Certificate generator.

9. **Security, Audit, & Integrity:**
   - Cryptographic SHA-256 evidence hashing upon ingest.
   - Tamper-evident hash-chained audit log with database-level concurrency locking.
   - Role-Based Access Control (RBAC): `investigator`, `reviewer`, and `admin`.

---

## Architecture Overview

```
CaseWeave/
├── backend/                  # FastAPI REST API & Pipeline Services
│   ├── api.py               # REST API endpoints & CORS
│   ├── auth.py              # JWT authentication & RBAC
│   ├── db.py                # Database models & connection management
│   ├── storage.py           # Content-addressed local object store
│   ├── job_queue.py          # RQ async job queue integration
│   ├── worker.py            # Background worker process
│   ├── upload_validation.py # Magic-byte verification & path sanitization
│   └── pipeline/            # 10+ core reasoning and extraction stages
├── frontend/                 # Next.js 16 + React 19 + Tailwind CSS
│   ├── app/                 # App Router UI
│   │   ├── case/[caseId]/   # Incident Reconstruction Studio & Entity Graph
│   │   └── scene/           # Dynamic Three.js 3D scene viewer
│   └── lib/                 # API client & auth session handling
```

---

## Tech Stack

- **Frontend:** Next.js 16 (App Router), React 19, Tailwind CSS v4, Three.js, React Three Fiber (`@react-three/fiber`), `@babel/standalone`.
- **Backend:** Python 3.11, FastAPI, Uvicorn, PyMySQL, RQ (Redis Queue), ReportLab (PDF), PyMuPDF.
- **Data & Storage:** MySQL (structured relations & audit trail), Redis (job queues), Local Object Store (content-addressed SHA-256).
- **AI Models & Inference:**
  - Primary: Meta AI API (`muse-wonder-1.0` for text reasoning & multimodal vision).
  - Audio: Groq Whisper (`whisper-large-v3`).
  - Fallback Chain: Meta → local model (optional) → Groq → Google Gemini.

---

## Getting Started

### 1. Prerequisites
- **Python 3.11+**
- **Node.js 20+** & npm
- **Docker** (for MySQL and Redis)

### 2. Infrastructure Setup
Start the required databases via Docker:
```bash
# MySQL container (port 3307, this machine only). Choose your own passwords.
docker run -d --name caseweave-mysql -p 127.0.0.1:3307:3306 -e MYSQL_ROOT_PASSWORD=<root-password> -e MYSQL_DATABASE=caseweave   -e MYSQL_USER=caseweave -e MYSQL_PASSWORD=<app-password> mysql:8.0

# Redis container (port 6381, this machine only, password required). Set the same value as REDIS_PASSWORD in the backend secrets.
docker run -d --name caseweave-redis -p 127.0.0.1:6381:6379 redis:7-alpine redis-server --requirepass <redis-password>
```

### 3. Backend Configuration & Run
```bash
cd backend

# Create virtual environment and install dependencies
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
# source venv/bin/activate

pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env with your credentials (META_API_KEY, optional GROQ_API_KEY / GOOGLE_API_KEY, MYSQL_* and REDIS_* settings).
# Set CASEWEAVE_ADMIN_PASSWORD to choose the first admin password; if you leave it blank the admin account starts on a
# shipped default and is forced to choose a new password at first sign-in.

# Terminal 1: Start FastAPI server
uvicorn api:app --port 8010 --reload

# Terminal 2: Start background pipeline worker
python worker.py
```

### 4. Frontend Setup & Run
```bash
cd frontend

# Install dependencies
npm install

# Start Next.js development server
npm run dev
```

Visit **`http://localhost:3000`** in your browser.  
First sign-in: user **`admin`** with the password you set in `CASEWEAVE_ADMIN_PASSWORD`. If you did not set one, the account starts on a
shipped default and the app makes you choose a new password (10+ characters) before anything else works. Admins add, reset and
remove users from **Users** on the home screen.

**Sample accounts for testing (this workstation only).** `admin`, `investigator1` and `reviewer1` all use the sample password
`CaseWeave-Sample-2026` so that anyone can try each role. This is for a test setup only: before real casework, sign in as each
one and change it (**Users → reset password**, or `/change-password`), or delete the sample accounts.
Browser smoke test of a running stack, with no model calls: `CW_PASSWORD=CaseWeave-Sample-2026 CW_CASE=<case id> node frontend/e2e/smoke.cjs`.

---

## Running Automated Tests

The backend tests create and delete rows, so they refuse to run unless `MYSQL_DATABASE` names a database containing "test".
Point them at a throwaway MySQL and Redis:
```bash
cd backend
MYSQL_DATABASE=caseweave_test MYSQL_PORT=3399 MYSQL_PASSWORD=<pw> REDIS_PORT=6399 python -m pytest tests -q
```
Frontend checks and the browser end-to-end script (needs the API and `npm run dev` or `npm start` running):
```bash
cd frontend
npx tsc --noEmit && npx eslint app && npx next build
CW_WEB=http://127.0.0.1:3000 CW_PASSWORD=<admin password> CW_CASE=<case id> node e2e/ui-check.cjs mytag
```
Set `NEXT_PUBLIC_API_URL` when the API is not on `http://127.0.0.1:8010` (and list the web address in the API's `ALLOWED_ORIGINS`).

---

## Privacy, integrity and AI use

- Case text sent to a language model has phone numbers, e-mails, Aadhaar, PAN, plates, IMEI and long numbers replaced by placeholders,
  and so are the names of people the analysis has resolved. Place names, free-text addresses and anything inside images are **not** redacted.
- Meta's hosted model is tried first. Only if it cannot answer does a local model, then Groq, then Gemini answer; the audit log records which.
  Set `LLM_PROVIDER_MODE=meta_only` or `local_only` to forbid the others. Audio transcription uses Groq and is refused outside `auto` mode.
- Uploaded originals are hashed, stored read-only and re-verified before they are shown or analysed. The audit trail is hash-chained and keyed.
- The legal library is a set of **summaries** written for this tool, not the official text of the Acts. Verify before relying on any section.
- Backups: set `BACKUP_ENCRYPTION_KEY` (any long random string) to encrypt the standing backup archive; without it the backup is plain files.

---

## Scope & Legal Boundaries

CaseWeave is an analytical aid for investigators. Deliberately out of scope:
- **No FIR/e-FIR registration** (statutory legal act with liability).
- **No physical lab integrations** (DNA, ballistics, physical forensics).
- **No statutory custody tracking or court-stage case management**.
- **No definitive guilt or innocence determinations**. All AI findings cite underlying sources and flag unverified gaps.

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
