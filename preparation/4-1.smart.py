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

# Excel Stil Kütüphaneleri
from openpyxl import load_workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# --- Page Config ---
st.set_page_config(page_title="SMART Pro Analyzer", layout="wide", initial_sidebar_state="collapsed")

# --- CSS ---
st.markdown("""
<style>
    .stApp {background-color: #f8f9fa;}
    code {font-family: 'Consolas', monospace !important; font-size: 0.8rem;}
</style>
""", unsafe_allow_html=True)

st.title("🧬 SMART Database: Professional Domain Analyzer")
st.markdown("Automated retrieval with **visual grouping** in Excel output.")

# --- Driver ---
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
        st.error(f"Driver Error: {e}")
        return None

# --- Helpers ---
def extract_number(text):
    match = re.search(r'\d+', text)
    if match: return int(match.group())
    return None

def update_queue_display(placeholder, df):
    placeholder.dataframe(df, use_container_width=True, hide_index=True)

# --- Main App ---
uploaded_file = st.file_uploader("Upload Protein FASTA Sequence", type=["fa", "fasta", "txt"])

if uploaded_file and st.button("🚀 Start Analysis & Generate Colored Excel"):
    
    stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
    sequences = list(SeqIO.parse(stringio, "fasta"))
    
    col_queue, col_log = st.columns([1.5, 1])
    
    # Queue Data
    queue_data = [{"Accession ID": s.id, "Status": "QUEUED", "Domains": 0} for s in sequences]
    df_queue = pd.DataFrame(queue_data)
    
    with col_queue:
        st.subheader("📋 Queue")
        q_place = st.empty()
        update_queue_display(q_place, df_queue)
        
    with col_log:
        st.subheader("📟 Logs")
        log_cont = st.container(height=400)
        log_place = st.empty()

    if 'logs' not in st.session_state: st.session_state.logs = []
    st.session_state.logs = []

    def log(msg, level="INFO"):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        icon = "ℹ️" if level=="INFO" else "✅" if level=="SUCCESS" else "⚠️" if level=="WARNING" else "❌"
        st.session_state.logs.insert(0, f"[{ts}] {icon} {msg}")
        with log_cont: log_place.code("\n".join(st.session_state.logs), language="bash")

    log(f"Initialized. Total sequences: {len(sequences)}", "INFO")
    
    driver = get_driver()
    all_results = []
    
    if driver:
        log("Driver connected.", "SUCCESS")
        
        for idx, seq_record in enumerate(sequences):
            prot_id = seq_record.id
            prot_seq = str(seq_record.seq)
            
            df_queue.loc[df_queue['Accession ID'] == prot_id, 'Status'] = '⏳ PROCESSING'
            update_queue_display(q_place, df_queue)
            
            log(f"Processing: {prot_id}", "INFO")
            
            try:
                driver.get("https://smart.embl-heidelberg.de/")
                
                # Mode
                try:
                    driver.implicitly_wait(1)
                    mode = driver.find_elements(By.CSS_SELECTOR, "a[href*='change_mode.cgi?mode=normal']")
                    if mode: driver.execute_script("arguments[0].click();", mode[0])
                except: pass
                
                # Form
                try:
                    pfam = driver.find_element(By.XPATH, "//input[contains(@name, 'PFAM') or @name='DO_PFAM']")
                    if not pfam.is_selected(): driver.execute_script("arguments[0].click();", pfam)
                except: pass
                
                seq_in = driver.find_element(By.NAME, "SEQUENCE")
                seq_in.clear()
                seq_in.send_keys(prot_seq)
                driver.execute_script("arguments[0].form.submit();", seq_in)
                
                # Wait & Extract
                start_t = time.time()
                found = False
                valid = 0
                
                while time.time() - start_t < 60:
                    try:
                        WebDriverWait(driver, 1).until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.dataTable tbody tr")))
                        rows = driver.find_elements(By.CSS_SELECTOR, "table.dataTable tbody tr")
                        
                        if len(rows) > 0 and "No data available" not in rows[0].text:
                            for row in rows:
                                cols = row.find_elements(By.TAG_NAME, "td")
                                if len(cols) >= 5: continue # Skip "Not Shown" tables
                                
                                if len(cols) >= 3:
                                    name = cols[0].text.strip()
                                    if not name:
                                        try: name = cols[0].find_element(By.TAG_NAME, "a").text.strip()
                                        except: pass
                                    
                                    if name.lower() in ["coiled coil", "low complexity"]: continue
                                    
                                    s_val = extract_number(cols[1].text)
                                    e_val = extract_number(cols[2].text)
                                    eval_txt = cols[3].text.strip() if len(cols)>3 else "N/A"
                                    
                                    if s_val is not None:
                                        all_results.append({
                                            "Protein_ID": prot_id,
                                            "Feature": name,
                                            "Start": s_val,
                                            "End": e_val,
                                            "E-value": eval_txt
                                        })
                                        valid += 1
                            found = True
                            break
                        
                        if "No domains found" in driver.page_source:
                            found = True
                            break
                    except: time.sleep(1)
                
                if found:
                    df_queue.loc[df_queue['Accession ID'] == prot_id, 'Status'] = '✅ COMPLETED'
                    df_queue.loc[df_queue['Accession ID'] == prot_id, 'Domains'] = valid
                    if valid > 0: log(f"Found {valid} domains.", "SUCCESS")
                    else: log("No domains found.", "WARNING")
                else:
                    df_queue.loc[df_queue['Accession ID'] == prot_id, 'Status'] = '❌ TIMEOUT'
                    
            except Exception as e:
                df_queue.loc[df_queue['Accession ID'] == prot_id, 'Status'] = '❌ FAILED'
                log(f"Error: {str(e)[:40]}", "ERROR")
            
            update_queue_display(q_place, df_queue)

        driver.quit()
        st.success("Analysis Finished.")
        
        # --- EXCEL GÜZELLEŞTİRME VE RENKLENDİRME ---
        if all_results:
            df_final = pd.DataFrame(all_results)
            # Sıralama
            df_final = df_final.sort_values(by=["Protein_ID", "Start"])
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_final.to_excel(writer, index=False, sheet_name='SMART_Domains')
                
                ws = writer.sheets['SMART_Domains']
                
                # Stiller
                # 1. Başlık Stili
                header_font = Font(bold=True, color="FFFFFF")
                header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid") # Koyu Mavi
                
                for cell in ws[1]:
                    cell.font = header_font
                    cell.fill = header_fill
                    cell.alignment = Alignment(horizontal="center")
                
                # 2. Renk Tanımları (Grup Ayrımı İçin)
                fill_color_1 = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid") # Beyaz
                fill_color_2 = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid") # Açık Yeşil/Gri
                
                current_protein = None
                toggle_color = True # True: Beyaz, False: Renkli
                
                # 3. Satır Satır Gez ve Renklendir
                # min_row=2 çünkü başlığı atlıyoruz
                for row in ws.iter_rows(min_row=2, max_col=5):
                    protein_cell = row[0] # Protein_ID sütunu
                    
                    # Eğer protein ID değiştiyse rengi değiştir (Switch)
                    if protein_cell.value != current_protein:
                        current_protein = protein_cell.value
                        toggle_color = not toggle_color
                    
                    # Seçili rengi o satırdaki tüm hücrelere uygula
                    current_fill = fill_color_1 if toggle_color else fill_color_2
                    
                    for cell in row:
                        cell.fill = current_fill
                        cell.border = Border(left=Side(style='thin', color="D3D3D3"), 
                                             right=Side(style='thin', color="D3D3D3"),
                                             bottom=Side(style='thin', color="D3D3D3"))

                # 4. Sütun Genişliklerini Otomatik Ayarla
                for column_cells in ws.columns:
                    length = max(len(str(cell.value)) for cell in column_cells)
                    ws.column_dimensions[get_column_letter(column_cells[0].column)].width = length + 4

            st.divider()
            st.subheader("📊 Organized & Colored Dataset")
            st.dataframe(df_final, use_container_width=True)
            
            st.download_button(
                label="📥 Download Colored Excel (.xlsx)",
                data=output.getvalue(),
                file_name="SMART_Domains_Colored.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("No data.")
