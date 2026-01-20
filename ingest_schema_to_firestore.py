"""
Complete Schema Ingestion Pipeline for ContosoRetailDW
======================================================
This unified script performs the entire ingestion workflow:

1. EXTRACT: Connect to SQL Server and extract schema metadata
   - Tables, columns, data types
   - Foreign key relationships
   - Sample rows (first 3)
   
2. SAVE: Export to local JSON file (crdw_schema_metadata.json)
   - Backup for version control
   - Can skip AI step if needed

3. CLASSIFY: Use Gemini AI to analyze tables
   - Classify as FACT/DIMENSION/BRIDGE/LOOKUP
   - Generate purpose summaries

4. SUMMARIZE: Generate strategic business summary
   - Markdown-formatted overview for executives
   
5. UPLOAD: Push to Firestore
   - Collection: crdw_ai_knowledge_base
   - Document: crdw_schema
   - Includes relationships for JOIN generation

Estimated Runtime: 3-5 minutes
Estimated Cost: ~$0.80 in Gemini API calls
"""

import json
import time
import os
import sys
import datetime
import base64
import math
from dotenv import load_dotenv

# Database libraries
import pandas as pd
from sqlalchemy import create_engine

# AI and Cloud libraries
from google import genai
from google.genai import types
from google.cloud import firestore

load_dotenv()

# =============================================
# Configuration
# =============================================
# Database
DB_SERVER = 'MARKF\\SQLEXPRESS'
DB_DATABASE = 'ContosoRetailDW'
SQL_SERVER_URI = (
    f"mssql+pyodbc://{DB_SERVER}/{DB_DATABASE}?"
    "trusted_connection=yes&driver=ODBC+Driver+17+for+SQL+Server"
)

# AI & Firestore
GEMINI_MODEL = 'gemini-2.5-flash-lite'
FIRESTORE_COLLECTION = 'crdw_ai_knowledge_base'
FIRESTORE_DOCUMENT = 'crdw_schema'

# Output
JSON_OUTPUT_FILE = 'crdw_schema_metadata.json'
SAMPLE_ROWS_LIMIT = 3
MAX_RETRIES = 5

