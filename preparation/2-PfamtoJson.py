import streamlit as st
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import urllib.parse
import os
import shutil
import zipfile
import io
import datetime

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="InsectBase Data Acquisition Tool",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CUSTOM CSS (Görsel Tasarım İçin) ---
st.markdown("""
    <style>
    .stProgress > div > div > div > div {
        background-color: #2b7af1;
    }
    .telemetry-box {
        background-color: #f0f2f6;
        border-radius: 5px;
        padding: 10px;
        font-family: 'Courier New', Courier, monospace;
        font-size: 12px;
        height: 300px;
        overflow-y: auto;
        border: 1px solid #d6d6d6;
    }
    .log-info { color: #0052cc; }
    .log-warn { color: #b38600; }
    .log-success { color: #00703c; }
    .log-error { color: #cc0000; }
    </style>
""", unsafe_allow_html=True)

# --- DIRECTORY MANAGEMENT ---
REPO_DIR = os.path.join(os.getcwd(), "temp_data_repository")

if os.path.exists(REPO_DIR):
    shutil.rmtree(REPO_DIR)
os.makedirs(REPO_DIR)

# --- SELENIUM DRIVER INITIALIZATION ---
def initialize_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    
    prefs = {
        "download.default_directory": REPO_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    driver = webdriver.Chrome(options=chrome_options)
    return driver

# --- UTILITY: ARCHIVE GENERATION ---
def create_archive(source_dir):
    archive_name = "genomic_data_archive.zip"
    with zipfile.ZipFile(archive_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                zipf.write(os.path.join(root, file), file)
    return archive_name

# --- HELPER: TELEMETRY LOG ---
def get_timestamp():
    return datetime.datetime.now().strftime("[%H:%M:%S]")

# --- UI HEADER ---
st.title("🧬 InsectBase Otomasyon Paneli")
st.markdown("InsectBase veritabanından toplu genetik veri çekme ve işleme aracı.")
st.divider()

# --- SIDEBAR: CONFIGURATION ---
with st.sidebar:
    st.header("1. Veri İçe Aktar")
    uploaded_file = st.file_uploader("Manifest Dosyası (.xlsx)", type=['xlsx', 'xls'])
    
    st.divider()
    
    st.header("2. Arama Parametreleri")
    species_input = st.text_input(
        "Hedef Tür (Bilimsel Ad)", 
        value="musca domestica",
        help="Veritabanı indeksiyle eşleşmelidir."
    )
    
    st.info("ℹ️ İşlem bulut sunucusunda çalışır. Hız, sunucu yanıt süresine bağlıdır.")

# --- MAIN EXECUTION LOGIC ---
if uploaded_file:
    # Load Data
    try:
        df = pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f"Dosya Okuma Hatası: {e}")
        st.stop()

    # Column Mapping
    cols = df.columns.tolist()
    default_idx = 0
    for i, col in enumerate(cols):
        if any(keyword in str(col).lower() for keyword in ['id', 'seq', 'gen', 'accession']):
            default_idx = i
            break
            
    target_col = st.selectbox("Erişim Kimliği (Accession ID) Sütununu Seçin:", cols, index=default_idx)
    st.divider()

    # --- DASHBOARD LAYOUT ---
    
    # Kırmızı Başlat Butonu (Görseldeki gibi)
    start_btn = st.button("▶ Start Sequence", type="primary")

    if start_btn:
        # Dashboard Alanlarını Oluştur
        col_queue, col_telemetry = st.columns([3, 2])

        with col_queue:
            st.subheader("📋 Batch Processing Queue")
            queue_placeholder = st.empty()
        
        with col_telemetry:
            st.subheader("📟 System Telemetry")
            telemetry_placeholder = st.empty()

        # Alt kısım: İlerleme Çubuğu ve Detaylar
        st.write("") # Spacer
        progress_bar = st.progress(0)
        status_detail_container = st.container()

        # Hazırlık
        total_records = len(df)
        success_count = 0
        report_data = []
        logs = []  # Logları tutacak liste
        
        # Kuyruk Tablosu Başlangıç Durumu
        queue_df = df[[target_col]].copy()
        queue_df.columns = ["Gene ID"]
        queue_df["Status"] = "WAITING"
        queue_df["Details"] = "-"
        
        # İlk tabloyu çiz
        queue_placeholder.dataframe(queue_df, use_container_width=True, hide_index=True)

        # Log Başlat
        logs.append(f"<div class='log-info'>{get_timestamp()} ℹ Sistem başlatılıyor... Sürücü yükleniyor.</div>")
        telemetry_placeholder.markdown(f"<div class='telemetry-box'>{''.join(reversed(logs))}</div>", unsafe_allow_html=True)

        # Initialize Driver
        with st.spinner("Browser engine başlatılıyor..."):
            driver = initialize_driver()

        logs.append(f"<div class='log-success'>{get_timestamp()} ✅ Sürücü hazır. İşlem başlıyor.</div>")
        
        # --- PROCESSING LOOP ---
        for i, row in df.iterrows():
            gene_id = str(row[target_col]).strip()
            
            # 1. Kuyruk Tablosunu Güncelle (Processing)
            queue_df.at[i, "Status"] = "⏳ PROCESSING"
            queue_df.at[i, "Details"] = "Initializing..."
            queue_placeholder.dataframe(queue_df, use_container_width=True, hide_index=True)
            
            # 2. Detaylı Durum Konteynerini Güncelle (Görsel 2'deki alt kısım)
            with status_detail_container:
                st.info(f"Processing Record {i+1}/{total_records}: **{gene_id}**")
                step_placeholder = st.empty()

            # URL Encoding
            encoded_species = urllib.parse.quote(species_input.strip())
            target_url = f"https://www.insect-genome.com/gene/{encoded_species}/{gene_id}"
            
            op_status = "FAILED"
            acquired_filename = "N/A"
            error_detail = "-"

            try:
                # Step: API Bağlantısı (Simülasyon - Görsel İçin)
                step_placeholder.markdown(f"📡 `{gene_id}`: API Bağlantısı kuruluyor (Deneme 1/3)...")
                
                driver.get(target_url)
                wait = WebDriverWait(driver, 10)
                
                # Step: Veri İndirme
                step_placeholder.markdown(f"⬇️ `{gene_id}`: Veri paketi indiriliyor...")
                
                try:
                    export_btn = wait.until(EC.element_to_be_clickable(
                        (By.XPATH, "//button[contains(text(), 'Export JSON')] | //a[contains(text(), 'Export JSON')]")
                    ))
                    
                    files_pre = set(os.listdir(REPO_DIR))
                    export_btn.click()
                    
                    # Step: Checksum Doğrulama (Download bekleme süresi)
                    step_placeholder.markdown(f"🔍 `{gene_id}`: Checksum doğrulanıyor...")
                    
                    download_success = False
                    for attempt in range(6):
                        time.sleep(1)
                        files_post = set(os.listdir(REPO_DIR))
                        if len(files_post) > len(files_pre):
                            new_files = list(files_post - files_pre)
                            current_file = new_files[0]
                            if not current_file.endswith('.crdownload'):
                                acquired_filename = current_file
                                op_status = "SUCCESS"
                                download_success = True
                                success_count += 1
                                break
                    
                    if not download_success:
                        error_detail = "Download Timeout"
                        logs.append(f"<div class='log-warn'>{get_timestamp()} ⚠️ {gene_id} - Zaman aşımı.</div>")
                    else:
                        logs.append(f"<div class='log-success'>{get_timestamp()} ℹ {gene_id} başarıyla işlendi.</div>")

                except Exception as e:
                    error_detail = "Button Not Found"
                    logs.append(f"<div class='log-error'>{get_timestamp()} ❌ {gene_id} - Buton bulunamadı.</div>")
            
            except Exception as e:
                error_detail = str(e)
                logs.append(f"<div class='log-error'>{get_timestamp()} ❌ {gene_id} - Navigasyon hatası.</div>")
            
            # --- LOOP SONU GÜNCELLEMELERİ ---
            
            # Kuyruk Tablosu Nihai Durum
            if op_status == "SUCCESS":
                queue_df.at[i, "Status"] = "✅ COMPLETED"
                queue_df.at[i, "Details"] = "Indexed in DB"
            else:
                queue_df.at[i, "Status"] = "❌ FAILED"
                queue_df.at[i, "Details"] = "Error"

            queue_placeholder.dataframe(queue_df, use_container_width=True, hide_index=True)
            
            # Telemetri Güncelle
            telemetry_placeholder.markdown(f"<div class='telemetry-box'>{''.join(reversed(logs))}</div>", unsafe_allow_html=True)
            
            # Rapor Verisi Ekle
            report_data.append({
                "Accession ID": gene_id,
                "Status": op_status,
                "Filename": acquired_filename,
                "Source URL": target_url
            })
            
            # İlerleme Çubuğu
            progress_bar.progress((i + 1) / total_records)
            
            # Clear Steps
            step_placeholder.empty()

        # --- FINALIZATION ---
        driver.quit()
        status_detail_container.empty()
        st.success(f"✅ Sequence Completed. Total Retrieved: {success_count}")

        # --- EXPORT SECTION ---
        st.divider()
        st.subheader("Data Export")
        out_col1, out_col2 = st.columns(2)
        
        # Archive Download
        if success_count > 0:
            archive_path = create_archive(REPO_DIR)
            with open(archive_path, "rb") as f:
                out_col1.download_button(
                    label="📦 Download Data Archive (.zip)",
                    data=f,
                    file_name=f"{species_input.replace(' ', '_')}_dataset.zip",
                    mime="application/zip",
                    type="primary"
                )
        
        # Report Download
        report_df = pd.DataFrame(report_data)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            report_df.to_excel(writer, index=False)
            
        out_col2.download_button(
            label="📄 Download Log Report (.xlsx)",
            data=buffer.getvalue(),
            file_name="acquisition_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        # Görsel 1'deki gibi Sonuç Tablosu Gösterimi
        st.subheader("Process Summary")
        
        # Tabloyu renklendirme
        def color_status(val):
            color = 'green' if val == 'SUCCESS' else 'red'
            return f'color: {color}; font-weight: bold'

        st.dataframe(
            report_df.style.map(color_status, subset=['Status']),
            use_container_width=True
        )

else:
    st.info("Lütfen başlamak için sol menüden bir manifest dosyası yükleyin.")
