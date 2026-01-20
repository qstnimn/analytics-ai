import os
import json
import time
# --- Groq Imports ---
from groq import Groq
from groq.types.chat import ChatCompletionMessageParam
# --- Gemini Imports ---
from google import genai
from google.cloud import firestore
import sys
import uuid
import pyodbc 
import pandas as pd
import re 
from dotenv import load_dotenv 
import plotly.express as px 
import plotly.graph_objects as go 
from dash import dcc, html
import anthropic
from dash import dash_table
import dash_bootstrap_components as dbc

import config
load_dotenv()
import warnings
warnings.filterwarnings("ignore", category=UserWarning)

# LLM Provider Configuration
# Set LLM_PROVIDER in your .env file: 'groq' or 'gemini'
LLM_PROVIDER = os.getenv('LLM_PROVIDER', 'gemini').lower()  # Default to Groq

# Model strategy: Use powerful models for critical tasks, fast models for simple tasks
if LLM_PROVIDER == 'gemini':
    MODEL_NAME = "gemini-2.5-pro"  # Critical: SQL, insights, visualizations
    FAST_MODEL_NAME = "gemini-2.5-flash-lite"  # Fast: classification, planning, summaries
else:  # groq
    MODEL_NAME = "moonshotai/kimi-k2-instruct"  # Critical: SQL, insights, visualizations
    FAST_MODEL_NAME = "meta-llama/llama-4-scout-17b-16e-instruct"  # Fast: classification, planning, summaries

MAX_RETRIES = 5
INITIAL_DELAY = 10

# Timeout configurations (in seconds)
DEFAULT_TIMEOUT = 120  # 2 minutes for most operations
SQL_GENERATION_TIMEOUT = 180  # 3 minutes for complex SQL generation
LONG_OPERATION_TIMEOUT = 300  # 5 minutes for very complex operations

# Global token tracking
TOKEN_USAGE = {
    'total_input': 0,
    'total_output': 0,
    'by_function': {}
}

# --- DATABASE CONNECTION DETAILS ---
CONNECTION_STRING = config.CONNECTION_STRING

db_summary_for_context = """
# 🏗️ Data Architecture Overview
Our Enterprise Data Warehouse is a **unified analytical hub** designed for retail analytics and decision-making. It consolidates data across three core pillars: **Sales, Inventory, and Customer Analytics.**

---

### 🔍 1. Dimensional Layers (The Context)
We use a **Star Schema** design with rich dimensional attributes, allowing you to slice and dice data across any business axis:

* **Market & Geography:** Track performance by `Region`, `Country`, and `Sales Territory`.
* **Product Hierarchy:** Deep-dive into specific `Categories` and `Subcategories`.
* **Customer & Channel:** Analyze by `Customer` demographics and `Sales Channel` (Store/Online/Reseller).
* **Organizational:** Monitor performance by `Store`, `Employee`, and `Promotion` effectiveness.
* **Temporal:** Time-series analysis using comprehensive `Date` dimension (fiscal/calendar periods).

---

### 📈 2. Fact Tables (The Metrics)
At the heart of the warehouse are event-level fact tables that capture every critical KPI:

| Category | Key Metrics & Tables |
| :--- | :--- |
| **Retail Sales** | Transaction-level sales data with quantities, costs, and amounts (`FactSales`). |
| **Online Sales** | E-commerce transactions with digital channel metrics (`FactOnlineSales`). |
| **Inventory** | Daily stock levels, costs, and aging analysis (`FactInventory`). |
| **Performance** | Sales quota tracking and attainment metrics (`FactSalesQuota`). |

---

### 💡 3. Analytical Power
By linking these layers via surrogate keys, the system enables comprehensive **retail analytics**:

* **Sales Performance:** Track revenue trends across products, territories, channels, and time periods.
* **Customer Analytics:** Segment customers by demographics and purchase behavior.
* **Inventory Optimization:** Monitor stock levels, turnover rates, and identify slow-moving items.
* **Channel Analysis:** Compare performance across retail stores, online, and reseller channels.
* **Promotion ROI:** Measure the effectiveness of marketing campaigns on sales lift.
* **Territory Management:** Analyze sales performance by geography and employee productivity.
""" 
def initialize_firestore_client():
    """Initializes and returns the synchronous Firestore client."""
    try:
        # The firestore.Client() automatically uses the credentials
        # set by your GOOGLE_APPLICATION_CREDENTIALS environment variable.
        db = firestore.Client()
        print("✅ Firestore client initialized.")
        return db
    except Exception as e:
        print(f"🛑 ERROR: Firestore Initialization failed. Is GOOGLE_APPLICATION_CREDENTIALS set? Details: {e}")
        sys.exit(1)

def initialize_groq_client():
    """Initializes and returns the synchronous Groq client."""
    if not os.environ.get("GROQ_API_KEY"):
        print("🛑 ERROR: GROQ_API_KEY environment variable not set.")
        sys.exit(1)
        
    try:
        # Client automatically looks for the GROQ_API_KEY environment variable
        client = Groq()
        print("✅ Groq client initialized.")
        return client
    except Exception as e:
        print(f"🛑 ERROR: Groq Initialization failed. Details: {e}")
        sys.exit(1)