# =============================================
# PHASE 1: DATABASE EXTRACTION
# =============================================
def make_json_safe(obj):
    """Recursively serialize values for JSON compatibility."""
    if isinstance(obj, dict):
        return {k: make_json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [make_json_safe(x) for x in obj]
    elif obj is None:
        return None
    elif isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    elif isinstance(obj, (pd.Timestamp, datetime.datetime, datetime.date)):
        return obj.isoformat()
    elif isinstance(obj, bytes):
        return base64.b64encode(obj).decode("utf-8")
    else:
        return obj

def extract_schema_from_database(engine):
    """Extract complete schema metadata from SQL Server."""
    print("🔌 Connecting to database...")
    
    # Get all tables
    tables_query = """
    SELECT TABLE_SCHEMA, TABLE_NAME
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_TYPE = 'BASE TABLE'
    ORDER BY TABLE_SCHEMA, TABLE_NAME
    """
    tables = pd.read_sql(tables_query, engine)
    print(f"   ✅ Found {len(tables)} tables")
    
    schema_data = {}
    
    print(f"\n📊 Extracting metadata for {len(tables)} tables...")
    for idx, row in tables.iterrows():
        schema, table = row["TABLE_SCHEMA"], row["TABLE_NAME"]
        table_key = f"{schema}.{table}"
        
        print(f"   [{idx+1}/{len(tables)}] {table_key}")
        
        # Get columns
        col_query = f"""
        SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = '{schema}' AND TABLE_NAME = '{table}'
        """
        cols = pd.read_sql(col_query, engine)
        cols = cols.where(pd.notna(cols), None)
        
        # Get sample rows
        try:
            sample_query = f"SELECT TOP {SAMPLE_ROWS_LIMIT} * FROM [{schema}].[{table}]"
            sample_df = pd.read_sql(sample_query, engine)
            sample = sample_df.map(lambda x: make_json_safe(x)).to_dict(orient="records")
        except Exception as e:
            sample = f"Could not fetch sample: {e}"
        
        schema_data[table_key] = {
            "schema": schema,
            "table_name": table,
            "columns": cols.to_dict(orient="records"),
            "sample_rows": sample,
        }
    
    # Get relationships (foreign keys)
    print(f"\n🔗 Extracting foreign key relationships...")
    relationships_query = """
    SELECT 
        fk.name AS FK_name,
        tp.name AS parent_table,
        cp.name AS parent_column,
        tr.name AS referenced_table,
        cr.name AS referenced_column
    FROM sys.foreign_keys AS fk
    INNER JOIN sys.foreign_key_columns AS fkc ON fkc.constraint_object_id = fk.object_id
    INNER JOIN sys.tables AS tp ON fkc.parent_object_id = tp.object_id
    INNER JOIN sys.columns AS cp ON fkc.parent_object_id = cp.object_id AND fkc.parent_column_id = cp.column_id
    INNER JOIN sys.tables AS tr ON fkc.referenced_object_id = tr.object_id
    INNER JOIN sys.columns AS cr ON fkc.referenced_object_id = cr.object_id AND fkc.referenced_column_id = cr.column_id
    """
    rels = pd.read_sql(relationships_query, engine)
    schema_data["_relationships"] = rels.to_dict(orient="records")
    print(f"   ✅ Found {len(rels)} foreign key relationships")
    
    return schema_data

def save_schema_to_json(schema_data, filepath):
    """Save schema to local JSON file."""
    print(f"\n💾 Saving schema to {filepath}...")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(make_json_safe(schema_data), f, indent=4)
    print(f"   ✅ Schema saved successfully")

# =============================================
# PHASE 2: AI CLASSIFICATION
# =============================================
def initialize_firestore_client():
    """Initialize Firestore client."""
    try:
        db = firestore.Client()
        print("✅ Firestore client initialized.")
        return db
    except Exception as e:
        print(f"❌ Firestore initialization failed: {e}")
        sys.exit(1)

def initialize_gemini_client():
    """Initialize Gemini client."""
    try:
        client = genai.Client()
        print("✅ Gemini client initialized.")
        return client
    except Exception as e:
        print(f"❌ Gemini initialization failed. Is GEMINI_API_KEY set? Error: {e}")
        sys.exit(1)

def call_gemini_with_backoff(client, prompt, model, system_instruction=None):
    """Call Gemini with exponential backoff."""
    for attempt in range(MAX_RETRIES):
        try:
            config = types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json"
            )
            
            if system_instruction:
                config.system_instruction = system_instruction
            
            resp = client.models.generate_content(
                model=model,
                contents=[prompt],
                config=config
            )
            
            # Parse JSON response
            json_text = resp.text.strip()
            return json.loads(json_text)
            
        except Exception as e:
            delay = 2 ** attempt
            print(f"   ⚠️ Attempt {attempt + 1}/{MAX_RETRIES} failed: {e}")
            if attempt + 1 == MAX_RETRIES:
                print(f"   ❌ All retries exhausted")
                return {"classification": "UNKNOWN", "purpose_summary": f"AI classification failed: {e}"}
            print(f"   ⏳ Retrying in {delay}s...")
            time.sleep(delay)

def classify_table(client, table_name, columns, sample_rows, related_fks):
    """Classify a single table using AI."""
    # Prepare compact column schema
    col_schema = {
        col['COLUMN_NAME']: f"{col['DATA_TYPE']} ({'NULL' if col['IS_NULLABLE'] == 'YES' else 'NOT NULL'})"
        for col in columns
    }
    
    # Limit sample rows
    limited_samples = sample_rows[:SAMPLE_ROWS_LIMIT] if isinstance(sample_rows, list) else []
    
    prompt = f"""
You are a data warehouse expert. Analyze this table and provide classification.

**Table:** {table_name}

**Columns:**
{json.dumps(col_schema, indent=2)}

**Sample Data (first {SAMPLE_ROWS_LIMIT} rows):**
{json.dumps(limited_samples, indent=2)}

**Related Foreign Keys:**
{json.dumps(related_fks, indent=2)}

Return a JSON object with:
{{
  "classification": "FACT" | "DIMENSION" | "BRIDGE" | "LOOKUP" | "OTHER",
  "purpose_summary": "One sentence (max 20 words) describing business purpose"
}}

Rules:
- FACT tables store metrics/transactions with foreign keys to dimensions
- DIMENSION tables store descriptive attributes (products, customers, dates)
- BRIDGE tables resolve many-to-many relationships
- LOOKUP tables are small reference tables
- Use sample data to understand actual content, not just column names
"""
    
    return call_gemini_with_backoff(
        client, 
        prompt, 
        GEMINI_MODEL,
        system_instruction="You are a data warehouse architect. Always return valid JSON only."
    )

