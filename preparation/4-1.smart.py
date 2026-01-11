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
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

# --- Page Configuration ---
st.set_page_config(page_title="SMART Batch Processor", layout="wide", initial_sidebar_state="collapsed")

# --- Custom CSS (Sadece görsellik için, scroll container st.container ile çözüldü) ---
st.markdown("""
<style>
    .stApp {background-color: #f8f9fa;}
    .block-container {padding-top: 2rem;}
</style>
""", unsafe_allow_html=True)

st.title("🧬 SMART Database: High-Throughput Domain Architecture Analysis")
st.markdown("Scientific extraction tool with strict filtering logic (Excluding 'Not Shown' features and non-structural repeats).")

# --- Driver Configuration ---
def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    try:
        service = Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install())
        return webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        st.error(f"Critical Driver Error: {e}")
        return None

# --- Telemetry Helper ---
def log_message(message, level="INFO"):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    icon = "ℹ️" if level == "INFO" else "✅" if level == "SUCCESS" else "⚠️" if level == "WARNING" else "❌"
    return f"[{timestamp}] {icon} {message}"

def update_queue_display(placeholder, df):
    placeholder.dataframe(df, use_container_width=True, hide_index=True)

# --- Core Logic ---
uploaded_file = st.file_uploader("Upload Protein FASTA Sequence (.fa, .fasta)", type=["fa", "fasta", "txt"])