def initialize_gemini_client():
    """Initializes and returns the Google Gemini client."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("🛑 ERROR: GEMINI_API_KEY environment variable not set.")
        sys.exit(1)
        
    try:
        client = genai.Client(api_key=api_key)
        print(f"✅ Gemini client initialized (Provider: {LLM_PROVIDER}, Model: {MODEL_NAME}).")
        return client
    except Exception as e:
        print(f"🛑 ERROR: Gemini Initialization failed. Details: {e}")
        sys.exit(1)
# Utilities functions
def call_groq_with_backoff(client, model_name, contents: list[ChatCompletionMessageParam], 
                           system_instruction: str, step_name: str, json_mode: bool = False, temperature: float = 0.3, timeout: int = 120):
    """Handles synchronous Groq API calls with exponential backoff and retries.
    
    Args:
        timeout: Maximum time in seconds to wait for a response (default: 120)
    """
    
    # Prepend the system instruction as the first message
    messages_with_system = [{"role": "system", "content": system_instruction}] + contents
    
    # Configure JSON response if needed
    response_format = {"type": "json_object"} if json_mode else None
    
    for attempt in range(MAX_RETRIES):
        try: 
            # Groq uses chat.completions.create for inference
            resp = client.chat.completions.create(
                model=model_name, 
                messages=messages_with_system, 
                temperature=temperature,
                response_format=response_format, # Pass response_format if json_mode is True
                timeout=timeout  # Add timeout to prevent hanging
            )
            
            # Track token usage
            if hasattr(resp, 'usage') and resp.usage:
                input_tokens = resp.usage.prompt_tokens
                output_tokens = resp.usage.completion_tokens
                
                # Update global totals
                TOKEN_USAGE['total_input'] += input_tokens
                TOKEN_USAGE['total_output'] += output_tokens
                
                # Track by function
                if step_name not in TOKEN_USAGE['by_function']:
                    TOKEN_USAGE['by_function'][step_name] = {'input': 0, 'output': 0, 'calls': 0}
                TOKEN_USAGE['by_function'][step_name]['input'] += input_tokens
                TOKEN_USAGE['by_function'][step_name]['output'] += output_tokens
                TOKEN_USAGE['by_function'][step_name]['calls'] += 1
                
                # Print usage for this call
                print(f"   💰 {step_name}: {input_tokens} in / {output_tokens} out (Model: {model_name})")
            
            # Groq response structure is standard OpenAI-style
            return resp.choices[0].message.content
            
        except Exception as e:
            # Groq SDK doesn't use gcp_exceptions, so we catch general exceptions
            delay = INITIAL_DELAY * (2 ** attempt)
            print(f"🛑 {step_name} (Attempt {attempt + 1}/{MAX_RETRIES}): Error: {e}. Retrying in {delay:.1f}s...")
            if attempt + 1 == MAX_RETRIES: raise e
            time.sleep(delay)
            
    return None

def call_gemini_with_backoff(client, model_name, contents: list, 
                             system_instruction: str, step_name: str, json_mode: bool = False, temperature: float = 0.3, timeout: int = 120):
    """Handles synchronous Gemini API calls with exponential backoff and retries.
    
    Args:
        timeout: Maximum time in seconds to wait for a response (default: 120)
    """
    
    import threading
    from contextlib import contextmanager
    
    @contextmanager
    def time_limit(seconds):
        """Cross-platform timeout using threading."""
        timer = None
        result = {'completed': False, 'exception': None}
        
        def timeout_handler():
            if not result['completed']:
                result['exception'] = TimeoutError(f"API call exceeded {seconds} second timeout")
        
        timer = threading.Timer(seconds, timeout_handler)
        timer.start()
        try:
            yield result
        finally:
            result['completed'] = True
            timer.cancel()
    
    for attempt in range(MAX_RETRIES):
        try:
            # Convert our format to Gemini format (simple parts structure)
            gemini_contents = []
            for msg in contents:
                role = "user" if msg["role"] == "user" else "model"
                gemini_contents.append({
                    "role": role,
                    "parts": [{"text": msg["content"]}]
                })
            
            # Configure generation with system instruction
            config = genai.types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=temperature,
                response_mime_type="application/json" if json_mode else "text/plain"
            )
            
            # Generate response using correct API with timeout
            with time_limit(timeout) as tl:
                response = client.models.generate_content(
                    model=model_name,
                    contents=gemini_contents,
                    config=config
                )
                
                # Check if timeout occurred
                if tl['exception']:
                    raise tl['exception']
            
            # Track token usage (Gemini provides usage metadata)
            try:
                if hasattr(response, 'usage_metadata') and response.usage_metadata:
                    input_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0)
                    output_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0)
                    
                    # Update global totals
                    TOKEN_USAGE['total_input'] += input_tokens
                    TOKEN_USAGE['total_output'] += output_tokens
                    
                    # Track by function
                    if step_name not in TOKEN_USAGE['by_function']:
                        TOKEN_USAGE['by_function'][step_name] = {'input': 0, 'output': 0, 'calls': 0}
                    TOKEN_USAGE['by_function'][step_name]['input'] += input_tokens
                    TOKEN_USAGE['by_function'][step_name]['output'] += output_tokens
                    TOKEN_USAGE['by_function'][step_name]['calls'] += 1
                    
                    # Print usage for this call
                    print(f"   💰 {step_name}: {input_tokens} in / {output_tokens} out (Model: {model_name})")
            except Exception:
                # If token tracking fails, continue anyway
                pass
            
            # Extract text from response
            # Gemini returns response.text directly
            return response.text
            
        except Exception as e:
            delay = INITIAL_DELAY * (2 ** attempt)
            print(f"🛑 {step_name} (Attempt {attempt + 1}/{MAX_RETRIES}): Error: {e}. Retrying in {delay:.1f}s...")
            if attempt + 1 == MAX_RETRIES: raise e
            time.sleep(delay)
            
    return None

def call_llm(client, model_name, contents: list, system_instruction: str, step_name: str, 
             json_mode: bool = False, temperature: float = 0.3, timeout: int = 120):
    """Unified LLM caller that routes to Groq or Gemini based on LLM_PROVIDER.
    
    Args:
        timeout: Maximum time in seconds to wait for a response (default: 120)
    """
    if LLM_PROVIDER == 'gemini':
        return call_gemini_with_backoff(client, model_name, contents, system_instruction, 
                                       step_name, json_mode, temperature, timeout)
    else:  # Default to Groq
        return call_groq_with_backoff(client, model_name, contents, system_instruction, 
                                     step_name, json_mode, temperature, timeout)

def reset_token_usage():
    """Resets the global token usage tracker."""
    global TOKEN_USAGE
    TOKEN_USAGE = {
        'total_input': 0,
        'total_output': 0,
        'by_function': {}
    }
    print(f"✅ Token usage tracker reset.")

def clean_sql_script(raw_sql):
    """
    Takes a raw string from the LLM and cleans it to be pure, executable SQL.
    (This function remains the same as it is client-agnostic)
    """
    if not raw_sql:
        return ""

    clean_sql = raw_sql.strip()
    if clean_sql.lower().startswith("```sql"):
        clean_sql = clean_sql[6:].strip()
    elif clean_sql.lower().startswith("```"):
        clean_sql = clean_sql[3:].strip()
        
    if clean_sql.endswith("```"):
        clean_sql = clean_sql[:-3].strip()
    
    # Find the last valid SQL keyword and take everything from that point onward.
    keywords = ['SELECT', 'WITH', 'INSERT', 'UPDATE', 'DELETE']
    last_pos = -1
    for keyword in keywords:
        pos = clean_sql.upper().rfind(keyword)
        if pos > last_pos:
            last_pos = pos
            
    if last_pos != -1:
        clean_sql = clean_sql[last_pos:]
        
    return clean_sql.strip() # Final trim
# =======================================================
# Chat Session Management Class 
# =======================================================
class ChatManager:
    """
    Manages chat history in Firestore for a specific session using transactions.
    """
    def __init__(self, db_client, session_id=None):
        self.session_id = session_id if session_id else str(uuid.uuid4())
        self.user_id = "user_abc" # Hardcoded for demo
        self.db_client = db_client # Store the client
        self.doc_ref = self.db_client.collection('users').document(self.user_id).collection('sessions').document(self.session_id)

    def add_message(self, role, content):
        message = {'role': role.lower(), 'content': content}

        @firestore.transactional
        def update_in_transaction(transaction, doc_ref, message, content):
            snapshot = doc_ref.get(transaction=transaction)
            if snapshot.exists:
                transaction.update(doc_ref, {'messages': firestore.ArrayUnion([message])})
            else:
                # If it's the first message, create the document with a title
                title = content[:50] + ("..." if len(content) > 50 else "")
                transaction.set(doc_ref, {
                    'created_at': firestore.SERVER_TIMESTAMP,
                    'title': title,
                    'messages': [message]
                })
        
        transaction = self.db_client.transaction()
        update_in_transaction(transaction, self.doc_ref, message, content)

    def get_history(self):
        doc = self.doc_ref.get()
        if doc.exists:
            return doc.to_dict().get('messages', [])
        return []
# =======================================================
# Core Application Logic
# =======================================================
def classify_question_type(groq_client, user_question):
    """
    Classifies a user question as:
    - direct_question
    - thinking_question
    - unrelated
    """
    system_prompt = """
You are an AI classifier with 3 possible labels, analyze the user's question and return ONLY one of the following labels:

**CRITICAL: Question length does NOT matter - only SQL query count matters!**

**Classification Rules:**

1. **direct_question** → Can be answered with ONE SELECT statement, even if the question is long or has multiple filters
   - Examples:
     ✓ "What are the top 10 products by sales revenue in the Pacific region during Q4 of 2014, broken down by subcategory?"
     ✓ "List all customers who purchased bikes between January and March 2013"
     ✓ "Find products that sell significantly well during weekdays but have near-zero sales on weekends."
     ✓ "I want pie charts showing sales by category for last year" (one query with GROUP BY)

2. **thinking_question** → Requires MULTIPLE steps or comparative analysis across different aggregations
   - Examples:
     ✓ "Analyze sales performance" (vague, needs breaking down into steps)
     ✓ "Compare year-over-year growth across regions" (needs 2 queries: one per year, then comparison)

3. **unrelated** → Not about business data, analytics, or databases
   - Examples: "What's the weather?", "Tell me a joke", "How are you?"

Respond with ONLY one label: direct_question, thinking_question, or unrelated.
"""

    messages = [{"role": "user", "content": user_question}]
    result = call_llm(
        client=groq_client,
        model_name=FAST_MODEL_NAME,  # Simple classification task
        contents=messages,
        system_instruction=system_prompt,
        step_name="Question Classification",
        temperature=0.0,
    )
    return result.strip().lower()

def get_ai_knowledge_base(db_client):
    doc_ref = db_client.collection(config.KNOWLEDGE_BASE_COLLECTION).document(config.KNOWLEDGE_BASE_DOCUMENT)
    doc = doc_ref.get()
    if doc.exists:
        data = doc.to_dict()
        # Extract FULL table details including columns AND sample_rows
        raw_schema_subset = data.get('classified_tables', {})
        
        # Extract relationships if they exist
        relationships = data.get('_relationships', [])
        
        # Debugging: Print to verify relationships and sample data are loaded
        tables_with_samples = sum(1 for t in raw_schema_subset.values() 
                                 if isinstance(t, dict) and 'sample_rows' in t and t['sample_rows'])
        print(f"📊 Loaded {len(raw_schema_subset)} tables ({tables_with_samples} with sample data) and {len(relationships)} relationships from knowledge base")
        
        return {
            'strategic_summary': data.get('strategic_summary', 'Schema summary missing.'),
            'raw_schema': raw_schema_subset,  # Now includes sample_rows!
            'relationships': relationships
        }
    else:
        raise FileNotFoundError(
            "AI Knowledge Base not found in Firestore. Please run ingestion_script.py first."
        )

def generate_business_plan(groq_client, chat_history, knowledge_base):
    from datetime import datetime
    
    # OPTIMIZATION: Extract only table names and column names (not full metadata)
    # This reduces token usage by ~75% compared to sending full raw_schema
    lightweight_schema = {}
    for table_name, table_details in knowledge_base['raw_schema'].items():
        # Extract just column names from the full column metadata
        if isinstance(table_details, dict) and 'columns' in table_details:
            lightweight_schema[table_name] = [col['COLUMN_NAME'] for col in table_details['columns']]
        elif isinstance(table_details, list):
            # If raw_schema already has column list format
            lightweight_schema[table_name] = table_details
    
    # Temporal context for relative date interpretation
    current_date = datetime.now().strftime('%B %d, %Y')
    temporal_context = f"""
**IMPORTANT - TEMPORAL CONTEXT:**
- Today's Date: {current_date}
- Database Coverage: 2020-2024 ONLY (no data exists beyond 2024)
- When user says "this year" or "recent" or "current" → Use 2024 (latest year in database)
- When user says "last year" → Use 2023
- When user says "this quarter" → Use Q4 2024 (latest quarter)
- When comparing periods, use years/quarters within 2020-2024 range
- If user mentions 2025 or later, inform them data only goes to 2024
"""
    
    system_prompt = f"""
{temporal_context}