def classify_all_tables(client, schema_data):
    """Classify all tables using AI."""
    relationships = schema_data.get('_relationships', [])
    tables = {k: v for k, v in schema_data.items() if k != '_relationships'}
    
    print(f"\n🤖 Starting AI classification for {len(tables)} tables...")
    print("   (This will take ~2-3 minutes)")
    
    classified_tables = {}
    
    for i, (table_name, table_data) in enumerate(sorted(tables.items()), 1):
        print(f"\n[{i}/{len(tables)}] Analyzing {table_name}...")
        
        columns = table_data.get('columns', [])
        sample_rows = table_data.get('sample_rows', [])
        
        # Find related foreign keys
        related_fks = [
            rel for rel in relationships 
            if rel['parent_table'] == table_data['table_name'] or 
               rel['referenced_table'] == table_data['table_name']
        ]
        
        # Classify with AI
        classification = classify_table(
            client,
            table_name,
            columns,
            sample_rows,
            related_fks
        )
        
        # Transform columns to simple schema format
        raw_columns = {
            col['COLUMN_NAME']: f"{col['DATA_TYPE']} ({'NULL' if col['IS_NULLABLE'] == 'YES' else 'NOT NULL'})"
            for col in columns
        }
        
        classified_tables[table_name] = {
            "classification": classification.get('classification', 'UNKNOWN'),
            "purpose_summary": classification.get('purpose_summary', 'No summary available'),
            "raw_columns": raw_columns,
            "sample_rows": sample_rows[:SAMPLE_ROWS_LIMIT] if isinstance(sample_rows, list) else []  # Save sample rows!
        }
        
        print(f"   ✅ Classified as: {classification.get('classification', 'UNKNOWN')}")
        
        # Brief pause to avoid rate limits
        time.sleep(0.5)
    
    return classified_tables

# =============================================
# PHASE 3: STRATEGIC SUMMARY
# =============================================
def generate_strategic_summary(client, classified_tables, relationships):
    """Generate a business-friendly strategic summary."""
    table_summary = {
        name: {
            "type": data["classification"],
            "purpose": data["purpose_summary"]
        }
        for name, data in classified_tables.items()
    }
    
    prompt = f"""
You are a senior data strategist. Create a strategic summary of this data warehouse for business executives.

**Classified Tables ({len(classified_tables)} total):**
{json.dumps(table_summary, indent=2)}

**Table Relationships ({len(relationships)} foreign keys):**
{json.dumps(relationships[:20], indent=2)}

Generate a comprehensive strategic summary with these sections:

1. **🏗️ Data Architecture Overview** (2-3 sentences)
   - What type of warehouse is this? (Star schema, snowflake, etc.)
   - What business domains are covered?

2. **📊 Core Fact Tables & Metrics**
   - List key fact tables and what metrics they track
   - Mention grain/granularity (daily transactions, aggregated, etc.)

3. **🔍 Dimensional Context**
   - List major dimension tables and what they describe
   - Highlight any hierarchies (product categories, org structure, etc.)

4. **🔗 Analytical Capabilities**
   - What types of business questions can this warehouse answer?
   - Example analytical scenarios (sales analysis, inventory tracking, etc.)

Format as markdown with emojis. Write for non-technical business users.
Maximum 400 words.
"""
    
    print(f"\n📝 Generating strategic business summary...")
    
    try:
        config = types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=1000
        )
        
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[prompt],
            config=config
        )
        
        print("   ✅ Strategic summary generated")
        return resp.text.strip()
        
    except Exception as e:
        print(f"   ⚠️ Strategic summary generation failed: {e}")
        return f"Strategic summary generation failed: {e}"

