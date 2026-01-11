import streamlit as st
import pandas as pd
import time
import datetime
import io
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType
from Bio import SeqIO

# --- Page Configuration ---
st.set_page_config(page_title="SMART Batch Analyzer", layout="wide", initial_sidebar_state="collapsed")

# --- Custom CSS for Scientific Dashboard Look ---
st.markdown("""
<style>
    .stApp {background-color: #f8f9fa;}
    .terminal-box {
        background-color: #0e1117;
        color: #00ff41;
        font-family: 'Courier New', Courier, monospace;
        padding: 15px;
        border-radius: 5px;
        border: 1px solid #333;
        height: 400px;
        overflow-y: auto;
        font-size: 0.85rem;
    }
    .status-badge {
        font-weight: bold;
        padding: 4px 8px;
        border-radius: 4px;
    }
</style>
""", unsafe_allow_html=True)

st.title("🧬 SMART Database: High-Throughput Domain Analysis")
st.markdown("Automated retrieval system for protein domain architectures with intelligent filtering.")

# --- Driver Configuration ---
def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--ignore-certificate-errors")
    # Academic Institution User-Agent Simulation
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    try:
        service = Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install())
        return webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        st.error(f"Critical Driver Error: {e}")
        return None

# --- Telemetry & UI Helpers ---
def log_telemetry(log_container, log_history, message, level="INFO"):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    icon = "ℹ️" if level == "INFO" else "✅" if level == "SUCCESS" else "⚠️" if level == "WARNING" else "❌"
    formatted_msg = f"[{timestamp}] [{level}] {message}"
    log_history.insert(0, formatted_msg) # Prepend new logs
    
    # Update the terminal-like display
    log_text = "\n".join(log_history)
    log_container.code(log_text, language="bash")
    return log_history

def update_queue_display(placeholder, df):
    placeholder.dataframe(df, use_container_width=True, hide_index=True)

# --- Core Logic ---
uploaded_file = st.file_uploader("Upload Protein FASTA Sequence (.fa, .fasta)", type=["fa", "fasta", "txt"])

