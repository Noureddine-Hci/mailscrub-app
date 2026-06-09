---
description: Environment setup and local development start
---

This workflow helps you or an AI agent set up the development environment and start the MailScrub server.

### 1. Create Virtual Environment
// turbo
```powershell
python -m venv .venv
```

### 2. Activate Virtual Environment
// turbo
```powershell
.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies
// turbo
```powershell
pip install -r backend/requirements.txt
```

### 4. Setup Environment Variables
If `backend/.env` does not exist, copy `.env.example`.
```powershell
if (!(Test-Path backend/.env)) { Copy-Item .env.example backend/.env }
```

### 5. Start Development Server
// turbo
```powershell
python -m uvicorn backend.main:app --reload --port 8000
```
