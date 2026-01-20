# 🎯 Analytics AI - GitHub Publishing Action Plan

## 📊 Project Analysis Summary

**Main Application:** Streamlit-based AI analytics platform (`app2.py`)
**Core Dependencies:** Gemini/Groq AI, Firestore, SQL Server
**Status:** Ready for cleanup and publication

---

## ✅ STEP-BY-STEP ACTION PLAN

### PHASE 1: CLEANUP (Do First)

#### 1.1 Delete Unused Files
Run these commands in PowerShell from the project root:

```powershell
# Delete old Dash app (replaced by app2.py)
Remove-Item "app.py" -Force

# Delete old versions folder
Remove-Item "old ones" -Recurse -Force

# Delete unrelated project
Remove-Item "my-sam" -Recurse -Force

# Delete cache folders
Remove-Item "__pycache__" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "cache" -Recurse -Force -ErrorAction SilentlyContinue

# Delete regeneratable schema files (will be recreated by users)
Remove-Item "crdw_schema_metadata.json" -Force -ErrorAction SilentlyContinue
Remove-Item "dw_schema_metadata.json" -Force -ErrorAction SilentlyContinue
```

#### 1.2 Secure Your Secrets (CRITICAL!)
**Before committing to Git, verify these files are NOT in your repo:**

```powershell
# Check if sensitive files exist
Get-ChildItem -Recurse -Include "*.env","service-account-key.json","secrets.toml" | Select-Object FullName

# If service-account-key.json exists, MOVE it outside the repo
Move-Item "service-account-key.json" "C:\safe-location\service-account-key.json"
```

**⚠️ CRITICAL:** Never commit:
- `.env` file
- `service-account-key.json`
- Any file with API keys

---

### PHASE 2: CONFIGURE

#### 2.1 Update config.py (Remove Hardcoded Credentials)
**Current Issue:** Your SQL Server name is hardcoded in `config.py`

**Recommended Changes:**
```python
# config.py - Updated version
import os
from dotenv import load_dotenv

load_dotenv()

# --- API Keys ---
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GEMINI_API_KEY = os.environ.get("GOOGLE_API_KEY")

# --- Database Connection ---
# Allow override via environment variable for different deployments
DB_SERVER = os.environ.get("DB_SERVER", "localhost\\SQLEXPRESS")
DB_DATABASE = os.environ.get("DB_DATABASE", "ContosoRetailDW")
CONNECTION_STRING = os.environ.get(
    "CONNECTION_STRING",
    f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={DB_SERVER};DATABASE={DB_DATABASE};Trusted_Connection=yes;'
)

# --- Firestore Details ---
KNOWLEDGE_BASE_COLLECTION = 'crdw_ai_knowledge_base'
KNOWLEDGE_BASE_DOCUMENT = 'crdw_schema'
CHAT_SESSIONS_COLLECTION = 'chat_sessions'
```

#### 2.2 Create Your .env File (Local Development Only)
```powershell
# Copy the example file
Copy-Item ".env.example" ".env"

# Edit .env with your actual credentials
notepad .env
```

Fill in your actual values:
```env
LLM_PROVIDER=gemini
GOOGLE_API_KEY=your_actual_gemini_key
GROQ_API_KEY=your_actual_groq_key
GOOGLE_APPLICATION_CREDENTIALS=C:\path\to\service-account-key.json
```

---

### PHASE 3: PREPARE FOR GITHUB

#### 3.1 Initialize Git Repository
```powershell
# Navigate to project folder
cd "C:\Analytics AI"

# Initialize Git
git init

# Add all files (respects .gitignore)
git add .

# Check what will be committed (verify no secrets!)
git status
```

**⚠️ VERIFY:** Run this command and ensure NO sensitive files are listed:
```powershell
git status | Select-String -Pattern "\.env|service-account|secrets\.toml"
```
If you see any, add them to `.gitignore` immediately!

#### 3.2 Create Initial Commit
```powershell
git commit -m "Initial commit: Analytics AI platform

- Streamlit-based AI analytics application
- Support for Gemini and Groq LLMs
- SQL Server integration with AI-powered queries
- Automatic visualization and insights
- Firestore knowledge base integration"
```

---

### PHASE 4: PUBLISH TO GITHUB

#### 4.1 Create GitHub Repository
1. Go to https://github.com/new
2. Repository name: `analytics-ai` (or your preferred name)
3. Description: "AI-powered data analytics platform with natural language queries"
4. **Keep it Public** (or Private if preferred)
5. **DO NOT** initialize with README (we already have one)
6. Click "Create repository"

