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

# --- CSS: Terminal Görünümü ---
st.markdown("""
<style>
    .stApp {background-color: #f8f9fa;}
    .block-container {padding-top: 2rem;}
</style>
""", unsafe_allow_html=True)

st.title("🧬 SMART Database: High-Throughput Domain Analysis")
st.markdown("Automated retrieval system with strict filtering (Excluding 'Not Shown' features and repeats).")

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

# --- Helpers ---
def log_message(message, level="INFO"):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    icon = "ℹ️" if level == "INFO" else "✅" if level == "SUCCESS" else "⚠️" if level == "WARNING" else "❌"
    return f"[{timestamp}] {icon} {message}"

def extract_number(text):
    """Metin içindeki sayıyı regex ile bulur. En güvenli yöntemdir."""
    match = re.search(r'\d+', text)
    if match:
        return int(match.group())
    return None

def update_queue_display(placeholder, df):
    placeholder.dataframe(df, use_container_width=True, hide_index=True)

# --- Main Logic ---
uploaded_file = st.file_uploader("Upload Protein FASTA Sequence (.fa, .fasta)", type=["fa", "fasta", "txt"])

if uploaded_file and st.button("🚀 Initialize Analysis Pipeline"):
    
    stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
    sequences = list(SeqIO.parse(stringio, "fasta"))
    
    col_queue, col_telemetry = st.columns([1.5, 1])
    
    # Session Log History
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
        # SCROLLABLE LOG CONTAINER (Sabit Yükseklik)
        log_container = st.container(height=400)

    def add_log(msg, level="INFO"):
        formatted = log_message(msg, level)
        st.session_state.log_history.insert(0, formatted)
        with log_container:
            st.code("\n".join(st.session_state.log_history), language="bash")

    add_log(f"Pipeline initialized. Target sequences: {len(sequences)}", "INFO")
    
    driver = get_driver()
    all_results = []
    
    if driver:
        add_log("Headless WebDriver connection established.", "SUCCESS")
        
        for idx, seq_record in enumerate(sequences):
            prot_id = seq_record.id
            prot_seq = str(seq_record.seq)
            
            # Update Queue UI
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
                
                # Pfam Check
                try:
                    pfam = driver.find_element(By.XPATH, "//input[contains(@name, 'PFAM') or @name='DO_PFAM']")
                    if not pfam.is_selected(): driver.execute_script("arguments[0].click();", pfam)
                except: pass
                
                # Sequence Input
                seq_in = driver.find_element(By.NAME, "SEQUENCE")
                seq_in.clear()
                seq_in.send_keys(prot_seq)
                
                # Force Submit
                driver.execute_script("arguments[0].form.submit();", seq_in)
                
                # Wait & Extract
                wait_start = time.time()
                features_found = False
                valid_count = 0
                
                while time.time() - wait_start < 60:
                    try:
                        # Tablo satırlarının yüklenmesini bekle (Critical Wait)
                        WebDriverWait(driver, 1).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "table.dataTable tbody tr"))
                        )
                        
                        # Tüm satırları çek (Hangi tabloda olduğuna bakmaksızın)
                        rows = driver.find_elements(By.CSS_SELECTOR, "table.dataTable tbody tr")
                        
                        if len(rows) > 0 and "No data available" not in rows[0].text:
                            
                            # Satırları tara
                            for row in rows:
                                cols = row.find_elements(By.TAG_NAME, "td")
                                
                                # --- FİLTRELEME MANTIĞI ---
                                # 1. Sütun Sayısı Kontrolü: 
                                # Eğer 5 veya daha fazla sütun varsa, bu "NOT shown" tablosudur (Reason sütunu vardır).
                                # Bizim istediğimiz tabloda 4 sütun vardır (Feature, Start, End, E-value).
                                if len(cols) >= 5: 
                                    continue
                                
                                if len(cols) >= 3:
                                    feat_name = cols[0].text.strip()
                                    if not feat_name: 
                                        try: feat_name = cols[0].find_element(By.TAG_NAME, "a").text.strip()
                                        except: pass
                                    
                                    # 2. İsim Filtresi (Coiled coil vb.)
                                    if feat_name.lower() in ["coiled coil", "low complexity"]:
                                        continue
                                        
                                    start_txt = cols[1].text.strip()
                                    end_txt = cols[2].text.strip()
                                    e_val = cols[3].text.strip() if len(cols) > 3 else "N/A"
                                    
                                    # 3. Sayısal Veri Kontrolü (Regex ile)
                                    start_val = extract_number(start_txt)
                                    end_val = extract_number(end_txt)
                                    
                                    if start_val is not None:
                                        all_results.append({
                                            "Protein_ID": prot_id,
                                            "Feature": feat_name,
                                            "Start": start_val,
                                            "End": end_val,
                                            "E-value": e_val
                                        })
                                        valid_count += 1
                            
                            features_found = True
                            break # While döngüsünden çık
                            
                        # "No domains" kontrolü
                        if "No domains found" in driver.page_source:
                            features_found = True
                            break
                            
                    except:
                        time.sleep(1)
                
                if features_found:
                    df_queue.loc[df_queue['Accession ID'] == prot_id, 'Status'] = '✅ COMPLETED'
                    df_queue.loc[df_queue['Accession ID'] == prot_id, 'Domains'] = valid_count
                    add_log(f"Extraction successful. {valid_count} valid domains recorded.", "SUCCESS")
                else:
                    df_queue.loc[df_queue['Accession ID'] == prot_id, 'Status'] = '❌ TIMEOUT'
                    add_log("Timeout awaiting results.", "ERROR")
                    
            except Exception as e:
                df_queue.loc[df_queue['Accession ID'] == prot_id, 'Status'] = '❌ FAILED'
                add_log(f"Runtime error: {str(e)[:50]}", "ERROR")
            
            update_queue_display(queue_placeholder, df_queue)

        driver.quit()
        add_log("Batch processing finished.", "SUCCESS")
        st.success("Analysis Completed.")
        
        # --- EXCEL EXPORT (Temiz ve Düzenli) ---
        if all_results:
            df_final = pd.DataFrame(all_results)
            
            # Sıralama: Önce Protein ID, Sonra Start Pozisyonu
            df_final = df_final.sort_values(by=["Protein_ID", "Start"])
            
            # Excel Oluşturma
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_final.to_excel(writer, index=False, sheet_name='SMART_Domains')
                
                # Sütun Genişliklerini Ayarla
                worksheet = writer.sheets['SMART_Domains']
                for column in worksheet.columns:
                    max_length = 0
                    column = [cell for cell in column]
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except: pass
                    adjusted_width = (max_length + 2)
                    worksheet.column_dimensions[get_column_letter(column[0].column)].width = adjusted_width

            st.divider()
            st.subheader("📊 Final Dataset")
            st.dataframe(df_final, use_container_width=True)
            
            st.download_button(
                label="📥 Download Organized Excel (.xlsx)",
                data=output.getvalue(),
                file_name="SMART_Analysis_Final.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("No domains detected.")
