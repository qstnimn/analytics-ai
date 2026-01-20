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

---

## Option 3: Streamlit Cloud (Easiest)

### 1. Push to GitHub
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/your-username/analytics-ai.git
git push -u origin main
```

### 2. Deploy to Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click "New app"
3. Select your GitHub repository
4. Main file path: `app2.py`
5. Click "Advanced settings"
6. Add secrets (copy from your `.streamlit/secrets.toml`)
7. Click "Deploy"

### 3. Manage Secrets in Cloud

**Streamlit Cloud Dashboard → App Settings → Secrets**

Paste your entire `secrets.toml` content:
```toml
GROQ_API_KEY = "your-key"
CONNECTION_STRING = "your-connection"

[firestore]
type = "service_account"
project_id = "your-project"
...
```

### 4. Access
Your app will be at: `https://your-app-name.streamlit.app`

---

## Option 4: Azure App Service

### 1. Prepare Deployment Files

Create `startup.sh`:
```bash
#!/bin/bash
streamlit run app2.py --server.port=$PORT --server.address=0.0.0.0
```

### 2. Create Azure Resources
```bash
# Login
az login

# Create resource group
az group create --name analytics-ai-rg --location eastus

# Create app service plan
az appservice plan create \
  --name analytics-ai-plan \
  --resource-group analytics-ai-rg \
  --sku B1 \
  --is-linux

# Create web app
az webapp create \
  --resource-group analytics-ai-rg \
  --plan analytics-ai-plan \
  --name analytics-ai-app \
  --runtime "PYTHON:3.11"
```

### 3. Configure Application Settings
```bash
# Add environment variables
az webapp config appsettings set \
  --resource-group analytics-ai-rg \
  --name analytics-ai-app \
  --settings \
    GROQ_API_KEY="your-key" \
    CONNECTION_STRING="your-connection" \
    GOOGLE_APPLICATION_CREDENTIALS="/home/site/wwwroot/service-account-key.json"
```

### 4. Deploy Code
```bash
# Using Azure CLI
az webapp up \
  --resource-group analytics-ai-rg \
  --name analytics-ai-app \
  --runtime "PYTHON:3.11"

# Or using Git deployment
git remote add azure https://analytics-ai-app.scm.azurewebsites.net/analytics-ai-app.git
git push azure main
```

### 5. Access
Your app will be at: `https://analytics-ai-app.azurewebsites.net`

---

## Option 5: AWS EC2

### 1. Launch EC2 Instance
```bash
# Use Amazon Linux 2 or Ubuntu 22.04
# Instance type: t3.medium or larger
# Security group: Allow inbound on port 8501
```

### 2. Connect and Setup
```bash
# SSH into instance
ssh -i your-key.pem ec2-user@your-instance-ip

# Update system
sudo yum update -y  # Amazon Linux
# OR
sudo apt update && sudo apt upgrade -y  # Ubuntu

# Install Python 3.11
sudo yum install python3.11 -y

# Install Git
sudo yum install git -y
```

### 3. Clone and Install
```bash
# Clone repository
git clone https://github.com/your-username/analytics-ai.git
cd analytics-ai

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 4. Configure Secrets
```bash
mkdir -p .streamlit
nano .streamlit/secrets.toml
# Paste your secrets and save
```

### 5. Run with Screen (Persistent)
```bash
# Install screen
sudo yum install screen -y

# Start screen session
screen -S analytics-ai

# Run app
streamlit run app2.py --server.port=8501 --server.address=0.0.0.0

# Detach: Press Ctrl+A, then D
# Reattach: screen -r analytics-ai
```

### 6. Run as Systemd Service (Production)
Create `/etc/systemd/system/analytics-ai.service`:
```ini
[Unit]
Description=Analytics AI Streamlit App
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/home/ec2-user/analytics-ai
Environment="PATH=/home/ec2-user/analytics-ai/venv/bin"
ExecStart=/home/ec2-user/analytics-ai/venv/bin/streamlit run app2.py --server.port=8501 --server.address=0.0.0.0
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable analytics-ai
sudo systemctl start analytics-ai
sudo systemctl status analytics-ai
```

### 7. Access
`http://your-instance-ip:8501`

---

## Option 6: Google Cloud Run

### 1. Install Google Cloud SDK
```bash
# Download from: https://cloud.google.com/sdk/docs/install
gcloud init
```

### 2. Build and Push Container
```bash
# Set project
gcloud config set project your-project-id

# Build image
gcloud builds submit --tag gcr.io/your-project-id/analytics-ai

# Or use Docker
docker build -t gcr.io/your-project-id/analytics-ai .
docker push gcr.io/your-project-id/analytics-ai
```

### 3. Deploy to Cloud Run
```bash
gcloud run deploy analytics-ai \
  --image gcr.io/your-project-id/analytics-ai \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GROQ_API_KEY=your-key \
  --set-secrets CONNECTION_STRING=sql-connection:latest \
  --port 8501
```

