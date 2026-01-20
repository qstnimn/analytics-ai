import streamlit as st
import pandas as pd
import ai_logic
import uuid
import time
import json
from datetime import datetime
from io import StringIO, BytesIO
import re
import plotly.graph_objects as go
import base64

# --- 1. SET PAGE CONFIG ---
st.set_page_config(
    page_title="Analytics AI", 
    layout="wide", 
    initial_sidebar_state="expanded",
    page_icon="📊"
)

# --- INJECT CUSTOM CSS ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    /* Apply to entire app */
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, sans-serif !important;
    }
    
    /* Streamlit specific overrides */
    .stMarkdown, .stText, p, h1, h2, h3, h4, h5, h6, span, div {
        font-family: 'Inter', -apple-system, sans-serif !important;
    }
    
    /* Chat messages */
    .stChatMessage {
        font-family: 'Inter', -apple-system, sans-serif !important;
    }
    
    /* Buttons */
    .stButton > button {
        font-family: 'Inter', -apple-system, sans-serif !important;
    }
    
    /* Inputs */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea {
        font-family: 'Inter', -apple-system, sans-serif !important;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. INITIALIZE CLIENTS (Cached) ---
@st.cache_resource
def get_clients():
    """Initialize and cache Firestore, LLM client (Groq or Gemini), and knowledge base."""
    try:
        db = ai_logic.initialize_firestore_client()
        
        # Initialize the appropriate LLM client based on LLM_PROVIDER
        if ai_logic.LLM_PROVIDER == 'gemini':
            llm_client = ai_logic.initialize_gemini_client()
        else:  # Default to Groq
            llm_client = ai_logic.initialize_groq_client()
        
        kb = ai_logic.get_ai_knowledge_base(db)
        return db, llm_client, kb
    except Exception as e:
        st.error(f"Failed to initialize clients: {str(e)}")
        st.stop()

db_client, groq_client, knowledge_base = get_clients()  # Note: groq_client now holds either Groq or Gemini client

# --- 3. EXPORT FUNCTIONS ---
def export_report_to_pdf(progress_callback=None):
    """Generate PDF using ReportLab - more reliable chart rendering."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak, Table, TableStyle
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT, TA_CENTER
        import plotly.io as pio
        from io import BytesIO
        import re
        
        def convert_markdown_to_reportlab(text):
            """Convert **bold** markdown to <b>bold</b> HTML tags for ReportLab."""
            # Convert **text** to <b>text</b>
            text = re.sub(r'\*\*([^\*]+)\*\*', r'<b>\1</b>', text)
            return text
        
        if progress_callback:
            progress_callback("Building PDF structure...")
        
        # Create PDF buffer
        pdf_buffer = BytesIO()
        doc = SimpleDocTemplate(
            pdf_buffer, 
            pagesize=letter, 
            topMargin=0.5*inch, 
            bottomMargin=0.5*inch,
            leftMargin=0.75*inch,
            rightMargin=0.75*inch
        )
        story = []
        
        # Styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=26,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=6,
            fontName='Helvetica-Bold'
        )
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#2980b9'),
            spaceAfter=8,
            spaceBefore=16,
            fontName='Helvetica-Bold'
        )
        body_style = ParagraphStyle(
            'CustomBody',
            parent=styles['BodyText'],
            fontSize=10,
            leading=14,
            textColor=colors.HexColor('#1a202c'),
            alignment=TA_LEFT
        )
        insight_style = ParagraphStyle(
            'InsightStyle',
            parent=body_style,
            fontSize=10,
            leading=14,
            leftIndent=10,
            rightIndent=10,
            textColor=colors.HexColor('#856404'),
            backColor=colors.HexColor('#fff3cd'),
            borderPadding=8
        )
        
        # Title
        story.append(Paragraph("📊 Strategic Analysis Report", title_style))
        story.append(Paragraph(f"<font size=9 color='#7f8c8d'>Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</font>", body_style))
        story.append(Spacer(1, 0.25*inch))
        
        # Executive Summary
        story.append(Paragraph("Executive Summary", heading_style))
        summary_text = st.session_state.report_data.get('summary', 'No summary available.')
        summary_text = convert_markdown_to_reportlab(summary_text)
        story.append(Paragraph(summary_text, body_style))
        story.append(Spacer(1, 0.2*inch))
        
        # Business Plan
        story.append(Paragraph("Business Plan", heading_style))
        plan_text = st.session_state.business_plan
        plan_text = convert_markdown_to_reportlab(plan_text)
        plan_text = plan_text.replace('\n', '<br/>')
        story.append(Paragraph(plan_text, body_style))
        story.append(Spacer(1, 0.25*inch))
        
        # Charts
        total_charts = len(st.session_state.report_data['dfs'])
        for idx, (key, result) in enumerate(st.session_state.report_data['dfs'].items(), 1):
            if result.get('data') is None or result['data'].empty:
                continue
            
            if progress_callback:
                progress_callback(f"Rendering chart {idx}/{total_charts}...")
            
            vis_config = result.get('vis_config', {})
            title = vis_config.get('title', result['description'])
            insight = vis_config.get('insight', 'No insight available.')
            
            # Add page break before new section (except first)
            if idx > 1:
                story.append(PageBreak())
            
            # Chart title
            story.append(Paragraph(title, heading_style))
            
            # Key insight with bold conversion
            insight = convert_markdown_to_reportlab(insight)
            story.append(Paragraph(f"<b>💡 Key Insight:</b> {insight}", insight_style))
            story.append(Spacer(1, 0.15*inch))
            
            # Generate chart image with higher quality
            try:
                fig = ai_logic.create_figure_from_config(vis_config, result['data'])
                
                # Increase chart size and quality
                img_bytes = pio.to_image(fig, format='png', width=1000, height=550, scale=2.5)
                img_buffer = BytesIO(img_bytes)
                
                # Add to PDF with better sizing
                img = Image(img_buffer, width=7*inch, height=3.85*inch)
                story.append(img)
                story.append(Spacer(1, 0.2*inch))
                
            except Exception as e:
                story.append(Paragraph(f"<font color='red'>⚠️ Chart rendering failed: {str(e)}</font>", body_style))
                story.append(Spacer(1, 0.15*inch))
        
        # Footer
        story.append(Spacer(1, 0.3*inch))
        story.append(Paragraph("<font size=8 color='#7f8c8d'>Powered by Groq AI • Enterprise Data Warehouse Analytics</font>", 
                              ParagraphStyle('footer', parent=body_style, alignment=TA_CENTER)))
        
        if progress_callback:
            progress_callback("Converting to PDF...")
        
        # Build PDF
        doc.build(story)
        
        pdf_buffer.seek(0)
        return pdf_buffer.getvalue()
        
    except ImportError:
        st.error("""📦 PDF export requires reportlab. Install with:
        
```bash
pip install reportlab
```
        """)
        return None
    except Exception as e:
        st.error(f"PDF generation failed: {str(e)}")
        import traceback
        st.error(traceback.format_exc())
        return None
        
        # Build HTML content with embedded chart images
        html_parts = ["""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                @page {
                    size: letter;
                    margin: 1.5cm;
                }
                body {
                    font-family: Arial, Helvetica, sans-serif;
                    line-height: 1.5;
                    color: #1a202c;
                }
                h1 {
                    color: #2c3e50;
                    font-size: 24px;
                    font-weight: bold;
                    margin-bottom: 0.3cm;
                    border-bottom: 2px solid #3498db;
                    padding-bottom: 0.2cm;
                }
                h2 {
                    color: #34495e;
                    font-size: 18px;
                    font-weight: bold;
                    margin-top: 0.8cm;
                    margin-bottom: 0.3cm;
                }
                .summary {
                    background-color: #d1ecf1;
                    padding: 0.5cm;
                    border-radius: 4px;
                    margin: 0.3cm 0;
                    border-left: 3px solid #0c5460;
                    color: #0c5460;
                }
                .insight {
                    background-color: #fff3cd;
                    padding: 0.4cm;
                    border-radius: 4px;
                    margin: 0.3cm 0;
                    border-left: 3px solid #856404;
                    color: #856404;
                }
                .chart-img {
                    width: 100%;
                    max-width: 700px;
                    margin: 0.3cm 0;
                }
                .step-title {
                    color: #2980b9;
                    font-size: 16px;
                    font-weight: bold;
                    margin-top: 0.5cm;
                }
                .footer {
                    margin-top: 1cm;
                    padding-top: 0.3cm;
                    border-top: 1px solid #ecf0f1;
                    font-size: 10px;
                    color: #7f8c8d;
                    text-align: center;
                }
                strong {
                    font-weight: bold;
                    color: #2c3e50;
                }
                .metadata {
                    color: #7f8c8d;
                    font-size: 11px;
                    margin-bottom: 0.5cm;
                }
            </style>
        </head>
        <body>
            <h1>Strategic Analysis Report</h1>
            <p class="metadata">Generated on """ + datetime.now().strftime('%B %d, %Y at %I:%M %p') + """</p>
            
            <h2>Executive Summary</h2>
            <div class="summary">
                """ + st.session_state.report_data.get('summary', 'No summary available.') + """
            </div>
            
            <h2>Business Plan</h2>
            <pre style="background-color: #f8f9fa; padding: 0.3cm; border-radius: 4px; white-space: pre-wrap; font-size: 11px;">""" + st.session_state.business_plan + """</pre>
        """]
        
        # Add each analysis step with charts as images
        total_charts = len(st.session_state.report_data['dfs'])
        for idx, (key, result) in enumerate(st.session_state.report_data['dfs'].items(), 1):
            if result.get('data') is None or result['data'].empty:
                continue
            
            if progress_callback:
                progress_callback(f"Rendering chart {idx}/{total_charts}...")
            
            vis_config = result.get('vis_config', {})
            title = vis_config.get('title', result['description'])
            insight = vis_config.get('insight', 'No insight available.')
            
            html_parts.append(f"""
                <div style="page-break-inside: avoid;">
                    <h2 class="step-title">{title}</h2>
                    <div class="insight"><strong>Key Insight:</strong> {insight}</div>
            """)
            
            # Generate chart as static image (OPTIMIZED: lower resolution, faster)
            try:
                fig = ai_logic.create_figure_from_config(vis_config, result['data'])
                img_bytes = pio.to_image(fig, format='png', width=600, height=350, scale=1.5)
                img_base64 = base64.b64encode(img_bytes).decode()
                html_parts.append(f'<img src="data:image/png;base64,{img_base64}" class="chart-img"/>')
            except Exception as e:
                html_parts.append(f'<p style="color: #e74c3c;">Chart rendering failed: {str(e)}</p>')
            
            html_parts.append("</div>")
        
        html_parts.append("""
            <div class="footer">
                <p>Powered by Groq AI - Enterprise Data Warehouse Analytics</p>
            </div>
        </body>
        </html>
        """)
        
        html_string = '\n'.join(html_parts)
        
        if progress_callback:
            progress_callback("Converting to PDF...")
        
        # Convert HTML to PDF
        pdf_buffer = BytesIO()
        pisa_status = pisa.CreatePDF(html_string, dest=pdf_buffer)
        
        if pisa_status.err:
            st.error("PDF generation encountered errors")
            return None
        
        pdf_buffer.seek(0)
        return pdf_buffer.getvalue()
        
    except ImportError:
        st.error("""📦 PDF export requires xhtml2pdf. Install with:
        
```bash
pip install xhtml2pdf
```
        """)
        return None
    except Exception as e:
        st.error(f"PDF generation failed: {str(e)}")
        import traceback
        st.error(traceback.format_exc())
        return None
    """Generate standalone HTML from the current report that can be saved or printed to PDF."""
    try:
        import plotly.io as pio
        
        # Build HTML content with embedded charts
        html_parts = [f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Analytics Report - {datetime.now().strftime('%Y-%m-%d')}</title>
            <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
            <style>
                body {{
                    font-family: 'Inter', -apple-system, sans-serif;
                    margin: 0;
                    padding: 2rem;
                    line-height: 1.6;
                    color: #1a202c;
                    background-color: #f9fafb;
                }}
                .container {{
                    max-width: 1200px;
                    margin: 0 auto;
                    background: white;
                    padding: 3rem;
                    border-radius: 8px;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                }}
                h1 {{
                    color: #2c3e50;
                    font-size: 32px;
                    font-weight: 700;
                    margin-bottom: 0.5rem;
                    border-bottom: 3px solid #3498db;
                    padding-bottom: 0.5rem;
                }}
                h2 {{
                    color: #34495e;
                    font-size: 24px;
                    font-weight: 600;
                    margin-top: 2rem;
                    margin-bottom: 1rem;
                }}
                .summary {{
                    background-color: #d1ecf1;
                    padding: 1.5rem;
                    border-radius: 8px;
                    margin: 1rem 0;
                    border-left: 4px solid #0c5460;
                    color: #0c5460;
                }}
                .insight {{
                    background-color: #fff3cd;
                    padding: 1rem;
                    border-radius: 6px;
                    margin: 1rem 0;
                    border-left: 4px solid #856404;
                    color: #856404;
                }}
                .chart-container {{
                    margin: 2rem 0;
                    padding: 1.5rem;
                    background: #f8f9fa;
                    border-radius: 8px;
                }}
                .step-title {{
                    color: #2980b9;
                    font-size: 20px;
                    font-weight: 600;
                    margin-bottom: 1rem;
                }}
                .footer {{
                    margin-top: 3rem;
                    padding-top: 1rem;
                    border-top: 2px solid #ecf0f1;
                    font-size: 14px;
                    color: #7f8c8d;
                    text-align: center;
                }}
                strong {{
                    font-weight: 600;
                    color: #2c3e50;
                }}
                .metadata {{
                    color: #7f8c8d;
                    font-size: 14px;
                    margin-bottom: 2rem;
                }}
                @media print {{
                    body {{ background-color: white; padding: 0; }}
                    .container {{ box-shadow: none; }}
                }}
            </style>
            <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
        </head>
        <body>
            <div class="container">
                <h1> Strategic Analysis Report</h1>
                <p class="metadata">Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')} | Session: {st.session_state.active_session_id[:8]}</p>
                
                <h2>Executive Summary</h2>
                <div class="summary">
                    {st.session_state.report_data.get('summary', 'No summary available.')}
                </div>
                
                <h2>Business Plan</h2>
                <pre style="background-color: #f8f9fa; padding: 1rem; border-radius: 6px; white-space: pre-wrap; font-family: 'Inter', sans-serif;">{st.session_state.business_plan}</pre>
        """]
        
        # Add each analysis step with charts
        for key, result in st.session_state.report_data['dfs'].items():
            if result.get('data') is None or result['data'].empty:
                continue
            
            vis_config = result.get('vis_config', {})
            title = vis_config.get('title', result['description'])
            insight = vis_config.get('insight', 'No insight available.')
            
            html_parts.append(f"""
                <div class="chart-container">
                    <h2 class="step-title">{title}</h2>
                    <div class="insight"><strong>💡 Key Insight:</strong> {insight}</div>
            """)
            
            # Generate interactive chart
            try:
                fig = ai_logic.create_figure_from_config(vis_config, result['data'])
                fig.update_layout(
                    height=500,
                    margin=dict(l=20, r=20, t=40, b=20)
                )
                # Convert to HTML div (interactive)
                chart_html = pio.to_html(fig, include_plotlyjs=False, div_id=f"chart_{key}")
                html_parts.append(chart_html)
            except Exception as e:
                html_parts.append(f'<p style="color: #e74c3c;">⚠️ Chart rendering failed: {str(e)}</p>')
            
            html_parts.append("</div>")
        
        html_parts.append(f"""
                <div class="footer">
                    <p>Powered by Groq AI • Connected to Enterprise Data Warehouse</p>
                </div>
            </div>
        </body>
        </html>
        """)
        
        return '\n'.join(html_parts)
        
    except Exception as e:
        st.error(f"HTML generation failed: {str(e)}")
        import traceback
        st.error(traceback.format_exc())
        return None

    """Generate PDF from the current report using HTML and chart images."""
    try:
        from weasyprint import HTML, CSS
        import plotly.io as pio
        
        # Build HTML content
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&display=swap');
                
                body {{
                    font-family: 'Inter', -apple-system, sans-serif;
                    margin: 2cm;
                    line-height: 1.6;
                    color: #1a1a1a;
                }}
                h1 {{
                    color: #2c3e50;
                    font-size: 28px;
                    font-weight: 700;
                    margin-bottom: 0.5cm;
                    border-bottom: 3px solid #3498db;
                    padding-bottom: 0.3cm;
                }}
                h2 {{
                    color: #34495e;
                    font-size: 20px;
                    font-weight: 600;
                    margin-top: 1cm;
                    margin-bottom: 0.3cm;
                }}
                .summary {{
                    background-color: #d1ecf1;
                    padding: 1cm;
                    border-radius: 8px;
                    margin: 0.5cm 0;
                    border-left: 4px solid #0c5460;
                    color: #0c5460;
                }}
                .insight {{
                    background-color: #fff3cd;
                    padding: 0.5cm;
                    border-radius: 6px;
                    margin: 0.3cm 0;
                    border-left: 4px solid #856404;
                    color: #856404;
                }}
                .chart {{
                    margin: 0.5cm 0;
                    page-break-inside: avoid;
                }}
                .chart img {{
                    max-width: 100%;
                    height: auto;
                }}
                .step-title {{
                    color: #2980b9;
                    font-size: 18px;
                    font-weight: 600;
                    margin-top: 0.8cm;
                }}
                .footer {{
                    margin-top: 2cm;
                    padding-top: 0.5cm;
                    border-top: 2px solid #ecf0f1;
                    font-size: 12px;
                    color: #7f8c8d;
                    text-align: center;
                }}
                strong {{
                    font-weight: 600;
                    color: #2c3e50;
                }}
            </style>
        </head>
        <body>
            <h1> Strategic Analysis Report</h1>
            <p style="color: #7f8c8d; font-size: 14px;">Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
            
            <h2>Executive Summary</h2>
            <div class="summary">
                {st.session_state.report_data.get('summary', 'No summary available.')}
            </div>
            
            <h2>Business Plan</h2>
            <pre style="background-color: #f8f9fa; padding: 0.5cm; border-radius: 6px; white-space: pre-wrap;">{st.session_state.business_plan}</pre>
        """
        
        # Add each analysis step with charts
        for key, result in st.session_state.report_data['dfs'].items():
            if result.get('data') is None or result['data'].empty:
                continue
            
            vis_config = result.get('vis_config', {})
            title = vis_config.get('title', result['description'])
            insight = vis_config.get('insight', 'No insight available.')
            
            html_content += f"""
            <div class="chart">
                <h2 class="step-title">{title}</h2>
                <div class="insight"><strong>💡 Key Insight:</strong> {insight}</div>
            """
            
            # Generate chart as static image
            try:
                fig = ai_logic.create_figure_from_config(vis_config, result['data'])
                img_bytes = pio.to_image(fig, format='png', width=800, height=500, scale=2)
                img_base64 = base64.b64encode(img_bytes).decode()
                html_content += f'<img src="data:image/png;base64,{img_base64}" style="width: 100%; max-width: 800px;"/>'
            except Exception as e:
                html_content += f'<p style="color: #e74c3c;">⚠️ Chart rendering failed: {str(e)}</p>'
            
            html_content += "</div>"
        
        html_content += f"""
            <div class="footer">
                <p>Powered by Groq AI • Connected to Enterprise Data Warehouse</p>
                <p>Session ID: {st.session_state.active_session_id}</p>
            </div>
        </body>
        </html>
        """
        
        # Convert HTML to PDF
        pdf_buffer = BytesIO()
        HTML(string=html_content).write_pdf(pdf_buffer)
        pdf_buffer.seek(0)
        
        return pdf_buffer.getvalue()
        
    except ImportError:
        st.error("""📦 PDF export requires additional packages. Install with:
        
