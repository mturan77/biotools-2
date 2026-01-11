import streamlit as st
import pandas as pd
from Bio import SeqIO
import io
import time
import sys
import datetime

# Selenium Kütüphaneleri
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType
from bs4 import BeautifulSoup

st.set_page_config(page_title="SMART Dashboard", layout="wide", initial_sidebar_state="collapsed")

# --- CSS İle Görsel Düzenleme (Opsiyonel: Daha şık görünüm için) ---
st.markdown("""
<style>
    .stCodeBlock {border: 1px solid #4CAF50;}
    div[data-testid="stMetricValue"] {font-size: 1.2rem;}
</style>
""", unsafe_allow_html=True)

st.title("🧬 SMART Analiz Dashboard")
st.markdown("Gerçek zamanlı işlem kuyruğu ve sistem telemetrisi.")

# --- Driver Ayarları ---
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
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    except Exception as e:
        st.error(f"Driver başlatılamadı: {e}")
        return None

# --- Dashboard Fonksiyonları ---

def log_telemetry(placeholder, log_history, message, type="info"):
    """
    Log kutusuna zaman damgalı mesaj ekler.
    """
    now = datetime.datetime.now().strftime("%H:%M:%S")
    
    if type == "success":
        icon = "✅"
    elif type == "error":
        icon = "❌"
    elif type == "warning":
        icon = "⚠️"
    else:
        icon = "ℹ️"
        
    new_line = f"[{now}] {icon} {message}"
    log_history.insert(0, new_line) # En yeniyi en üste ekle
    
    # Ekrana bas (Kod bloğu içinde terminal havası veriyoruz)
    log_text = "\n".join(log_history)
    placeholder.code(log_text, language="bash")
    return log_history

def update_queue_table(placeholder, df):
    """
    Kuyruk tablosunu günceller.
    """
    placeholder.dataframe(df, use_container_width=True, hide_index=True)

# --- Ana İşlem Döngüsü ---

uploaded_file = st.file_uploader("Protein FASTA Dosyası Yükle", type=["fa", "fasta", "txt"])