**TASK:** You are an Intelligent Executive Consultant/Data Analyst. Your task is to transform a business problem into a **concise**, **high-impact**, **efficient**, and **non-redundant** strategic plan. 

**CRITICAL FORMATTING INSTRUCTION:**
Do NOT output any pre-computation, thought processes, or SQL SCRIPT. Only output the structured sections requested (Executive Summary, Action Plan, Key Metrics).

**TONE & FORMAT RULES:**
1. **Focus on Business Value:** Use professional business language.
2. **Be Grounded:** Use the provided database context to ensure the strategy is achievable.

3. **CRITICAL RULE FOR ACTION PLAN - EACH STEP MUST BE 100% INDEPENDENT:**
    
    The **Action Plan** must contain ONLY steps that can execute **completely independently** with a single SQL query! No step should rely on specific IDs, keys, or outputs from previous steps to ensures that each step can be executed in isolation without dependency issues. 
    The action plan also need to be simple and concise avoid unnecessary complexity. Make the steps easy to understand and implement for LLM  to execute.
    
    **❌ FORBIDDEN - Steps that need specific IDs/keys from previous steps:**
    WRONG - DON't DO THIS❌:
    Step 1: Calculate total spend for each customer and identify top 10
    Step 2: For those top 10 customers, find their most purchased category

4. **Handle Feedback:** If the user's latest message is feedback on a plan you just provided, you MUST generate a new, improved version of the plan that incorporates their feedback. Acknowledge their feedback in your new Executive Summary.

    **OUTPUT STRUCTURE:**
The final plan MUST ONLY have three main sections: **Executive Summary**, **Action Plan**, and **Key Metrics**.
**Executive Summary:** Summarize the potential business value, and insights from the business problem in 2-3 sentences.
**Action Plan:** A numbered list of clear, executable data analysis tasks (one per line). (Maximum of 6 steps)
**Key Metrics:** A list of key metrics to track and monitor during the implementation phase, provide descriptions or relations between metrics.

**CONTEXT - DATABASE SCHEMA SUMMARY:**
---
{knowledge_base['strategic_summary']}
---

**AVAILABLE TABLES & COLUMNS:**
---
{json.dumps(lightweight_schema, indent=2)}
---
"""
    
    resp_text = call_llm(
        client=groq_client, 
        model_name=FAST_MODEL_NAME,  
        contents=chat_history, 
        system_instruction=system_prompt, 
        step_name="Business Plan Generation",
        temperature=0.3
    )
    
    return resp_text if resp_text else "Error: Could not generate a plan."

def generate_direct_action_plan(user_question):
    """
    Creates a simplified, one-step business plan structure for a direct question.
    """
    executive_summary = f"The analysis for the direct question: '{user_question}' is executed immediately without a multi-step planning phase."
    action_plan = f"1. {user_question}"
    key_metrics = "The core metric(s) derived directly from the question."

    business_plan = f"""
**Executive Summary:**
{executive_summary}

**Action Plan:**
{action_plan}