```bash
pip install weasyprint kaleido
```
        
**Note:** WeasyPrint also requires GTK+ libraries:
- **Windows:** Download from https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases
- **Mac:** `brew install pango`
- **Linux:** `sudo apt-get install libpango-1.0-0 libpangoft2-1.0-0`
        """)
        return None
    except Exception as e:
        st.error(f"PDF generation failed: {str(e)}")
        import traceback
        st.error(traceback.format_exc())
        return None

# --- 4. SESSION STATE INITIALIZATION ---
def initialize_session_state():
    """Initialize all session state variables with proper defaults."""
    defaults = {
        "messages": [{"role": "assistant", "content": "Hello! I'm your AI Data Analyst. What should we analyze today?"}],
        "active_session_id": str(uuid.uuid4()),
        "report_data": None,
        "current_plan": None,
        "actionable_steps": [],
        "business_plan": "",
        "plan_approved": False,
        "editing_chart_key": None,
        "analysis_running": False,
        "user_id": "user_abc",  # In production, integrate with auth
        "execution_log": []  # Store execution progress for transparency
    }
    
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value

initialize_session_state()

# --- 4. UTILITY FUNCTIONS ---
def sync_to_firestore(session_id, updates):
    """Asynchronously sync state changes to Firestore."""
    try:
        doc_ref = db_client.collection('users').document(st.session_state.user_id).collection('sessions').document(session_id)
        doc_ref.set(updates, merge=True)
    except Exception as e:
        st.warning(f"Failed to sync to Firestore: {str(e)}")

def load_session_from_firestore(session_id):
    """Load a complete session state from Firestore."""
    try:
        doc_ref = db_client.collection('users').document(st.session_state.user_id).collection('sessions').document(session_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            st.error("Session not found.")
            return None
        
        session_data = doc.to_dict()
        
        # Restore messages
        st.session_state.messages = session_data.get('messages', [])
        st.session_state.active_session_id = session_id
        st.session_state.business_plan = session_data.get('business_plan', '')
        
        # Restore report data if it exists
        final_results = session_data.get('final_results', {})
        if final_results and 'recipe' in final_results:
            # Reconstruct DataFrames from JSON
            restored_report = {
                'recipe': final_results['recipe'],
                'summary': final_results.get('summary', ''),
                'dfs': {}
            }
            
            for step_key, step_data in final_results['recipe'].items():
                try:
                    if step_data['data_json']:
                        df = pd.read_json(StringIO(step_data['data_json']), orient='split')
                        restored_report['dfs'][step_key] = {
                            'description': step_data['description'],
                            'data': df,
                            'vis_config': step_data['vis_config']
                        }
                except Exception as e:
                    st.warning(f"Could not restore data for {step_key}: {str(e)}")
            
            st.session_state.report_data = restored_report
        else:
            st.session_state.report_data = None
        
        st.session_state.plan_approved = False
        return True
        
    except Exception as e:
        st.error(f"Error loading session: {str(e)}")
        return None

def delete_session_from_firestore(session_id):
    """Delete a session from Firestore."""
    try:
        doc_ref = db_client.collection('users').document(st.session_state.user_id).collection('sessions').document(session_id)
        doc_ref.delete()
        return True
    except Exception as e:
        st.error(f"Failed to delete session: {str(e)}")
        return False

def get_chat_sessions():
    """Retrieve all chat sessions for the current user."""
    try:
        sessions_ref = db_client.collection('users').document(st.session_state.user_id).collection('sessions')
        sessions = sessions_ref.order_by('created_at', direction='DESCENDING').limit(50).stream()
        return list(sessions)
    except Exception as e:
        st.warning(f"Could not load chat history: {str(e)}")
        return []

def rename_session(session_id, new_title):
    """Rename a chat session in Firestore."""
    try:
        doc_ref = db_client.collection('users').document(st.session_state.user_id).collection('sessions').document(session_id)
        doc_ref.update({'title': new_title})
        return True
    except Exception as e:
        st.error(f"Failed to rename session: {str(e)}")
        return False

def process_chart_edit(step_key, edit_request):
    """
    Handles AI-powered chart editing with proper error handling.
    Distinguishes between data changes and visualization changes.
    """
    try:
        # Get current step data
        current_step_data = st.session_state.report_data['recipe'][step_key]
        original_description = current_step_data['description']
        
        # Reconstruct DataFrame from stored JSON
        if current_step_data['data_json']:
            df = pd.read_json(StringIO(current_step_data['data_json']), orient='split')
        else:
            st.error("No data available to modify.")
            return
        
        # Classify the edit request
        st.write("🔍 Analyzing your request...")
        edit_type = ai_logic.classify_edit_request(groq_client, edit_request, original_description)
        
        new_description = f"{original_description} (Updated: {edit_request})"
        new_df = df
        
        # If data change is needed, regenerate SQL
        if edit_type == 'data_change':
            st.write("🔧 Regenerating SQL with new criteria...")
            new_sql = ai_logic.generate_sql_for_step(groq_client, new_description, knowledge_base)
            
            if new_sql:
                df_retrieved = ai_logic.execute_sql_query(groq_client, knowledge_base, new_sql, new_description)
                
                if df_retrieved is not None and not df_retrieved.empty:
                    new_df = df_retrieved
                    st.success("✅ Data retrieved successfully!")
                else:
                    st.warning("New query returned no data. Keeping original dataset.")
            else:
                st.warning("Could not generate new SQL. Keeping original dataset.")
        
        # Generate new visualization config
        st.write("🎨 Creating new visualization...")
        new_vis_config = ai_logic.generate_visualization_config(groq_client, new_description, new_df)
        
        if not new_vis_config:
            st.error("Failed to generate visualization. Please try again.")
            return
        
        # Update session state
        st.session_state.report_data['recipe'][step_key] = {
            "description": new_description,
            "data_json": new_df.to_json(orient='split'),
            "vis_config": new_vis_config
        }
        
        st.session_state.report_data['dfs'][step_key] = {
            "description": new_description,
            "data": new_df,
            "vis_config": new_vis_config
        }
        
        # Regenerate consolidated summary to reflect the chart changes
        st.write("📝 Updating executive summary...")
        try:
            # Extract user's original question(s) from messages
            user_questions = [msg['content'] for msg in st.session_state.messages if msg['role'] == 'user']
            user_question = ' | '.join(user_questions)  # Combine multiple questions if present
            
            updated_summary = ai_logic.generate_consolidated_summary(
                groq_client,
                st.session_state.business_plan,
                st.session_state.report_data['recipe'],
                user_question=user_question
            )
            st.session_state.report_data['summary'] = updated_summary
        except Exception as e:
            st.warning(f"Could not regenerate summary: {str(e)}")
        
        # Sync to Firestore
        st.write("💾 Saving changes to Firestore...")
        sync_to_firestore(st.session_state.active_session_id, {
            'final_results': {
                'recipe': st.session_state.report_data['recipe'],
                'summary': st.session_state.report_data.get('summary', '')
            }
        })
        
        st.success("✅ Chart updated successfully!")
        time.sleep(1)
        st.rerun()
        
    except Exception as e:
        st.error(f"❌ Update failed: {str(e)}")
        import traceback
        st.error(f"Details: {traceback.format_exc()}")

# --- 5. SIDEBAR: CHAT HISTORY & DB INFO ---
with st.sidebar:
    st.title("📊 Analytics AI")
    
    # New Chat Button (disabled during analysis)
    if st.button(
        "✨ New Chat", 
        use_container_width=True, 
        type="primary",
        disabled=st.session_state.analysis_running
    ):
        st.session_state.messages = [{"role": "assistant", "content": "Hello! I'm your AI Data Analyst. What should we analyze today?"}]
        st.session_state.active_session_id = str(uuid.uuid4())
        st.session_state.report_data = None
        st.session_state.current_plan = None
        st.session_state.actionable_steps = []
        st.session_state.business_plan = ""
        st.session_state.plan_approved = False
        st.rerun()

    st.divider()
    
    # Chat History
    st.subheader("💬 Chat History")
    sessions = get_chat_sessions()
    
    if sessions:
        for session in sessions:
            session_data = session.to_dict()
            session_id = session.id
            title = session_data.get('title', 'Untitled Chat')
            created_at = session_data.get('created_at', datetime.now())
            
            # Format timestamp
            if hasattr(created_at, 'timestamp'):
                time_str = created_at.strftime('%b %d, %I:%M %p')
            else:
                time_str = "Recent"
            
            col1, col2, col3 = st.columns([3, 0.5, 0.5])
            
            with col1:
                # Highlight active session
                if session_id == st.session_state.active_session_id:
                    button_label = f"🔵 {title}"
                    button_type = "secondary"
                else:
                    button_label = title
                    button_type = "tertiary"
                
                if st.button(
                    button_label, 
                    key=f"load_{session_id}",
                    use_container_width=True,
                    type=button_type,
                    help=f"Created: {time_str}",
                    disabled=st.session_state.analysis_running
                ):
                    load_session_from_firestore(session_id)
                    st.rerun()
            
            with col2:
                # Rename functionality using popover
                with st.popover(" ✏️ ", use_container_width=False, disabled=st.session_state.analysis_running):
                    st.write("**Rename Chat**")
                    
                    new_title = st.text_input(
                        "New title:",
                        value=title,
                        key=f"rename_input_{session_id}",
                        placeholder="Enter new chat title..."
                    )
                    
                    if st.button("💾 Save", key=f"save_rename_{session_id}", type="primary", use_container_width=True):
                        if new_title and new_title.strip() and new_title.strip() != title:
                            if rename_session(session_id, new_title.strip()):
                                st.success("✅ Renamed!")
                                time.sleep(0.5)
                                st.rerun()
                        elif new_title.strip() == title:
                            st.info("Title unchanged")
                        else:
                            st.warning("Enter a valid title")
                    
                    if st.button("❌ Cancel", key=f"cancel_rename_{session_id}", use_container_width=True):
                        st.rerun()
            
            with col3:
                if st.button("🗑️", key=f"delete_{session_id}", help="Delete this chat", disabled=st.session_state.analysis_running):
                    if delete_session_from_firestore(session_id):
                        if session_id == st.session_state.active_session_id:
                            # Reset to new chat if deleting active session
                            st.session_state.messages = [{"role": "assistant", "content": "Hello! I'm your AI Data Analyst. What should we analyze today?"}]
                            st.session_state.active_session_id = str(uuid.uuid4())
                            st.session_state.report_data = None
                        st.rerun()
    else:
        st.info("No previous chats. Start a new conversation!")
    
    st.divider()
    
    # Database Architecture
    with st.expander("🗄️About the Database", expanded=False):
        st.markdown(ai_logic.db_summary_for_context)
    
    # Debug: Show Metadata Statistics
    with st.expander("🔍 Metadata Inspector", expanded=False):
        st.write("**Knowledge Base Statistics:**")
        st.write(f"- Tables: {len(knowledge_base.get('raw_schema', {}))}")
        st.write(f"- Relationships: {len(knowledge_base.get('relationships', []))}")
        
        if knowledge_base.get('relationships'):
            st.write("\n**Sample Relationships:**")
            sample_rels = knowledge_base['relationships'][:10]
            for rel in sample_rels:
                st.code(f"{rel['parent_table']}.{rel['parent_column']} → {rel['referenced_table']}.{rel['referenced_column']}", language="text")
        else:
            st.warning("⚠️ No relationships found! They may not be loaded from Firestore.")
    
    # Token Usage Panel
    with st.expander("💰 Token Usage", expanded=False):
        total_in = ai_logic.TOKEN_USAGE['total_input']
        total_out = ai_logic.TOKEN_USAGE['total_output']
        total = total_in + total_out
        
        st.metric("Total Tokens", f"{total:,}", delta=None)
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Input", f"{total_in:,}")
        with col2:
            st.metric("Output", f"{total_out:,}")
        
        if ai_logic.TOKEN_USAGE['by_function']:
            st.write("**By Function:**")
            for func_name, usage in sorted(
                ai_logic.TOKEN_USAGE['by_function'].items(),
                key=lambda x: x[1]['input'] + x[1]['output'],
                reverse=True
            )[:5]:  # Top 5
                func_total = usage['input'] + usage['output']
                st.write(f"- {func_name}: {func_total:,} tokens ({usage['calls']} calls)")
        
        if st.button("🔄 Reset Counter"):
            ai_logic.reset_token_usage()
            st.rerun()

    # Debug: Session State Viewer
    with st.sidebar.expander("🐛 Debug"):
        st.write("Session State:", st.session_state)

# --- 6. MAIN CHAT INTERFACE ---
st.header("Strategic Analysis Assistant")

# Show status banner if analysis is running
if st.session_state.analysis_running:
    st.info("Analysis in progress... Please wait. All buttons are disabled to prevent interruption.")

# Display chat messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- 7. CHAT INPUT & LOGIC ---
if prompt := st.chat_input(
    "Ask a question about your data..." if not st.session_state.analysis_running else "Analysis in progress...",
    key="main_chat_input",
    disabled=st.session_state.analysis_running
):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Sync to Firestore
    chat_manager = ai_logic.ChatManager(db_client=db_client, session_id=st.session_state.active_session_id)
    chat_manager.add_message("user", prompt)
    
    with st.chat_message("user"):
        st.markdown(prompt)

    # Determine if this is the first user message
    is_first_message = len([m for m in st.session_state.messages if m['role'] == 'user']) == 1
    
    # Classification & Planning Phase
    with st.chat_message("assistant"):
        with st.spinner("🤔 Analyzing your question..."):
            try:
                intent = ai_logic.classify_question_type(groq_client, prompt)
                
                if intent == 'unrelated':
                    response = "I'm sorry, I can only help with business and data-related questions. Please ask something related to your data warehouse."
                    st.session_state.current_plan = None
                    st.session_state.actionable_steps = []
                    
                elif intent == 'direct_question':
                    # For direct questions, create a simplified plan
                    if is_first_message:
                        plan = ai_logic.generate_direct_action_plan(prompt)
                        st.session_state.business_plan = plan
                        st.session_state.current_plan = plan
                        st.session_state.actionable_steps = [prompt]
                        
                        response = f"{plan}\n\n✅ This is a direct query. Click **'Run Analysis'** below to execute."
                    else:
                        # If not first message, treat as feedback on existing plan
                        plan = ai_logic.generate_business_plan(groq_client, st.session_state.messages, knowledge_base)
                        st.session_state.business_plan = plan
                        st.session_state.current_plan = plan
                        st.session_state.actionable_steps = ai_logic.parse_business_plan_steps(plan)
                        
                        response = f"{plan}\n\n📋 Review the updated plan and click **'Approve & Run Analysis'** to proceed."
                else:
                    # Thinking question - generate full plan
                    if is_first_message:
                        plan = ai_logic.generate_business_plan(groq_client, st.session_state.messages, knowledge_base)
                        st.session_state.business_plan = plan
                        st.session_state.current_plan = plan
                        st.session_state.actionable_steps = ai_logic.parse_business_plan_steps(plan)
                        
                        response = f"{plan}\n\n📋 Review this plan and click **'Approve & Run Analysis'** to proceed or type your feedback to refine the steps."
                    else:
                        # If not first message, treat as feedback on existing plan
                        plan = ai_logic.generate_business_plan(groq_client, st.session_state.messages, knowledge_base)
                        st.session_state.business_plan = plan
                        st.session_state.current_plan = plan
                        st.session_state.actionable_steps = ai_logic.parse_business_plan_steps(plan)
                        
                        response = f"{plan}\n\n📋 Review the updated plan and click **'Approve & Run Analysis'** to proceed."                    
                
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
                
                # Sync to Firestore
                chat_manager.add_message("assistant", response)
                sync_to_firestore(st.session_state.active_session_id, {
                    'business_plan': st.session_state.business_plan,
                    'title': st.session_state.messages[1]['content'][:50] if len(st.session_state.messages) > 1 else 'New Chat',
                    'updated_at': datetime.now()
                })
                
            except Exception as e:
                error_msg = f"⚠️ An error occurred during planning: {str(e)}"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
                chat_manager.add_message("assistant", error_msg)
    
    # Reset plan approval status
    st.session_state.plan_approved = False
    st.rerun()

# --- 8. PLAN APPROVAL BUTTON ---
if st.session_state.current_plan and st.session_state.actionable_steps and not st.session_state.plan_approved:
    st.divider()
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button(
            "✅ Approve & Run Analysis", 
            type="primary", 
            use_container_width=True, 
            key="approve_plan",
            disabled=st.session_state.analysis_running
        ):
            st.session_state.plan_approved = True
            st.session_state.analysis_running = True
            st.rerun()

# --- 9. ANALYSIS EXECUTION (Sequential with Real-Time Updates) ---
if st.session_state.plan_approved and st.session_state.analysis_running:
    st.divider()
    st.header("🔬 Analysis Execution")
    
    steps = st.session_state.actionable_steps
    results_with_dfs = {}
    results_for_storage = {}
    previous_step_contexts = {}  # NEW: Accumulate context from previous steps
    
    # Initialize execution log for this analysis
    st.session_state.execution_log = []
    st.session_state.execution_log.append({"type": "header", "message": f"🚀 Analysis started with {len(steps)} steps"})
    
    # Use st.status for live progress tracking
    with st.status("🚀 Running Analysis...", expanded=True) as status:
        for i, step in enumerate(steps):
            step_num = i + 1
            step_key = f"step_{step_num}"
            
            st.write(f"**Step {step_num}/{len(steps)}:** {step}")
            st.session_state.execution_log.append({"type": "step", "message": f"**Step {step_num}/{len(steps)}:** {step}"})
            
            try:
                # PHASE 1: SQL Generation (NOW WITH CONTEXT FROM PREVIOUS STEPS)
                with st.spinner(f"   ⚙️ Generating SQL for step {step_num}..."):
                    st.session_state.execution_log.append({"type": "info", "message": f"   ⚙️ Generating SQL for step {step_num}..."})
                    sql = ai_logic.generate_sql_for_step(
                        groq_client, 
                        step, 
                        knowledge_base,
                        previous_results=previous_step_contexts  # Pass accumulated context
                    )
                    
                    if not sql:
                        st.warning(f"   ⚠️ Could not generate SQL for step {step_num}. Skipping...")
                        st.session_state.execution_log.append({"type": "warning", "message": f"   ⚠️ Could not generate SQL for step {step_num}. Skipping..."})
                        continue
                    st.session_state.execution_log.append({"type": "success", "message": f"   ✅ SQL generated successfully"})
                
                # PHASE 2: SQL Execution with Self-Healing
                with st.spinner(f"   🔧 Executing & debugging query..."):
                    st.session_state.execution_log.append({"type": "info", "message": f"   🔧 Executing & debugging query..."})
                    df = ai_logic.execute_sql_query(groq_client, knowledge_base, sql, step)
                    
                    # Edge Case: Empty DataFrame
                    if df is None or df.empty:
                        st.warning(f"   📭 No data returned for step {step_num}. Query may need refinement.")
                        st.session_state.execution_log.append({"type": "warning", "message": f"   📭 No data returned for step {step_num}. Query may need refinement."})
                        # Store placeholder for this step
                        results_for_storage[step_key] = {
                            "description": step,
                            "data_json": None,
                            "vis_config": {"type": "error", "message": "No data found"},
                            "error": "No data returned"
                        }
                        continue
                    st.session_state.execution_log.append({"type": "success", "message": f"   ✅ Query executed successfully - {len(df)} rows returned"})
                
                # PHASE 3: Visualization Config Generation
                with st.spinner(f"   🎨 Creating visualization..."):
                    st.session_state.execution_log.append({"type": "info", "message": f"   🎨 Creating visualization..."})
                    vis_config = ai_logic.generate_visualization_config(groq_client, step, df)
                    
                    # Edge Case: Missing vis_config
                    if not vis_config:
                        st.warning(f"   ⚠️ Could not generate visualization config for step {step_num}. Using table view.")
                        st.session_state.execution_log.append({"type": "warning", "message": f"   ⚠️ Could not generate visualization config. Using table view."})
                        vis_config = {
                            "type": "table",
                            "title": step,
                            "insight": "Visualization configuration failed. Showing raw data.",
                            "x_column": None,
                            "y_column": None
                        }
                    else:
                        st.session_state.execution_log.append({"type": "success", "message": f"   ✅ Visualization config created - {vis_config.get('type', 'unknown')} chart"})
                
                # Success - Store results
                results_with_dfs[step_key] = {
                    "description": step,
                    "data": df,
                    "vis_config": vis_config
                }
                
                results_for_storage[step_key] = {
                    "description": step,
                    "data_json": df.to_json(orient='split'),
                    "vis_config": vis_config
                }
                
                # NEW: Build context for future steps
                step_context = ai_logic.build_step_context(step, df)
                previous_step_contexts[step_key] = step_context
                
                st.success(f"   ✅ Step {step_num} completed successfully!")
                st.session_state.execution_log.append({"type": "success", "message": f"   ✅ Step {step_num} completed successfully!"})
                
            except Exception as e:
                st.error(f"   ❌ Error in step {step_num}: {str(e)}")
                st.session_state.execution_log.append({"type": "error", "message": f"   ❌ Error in step {step_num}: {str(e)}"})
                # Gracefully handle errors - don't crash, just skip
                results_for_storage[step_key] = {
                    "description": step,
                    "data_json": None,
                    "vis_config": {"type": "error", "message": str(e)},
                    "error": str(e)
                }
                continue
        
        # PHASE 4: Generate Executive Summary
        if results_for_storage:
            st.write("\n📊 Synthesizing executive summary...")
            st.session_state.execution_log.append({"type": "info", "message": "📊 Synthesizing executive summary..."})
            try:
                # Extract user's original question(s) from messages
                user_questions = [msg['content'] for msg in st.session_state.messages if msg['role'] == 'user']
                user_question = ' | '.join(user_questions)  # Combine multiple questions if present
                
                summary = ai_logic.generate_consolidated_summary(
                    groq_client, 
                    st.session_state.business_plan, 
                    results_for_storage,
                    user_question=user_question
                )
                st.session_state.execution_log.append({"type": "success", "message": "✅ Executive summary generated"})
            except Exception as e:
                st.warning(f"Could not generate summary: {str(e)}")
                st.session_state.execution_log.append({"type": "warning", "message": f"⚠️ Could not generate summary: {str(e)}"})
                summary = "Analysis completed. Review individual insights below."
        else:
            summary = "⚠️ No successful results to summarize. Please refine your question."
            st.session_state.execution_log.append({"type": "warning", "message": "⚠️ No successful results to summarize"})
        
        st.session_state.execution_log.append({"type": "header", "message": "✅ Analysis Complete!"})
        status.update(label="✅ Analysis Complete!", state="complete", expanded=False)
    
    # Store final results in session state
    st.session_state.report_data = {
        "recipe": results_for_storage,
        "summary": summary,
        "dfs": results_with_dfs
    }
    
    # Sync to Firestore
    sync_to_firestore(st.session_state.active_session_id, {
        'final_results': {
            'recipe': results_for_storage,
            'summary': summary
        },
        'analysis_completed_at': datetime.now()
    })
    
    st.session_state.analysis_running = False
    st.rerun()

# --- 10. REPORT RENDERING ---
if st.session_state.report_data and not st.session_state.analysis_running:
    st.divider()
    
    # Header with Export Button
    col_header, col_export = st.columns([4, 1])
    with col_header:
        st.header("📊 Strategic Analysis Report")
    with col_export:
        if st.button("📥 Export PDF", type="secondary", use_container_width=True):
            progress_bar = st.progress(0, text="Starting PDF generation...")
            
            def update_progress(message):
                """Update progress bar with message"""
                st.session_state['pdf_progress'] = message
                
            try:
                pdf_data = export_report_to_pdf(progress_callback=update_progress)
                progress_bar.progress(100, text="PDF ready!")
                
                if pdf_data:
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f"Analysis_Report_{timestamp}.pdf"
                    
                    st.download_button(
                        label="💾 Download PDF",
                        data=pdf_data,
                        file_name=filename,
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True
                    )
                else:
                    progress_bar.empty()
            except Exception as e:
                progress_bar.empty()
                st.error(f"PDF generation failed: {str(e)}")
    
    # Executive Summary
    st.subheader("Executive Summary")
    summary_text = st.session_state.report_data.get('summary', '')
    
    # Fallback for old sessions without consolidated summary
    if not summary_text or summary_text.strip() == '':
        summary_text = "**Analysis completed.** Individual insights are shown below for each step."
    
    # Convert markdown bold syntax to HTML
    summary_html = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', summary_text)
    st.markdown(f"""
        <div style="background-color: #d1ecf1; padding: 1rem; border-radius: 0.5rem; 
                    font-family: sans-serif; line-height: 1.6; word-spacing: normal; color: #0c5460;">
            {summary_html}
        </div>
    """, unsafe_allow_html=True)
    
    # Render each analysis step
    for key, result in st.session_state.report_data['dfs'].items():
            # Handle error cases gracefully
            if result.get('vis_config', {}).get('type') == 'error':
                with st.container(border=True):
                    st.subheader(result['description'])
                    st.error(f"⚠️ {result['vis_config'].get('message', 'An error occurred')}")
                continue
            
            # Check if data exists
            if result.get('data') is None or result['data'].empty:
                with st.container(border=True):
                    st.subheader(result['description'])
                    st.warning("📭 No data available for this step.")
                continue
            
            with st.container(border=True):
                # Title and Edit Button Row
                col_title, col_edit = st.columns([5, 1])
                
                with col_title:
                    st.subheader(result['vis_config'].get('title', result['description']))
                
                with col_edit:
                    # Chart Editing Feature using st.popover
                    with st.popover("🎨 Edit", use_container_width=True):
                        st.write("**Modify this chart**")
                        st.caption("Examples: 'Show as pie chart', 'Filter for 2020', 'Show top 5'")
                        
                        edit_input = st.text_area(
                            "Your request:",
                            key=f"edit_input_{key}",
                            height=80,
                            placeholder="Change to bar chart..."
                        )
                        
                        if st.button("Apply Changes", key=f"apply_edit_{key}", type="primary"):
                            if edit_input and edit_input.strip():
                                # Process the edit request directly in the popover
                                with st.spinner(f"🔄 Processing..."):
                                    process_chart_edit(key, edit_input.strip())
                            else:
                                st.warning("Please enter a request.")
                
                # Display Insight
                insight_text = result['vis_config'].get('insight', 'No insight generated.')
                # Convert markdown bold syntax to HTML
                insight_html = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', insight_text)
                
                st.markdown(f"""
                    <div style="font-family: sans-serif; line-height: 1.6; word-spacing: normal;">
                        <strong>💡 Key Insight:</strong> {insight_html}
                    </div>
                """, unsafe_allow_html=True)
                
                # Create and Display Visualization
                try:
                    fig = ai_logic.create_figure_from_config(result['vis_config'], result['data'])
                    st.plotly_chart(fig, use_container_width=True, key=f"chart_{key}")
                except Exception as e:
                    st.error(f"⚠️ Visualization error: {str(e)}")
                    st.dataframe(result['data'], use_container_width=True, key=f"fallback_table_{key}")
                
                # Collapsible Raw Data Table
                with st.expander("📊 View Raw Data"):
                    st.dataframe(result['data'], use_container_width=True, key=f"data_table_{key}")
    
    # --- EXECUTION LOG (Collapsible) ---
    if st.session_state.get('execution_log') and len(st.session_state.execution_log) > 0:
        st.divider()
        with st.expander("📋 Execution Log", expanded=False):
            st.caption("Analysis execution details and progress tracking")
            
            for log_entry in st.session_state.execution_log:
                log_type = log_entry.get('type', 'info')
                message = log_entry.get('message', '')
                
                if log_type == 'header':
                    st.markdown(f"**{message}**")
                elif log_type == 'step':
                    st.markdown(message)
                elif log_type == 'success':
                    st.success(message, icon="✅")
                elif log_type == 'warning':
                    st.warning(message, icon="⚠️")
                elif log_type == 'error':
                    st.error(message, icon="❌")
                elif log_type == 'info':
                    st.info(message, icon="ℹ️")
                else:
                    st.write(message)

# --- 12. FOOTER ---
st.divider()
st.caption("Powered by Groq AI • Connected to Enterprise Data Warehouse")