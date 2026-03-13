# 🚀 Deployment Guide - Analytics AI (Streamlit)

## Pre-Deployment Checklist

- [ ] All tests pass (`python test_streamlit_app.py`)
- [ ] Environment variables configured
- [ ] Firestore service account key obtained
- [ ] SQL Server connection string verified
- [ ] API keys (Groq, Anthropic) secured
- [ ] `.streamlit/secrets.toml` created (from example)
- [ ] `.gitignore` updated to exclude secrets

---

## Option 1: Local Development

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Secrets
```bash
# Copy the example and fill in your actual values
cp .streamlit/secrets.toml.example .streamlit/secrets.toml

# Edit with your credentials
notepad .streamlit/secrets.toml  # Windows
nano .streamlit/secrets.toml     # Mac/Linux
```

### 3. Set Environment Variables (Alternative)
```bash
# Windows PowerShell
$env:GROQ_API_KEY = "your-key-here"
$env:CONNECTION_STRING = "your-connection-string"
$env:GOOGLE_APPLICATION_CREDENTIALS = "service-account-key.json"

# Mac/Linux
export GROQ_API_KEY="your-key-here"
export CONNECTION_STRING="your-connection-string"
export GOOGLE_APPLICATION_CREDENTIALS="service-account-key.json"
```

### 4. Run the Application
```bash
streamlit run app2.py
```

### 5. Access
Open browser to: `http://localhost:8501`

---

## Option 2: Docker Deployment

### 1. Create `.env` File
```bash
# Create .env file with your secrets
cat > .env << EOF
GROQ_API_KEY=your-groq-key
ANTHROPIC_API_KEY=your-anthropic-key
CONNECTION_STRING=your-sql-connection-string
EOF
```

### 2. Build the Image
```bash
docker build -t analytics-ai:latest .
```

### 3. Run with Docker Compose
```bash
docker-compose up -d
```

### 4. View Logs
```bash
docker-compose logs -f analytics-ai
```

### 5. Stop the Service
```bash
docker-compose down
```

### 6. Access
Open browser to: `http://localhost:8501`