**Key Metrics:**
{key_metrics}
"""
    return business_plan
# =======================================================
# Step 1: Function to Parse the Business Plan 
# =======================================================
def parse_business_plan_steps(plan_text):
    """
    A more robust parser that finds the 'Action Plan' heading and 
    extracts the numbered list items from between the headings.
    """
    print("   - Step 1 of 2: Extracting actionable steps from the approved plan...")
    actionable_steps = []
    in_action_plan_section = False
    
    lines = plan_text.split('\n')
    for line in lines:
        line_stripped = line.strip()
        
        # 1. Identify the start of the Action Plan section
        if 'action plan' in line_stripped.lower():
            in_action_plan_section = True
            continue
        
        # 2. Identify the end of the Action Plan section (e.g., when the next section starts)
        # We also check for any subsequent heading like 'key metrics'
        if in_action_plan_section and (line_stripped.startswith('---') or 'key metrics' in line_stripped.lower()):
            break
            
        if in_action_plan_section:
            # 3. Use a regex to look for any numbered list item (1., 2., 3. etc.) or bullet points (*, -)
            # This expression specifically looks for digits followed by a dot, or a bullet symbol, 
            # at the very beginning of the line (after stripping).
            match = re.match(r'^\s*[\d]+\.\s*(.*)', line) # Match pattern '1. ' or ' 2. '
            
            if match:
                # The group(1) contains the text after the number and period
                step_text = match.group(1).strip()
                if step_text:
                    actionable_steps.append(step_text)
            
            # Optionally, check for bullet points too (e.g., if the LLM changes format)
            elif line_stripped.startswith('*') or line_stripped.startswith('-'):
                 # Remove the bullet and leading space
                 step_text = re.sub(r'^[\*\-]\s*', '', line_stripped)
                 if step_text:
                    actionable_steps.append(step_text)
                    
    print(f"   - ✅ Found {len(actionable_steps)} actionable steps.")
    return actionable_steps

# =======================================================
# Smart Schema Filtering - Reduces Token Usage by 70%
# =======================================================
def filter_relevant_relationships(relevant_tables, all_relationships):
    """
    Filters relationships to only include foreign keys between the relevant tables.
    This prevents sending unnecessary relationship data for tables we're not using.
    """
    if not all_relationships:
        return []
    
    # Get lowercase table names for comparison (without schema prefix)
    relevant_table_names = set()
    for table in relevant_tables.keys():
        # Extract table name without 'dbo.' prefix
        table_name = table.lower().replace('dbo.', '')
        relevant_table_names.add(table_name)
    
    # Debug: print first relationship to see structure
    if all_relationships and len(all_relationships) > 0:
        print(f"   🔍 Sample relationship structure: {list(all_relationships[0].keys())}")
    
    filtered_relationships = []
    for rel in all_relationships:
        # Try different possible field names for parent/child tables
        parent_table = (rel.get('parent_table', '') or 
                       rel.get('table', '') or 
                       rel.get('child_table', '')).lower().replace('dbo.', '')
        
        child_table = (rel.get('child_table', '') or 
                      rel.get('referenced_table', '') or 
                      rel.get('parent_table', '')).lower().replace('dbo.', '')
        
        # Also check if either table is in our relevant set (not just both)
        # because sometimes we need parent-child even if one isn't directly mentioned
        if parent_table in relevant_table_names or child_table in relevant_table_names:
            filtered_relationships.append(rel)
    
    return filtered_relationships

def identify_relevant_tables(step_description, full_schema):
    """
    Intelligently selects only the tables mentioned in the step description.
    Falls back to all tables if none are explicitly mentioned.
    
    This reduces token usage from ~8,000 to ~2,000 per SQL generation call.
    """
    step_lower = step_description.lower()
    
    # Updated table lists (15 tables total - cleaned schema)
    fact_tables = ['factsales', 'factonlinesales', 'factinventory', 'factsalesquota']
    dim_tables = ['dimproduct', 'dimproductcategory', 'dimproductsubcategory', 
                  'dimcustomer', 'dimstore', 'dimdate', 'dimemployee', 
                  'dimchannel', 'dimpromotion', 'dimgeography', 'dimsalesterritory']
    
    all_table_keywords = fact_tables + dim_tables
    
    # Find tables mentioned in the description
    relevant_tables = {}
    mentioned_tables = set()
    
    for table_name in all_table_keywords:
        # Check if table name (without 'Fact' or 'Dim' prefix) appears in description
        clean_name = table_name.replace('fact', '').replace('dim', '')
        if clean_name in step_lower or table_name in step_lower:
            mentioned_tables.add(table_name)
    
    # Add actual schema entries for mentioned tables (case-insensitive match)
    for schema_table, schema_details in full_schema.items():
        schema_table_lower = schema_table.lower().replace('dbo.', '')
        if schema_table_lower in mentioned_tables:
            relevant_tables[schema_table] = schema_details
    
    # Fallback: If no tables detected, include common analysis tables
    if len(relevant_tables) == 0:
        common_tables = ['dbo.FactSales', 'dbo.DimProduct', 'dbo.DimDate', 'dbo.DimCustomer', 'dbo.DimStore']
        for schema_table, schema_details in full_schema.items():
            if schema_table in common_tables:
                relevant_tables[schema_table] = schema_details
    
    # Always include DimDate if we have any Fact table (nearly all queries need dates)
    has_fact_table = any('Fact' in t for t in relevant_tables.keys())
    has_dim_date = any('DimDate' in t for t in relevant_tables.keys())
    if has_fact_table and not has_dim_date:
        for schema_table, schema_details in full_schema.items():
            if 'DimDate' in schema_table:
                relevant_tables[schema_table] = schema_details
                break
    
    # Limit to max 8 tables to prevent token explosion
    if len(relevant_tables) > 8:
        # Prioritize Fact tables over Dim tables
        fact_priority = {k: v for k, v in relevant_tables.items() if 'Fact' in k}
        dim_priority = {k: v for k, v in relevant_tables.items() if 'Dim' in k}
        relevant_tables = {**fact_priority, **dict(list(dim_priority.items())[:8-len(fact_priority)])}
    
    print(f"   📊 Schema Filter: Sending {len(relevant_tables)} tables (down from {len(full_schema)})")
    return relevant_tables

# =======================================================
# Step Context Builder - Helps with Multi-Step Dependencies
# =======================================================
def build_step_context(step_description, data_frame):
    """
    Creates a compact summary of a step's results for use in subsequent steps.
    Returns dict with 'description', 'summary', and 'key_values'.
    """
    if data_frame is None or data_frame.empty:
        return {
            "description": step_description,
            "summary": "No data returned",
            "key_values": {}
        }
    
    context = {
        "description": step_description,
        "key_values": {}
    }
    
    # Case 1: Single value (e.g., "Calculate average sales")
    if data_frame.shape == (1, 1):
        value = data_frame.iloc[0, 0]
        col_name = data_frame.columns[0]
        context['summary'] = f"{col_name} = {value:,.2f}" if isinstance(value, (int, float)) else f"{col_name} = {value}"
        context['key_values'][col_name] = value
    
    # Case 2: Single row with multiple columns (e.g., "Get year range")
    elif data_frame.shape[0] == 1:
        summary_parts = []
        for col in data_frame.columns:
            val = data_frame[col].iloc[0]
            summary_parts.append(f"{col}={val}")
            context['key_values'][col] = val
        context['summary'] = ", ".join(summary_parts)
    
    # Case 3: Multiple rows - provide aggregates
    else:
        summary_parts = []
        summary_parts.append(f"{len(data_frame)} rows returned")
        
        # Get first column name and try to provide useful stats
        for col in data_frame.columns:
            if pd.api.types.is_numeric_dtype(data_frame[col]):
                avg_val = data_frame[col].mean()
                max_val = data_frame[col].max()
                min_val = data_frame[col].min()
                summary_parts.append(f"{col}: avg={avg_val:,.2f}, min={min_val:,.2f}, max={max_val:,.2f}")
                context['key_values'][f"{col}_average"] = avg_val
                context['key_values'][f"{col}_max"] = max_val
                context['key_values'][f"{col}_min"] = min_val
                break  # Just first numeric column to keep it concise
        
        context['summary'] = ", ".join(summary_parts)
    
    return context

# =======================================================
# Step 2: Function to Generate, Execute SQL and Retrieve Data
# =======================================================
def validate_sql_columns(sql_query, schema):
    """Validates that column names in SQL query exist in the provided schema."""
    # Extract all available columns from schema
    available_columns = set()
    for table_name, table_details in schema.items():
        if isinstance(table_details, dict) and 'columns' in table_details:
            for col in table_details['columns']:
                col_name = col['COLUMN_NAME'].lower()
                available_columns.add(col_name)
    
    # Look for suspicious patterns in SQL that might reference non-existent columns
    sql_upper = sql_query.upper()
    sql_lower = sql_query.lower()
    
    # Extract column references after SELECT (before FROM)
    select_match = re.search(r'SELECT\s+(.*?)\s+FROM', sql_upper, re.DOTALL)
    if select_match:
        select_clause = select_match.group(1)
        
        # Check for NULL AS ColumnName patterns (suspicious!)
        null_columns = re.findall(r'NULL\s+AS\s+(\w+)', select_clause, re.IGNORECASE)
        if null_columns:
            print(f"   ⚠️ WARNING: SQL creates NULL columns: {null_columns}")
            print(f"   ⚠️ This will result in empty data! The LLM should JOIN to actual tables instead.")
        
        # Check for direct column references that might not exist
        # Look for standalone words that look like column names (not functions, not keywords)
        potential_cols = re.findall(r'\b([a-z_][a-z0-9_]*)\b', select_clause.lower())
        
        sql_keywords = {'select', 'from', 'where', 'join', 'inner', 'left', 'right', 'outer', 
                       'on', 'and', 'or', 'as', 'case', 'when', 'then', 'else', 'end',
                       'sum', 'avg', 'count', 'max', 'min', 'group', 'by', 'order',
                       'null', 'top', 'distinct', 'having'}
        
        suspicious_cols = [col for col in potential_cols 
                          if col not in sql_keywords 
                          and col not in available_columns
                          and len(col) > 2  # Ignore aliases like 'd', 'fs'
                          and not col.startswith('q')  # Ignore Q1, Q2 string literals
                          and col not in ['january', 'february', 'march', 'april', 'may', 'june',
                                         'july', 'august', 'september', 'october', 'november', 'december']]
        
        if suspicious_cols:
            print(f"   ⚠️ WARNING: SQL may reference non-existent columns: {set(suspicious_cols)}")
            print(f"   ⚠️ Available columns: {sorted(list(available_columns))[:20]}...")

def generate_sql_for_step(groq_client, step_description, knowledge_base, previous_results=None):
    """
    A single, robust API call to a "Senior SQL Developer" agent.
    Now with context awareness - can reference results from previous steps.
    
    Args:
        previous_results: Dict with format {"step_1": {"description": "...", "summary": "Average was $5,243", "key_values": {...}}}
    """
    from datetime import datetime
    
    # OPTIMIZATION: Only send relevant tables to reduce token usage by 70%
    relevant_schema = identify_relevant_tables(step_description, knowledge_base['raw_schema'])
    
    # DEBUG: Show which tables are being sent
    print(f"   📋 Tables being sent to SQL generator: {list(relevant_schema.keys())}")
    for table_name, table_details in relevant_schema.items():
        if isinstance(table_details, dict) and 'columns' in table_details:
            col_names = [col['COLUMN_NAME'] for col in table_details['columns']]
            print(f"      - {table_name}: {len(col_names)} columns - {col_names[:10]}{'...' if len(col_names) > 10 else ''}")
    
    # OPTIMIZATION: Only send relationships for the relevant tables
    relevant_relationships = filter_relevant_relationships(relevant_schema, knowledge_base.get('relationships', []))
    print(f"   🔗 Relationship Filter: Sending {len(relevant_relationships)} foreign keys (down from {len(knowledge_base.get('relationships', []))})")
    
    # OPTIMIZATION: Extract sample rows for relevant tables (especially DimDate)
    # This helps LLM understand actual data format and column usage
    sample_rows = {}
    full_knowledge = knowledge_base.get('raw_schema', {})
    for table_name in relevant_schema.keys():
        if table_name in full_knowledge:
            table_data = full_knowledge[table_name]
            # Check if sample_rows exist in the knowledge base
            if isinstance(table_data, dict) and 'sample_rows' in table_data:
                # Take first 3 sample rows
                sample_rows[table_name] = table_data['sample_rows'][:3]
    
    if sample_rows:
        print(f"   📊 Sample rows available for: {list(sample_rows.keys())}")
    
    # Build context section from previous results (silent mode - no verbose logging)
    context_section = ""
    if previous_results and len(previous_results) > 0:
        context_section = "\n**RESULTS FROM PREVIOUS STEPS (for reference):**\n---\n"
        for step_key, result_info in previous_results.items():
            context_section += f"{step_key.upper()}: {result_info.get('description', 'N/A')}\n"
            
            # Include summary statistics or key values
            if 'summary' in result_info:
                context_section += f"   Result: {result_info['summary']}\n"
            
            # Include specific key values that might be referenced
            if 'key_values' in result_info:
                for key, value in result_info['key_values'].items():
                    context_section += f"   - {key}: {value}\n"
            context_section += "\n"
        context_section += "---\n"
        context_section += "**IMPORTANT:** If the current task references 'the average', 'the threshold', or 'the values from step X', use the actual numbers provided above and hardcode them into your SQL query.\n\n"
    
    # Build sample rows section if available
    sample_rows_section = ""
    if sample_rows:
        sample_rows_section = "\n**SAMPLE DATA (First 3 rows from each table):**\n---\n"
        for table_name, rows in sample_rows.items():
            sample_rows_section += f"{table_name}:\n"
            sample_rows_section += json.dumps(rows, indent=2, default=str)
            sample_rows_section += "\n\n"
        sample_rows_section += "---\n"
        sample_rows_section += "**NOTE:** Use these samples to understand column values. For example, CalendarQuarter contains 1/2/3/4, not 'Q1'/'Q2'.\n\n"
    
    # Build compact schema (just column names to save tokens)
    compact_schema = {}
    for table_name, table_data in relevant_schema.items():
        if isinstance(table_data, dict) and 'raw_columns' in table_data:
            compact_schema[table_name] = list(table_data['raw_columns'].keys())
        elif isinstance(table_data, dict):
            compact_schema[table_name] = list(table_data.keys())
        else:
            compact_schema[table_name] = []
    
    # Temporal context for date interpretation
    current_date = datetime.now().strftime('%B %d, %Y')
    temporal_note = f"""
**TEMPORAL CONTEXT:**
- Today: {current_date}
- Database Coverage: 2020-2024 ONLY
- \"This year\" = 2024, \"Last year\" = 2023, \"Recent/Latest\" = 2024

"""
    
    # The prompt is simplified to send only the latest request, no history.
    sql_contents = [{"role": "user", "content": f"""
{temporal_note}**DATABASE SCHEMA FOR REFERENCE (Relevant Tables Only):**
---
{json.dumps(relevant_schema, indent=2)}
---

**TABLE RELATIONSHIPS (FOREIGN KEYS - Relevant Only):**
---
{json.dumps(relevant_relationships, indent=2)}
---

{context_section} **TASK:**
Write the complete, self-contained T-SQL query for the following analytical step: "{step_description}"
*IMPORTANT*: Ensure all table and column names are 100% accurate based on the provided schema. Use the foreign key relationships to properly JOIN tables.
"""}]
    
    sql_system_prompt = """