#### 4.2 Link and Push
```powershell
# Add GitHub remote (replace YOUR_USERNAME)
git remote add origin https://github.com/YOUR_USERNAME/analytics-ai.git

# Push to GitHub
git branch -M main
git push -u origin main
```

---

### PHASE 5: POST-PUBLISH SETUP

#### 5.1 Add a LICENSE File
Create `LICENSE` file with MIT License:
```powershell
# You can do this on GitHub's web interface:
# Repository → Add file → Create new file → Name it "LICENSE"
# Choose MIT License from the template
```

#### 5.2 Update Repository Settings (on GitHub)
1. Go to repository Settings → General
2. Add topics/tags: `ai`, `analytics`, `streamlit`, `data-visualization`, `gemini`, `sql`
3. Update description
4. Add website URL (if deployed)

#### 5.3 Create First Release
1. Go to Releases → Create a new release
2. Tag: `v1.0.0`
3. Title: "Analytics AI v1.0.0 - Initial Release"
4. Description: Summarize key features

---

## 📝 IMPORTANT NOTES FOR USERS

### What Users Need to Run Your Application:

1. **Python 3.8+** installed
2. **SQL Server** with sample database (or their own)
3. **ODBC Driver 17** for SQL Server
4. **Google Cloud account** for Firestore
5. **API Keys:**
   - Gemini API key (from Google AI Studio)
   - OR Groq API key (from Groq Console)
6. **Service Account JSON** for Firestore access

### Setup Complexity: Medium
- Not beginner-friendly due to multiple cloud dependencies
- Clear documentation helps significantly
- Consider creating a video tutorial

---

## 🔍 RECOMMENDED IMPROVEMENTS

### Before Publishing:
- [ ] Remove hardcoded server name from config.py
- [ ] Add error handling for missing API keys
- [ ] Test installation on fresh machine
- [ ] Create requirements.txt freeze: `pip freeze > requirements.txt`

### Nice to Have:
- [ ] Add demo video/GIF to README
- [ ] Create Docker image for easier deployment
- [ ] Add unit tests
- [ ] Create sample database schema script
- [ ] Add logging configuration
- [ ] Create CONTRIBUTING.md guide

---

## ⚠️ SECURITY CHECKLIST

Before pushing to GitHub, verify:

- [ ] `.env` is in `.gitignore` and NOT committed
- [ ] `service-account-key.json` is in `.gitignore` and NOT committed
- [ ] No API keys hardcoded in any `.py` files
- [ ] `secrets.toml` is in `.gitignore`
- [ ] Run `git log --all --full-history -- service-account-key.json` to check history
- [ ] Reviewed all files in `git status` before committing

---

## 🎬 QUICK START COMMANDS

Complete cleanup and prepare in one go:

```powershell
# Step 1: Cleanup
Remove-Item "app.py","old ones","my-sam" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "__pycache__","cache" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "*schema_metadata.json" -Force -ErrorAction SilentlyContinue

# Step 2: Initialize Git
git init
git add .
git status  # VERIFY NO SECRETS!

# Step 3: Commit
git commit -m "Initial commit: Analytics AI platform"

# Step 4: Push (replace YOUR_USERNAME)
git remote add origin https://github.com/YOUR_USERNAME/analytics-ai.git
git branch -M main
git push -u origin main
```

---

## 📞 USER SUPPORT STRATEGY

### Expected User Questions:
1. "How do I get a Gemini API key?" → Link to Google AI Studio
2. "What is Firestore?" → Add explanation in README
3. "Can I use my own database?" → Yes, run ingest_schema_to_firestore.py
4. "Do I need both Gemini and Groq?" → No, choose one
5. "How much does this cost?" → Gemini free tier: 15 requests/min

### Recommended Support Channels:
- GitHub Issues (for bugs)
- GitHub Discussions (for questions)
- Add FAQ section to README

---

## 📚 ADDITIONAL DOCUMENTATION TO CREATE

### Optional but Helpful:
1. **CONTRIBUTING.md** - Guidelines for contributors
2. **CHANGELOG.md** - Version history
3. **docs/API_KEYS.md** - Detailed API key setup guide
4. **docs/DATABASE_SETUP.md** - Database configuration guide
5. **docs/TROUBLESHOOTING.md** - Common issues and solutions

---

## ✨ SUCCESS CRITERIA

Your repository is ready when:
- ✅ README clearly explains what the project does
- ✅ Users can run it following the setup steps
- ✅ No secrets are committed to Git
- ✅ .gitignore prevents future secret leaks
- ✅ Requirements.txt is accurate
- ✅ Code is clean (no unused files)
- ✅ License is included

---

**Need help?** Review the README.md, DEPLOYMENT_GUIDE.md, and this action plan!