### 4. Access
Your app will be at: `https://analytics-ai-xxxxx.run.app`

---

## Post-Deployment Tasks

### 1. Verify Functionality
- [ ] Chat interface loads
- [ ] New chat creation works
- [ ] Example prompts execute
- [ ] Plan generation succeeds
- [ ] Analysis execution completes
- [ ] Charts render correctly
- [ ] Chart editing works
- [ ] Firestore sync active

### 2. Monitor Performance
```bash
# Check logs
streamlit run app2.py --logger.level=info

# Docker logs
docker logs -f analytics-ai-streamlit

# System metrics
htop  # CPU/Memory usage
```

### 3. Set Up Monitoring (Production)

#### Option A: Streamlit Cloud
- Built-in metrics in dashboard
- View logs in real-time

#### Option B: Custom Monitoring
```python
# Add to app2.py
import logging
logging.basicConfig(
    filename='analytics_ai.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Log important events
logging.info(f"New session created: {session_id}")
logging.error(f"Analysis failed: {error}")
```

#### Option C: Application Insights (Azure)
```bash
pip install opencensus-ext-azure

# Add to app2.py
from opencensus.ext.azure.log_exporter import AzureLogHandler
logger.addHandler(AzureLogHandler(
    connection_string='InstrumentationKey=your-key'
))
```

### 4. Set Up Alerts

Create health check endpoint (add to `app2.py`):
```python
# At the bottom of app2.py
import os
if os.getenv('ENABLE_HEALTH_CHECK'):
    st.write("")  # Hidden health check
```

Monitor with:
- **UptimeRobot** (free)
- **Pingdom**
- **AWS CloudWatch**
- **Azure Monitor**

---

## Security Hardening

### 1. Enable HTTPS
```bash
# Use Nginx reverse proxy
sudo apt install nginx

# Configure /etc/nginx/sites-available/analytics-ai
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}

# Get SSL certificate
sudo certbot --nginx -d your-domain.com
```

### 2. Restrict Access
```python
# Add authentication (app2.py)
import streamlit_authenticator as stauth

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days']
)

name, authentication_status, username = authenticator.login('Login', 'main')

if not authentication_status:
    st.stop()
```

### 3. Rate Limiting
```python
# Add to app2.py
from streamlit_extras.add_vertical_space import add_vertical_space
import time

if 'last_request' not in st.session_state:
    st.session_state.last_request = 0

# Rate limit: 1 request per 5 seconds
if time.time() - st.session_state.last_request < 5:
    st.warning("Please wait a few seconds between requests.")
    st.stop()

st.session_state.last_request = time.time()
```

---

## Troubleshooting

### Issue: Port already in use
```bash
# Find process using port 8501
lsof -i :8501  # Mac/Linux
netstat -ano | findstr :8501  # Windows

# Kill the process
kill -9 <PID>  # Mac/Linux
taskkill /PID <PID> /F  # Windows
```

### Issue: Module not found
```bash
pip install -r requirements.txt --force-reinstall
```

### Issue: Firestore connection fails
```bash
# Verify service account key
cat service-account-key.json

# Test connection
python -c "from google.cloud import firestore; db = firestore.Client(); print('Connected!')"
```

### Issue: SQL Server connection fails
```bash
# Test ODBC connection
python -c "import pyodbc; print(pyodbc.drivers())"

# Verify connection string
python -c "import pyodbc; conn = pyodbc.connect('your-connection-string'); print('Connected!')"
```

---

## Performance Tuning

### 1. Enable Caching
```python
# Already implemented in app2.py
@st.cache_resource
def get_clients():
    ...
```

### 2. Optimize Firestore Reads
```python
# Use batch reads
batch = db_client.batch()
refs = [db_client.collection('users').document(id) for id in ids]
docs = db_client.get_all(refs)
```

### 3. Database Connection Pooling
```python
# Add to ai_logic.py
from sqlalchemy import create_engine, pool
engine = create_engine(CONNECTION_STRING, poolclass=pool.QueuePool)
```

---

## Backup and Recovery

### 1. Backup Firestore
```bash
gcloud firestore export gs://your-backup-bucket/backups/$(date +%Y%m%d)
```

### 2. Backup Application State
```python
# Export session data
import json
with open(f'backup_{session_id}.json', 'w') as f:
    json.dump(st.session_state.report_data, f)
```

### 3. Recovery Procedure
```bash
# Restore from backup
gcloud firestore import gs://your-backup-bucket/backups/20240112
```

---

## 🎉 Deployment Complete!

Your Analytics AI application is now running in production. Monitor logs, set up alerts, and iterate based on user feedback.

**Next Steps:**
1. Share with initial users for beta testing
2. Collect feedback
3. Monitor error rates and performance
4. Iterate and improve

**Support:**
- 📧 Email: your-support-email@company.com
- 📖 Docs: Internal wiki link
- 🐛 Issues: GitHub Issues page