You are a meticulous, expert and intelligent T-SQL developer for Microsoft SQL Server. Your task is to write a single, executable SQL query to accomplish the user's request based on the provided database schema.

**CRITICAL RULES:**
1.  **ONLY output the raw SQL query.** Do NOT include any explanations or Markdown.
2.  **Accuracy is Paramount:** Use the provided raw schema to ensure all table and column names are 100% accurate. Do NOT invent or assume any table or column names that are not present in the schema.
3.  **Write Robust Queries:** For any division operation, you MUST prevent 'divide by zero' errors using `NULLIF(denominator, 0)`.
4.  **Syntax Must Be Flawless:** The query must be a complete, single, executable T-SQL statement.
5.  **NO SHORTCUTS:** You MUST derive all results directly from the base tables provided in the schema using `JOIN`s and aggregations. 
    **You are strictly forbidden from inventing or referencing summary tables or views that are not in the schema** (e.g., `CategorySales`, `MonthlySales`, `RankedItems` are FORBIDDEN). Every table you query must be present in the provided schema.    
6. **NEVER SELECT SURROGATE KEYS FOR CHARTS - CRITICAL RULE:**
   ❌ **NEVER** use columns ending in 'Key' (GeographyKey, ProductKey, CustomerKey, StoreKey, etc.) in SELECT clause for grouping/charting
   ✅ **ALWAYS** use descriptive columns instead:
      - GeographyKey → Use CountryRegionName, StateProvinceName, or CityName from DimGeography
      - ProductKey → Use ProductName from DimProduct
      - CustomerKey → Use CustomerName from DimCustomer
      - CategoryKey → Use CategoryName from DimProductCategory
      - StoreKey → Use StoreName from DimStore
   
   **Example - WRONG:**
   SELECT GeographyKey, SUM(TotalSales) FROM FactSales GROUP BY GeographyKey
   
   **Example - CORRECT:**
   SELECT g.CountryRegionName, SUM(fs.TotalSales) 
   FROM FactSales fs 
   JOIN DimGeography g ON fs.GeographyKey = g.GeographyKey 
   GROUP BY g.CountryRegionName

7. TIME-SERIES LABELLING: 
   - NEVER use raw numeric keys like '200801' or '20081' for chart axes.
   - For Quarters: Use CASE to create 'Q1', 'Q2', 'Q3', 'Q4'
   - For Months: Use "FORMAT(DateKey, 'MMM yyyy')" or "DATENAME(month, DateKey)"

8. Syntax Check: Ensure every aliased subquery is preceded by a comma. Verify parentheses are balanced.


**OUTPUT RULES:**
❗ Filter NULLs: WHERE [Column] IS NOT NULL on key columns
❗ Limit large results: Use TOP 5000 if query returns >10K rows
❗ JOIN dimension tables to get readable names (ProductName, CountryName, etc.) - NEVER output raw Keys!

**FORBIDDEN - DO NOT USE:**
❌ Subqueries in FROM clause
❌ NULL AS ColumnName (creates fake columns with no data)
❌ Surrogate key columns (GeographyKey, ProductKey, etc.) in SELECT for charts
❌ Column names not in the schema

Now analyze the schema provided, plan your query following the rules above, then output ONLY the SQL.
"""

    sql_query_raw = call_llm(
        client=groq_client, model_name=MODEL_NAME, contents=sql_contents,
        system_instruction=sql_system_prompt, step_name="SQL Generation",
        temperature=0.0, timeout=SQL_GENERATION_TIMEOUT  # Use longer timeout for SQL
    )
    
    if not sql_query_raw:
        print("   - ❗ LLM failed to generate a SQL script for this step.")
        return ""
    
    cleaned_sql = clean_sql_script(sql_query_raw)
    
    # DEBUG: Show the generated SQL query
    print(f"   📝 Generated SQL Query:")
    print(f"   {'-'*60}")
    sql_lines = cleaned_sql.split('\n')
    for line in sql_lines[:30]:  # Show first 30 lines
        print(f"   {line}")
    if len(sql_lines) > 30:
        remaining = len(sql_lines) - 30
        print(f"   ... ({remaining} more lines)")
    print(f"   {'-'*60}")
    
    # VALIDATION: Check if SQL references columns that actually exist
    validate_sql_columns(cleaned_sql, relevant_schema)
    
    # Quick validation: Check if query references tables that exist in schema
    available_tables = list(knowledge_base['raw_schema'].keys())
    for table in available_tables:
        # This is a basic check - just warn, don't block
        pass  # We'll let the database validation catch issues
    
    return cleaned_sql
def execute_sql_query(groq_client, knowledge_base, sql_query, step_description):
    """
    Connects to the SQL Server database and executes a query. If it fails, it asks
    an AI debugger for a fix and retries once.
    """
    if not sql_query:
        print(f"   - ❗ Skipping execution for '{step_description}': No SQL query was generated.")
        return None

    for attempt in range(2):
        cnxn = None
        try:
            if attempt > 0:
                print("   - 🛠️ Attempting to execute the DEBUGGED SQL query...")
            else:
                print("   - 🛠️ Executing generated SQL query...")

            cnxn = pyodbc.connect(CONNECTION_STRING)
            df = pd.read_sql_query(sql_query, cnxn)
            print("   - ✅ Query executed successfully.")
            
            # Check for NULL-only columns
            null_columns = [col for col in df.columns if df[col].isnull().all()]
            if null_columns:
                print(f"   ⚠️ WARNING: Query returned columns with ALL NULL values: {null_columns}")
                print(f"   💡 This usually means a JOIN failed or columns don't exist in the source table.")
            
            # If ALL columns are NULL, treat it as a failed query
            if len(null_columns) == len(df.columns):
                print(f"   ❌ All columns contain only NULL values. Treating as query failure.")
                return None
            
            return df  # Return the DataFrame on success
            
        except Exception as ex:
            print(f"   - ❌ DATABASE-RELATED ERROR on attempt {attempt + 1}.")
            
            if attempt == 1:
                print("   - ❌ Debugged query also failed. Aborting step.")
                print(f"   - Final Error: {ex}")
                return None

            # --- SELF-HEALING STEP ---
            print("   - 🤖 Sending error to AI Debugger for a fix...")
            error_message = str(ex)
            
            # OPTIMIZATION: Use filtered schema to reduce debugging tokens
            relevant_schema_for_debug = identify_relevant_tables(step_description, knowledge_base['raw_schema'])
            
            debug_system_prompt = """
You are a SQL debugging expert for Microsoft SQL Server. Your task is to analyze a failed SQL query and fix it using ONLY the tables and columns that exist in the schema.

**CRITICAL DEBUGGING RULES:**
1.  **Check for Hallucinated Tables:** If the error is "Invalid object name 'TableName'", the original query referenced a table that doesn't exist. You MUST rewrite the query using only tables from the schema.
2.  **Check for Wrong Columns:** If the error is "Invalid column name 'ColumnName'", look up the ACTUAL column names in the schema for that table.
3.  **NO CTEs OR SUBQUERIES:** If the failed query used WITH clauses, CTEs, or subqueries in FROM clauses, rewrite it as a single flat SELECT statement.
4.  **SYNTAX ERRORS:** If you see "Incorrect syntax near ')'" or similar, the query has unbalanced parentheses. Remove ALL subqueries and write a simple SELECT with JOINs only.
5.  **Verify Every Name:** Before using any table or column name, verify it exists in the schema below.
6.  **Output ONLY the corrected SQL query** - no explanations, no markdown.

**COMMON ERROR PATTERNS:**

Error Type 1: "Invalid object name 'YoYChange'" or "Invalid object name 'GrowthRate'"
- **Cause:** Query referenced a computed table that doesn't exist
- **Fix:** Rewrite using base tables with JOINs and aggregations

Error Type 2: "Invalid column name 'CustomerKey'" in FactSales
- **Cause:** Wrong column name (FactSales uses CustomerKey or CustomerSK?)
- **Fix:** Check the schema and use the EXACT column name

Error Type 3: "Incorrect syntax near ')'"
- **Cause:** Unbalanced parentheses from malformed subquery
- **Fix:** REMOVE ALL SUBQUERIES. Write as: SELECT ... FROM table1 JOIN table2 ON ... WHERE ... GROUP BY ...

Error Type 4: Duplicate FROM/JOIN clauses
- **Cause:** Syntax error from malformed query
- **Fix:** Reconstruct with proper structure: SELECT ... FROM ... JOIN ... WHERE ... GROUP BY ...

**YOUR TASK:**
Analyze the failed query and error, then write a corrected query using ONLY tables/columns from the schema.
"""

            
            debug_prompt = f"""
**USER'S ORIGINAL GOAL:** "{step_description}"

**DATABASE SCHEMA FOR REFERENCE (Relevant Tables):**
---
{json.dumps(relevant_schema_for_debug, indent=2)}
---
**FAILED SQL QUERY:**
{sql_query}

DATABASE ERROR MESSAGE:
"{error_message}"

