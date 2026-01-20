# config.py - PRODUCTION READY VERSION
# This version uses environment variables for flexibility
# Copy this content to replace your current config.py

import os
from dotenv import load_dotenv

# Load environment variables from .env file (for local development)
load_dotenv()

# --- API Keys ---
# These should be set in your .env file or environment variables
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GEMINI_API_KEY = os.environ.get("GOOGLE_API_KEY")

# --- Database Connection ---
# Default values work for local development with ContosoRetailDW
# Override these in .env file for different environments
DB_SERVER = os.environ.get("DB_SERVER", "localhost\\SQLEXPRESS")
DB_DATABASE = os.environ.get("DB_DATABASE", "ContosoRetailDW")

# You can override the entire connection string if needed
CONNECTION_STRING = os.environ.get(
    "CONNECTION_STRING",
    f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={DB_SERVER};DATABASE={DB_DATABASE};Trusted_Connection=yes;'
)

# --- Firestore Details ---
# Collection and document names for AI knowledge base storage
KNOWLEDGE_BASE_COLLECTION = 'crdw_ai_knowledge_base'
KNOWLEDGE_BASE_DOCUMENT = 'crdw_schema'
CHAT_SESSIONS_COLLECTION = 'chat_sessions'

# --- Validation ---
# Helpful warnings for missing configuration
if not os.environ.get("GOOGLE_API_KEY") and not os.environ.get("GROQ_API_KEY"):
    print("⚠️  Warning: No API keys found. Set GOOGLE_API_KEY or GROQ_API_KEY in .env file")

if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
    print("⚠️  Warning: GOOGLE_APPLICATION_CREDENTIALS not set. Firestore may not work.")