if uploaded_file and st.button("🚀 Analizi Başlat"):
    # 1. Dosyayı Oku
    stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
    sequences = list(SeqIO.parse(stringio, "fasta"))
    
    # 2. Kuyruk Verisini Hazırla
    queue_data = []
    for s in sequences:
        queue_data.append({"Gene ID": s.id, "Status": "QUEUED", "Details": "-"})
    
    df_queue = pd.DataFrame(queue_data)
    
    # 3. Ekran Düzeni (2 Sütun)
    col1, col2 = st.columns([3, 2]) # Sol taraf (Tablo) daha geniş
    
    with col1:
        st.subheader("📋 Batch Processing Queue")
        queue_table_placeholder = st.empty()
        # İlk tabloyu göster
        update_queue_table(queue_table_placeholder, df_queue)
        
    with col2:
        st.subheader("📟 System Telemetry")
        log_placeholder = st.empty()
        
    # Log geçmişi listesi
    logs = []
    all_features = []
    
    # 4. Driver Başlatılıyor Logu
    logs = log_telemetry(log_placeholder, logs, "Workspace initialized.", "info")
    logs = log_telemetry(log_placeholder, logs, "Initializing WebDriver...", "info")
    
    driver = get_driver()
    
    if driver:
        logs = log_telemetry(log_placeholder, logs, "WebDriver handshake established.", "success")
        
        # Mod Seçimi
        try:
            logs = log_telemetry(log_placeholder, logs, "Setting SMART to 'Normal Mode'...", "warning")
            driver.get("https://smart.embl-heidelberg.de/smart/change_mode.pl?to=NORMAL")
            time.sleep(2)
            logs = log_telemetry(log_placeholder, logs, "Mode configuration synced.", "success")
        except:
            pass

        # İlerleme Çubuğu
        progress_bar = st.progress(0)
        
        # 5. Her Protein İçin Döngü
        base_url = "https://smart.embl-heidelberg.de/smart/show_motifs.pl"
        
        for i, seq_record in enumerate(sequences):
            prot_id = seq_record.id
            prot_seq = str(seq_record.seq)
            
            # --- DURUM GÜNCELLEME: PROCESSING ---
            df_queue.loc[df_queue['Gene ID'] == prot_id, 'Status'] = '⏳ PROCESSING'
            update_queue_table(queue_table_placeholder, df_queue)
            
            logs = log_telemetry(log_placeholder, logs, f"ID {prot_id}: Payload secured. Sending request...", "info")
            
            # Siteye Git
            final_url = f"{base_url}?SEQUENCE={prot_seq}&DO_PFAM=DO_PFAM&INCLUDE_SIGNALP=OFF&INCLUDE_REPEATS=OFF"
            driver.get(final_url)
            
            # Bekleme Mantığı
            attempt = 0
            found = False
            details_msg = "No Domain"
            
            while attempt < 10:
                page_source = driver.page_source
                
                if "Confidently predicted domains" in page_source:
                    logs = log_telemetry(log_placeholder, logs, f"ID {prot_id}: Response received. Parsing HTML...", "success")
                    
                    # Parse İşlemi
                    soup = BeautifulSoup(page_source, 'html.parser')
                    tables = soup.find_all("table")
                    target_table = None
                    for table in tables:
                        headers = [th.get_text(strip=True) for th in table.find_all("th")]
                        if "Feature" in headers:
                            target_table = table
                            break
                    
                    if target_table:
                        count = 0
                        rows = target_table.find_all("tr")[1:]
                        for row in rows:
                            cols = row.find_all("td")
                            if len(cols) >= 3 and cols[1].get_text(strip=True).isdigit():
                                f_name = cols[0].get_text(strip=True)
                                if cols[0].find('a'): f_name = cols[0].find('a').get_text(strip=True)
                                
                                all_features.append({
                                    "Protein_ID": prot_id,
                                    "Feature": f_name,
                                    "Start": int(cols[1].get_text(strip=True)),
                                    "End": int(cols[2].get_text(strip=True)),
                                    "E-value": cols[3].get_text(strip=True) if len(cols)>3 else "N/A"
                                })
                                count += 1
                        
                        details_msg = f"{count} Features"
                        found = True
                    break
                
                elif "No domains found" in page_source:
                    logs = log_telemetry(log_placeholder, logs, f"ID {prot_id}: Analysis complete. No domains found.", "warning")
                    found = True
                    break
                
                elif "Select your preferred SMART mode" in page_source:
                    logs = log_telemetry(log_placeholder, logs, "Mode Selection triggered. Retrying...", "error")
                    driver.get("https://smart.embl-heidelberg.de/smart/change_mode.pl?to=NORMAL")
                    time.sleep(1)
                    driver.get(final_url)
                
                time.sleep(1.5)
                attempt += 1
            
            # --- DURUM GÜNCELLEME: COMPLETED ---
            status_icon = "✅ COMPLETED" if found else "❌ TIMEOUT"
            df_queue.loc[df_queue['Gene ID'] == prot_id, 'Status'] = status_icon
            df_queue.loc[df_queue['Gene ID'] == prot_id, 'Details'] = details_msg
            update_queue_table(queue_table_placeholder, df_queue)
            
            progress_bar.progress((i + 1) / len(sequences))
            
        # Bitiş
        driver.quit()
        logs = log_telemetry(log_placeholder, logs, "All tasks finished. Driver session closed.", "success")
        
        st.success("Tüm Analizler Tamamlandı!")
        
        # Excel İndirme
        if all_features:
            df_res = pd.DataFrame(all_features)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_res.to_excel(writer, index=False, sheet_name='SMART_Results')
            
            st.download_button("📥 Excel İndir", output.getvalue(), "smart_dashboard_results.xlsx")
        else:
            st.warning("Hiçbir sonuç bulunamadı.")