Please provide the corrected SQL query only without any explanations.
"""
            # The debugger is a one-off request, not a chat
            debug_contents = [{"role": "user", "content": debug_prompt}]
            
            corrected_sql_raw = call_llm(
                client=groq_client, 
                model_name=MODEL_NAME, 
                contents=debug_contents,
                system_instruction=debug_system_prompt, 
                step_name="SQL Debugging",
                temperature=0.0
            )
        
            if not corrected_sql_raw:
                print("   - ❌ AI Debugger failed to provide a fix. Aborting step.")
                return None

            sql_query = clean_sql_script(corrected_sql_raw)
            print("   - 💡 AI Debugger provided a potential fix. Retrying...")

        finally:
            if cnxn:
                cnxn.close()

    return None
# =======================================================
# STEP 3: Dashboard & Report Generation
# =======================================================
def repair_json_string(json_string):
    """
    A simple but effective function to fix common LLM JSON errors.
    (This remains the same)
    """
    repaired = re.sub(r'(?<!\\)\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', json_string)
    repaired = repaired.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
    return repaired

def clean_and_extract_json(text):
    """
    Extracts a JSON object from a string that might contain markdown or extra text.
    """
    if not text: return None
    
    # 1. Try to find content between ```json and ```
    match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        return match.group(1)
        
    # 2. If no markdown, try to find the first '{' and last '}'
    match = re.search(r'(\{.*\})', text, re.DOTALL)
    if match:
        return match.group(1)
        
    # 3. Return original text if no brackets found (likely will fail parsing, but worth a shot)
    return text

def generate_visualization_config(groq_client, step_description, data_frame):
    """
    Uses JSON mode and a precise prompt to enforce structure.
    """
    if data_frame is None or data_frame.empty:
        return None

    # --- PART 1: Generate the Business Insight ---
    print("   - Generating key insight from data...")
    column_names = list(data_frame.columns)
    data_shape = data_frame.shape
    numeric_summary = data_frame.describe().to_string()
    categorical_summary = data_frame.describe(include=['object']).to_string() if not data_frame.select_dtypes(include=['object']).empty else ""

    insight_system_prompt = "You are a highly experienced Senior Executive Data Analyst. Your task is to analyze a dataset and its statistical summary, then write a compelling, structured, and data-driven insight for a business executive. You must follow the user's rules exactly."
    
    insight_prompt = f"""
**Business Goal:** "{step_description}"

**Data Summary & Shape:**
- The data has {data_shape[0]} rows and {data_shape[1]} columns: {column_names}
**Data Frame:**
{data_frame}
**Statistical Summary of NUMERIC data:**
{numeric_summary}
**Statistical Summary of CATEGORICAL data:**
{categorical_summary}

Based on the summaries above, what is the most important business insight a manager could learn?

**CRITICAL RULES FOR INSIGHT GENERATION:**
1.  **Lead with Impact:** Start with the most important finding, **bolded using Markdown (`**...**`)**, then support it with specific numbers from the data (e.g., "**Bikes dominate revenue at $28.3M** - 65% higher than the next category").
2.  **Supporting Statistics:** In the next sentence, provide key statistics from the data summary to support your headline. Mention the average, total, max, or key categorical counts. (e.g., "The category generated a total of $28.3M in sales, with an average transaction value significantly higher than any other category.")
3.  **Be Actionable:** Identify extremes, anomalies, or trends that suggest a business action (e.g., "Q4 shows a 30% spike - consider increasing inventory for this period").
4.  **Stay Concise:** Write 5-6 sentences maximum. No jargons and if using any acronyms make sure to explain them.

**FORMAT:** Single paragraph, no headers or tags.
"""
    insight_contents = [{"role": "user", "content": insight_prompt}]

    key_insight = call_llm(
        client=groq_client, model_name=FAST_MODEL_NAME, contents=insight_contents,
        system_instruction=insight_system_prompt, step_name="Insight Generation",
        temperature=0.2
    )
    key_insight = key_insight if key_insight else "No specific insight could be derived from the data summary."
    
    # Clean up the insight text to prevent markdown rendering issues
    key_insight = ' '.join(key_insight.split())  # Normalize whitespace
    key_insight = re.sub(r'\*\*([^*]+)\*\*', r'**\1**', key_insight)  # Fix broken bold markers
    
    print(f"   - Insight: \"{key_insight}\"")

    # --- PART 2: Generate the Chart Configuration using the Insight (JSON Mode) ---
    print("   - Generating visualization config based on insight...")
    
    df_head_str = data_frame.head(5).to_string()

    config_system_prompt = "You are a Data Visualization Expert. Your task is to choose the best chart configuration to visually represent the business insight. You MUST return a single, clean JSON object that strictly adheres to the requested schema. Do not output any explanation or markdown wrappers."
    
    json_schema_definition = """
    {
        "chart_type": "string",  // Choose: 'bar', 'line', 'pie', 'scatter', 'heatmap', 'treemap', 'histogram', 'box', 'combo', 'table', 'kpi'
        "title": "string",        // Clear, professional chart title
        "x_axis": "string",       // Column for X-axis (bar, line, scatter, histogram, box, heatmap, combo)
        "y_axis": "string",       // Column for Y-axis (bar, line, scatter, box, heatmap) OR primary metric for combo
        "y_axis_secondary": "string", // COMBO ONLY: Secondary metric for right Y-axis (usually a percentage/ratio)
        "z_axis_color": "string", // Column for heatmap color values
        "color_column": "string", // Column for color segmentation (bar, line, scatter) - creates legend
        "path_column": "string or list",  // Hierarchy columns for treemap (e.g., ["Category", "Subcategory"])
        "values_column": "string", // Numeric values for pie/treemap
        "names_column": "string",  // Category names for pie charts
        "show_legend": "boolean",  // Display legend (default: true if color/names used)
        "options": {               // OPTIONAL: Advanced Plotly parameters
            "barmode": "group|stack",      // For bar charts: group bars side-by-side or stack them
            "orientation": "v|h",          // 'v' for vertical (default), 'h' for horizontal bars
            "color_discrete_sequence": ["#color1", "#color2"]  // Custom color palette
        }
    }
    // REQUIRED: chart_type, title. All column names must match available columns exactly.
    """
    
    config_prompt = f"""
**SCHEMA:**
{json_schema_definition}

**Context:**
- Business Insight: "{key_insight}"
- Analysis Goal: "{step_description}"
- Available Columns: {column_names}
- Data Preview:
{df_head_str}

**Instructions:**
You are a data visualization expert. Choose the SINGLE BEST chart type and configuration to communicate the insight.

**Chart Selection Guidelines:**
- **kpi**: Only for single-cell numeric data (1 row × 1 column)
- **line**: Time-series trends (dates, months, years on x-axis)
- **bar**: Category comparisons (e.g., Sales by Product, Revenue by Region)
- **combo**: Dual-axis chart showing bars + line together (e.g., Revenue as bars + Profit% as line)
- **pie**: Proportions of a whole (< 6 categories); use `names_column` + `values_column`
- **scatter**: Correlation between two numeric variables
- **treemap**: Hierarchical data (use `path_column` as list)
- **histogram/box**: Distribution of single numeric variable
- **table**: Fallback for complex/unsuitable data

**🎨 CRITICAL - ALWAYS Use Color:**
1. Bar/Line/Scatter charts:
   - If categorical columns exist (Product, Region, Category, StoreType, etc.) → MUST set `color_column` to one of them
   - If no categorical, but multiple numeric → set `color_column` to X-axis column
   - Example: {{"chart_type": "bar", "x_axis": "StoreType", "y_axis": "TotalSales", "color_column": "StoreType", "show_legend": true}}

2. Pie charts:
   - `names_column` = categorical column (e.g., "StoreType", "Product")
   - `values_column` = NUMERIC column (e.g., "TotalSales", "Quantity") - NEVER use same column for both!
   - ALWAYS set `show_legend: true`
   - Example: {{"chart_type": "pie", "names_column": "StoreType", "values_column": "TotalSales", "show_legend": true}}

3. Treemap:
   - `path_column` = list of hierarchy columns ["Category", "Subcategory"]
   - `values_column` = NUMERIC column for sizing

**Advanced Options (optional):**
- Grouped bars: `"options": {{"barmode": "group"}}`
- Stacked bars: `"options": {{"barmode": "stack"}}`
- Horizontal bars: `"options": {{"orientation": "h"}}`
- Custom colors: `"options": {{"color_discrete_sequence": ["#FF6B6B", "#4ECDC4", "#45B7D1"]}}`

**Validation Checklist:**
✓ All column names match {column_names} exactly (case-sensitive)
✓ Pie/treemap: `values_column` is NUMERIC (check data preview)
✓ Used `color_column` or `names_column` for visual variety
✓ Set `show_legend: true` when using color