# =============================================
# PHASE 4: FIRESTORE UPLOAD
# =============================================
def upload_to_firestore(db_client, classified_tables, relationships, strategic_summary):
    """Upload the complete knowledge base to Firestore."""
    firestore_document = {
        'status': 'Complete',
        'generated_at': firestore.SERVER_TIMESTAMP,
        'strategic_summary': strategic_summary,
        'classified_tables': classified_tables,
        '_relationships': relationships,
        'metadata': {
            'source_file': JSON_OUTPUT_FILE,
            'database': DB_DATABASE,
            'model_used': GEMINI_MODEL,
            'total_tables': len(classified_tables),
            'total_relationships': len(relationships)
        }
    }
    
    print(f"\n☁️ Uploading to Firestore...")
    doc_ref = db_client.collection(FIRESTORE_COLLECTION).document(FIRESTORE_DOCUMENT)
    doc_ref.set(firestore_document)
    
    print(f"\n🎉 SUCCESS! Knowledge base uploaded to Firestore:")
    print(f"   📂 Collection: {FIRESTORE_COLLECTION}")
    print(f"   📄 Document: {FIRESTORE_DOCUMENT}")
    print(f"   📊 Tables: {len(classified_tables)}")
    print(f"   🔗 Relationships: {len(relationships)}")

# =============================================
# MAIN ORCHESTRATION
# =============================================
def run_complete_ingestion():
    """Execute the full ingestion pipeline."""
    print("=" * 60)
    print("  COMPLETE SCHEMA INGESTION PIPELINE")
    print("=" * 60)
    
    # PHASE 1: Extract from Database
    print("\n📥 PHASE 1: DATABASE EXTRACTION")
    print("-" * 60)
    try:
        engine = create_engine(SQL_SERVER_URI)
        schema_data = extract_schema_from_database(engine)
        save_schema_to_json(schema_data, JSON_OUTPUT_FILE)
    except Exception as e:
        print(f"\n❌ Database extraction failed: {e}")
        sys.exit(1)
    
    # PHASE 2: Initialize AI clients
    print("\n🤖 PHASE 2: AI INITIALIZATION")
    print("-" * 60)
    gemini_client = initialize_gemini_client()
    db_client = initialize_firestore_client()
    
    # PHASE 3: AI Classification
    print("\n🔬 PHASE 3: AI CLASSIFICATION")
    print("-" * 60)
    classified_tables = classify_all_tables(gemini_client, schema_data)
    
    # PHASE 4: Strategic Summary
    print("\n📋 PHASE 4: STRATEGIC SUMMARY GENERATION")
    print("-" * 60)
    relationships = schema_data.get('_relationships', [])
    strategic_summary = generate_strategic_summary(
        gemini_client,
        classified_tables,
        relationships
    )
    
    # PHASE 5: Upload to Firestore
    print("\n☁️ PHASE 5: FIRESTORE UPLOAD")
    print("-" * 60)
    upload_to_firestore(db_client, classified_tables, relationships, strategic_summary)
    
    print("\n" + "=" * 60)
    print("  ✅ INGESTION COMPLETE!")
    print("=" * 60)
    print(f"\n📁 Local backup: {JSON_OUTPUT_FILE}")
    print(f"☁️ Firestore: {FIRESTORE_COLLECTION}/{FIRESTORE_DOCUMENT}")
    print(f"\n🚀 Your Analytics AI app is ready to use the updated schema!")

# =============================================
# ENTRY POINT
# =============================================
if __name__ == "__main__":
    # Validate environment
    if 'GEMINI_API_KEY' not in os.environ:
        print("❌ GEMINI_API_KEY environment variable not set.")
        print("   Set it with: $env:GEMINI_API_KEY='your-key-here'")
        sys.exit(1)
    
    # Run the pipeline
    run_complete_ingestion()