if uploaded_file and st.button("🚀 Initialize Batch Analysis"):
    # 1. Parse Input
    stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
    sequences = list(SeqIO.parse(stringio, "fasta"))
    
    # 2. Initialize Queue Data
    queue_data = [{"Accession ID": s.id, "Status": "QUEUED", "Domains Detected": 0} for s in sequences]
    df_queue = pd.DataFrame(queue_data)
    
    # 3. Layout Setup
    col_queue, col_telemetry = st.columns([1.5, 1])
    
    with col_queue:
        st.subheader("📋 Batch Processing Queue")
        queue_placeholder = st.empty()
        update_queue_display(queue_placeholder, df_queue)
        
    with col_telemetry:
        st.subheader("📟 System Telemetry")
        log_placeholder = st.empty()
    
    # 4. Process Initialization
    logs = []
    logs = log_telemetry(log_placeholder, logs, f"Batch initialized. Total sequences: {len(sequences)}", "INFO")
    logs = log_telemetry(log_placeholder, logs, "Initializing Headless WebDriver...", "INFO")
    
    driver = get_driver()
    all_results = []
    
    if driver:
        logs = log_telemetry(log_placeholder, logs, "WebDriver handshake successful. Establishing connection...", "SUCCESS")
        
        # --- Session Setup (Mode & Pfam) ---
        driver.get("https://smart.embl-heidelberg.de/")
        
        # Mode Selection Logic
        try:
            driver.implicitly_wait(2)
            links = driver.find_elements(By.CSS_SELECTOR, "a[href*='change_mode.cgi?mode=normal']")
            if links:
                logs = log_telemetry(log_placeholder, logs, "Defaulting to 'Normal Mode'...", "INFO")
                driver.execute_script("arguments[0].click();", links[0])
                time.sleep(2)
        except Exception as e:
            pass # Already in correct mode
            
        # --- Iteration Loop ---
        for idx, seq_record in enumerate(sequences):
            prot_id = seq_record.id
            prot_seq = str(seq_record.seq)
            
            # Update Queue UI
            df_queue.loc[df_queue['Accession ID'] == prot_id, 'Status'] = '⏳ PROCESSING'
            update_queue_display(queue_placeholder, df_queue)
            
            logs = log_telemetry(log_placeholder, logs, f"Processing ID: {prot_id} ({idx+1}/{len(sequences)})", "INFO")
            
            try:
                # 1. Reset/Navigate
                if idx > 0: driver.get("https://smart.embl-heidelberg.de/")
                
                # 2. Form Configuration
                try:
                    pfam_chk = driver.find_element(By.XPATH, "//input[contains(@name, 'PFAM') or @name='DO_PFAM']")
                    if not pfam_chk.is_selected():
                        driver.execute_script("arguments[0].click();", pfam_chk)
                except:
                    pass # Pfam might be auto-selected
                    
                # 3. Sequence Injection & Submission
                seq_input = driver.find_element(By.NAME, "SEQUENCE")
                seq_input.clear()
                seq_input.send_keys(prot_seq)
                
                logs = log_telemetry(log_placeholder, logs, "Payload injected. Executing force submission...", "INFO")
                driver.execute_script("arguments[0].form.submit();", seq_input)
                
                # 4. Result Waiting (Dynamic DOM)
                wait_start = time.time()
                data_extracted = False
                domain_count = 0
                
                while time.time() - wait_start < 60: # 60s Timeout
                    try:
                        # Check for Results Table Presence
                        WebDriverWait(driver, 1).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "table.dataTable tbody tr"))
                        )
                        
                        # Wait for DataTables to populate rows (skip "Loading..." or empty rows)
                        rows = driver.find_elements(By.CSS_SELECTOR, "table.dataTable tbody tr")
                        if len(rows) > 0 and "No data available" not in rows[0].text:
                            
                            # --- DATA EXTRACTION ---
                            logs = log_telemetry(log_placeholder, logs, "DataTables populated. Extracting features...", "SUCCESS")
                            
                            for row in rows:
                                cols = row.find_elements(By.TAG_NAME, "td")
                                if len(cols) >= 3:
                                    # Safe text extraction
                                    feature_text = cols[0].text.strip()
                                    if not feature_text: # Try nested anchor
                                        try: feature_text = cols[0].find_element(By.TAG_NAME, "a").text.strip()
                                        except: pass
                                    
                                    # --- FILTERING LOGIC ---
                                    # Exclude "coiled coil" and "low complexity"
                                    if feature_text.lower() in ["coiled coil", "low complexity"]:
                                        continue
                                        
                                    start_text = cols[1].text.strip()
                                    end_text = cols[2].text.strip()
                                    e_val = cols[3].text.strip() if len(cols) > 3 else "N/A"
                                    
                                    # Validation: Must have numeric start
                                    if start_text.isdigit():
                                        all_results.append({
                                            "Protein_ID": prot_id,
                                            "Feature": feature_text,
                                            "Start": int(start_text),
                                            "End": int(end_text),
                                            "E-value": e_val
                                        })
                                        domain_count += 1
                                        
                            data_extracted = True
                            break # Exit wait loop
                            
                    except:
                        # Handle "No domains found" case
                        if "No domains found" in driver.page_source:
                            logs = log_telemetry(log_placeholder, logs, "Analysis complete. No confident domains detected.", "WARNING")
                            data_extracted = True
                            break
                        time.sleep(1) # Wait before retry
                
                # 5. Finalize Status
                if data_extracted:
                    df_queue.loc[df_queue['Accession ID'] == prot_id, 'Status'] = '✅ COMPLETED'
                    df_queue.loc[df_queue['Accession ID'] == prot_id, 'Domains Detected'] = domain_count
                    logs = log_telemetry(log_placeholder, logs, f"Acquisition complete. {domain_count} relevant features parsed.", "SUCCESS")
                else:
                    df_queue.loc[df_queue['Accession ID'] == prot_id, 'Status'] = '❌ TIMEOUT'
                    logs = log_telemetry(log_placeholder, logs, "Server response timeout.", "ERROR")
                    
            except Exception as e:
                df_queue.loc[df_queue['Accession ID'] == prot_id, 'Status'] = '❌ FAILED'
                logs = log_telemetry(log_placeholder, logs, f"Runtime Error: {str(e)[:50]}...", "ERROR")
            
            update_queue_display(queue_placeholder, df_queue)
            
        driver.quit()
        logs = log_telemetry(log_placeholder, logs, "Session terminated. Generating report...", "INFO")
        st.success("Batch Analysis Sequence Completed.")
        
        # --- EXCEL EXPORT ---
        if all_results:
            df_results = pd.DataFrame(all_results)
            
            # Generate Excel in Memory
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_results.to_excel(writer, index=False, sheet_name='SMART_Domains')
            
            st.divider()
            st.subheader("📊 Analytical Results")
            st.dataframe(df_results, use_container_width=True)
            
            st.download_button(
                label="📥 Download Dataset (.xlsx)",
                data=output.getvalue(),
                file_name="SMART_Analysis_Results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("No significant domains were detected across the filtered dataset.")