Return ONLY the JSON configuration.
"""
    config_contents = [{"role": "user", "content": config_prompt}]
    
    raw_json_text = None
    try:
        raw_json_text = call_llm(
            client=groq_client, model_name=FAST_MODEL_NAME, contents=config_contents,
            system_instruction=config_system_prompt, step_name="Visualization Config Generation",
            temperature=0.1, json_mode=True 
        )

        if not raw_json_text: return None

        # 1. Clean the text using the helper
        cleaned_json_text = clean_and_extract_json(raw_json_text)
    
        # Pass the pre-generated insight into the final config object
        final_config = json.loads(cleaned_json_text)
        final_config['insight'] = key_insight 
        return final_config
    except json.JSONDecodeError as e:
        print(f"   - ❌ JSON DECODE ERROR: {e}")
        print(f"   - 🔍 RAW OUTPUT WAS:\n{raw_json_text}\n")
        try:
            repaired_text = repair_json_string(cleaned_json_text)
            final_config = json.loads(repaired_text)
            final_config['insight'] = key_insight
            return final_config
        except Exception as repair_error:
            print(f"   - 💀 Repair failed: {e}")
            return None
    except Exception as e:
        print(f"   - ❗ An unexpected error occurred: {e}")
        return None

def create_figure_from_config(config, data_frame):
    """
    Plotly factory remains the same as it is client-agnostic.
    """
    chart_type = config.get("chart_type", "table").lower()
    title = config.get("title", "Analysis Result")

    if data_frame.shape == (1, 1):
        value = data_frame.iloc[0, 0]
        # Ensure the value is a number before creating the indicator
        if pd.api.types.is_number(value):
            fig = go.Figure(go.Indicator(mode="number", value=value, title={"text": title}))
            return fig
        else:
            # If the single cell is not a number, fall back to a table
            print(f"   - ❗ Warning: Data has a single cell but it is not numeric ('{value}'). Falling back to table.")
            chart_type = 'table' # Force fallback to table

    # Handle simple cases first
    if chart_type == 'kpi':
        # KPI is valid if: single row OR single cell with numeric value
        if data_frame.shape[0] == 1:
            # Single row - find the numeric column for KPI display
            numeric_cols = data_frame.select_dtypes(include=['number']).columns.tolist()
            if not numeric_cols:
                print(f"   - ❗ Warning: KPI requires numeric data but none found. Falling back to table.")
                chart_type = 'table'
        elif data_frame.shape != (1, 1):
            print(f"   - ❗ Warning: KPI requires single row or single cell, got {data_frame.shape}. Falling back to table.")
            chart_type = 'table'

    if chart_type == 'table':
        header = dict(values=list(data_frame.columns), fill_color='paleturquoise', align='left')
        cells = dict(values=[data_frame[col] for col in data_frame.columns], fill_color='lavender', align='left')
        fig = go.Figure(data=[go.Table(header=header, cells=cells)])
        fig.update_layout(title_text=title)
        return fig

    # ✅ PRE-VALIDATION: Check config before calling Plotly
    def validate_config(config, df, chart_type):
        """Validate config and return corrected version or raise error."""
        # Rule 1: Pie charts need numeric values_column
        if chart_type == 'pie':
            values_col = config.get('values_column')
            names_col = config.get('names_column')
            if not values_col or not names_col:
                raise ValueError(f"Pie chart requires both 'names_column' and 'values_column'. Got: {config}")
            if values_col not in df.columns:
                raise ValueError(f"Column '{values_col}' not found in dataframe. Available: {list(df.columns)}")
            if not pd.api.types.is_numeric_dtype(df[values_col]):
                # Auto-fix: Find first numeric column
                numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
                if numeric_cols:
                    print(f"   - ⚠️  '{values_col}' is not numeric. Auto-correcting to '{numeric_cols[0]}'")
                    config['values_column'] = numeric_cols[0]
                else:
                    raise ValueError(f"Pie chart needs numeric values but '{values_col}' is {df[values_col].dtype}. No numeric columns found!")
        
        # Rule 2: All referenced columns must exist
        col_keys = ['x_axis', 'y_axis', 'color_column', 'values_column', 'names_column', 'z_axis_color']
        for key in col_keys:
            col = config.get(key)
            if col and isinstance(col, str) and col not in df.columns:
                print(f"   - ⚠️  Column '{col}' from '{key}' not found. Removing from config.")
                config[key] = None
        
        return config
    
    # Validate before proceeding
    config = validate_config(config, data_frame, chart_type)

    # Handle complex, multi-dimensional charts dynamically
    try:
        plotly_args = {}
        # Map our config keys to Plotly's expected argument names
        arg_map = {
            'x_axis': 'x', 'y_axis': 'y', 'z_axis_color': 'color',
            'color_column': 'color', 'size_column': 'size',
            'path_column': 'path', 'values_column': 'values',
            'names_column': 'names'
        }
        
        # Define valid arguments for each chart type
        valid_args_by_chart = {
            'bar': ['x', 'y', 'color', 'text_auto', 'barmode', 'orientation'],
            'line': ['x', 'y', 'color'],
            'scatter': ['x', 'y', 'color', 'size'],
            'pie': ['values', 'names'],  # Pie charts don't use 'color' parameter
            'treemap': ['path', 'values', 'color', 'text_auto'],
            'histogram': ['x', 'color', 'barmode'],
            'box': ['x', 'y', 'color'],
            'heatmap': ['x', 'y', 'color'],  # Special handling below
            'combo': ['x', 'y']  # Combo uses Graph Objects, not Express
        }
            
        for config_key, plotly_key in arg_map.items():
            value = config.get(config_key)
            if value:
                # Skip if this argument is not valid for the current chart type
                if chart_type in valid_args_by_chart and plotly_key not in valid_args_by_chart[chart_type]:
                    continue
                    
                # Handle path column which can be a list (from JSON string representation)
                if config_key == 'path_column' and isinstance(value, str):
                    # Attempt to parse a list string if the model outputted it as such
                    try:
                        value = json.loads(value.replace("'", '"'))
                    except:
                        pass # keep as string if parsing fails
                        
                # Validate column exists in dataframe
                if isinstance(value, list) and all(v in data_frame.columns for v in value):
                    plotly_args[plotly_key] = value
                elif isinstance(value, str) and value in data_frame.columns:
                    plotly_args[plotly_key] = value 
                elif isinstance(value, str) and value.lower() in ['group', 'stack']:
                    plotly_args[plotly_key] = value

        # Only add text_auto for chart types that support it
        if chart_type in ['bar', 'treemap']:
            plotly_args['text_auto'] = True
        
        # ✅ FIX: Remove color when it duplicates x-axis (creates N traces with 1 point each = invisible)
        if 'color' in plotly_args and 'x' in plotly_args:
            if plotly_args['color'] == plotly_args['x']:
                print(f"   - ⚠️  Removing color='{plotly_args['color']}' (same as x-axis, creates invisible single-bar traces)")
                del plotly_args['color']
        
        # Extract advanced options from config
        options = config.get('options', {})
        if options:
            # Add barmode for bar/histogram charts
            if 'barmode' in options and chart_type in ['bar', 'histogram']:
                plotly_args['barmode'] = options['barmode']
            # REMOVED: orientation - it causes more problems than it solves
            # Vertical bars work fine with x=categorical, y=numeric
            # if 'orientation' in options and chart_type == 'bar':
            #     plotly_args['orientation'] = options['orientation']
            # Add custom color sequence
            if 'color_discrete_sequence' in options:
                plotly_args['color_discrete_sequence'] = options['color_discrete_sequence']
        
        print(f"   - Creating {chart_type} chart with args: {plotly_args}")
        print(f"   - DataFrame shape: {data_frame.shape}, columns: {list(data_frame.columns)}")
        if chart_type == 'bar' and 'x' in plotly_args and 'y' in plotly_args:
            x_col = plotly_args['x']
            y_col = plotly_args['y']
            print(f"   - X-axis '{x_col}': dtype={data_frame[x_col].dtype}, unique={data_frame[x_col].nunique()}, sample={data_frame[x_col].head(3).tolist()}")
            print(f"   - Y-axis '{y_col}': dtype={data_frame[y_col].dtype}, range=[{data_frame[y_col].min()}, {data_frame[y_col].max()}], sample={data_frame[y_col].head(3).tolist()}")
        
        if chart_type == 'kpi':
            # KPI Card - show single numeric value prominently
            # Find the numeric column to display
            numeric_cols = data_frame.select_dtypes(include=['number']).columns.tolist()
            if numeric_cols:
                kpi_value = data_frame[numeric_cols[0]].iloc[0]
                # Get the label (usually the other column or use column name)
                label_cols = [col for col in data_frame.columns if col not in numeric_cols]
                kpi_label = data_frame[label_cols[0]].iloc[0] if label_cols else numeric_cols[0]
                
                fig = go.Figure(go.Indicator(
                    mode="number",
                    value=kpi_value,
                    title={'text': f"{kpi_label}<br><span style='font-size:0.6em'>{title}</span>"},
                    number={'valueformat': ',.2f' if kpi_value < 100 else ',.0f'},
                    domain={'x': [0, 1], 'y': [0, 1]}
                ))
                fig.update_layout(height=300)
            else:
                raise ValueError("KPI requires at least one numeric column")
        elif chart_type == 'bar':
            fig = px.bar(data_frame, **plotly_args)
        elif chart_type == 'line':
            fig = px.line(data_frame, **plotly_args)
        elif chart_type == 'scatter':
            fig = px.scatter(data_frame, **plotly_args)
        elif chart_type == 'pie':
            fig = px.pie(data_frame, **plotly_args)
        elif chart_type == 'histogram':
            fig = px.histogram(data_frame, **plotly_args)
        elif chart_type == 'box':
            fig = px.box(data_frame, **plotly_args)
        elif chart_type == 'treemap':
            fig = px.treemap(data_frame, **plotly_args)
        elif chart_type == 'heatmap':
            index_col = config.get('y_axis')
            cols_col = config.get('x_axis')
            vals_col = config.get('z_axis_color')
            if index_col and cols_col and vals_col:
                pivot_df = data_frame.pivot(index=index_col, columns=cols_col, values=vals_col)
                fig = px.imshow(pivot_df, text_auto=True)
            else:
                raise ValueError("Heatmap requires x_axis, y_axis, and z_axis_color to be defined.")
        elif chart_type == 'combo':
            # Combo chart: Bars (left axis) + Line (right axis)
            x_col = config.get('x_axis')
            y_primary = config.get('y_axis')  # Bars
            y_secondary = config.get('y_axis_secondary')  # Line
            
            if not x_col or not y_primary or not y_secondary:
                raise ValueError(f"Combo chart requires x_axis, y_axis, and y_axis_secondary. Got: {config}")
            
            # Create figure with Graph Objects
            fig = go.Figure()
            
            # Add bars (primary metric, left axis)
            fig.add_trace(go.Bar(
                x=data_frame[x_col],
                y=data_frame[y_primary],
                name=y_primary,
                marker_color='#4ECDC4',
                yaxis='y'
            ))
            
            # Add line (secondary metric, right axis)
            fig.add_trace(go.Scatter(
                x=data_frame[x_col],
                y=data_frame[y_secondary],
                name=y_secondary,
                mode='lines+markers',
                line=dict(color='#FF6B6B', width=3),
                marker=dict(size=8),
                yaxis='y2'
            ))
            
            # Configure dual axes
            fig.update_layout(
                yaxis=dict(title=y_primary, side='left'),
                yaxis2=dict(title=y_secondary, overlaying='y', side='right'),
                hovermode='x unified'
            )
        else:
            raise ValueError(f"Unknown chart type: {chart_type}")
        
        # Apply styling based on chart type
        if chart_type == 'line':
            # For line charts, make lines visible and bold
            if 'color' not in plotly_args:
                fig.update_traces(line=dict(color='#4ECDC4', width=3))
            else:
                fig.update_traces(line=dict(width=3))
        elif chart_type in ['bar', 'scatter']:
            if 'color' not in plotly_args:
                fig.update_traces(marker_color='#4ECDC4')
        
        # Chart-specific text positioning
        if chart_type == 'pie':
            fig.update_traces(textposition='inside', textinfo='percent+label')
        elif chart_type == 'bar':
            fig.update_traces(textposition='outside')

        # Determine if legend should be shown - DEFAULT TO TRUE for better charts
        # Pie charts: Always show legend (uses names for colors)
        # Other charts: Show legend if color column set OR if multiple traces
        if chart_type == 'pie':
            show_legend = config.get('show_legend', True)  # Always show for pie
        else:
            show_legend = config.get('show_legend', 'color' in plotly_args or len(fig.data) > 1)
        
        # ✅ FIX: Clean up year/date axes (prevent 2020.5, 2021.5 tick marks)
        x_col = (config.get('x_axis') or '').lower()
        y_col = (config.get('y_axis') or '').lower()
        # Check for common year/date column names
        year_keywords = ['year', 'calendar', 'fiscal', 'date', 'month', 'quarter']
        if x_col and any(keyword in x_col for keyword in year_keywords):
            fig.update_xaxes(dtick=1)  # Force integer ticks
        if y_col and any(keyword in y_col for keyword in year_keywords):
            fig.update_yaxes(dtick=1)  # Force integer ticks
        
        fig.update_layout(
            title_text=title, 
            template="plotly_white",
            showlegend=show_legend,
            # Better color scheme for charts
            colorway=['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A', '#98D8C8', '#F7DC6F', '#BB8FCE']
        )
        return fig

    except Exception as e:
        print(f"   - ❗ Could not create dynamic chart '{title}' due to error: {e}. Falling back to a table.")
        header = dict(values=list(data_frame.columns), fill_color='paleturquoise', align='left')
        cells = dict(values=[data_frame[col] for col in data_frame.columns], fill_color='lavender', align='left')
        fig = go.Figure(data=[go.Table(header=header, cells=cells)])
        fig.update_layout(title_text=title)
        return fig

def classify_edit_request(groq_client, edit_request, original_step):
    """Classifies an edit request as either a 'visualization_change' or a 'data_change'."""
    system_prompt = """