if uploaded_file and st.button("🚀 Initialize Analysis Pipeline"):
    
    # 1. Parse Input
    stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
    sequences = list(SeqIO.parse(stringio, "fasta"))
    
    # 2. UI Setup
    col_queue, col_telemetry = st.columns([1.5, 1])
    
    # Session State for Logs (to persist them)
    if 'log_history' not in st.session_state:
        st.session_state.log_history = []
        
    queue_data = [{"Accession ID": s.id, "Status": "QUEUED", "Domains": 0} for s in sequences]
    df_queue = pd.DataFrame(queue_data)
    
    with col_queue:
        st.subheader("📋 Processing Queue")
        queue_placeholder = st.empty()
        update_queue_display(queue_placeholder, df_queue)
        
    with col_telemetry:
        st.subheader("📟 System Telemetry")
        # SCROLLABLE CONTAINER (Sabit yükseklik, aşağı uzamaz)
        log_container = st.container(height=400)

    # Helper to write to scrollable container
    def add_log(msg, level="INFO"):
        formatted = log_message(msg, level)
        st.session_state.log_history.insert(0, formatted) # Add to top
        with log_container:
            # Re-render logs
            st.code("\n".join(st.session_state.log_history), language="bash")

    add_log(f"Pipeline initialized. Target sequences: {len(sequences)}", "INFO")
    
    driver = get_driver()
    all_results = []
    
    if driver:
        add_log("Headless WebDriver connection established.", "SUCCESS")
        
        # --- Main Loop ---
        for idx, seq_record in enumerate(sequences):
            prot_id = seq_record.id
            prot_seq = str(seq_record.seq)
            
            # Update UI
            df_queue.loc[df_queue['Accession ID'] == prot_id, 'Status'] = '⏳ PROCESSING'
            update_queue_display(queue_placeholder, df_queue)
            
            add_log(f"Processing Accession: {prot_id} ({idx+1}/{len(sequences)})", "INFO")
            
            try:
                driver.get("https://smart.embl-heidelberg.de/")
                
                # Mode Check
                try:
                    driver.implicitly_wait(1)
                    mode_btn = driver.find_elements(By.CSS_SELECTOR, "a[href*='change_mode.cgi?mode=normal']")
                    if mode_btn: driver.execute_script("arguments[0].click();", mode_btn[0])
                except: pass
                
                # Form Fill
                try:
                    pfam = driver.find_element(By.XPATH, "//input[contains(@name, 'PFAM') or @name='DO_PFAM']")
                    if not pfam.is_selected(): driver.execute_script("arguments[0].click();", pfam)
                except: pass # Pfam default might be on
                
                seq_in = driver.find_element(By.NAME, "SEQUENCE")
                seq_in.clear()
                seq_in.send_keys(prot_seq)
                
                # Force Submit
                driver.execute_script("arguments[0].form.submit();", seq_in)
                
                # Wait & Parse
                wait_start = time.time()
                features_found = False
                valid_features_count = 0
                
                while time.time() - wait_start < 60:
                    try:
                        # Tablonun varlığını bekle
                        WebDriverWait(driver, 1).until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.dataTable tbody tr")))
                        
                        # Sayfadaki TÜM tabloları al
                        tables = driver.find_elements(By.CSS_SELECTOR, "table.dataTable")
                        
                        if len(tables) > 0:
                            
                            # --- KRİTİK FİLTRELEME MANTIĞI ---
                            target_table = None
                            
                            for tbl in tables:
                                # Tablo başlıklarını al
                                header_text = tbl.get_attribute("innerText")
                                
                                # 1. Kontrol: Eğer tabloda "Reason" sütunu varsa, bu "NOT shown" tablosudur -> ATLA
                                if "Reason" in header_text:
                                    continue
                                
                                # 2. Kontrol: Eğer tablonun hemen üstündeki başlıkta "NOT shown" yazıyorsa -> ATLA
                                # (Bunu JS ile kontrol etmek daha güvenlidir ama "Reason" sütunu genelde yeterlidir)
                                
                                # 3. Kontrol: Doğru tabloda "Start" ve "End" olmalı
                                if "Start" in header_text and "End" in header_text:
                                    target_table = tbl
                                    break
                            
                            if target_table:
                                # Satırları oku
                                rows = target_table.find_elements(By.TAG_NAME, "tr")
                                temp_features = []
                                
                                for row in rows:
                                    cols = row.find_elements(By.TAG_NAME, "td")
                                    if len(cols) >= 3:
                                        # İsim temizliği
                                        feat_name = cols[0].text.strip()
                                        if not feat_name: 
                                            try: feat_name = cols[0].find_element(By.TAG_NAME, "a").text.strip()
                                            except: pass
                                        
                                        # YASAKLI KELİMELERİ FİLTRELE
                                        if feat_name.lower() in ["coiled coil", "low complexity"]:
                                            continue
                                            
                                        start_txt = cols[1].text.strip()
                                        end_txt = cols[2].text.strip()
                                        e_val = cols[3].text.strip() if len(cols) > 3 else "N/A"
                                        
                                        # Sadece geçerli sayısal verileri al
                                        if start_txt.isdigit():
                                            all_results.append({
                                                "Protein_ID": prot_id,
                                                "Feature": feat_name,
                                                "Start": int(start_txt),
                                                "End": int(end_txt),
                                                "E-value": e_val
                                            })
                                            valid_features_count += 1
                                
                                features_found = True
                                break # While döngüsünden çık
                        
                        # Eğer tablo yoksa ve "No domains" yazıyorsa
                        if "No domains found" in driver.page_source:
                            features_found = True # İşlem tamam ama boş
                            break
                            
                    except:
                        time.sleep(1)
                
                if features_found:
                    df_queue.loc[df_queue['Accession ID'] == prot_id, 'Status'] = '✅ COMPLETED'
                    df_queue.loc[df_queue['Accession ID'] == prot_id, 'Domains'] = valid_features_count
                    add_log(f"Extraction successful. {valid_features_count} valid domains recorded.", "SUCCESS")
                else:
                    df_queue.loc[df_queue['Accession ID'] == prot_id, 'Status'] = '❌ TIMEOUT'
                    add_log("Server response timed out or no valid table structure found.", "ERROR")
                    
            except Exception as e:
                df_queue.loc[df_queue['Accession ID'] == prot_id, 'Status'] = '❌ FAILED'
                add_log(f"Runtime error: {e}", "ERROR")
            
            update_queue_display(queue_placeholder, df_queue)

        driver.quit()
        add_log("Pipeline operations finished.", "SUCCESS")
        st.success("Analysis Completed Successfully.")
        
        # --- PROFESSIONAL EXCEL OUTPUT ---
        if all_results:
            # 1. Create DataFrame
            df_final = pd.DataFrame(all_results)
            
            # 2. Sort Data (Protein ID A-Z, then Start Position Ascending)
            df_final = df_final.sort_values(by=["Protein_ID", "Start"])
            
            # 3. Write to Excel with Auto-Formatting
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_final.to_excel(writer, index=False, sheet_name='SMART_Domains')
                
                # Auto-adjust column width
                worksheet = writer.sheets['SMART_Domains']
                for column in worksheet.columns:
                    max_length = 0
                    column = [cell for cell in column]
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = (max_length + 2)
                    worksheet.column_dimensions[get_column_letter(column[0].column)].width = adjusted_width

            st.divider()
            st.subheader("📊 Final Dataset Preview")
            st.dataframe(df_final, use_container_width=True)
            
            st.download_button(
                label="📥 Download Structured Excel (.xlsx)",
                data=output.getvalue(),
                file_name="SMART_Analysis_Cleaned.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("No domains detected after filtering.")
