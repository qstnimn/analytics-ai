# 📊 Analytics AI - Intelligent Data Analytics Platform

An AI-powered data analytics platform that uses natural language to query, analyze, and visualize data from your SQL Server database. Built with Streamlit and powered by Gemini/Groq LLMs.

## ✨ Features

- 🤖 **Natural Language Queries** - Ask questions in plain English
- 📈 **Automatic Visualization** - AI generates appropriate charts and graphs
- 💡 **Smart Insights** - Get AI-powered analysis and recommendations
- 🔄 **Multi-Step Plans** - Complex analyses broken into manageable steps
- 📊 **Interactive Charts** - Powered by Plotly for rich visualizations
- 💾 **Export Results** - Download data as CSV, Excel, or PDF reports
- 🎨 **Modern UI** - Clean, responsive interface with custom styling

## 🏗️ Architecture

- **Frontend:** Streamlit (Python web framework)
- **AI Engine:** Gemini / Groq (configurable)
- **Database:** SQL Server (ContosoRetailDW)
- **Knowledge Base:** Google Firestore
- **Visualizations:** Plotly

## 📋 Prerequisites

- Python 3.8+
- SQL Server with ODBC Driver 17+
- Google Cloud account (for Firestore)
- Gemini API key OR Groq API key

## 🚀 Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/YOUR_USERNAME/analytics-ai.git
cd analytics-ai
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Create a `.env` file in the project root:

```env
# LLM Provider: 'gemini' or 'groq'
LLM_PROVIDER=gemini

# Gemini API Key (if using Gemini)
GOOGLE_API_KEY=your_gemini_api_key_here

# Groq API Key (if using Groq)
GROQ_API_KEY=your_groq_api_key_here

# Google Cloud Service Account (for Firestore)
GOOGLE_APPLICATION_CREDENTIALS=path/to/your/service-account-key.json
```

**Important:** Never commit your `.env` file or service account JSON to Git!

### 4. Configure Database Connection
Edit `config.py` and update your SQL Server connection details:

```python
DB_SERVER = 'YOUR_SERVER_NAME'
DB_DATABASE = 'YOUR_DATABASE_NAME'
CONNECTION_STRING = f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={DB_SERVER};DATABASE={DB_DATABASE};Trusted_Connection=yes;'
```

### 5. Ingest Database Schema (First Time Only)
This loads your database schema into Firestore for AI analysis:

```bash
python ingest_schema_to_firestore.py
```

Expected output: "✅ Schema successfully uploaded to Firestore!"

### 6. Run the Application
```bash
streamlit run app2.py
```

The app will open in your browser at `http://localhost:8501`

## 🔧 Configuration

### LLM Provider Selection
Choose between Gemini or Groq by setting `LLM_PROVIDER` in your `.env` file:

**Gemini (Recommended):**
- Better accuracy for complex queries
- Models: `gemini-2.5-pro` (powerful), `gemini-2.5-flash-lite` (fast)
- Get API key: [Google AI Studio](https://makersuite.google.com/app/apikey)

**Groq (Free):**
- Lower latency
- Models: `kimi-k2-instruct`, `llama-4-scout`
- Get API key: [Groq Console](https://console.groq.com)

### Database Configuration
The application is pre-configured for the ContosoRetailDW sample database. To use your own database:

1. Update `config.py` with your connection details
2. Ensure ODBC Driver 17 for SQL Server is installed
3. Run `ingest_schema_to_firestore.py` to index your schema

### Firestore Setup
1. Create a Google Cloud project
2. Enable Firestore API
3. Create a service account with Firestore Admin role
4. Download the JSON key file
5. Set `GOOGLE_APPLICATION_CREDENTIALS` in `.env`

## 📖 Usage Examples

**Simple Query:**
```
"What were the top 10 products by sales in 2008?"
```

**Complex Analysis:**
```
"Analyze customer retention trends over the last 3 years and suggest improvements"
```

**Visualization Request:**
```
"Show me a chart of monthly revenue by product category"
```

## 🗂️ Project Structure

```
analytics-ai/
├── app2.py                          # Main Streamlit application
├── ai_logic.py                      # AI/LLM logic & database operations
├── ingest_schema_to_firestore.py    # Schema ingestion script
├── config.py                        # Configuration settings
├── requirements.txt                 # Python dependencies
├── DEPLOYMENT_GUIDE.md              # Detailed deployment instructions
├── assets/
│   └── style.css                    # Custom CSS styling
├── .env.example                     # Environment variables template
└── README.md                        # This file
```

## 🐛 Troubleshooting

### "Failed to initialize clients"
- Check your API keys in `.env`
- Verify `GOOGLE_APPLICATION_CREDENTIALS` path is correct
- Ensure Firestore API is enabled in Google Cloud

### "Database connection failed"
- Verify SQL Server is running
- Check connection string in `config.py`
- Ensure ODBC Driver 17+ is installed
- Test with: `sqlcmd -S YOUR_SERVER -E`

### "No schema found in Firestore"
- Run `python ingest_schema_to_firestore.py`
- Check Firestore console for `crdw_ai_knowledge_base` collection

### Import Errors
- Ensure all dependencies are installed: `pip install -r requirements.txt`
- Use Python 3.8 or higher: `python --version`

## 📊 Database Schema

This project uses the **ContosoRetailDW** sample database. Key tables:
- `FactSales` - Transaction-level sales data
- `FactOnlineSales` - E-commerce transactions
- `FactInventory` - Inventory levels
- `DimProduct`, `DimCustomer`, `DimStore`, etc. - Dimensional data

## 🔒 Security Best Practices

- ✅ Never commit API keys or credentials
- ✅ Use `.env` for secrets (already in `.gitignore`)
- ✅ Keep service account JSON files local
- ✅ Use environment variables in production
- ✅ Review `.gitignore` before first commit

## 📦 Deployment

See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for detailed instructions on:
- Local development
- Docker deployment
- Streamlit Cloud
- Azure App Service
- AWS EC2

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- Built with [Streamlit](https://streamlit.io/)
- AI powered by [Google Gemini](https://deepmind.google/technologies/gemini/) / [Groq](https://groq.com/)
- Visualizations by [Plotly](https://plotly.com/)
- Database: [ContosoRetailDW Sample](https://www.microsoft.com/en-us/download/details.aspx?id=18279)

## 📧 Support

For issues and questions:
- Open an issue on GitHub
- Check the [Troubleshooting](#-troubleshooting) section
- Review [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)

---