You are an AI classifier. Your task is to determine if a user's chart edit request requires new data from the database, or if it's just a change to the existing chart's appearance.

You MUST respond with ONLY one of the following two labels and nothing else:
- visualization_change
- data_change

- Use 'visualization_change' if the user wants to change the chart type, title, colors, or axes using the data that is already present. (e.g., "show as a bar chart", "make the title bigger", "use country for the color", "only show the top 5 from the current data").
- Use 'data_change' if the user is asking to filter, group, or calculate the data differently, which requires a new SQL query. (e.g., "filter for 2008 only", "show this by country instead of category", "calculate the average instead of the sum").

Respond now with only one label. Don't respond safe.
"""
    prompt = f"Original Task: '{original_step}'\nUser's Edit Request: '{edit_request}'"
    contents = [{"role": "user", "content": prompt}]

    # You can use a faster, cheaper model for this simple classification task
    classification = call_llm( 
        client=groq_client, model_name=FAST_MODEL_NAME, 
        contents=contents, system_instruction=system_prompt,
        step_name="Edit Request Classification", temperature=0.0,
        timeout=DEFAULT_TIMEOUT
    )
    cleaned_classification = classification.strip().lower()

        # Check if the output is valid
    if cleaned_classification in ['visualization_change', 'data_change']:
        return cleaned_classification # It worked, return the result
        
        # If it failed, update the prompt to scold the AI and try again
    print(f"   - ⚠️ Classifier returned invalid label: '{cleaned_classification}'. Retrying with corrective prompt...")
    prompt = f"Your previous response was incorrect. You MUST respond with either 'visualization_change' or 'data_change'.\n\nOriginal Task: '{original_step}'\nUser's Edit Request: '{edit_request}'"

    # If it fails even after the retry, default to the safest option.
    print("   - ❌ Classifier failed after retry. Defaulting to 'visualization_change'.")
    return 'visualization_change'

def generate_consolidated_summary(groq_client, business_plan, final_results_recipe, user_question=""):
    """
    Takes all the individual insights from the report recipe and generates a single,
    high-level executive summary that tells a cohesive story.
    
    Args:
        user_question: The original user's question(s) to provide context for the summary
    """
    print("   - ✍️ Synthesizing individual insights into a final narrative...")

    # 1. Extract all the individual insights into a clean, numbered list
    insight_list = []
    for i, (step_key, result_recipe) in enumerate(final_results_recipe.items()):
        description = result_recipe.get("description", "Unnamed Analysis")
        vis_config = result_recipe.get("vis_config") 
        if vis_config is None:
            vis_config = {}
            
        insight = vis_config.get("insight", "")
        if insight:
            insight_list.append(f"{i+1}. Insight for Step '{description}':\n{insight}")

    if not insight_list:
        return "The analysis was completed, but no specific insights were generated to summarize."

    insights_text = "\n\n".join(insight_list)

    # 2. Define the System Prompt for our "Consolidator" AI
    system_prompt = """
You are a world-class Senior Executive Data Strategist. Your task is to analyze a business plan and a list of individual data insights that have already been generated. Your ONLY job is to write a single, high-level **Executive Summary** that synthesizes these standalone points into a cohesive narrative or story.

**CRITICAL INSTRUCTIONS:**
1.  **Synthesize, Don't Just Repeat:** Do not simply list the insights back. Your value is in finding the connection or the overarching story that links them together.
2.  **Tell a Story:** Start with the most important finding and build upon it to a final conclusion or recommendation. Use transition words (e.g., "Building on this," "However," "This leads to...") to create a logical flow.
3.  **Focus on the Big Picture:** The summary should be concise (3-5 sentences) and targeted at a busy executive who needs to understand the main takeaway from the entire report.
4.  **Output ONLY Markdown:** Your entire response must be ONLY the text of the executive summary in plain Markdown format. Do NOT use HTML tags like <div>, <p>, or <span>. Use only Markdown formatting (**, *, -, etc.).
5.  **Bold Key Findings:** Any critical findings or recommendations should be bolded using Markdown (`**...**`).
"""

    # 3. Define the User Prompt
    # Build user question section if available
    question_context = ""
    if user_question and user_question.strip():
        question_context = f"""
**USER'S ORIGINAL QUESTION:**
{user_question}

"""
    
    user_prompt = f"""
{question_context}**ORIGINAL BUSINESS PLAN:**
{business_plan}

**INDIVIDUAL INSIGHTS GENERATED FROM EACH STEP:**
{insights_text}

**YOUR TASK:**
Based on the user's question, the business plan, and all the individual insights provided, write the final, consolidated Executive Summary now.
"""

    # 4. Call the AI
    summary_contents = [{"role": "user", "content": user_prompt}]
    
    # We use a medium-speed model for this synthesis task
    executive_summary = call_llm(
        client=groq_client, model_name=FAST_MODEL_NAME,
        contents=summary_contents,
        system_instruction=system_prompt, step_name="Insight Consolidation",
        temperature=0.4, # Slightly higher temperature for more creative synthesis
        timeout=DEFAULT_TIMEOUT
    )

    return executive_summary or "Failed to generate a consolidated summary."
    