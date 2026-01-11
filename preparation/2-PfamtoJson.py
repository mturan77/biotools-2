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

# --- SESSION STATE BAŞLATMA ---
if 'process_completed' not in st.session_state:
    st.session_state.process_completed = False
if 'report_df' not in st.session_state:
    st.session_state.report_df = None
if 'zip_buffer' not in st.session_state:
    st.session_state.zip_buffer = None
if 'telemetry_logs' not in st.session_state:
    st.session_state.telemetry_logs = []
if 'zip_filename' not in st.session_state:
    st.session_state.zip_filename = "data.zip"

# --- CUSTOM CSS ---
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
# Ana kök dizin
BASE_REPO_DIR = os.path.join(os.getcwd(), "temp_data_repository")

# --- FUNCTIONS ---

def initialize_driver(download_folder_path):
    """
    Sürücüyü başlatırken indirme klasörünü parametre olarak alır.
    Böylece her tür kendi klasörüne iner.
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    
    prefs = {
        "download.default_directory": download_folder_path, # Dinamik klasör yolu
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    driver = webdriver.Chrome(options=chrome_options)
    return driver

def create_archive_bytes_and_cleanup(source_dir):
    """
    Belirtilen klasörü RAM'de zipler ve ardından diskteki klasörü siler.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                # Dosyayı zip'in içine, klasör yapısı olmadan (flat) ekleyelim ki karışıklık olmasın
                # Veya klasörlü isterseniz: arcname=os.path.relpath(os.path.join(root, file), os.path.dirname(source_dir))
                zipf.write(os.path.join(root, file), arcname=file)
    
    buffer.seek(0)
    
    # --- TEMİZLİK KISMI ---
    # Zip işlemi bitti, diskteki dosyaları siliyoruz.
    try:
        shutil.rmtree(source_dir)
        print(f"Temizlik yapıldı: {source_dir} silindi.")
    except Exception as e:
        print(f"Silme hatası: {e}")
        
    return buffer

def get_timestamp():
    return datetime.datetime.now().strftime("[%H:%M:%S]")

def reset_analysis():
    # Session state temizle
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# --- UI HEADER ---
st.title("🧬 InsectBase Otomasyon Paneli")
st.markdown("InsectBase veritabanından toplu genetik veri çekme ve işleme aracı.")
st.divider()

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Veri İçe Aktar")
    uploaded_file = st.file_uploader("Pfam İçeren Dosya (.xlsx)", type=['xlsx', 'xls'])
    
    st.divider()
    
    st.header("2. Arama Parametreleri")
    species_input = st.text_input(
        "Hedef Tür (Bilimsel Ad)", 
        value="musca domestica",
        help="Veritabanı indeksiyle eşleşmelidir."
    )
    
    st.divider()
    
    if st.session_state.process_completed:
        st.warning("⚠️ Yeni bir analiz yapmak için:")
        if st.button("🔄 New Analysis (Sıfırla)", type="secondary"):
            reset_analysis()
    
    st.info("ℹ️ İşlem bulut sunucusunda çalışır. Hız, sunucu yanıt süresine bağlıdır.")

# --- MAIN LOGIC ---
if uploaded_file:
    # Load Data
    try:
        df = pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f"Dosya Okuma Hatası: {e}")
        st.stop()

    cols = df.columns.tolist()
    default_idx = 0
    for i, col in enumerate(cols):
        if any(keyword in str(col).lower() for keyword in ['id', 'seq', 'gen', 'accession']):
            default_idx = i
            break
            
    target_col = st.selectbox("Erişim Kimliği (Accession ID) Sütununu Seçin:", cols, index=default_idx)
    st.divider()

    if not st.session_state.process_completed:
        start_btn = st.button("▶ Start Sequence", type="primary")
        
        if start_btn:
            # --- HAZIRLIK: KLASÖR YAPISI ---
            
            # 1. Tür ismini güvenli klasör adına çevir (boşlukları _ yap)
            safe_species_name = species_input.strip().replace(" ", "_")
            
            # 2. Bu türe özel indirme klasörünü belirle: temp_data_repository/musca_domestica
            current_species_dir = os.path.join(BASE_REPO_DIR, safe_species_name)
            
            # 3. Eğer eski kalıntılar varsa temizle ve yeniden oluştur
            if os.path.exists(current_species_dir):
                shutil.rmtree(current_species_dir)
            os.makedirs(current_species_dir)

            # Dashboard Alanlarını Oluştur
            col_queue, col_telemetry = st.columns([3, 2])
            with col_queue:
                st.subheader("📋 Batch Processing Queue")
                queue_placeholder = st.empty()
            with col_telemetry:
                st.subheader("📟 System Telemetry")
                telemetry_placeholder = st.empty()

            progress_bar = st.progress(0)
            status_container = st.container()

            # Veri Hazırlığı
            total_records = len(df)
            success_count = 0
            temp_report_data = []
            
            queue_df = df[[target_col]].copy()
            queue_df.columns = ["Gene ID"]
            queue_df["Status"] = "WAITING"
            queue_df["Details"] = "-"
            queue_placeholder.dataframe(queue_df, use_container_width=True, hide_index=True)

            logs = []
            logs.append(f"<div class='log-info'>{get_timestamp()} ℹ İşlem klasörü: {safe_species_name}</div>")
            telemetry_placeholder.markdown(f"<div class='telemetry-box'>{''.join(reversed(logs))}</div>", unsafe_allow_html=True)

            # Initialize Driver (ÖZEL KLASÖR YOLU İLE)
            with st.spinner(f"Browser engine başlatılıyor ({safe_species_name} için)..."):
                driver = initialize_driver(current_species_dir)
            
            logs.append(f"<div class='log-success'>{get_timestamp()} ✅ Sürücü hazır.</div>")

            # --- LOOP ---
            for i, row in df.iterrows():
                gene_id = str(row[target_col]).strip()
                
                # Update Queue Visuals
                queue_df.at[i, "Status"] = "⏳ PROCESSING"
                queue_placeholder.dataframe(queue_df, use_container_width=True, hide_index=True)
                
                with status_container:
                    st.info(f"Processing: **{gene_id}** ({i+1}/{total_records})")
                
                encoded_species = urllib.parse.quote(species_input.strip())
                target_url = f"https://www.insect-genome.com/gene/{encoded_species}/{gene_id}"
                
                op_status = "FAILED"
                acquired_filename = "N/A"
                
                try:
                    driver.get(target_url)
                    wait = WebDriverWait(driver, 5)
                    
                    try:
                        export_btn = wait.until(EC.element_to_be_clickable(
                            (By.XPATH, "//button[contains(text(), 'Export JSON')] | //a[contains(text(), 'Export JSON')]")
                        ))
                        
                        # Klasördeki dosya sayısını kontrol et (ÖZEL KLASÖRDE)
                        files_pre = set(os.listdir(current_species_dir))
                        export_btn.click()
                        
                        # Download Verification
                        download_success = False
                        for _ in range(6):
                            time.sleep(1)
                            # Yine sadece o klasöre bakıyoruz
                            if not os.path.exists(current_species_dir): continue
                            
                            files_post = set(os.listdir(current_species_dir))
                            if len(files_post) > len(files_pre):
                                new_files = list(files_post - files_pre)
                                if not new_files[0].endswith('.crdownload'):
                                    acquired_filename = new_files[0]
                                    op_status = "SUCCESS"
                                    download_success = True
                                    success_count += 1
                                    break
                        
                        if download_success:
                            logs.append(f"<div class='log-success'>{get_timestamp()} ℹ {gene_id} OK.</div>")
                        else:
                            logs.append(f"<div class='log-warn'>{get_timestamp()} ⚠️ {gene_id} Timeout.</div>")

                    except:
                        logs.append(f"<div class='log-error'>{get_timestamp()} ❌ {gene_id} Not Found.</div>")
                
                except Exception as e:
                    logs.append(f"<div class='log-error'>{get_timestamp()} ❌ {gene_id} Error.</div>")

                # Update Final Queue Status
                if op_status == "SUCCESS":
                    queue_df.at[i, "Status"] = "✅ COMPLETED"
                else:
                    queue_df.at[i, "Status"] = "❌ FAILED"
                
                queue_placeholder.dataframe(queue_df, use_container_width=True, hide_index=True)
                telemetry_placeholder.markdown(f"<div class='telemetry-box'>{''.join(reversed(logs))}</div>", unsafe_allow_html=True)
                
                temp_report_data.append({
                    "Accession ID": gene_id,
                    "Status": op_status,
                    "Filename": acquired_filename,
                    "Source URL": target_url
                })
                
                progress_bar.progress((i + 1) / total_records)
            
            # --- FINALIZE ---
            driver.quit()
            status_container.empty()
            
            st.session_state.telemetry_logs = logs
            st.session_state.report_df = pd.DataFrame(temp_report_data)
            
            if success_count > 0:
                # ÖZEL FONKSİYON: O klasörü ziple ve sonrasında klasörü SİL.
                st.session_state.zip_buffer = create_archive_bytes_and_cleanup(current_species_dir)
                st.session_state.zip_filename = f"{safe_species_name}_dataset.zip"
            
            st.session_state.process_completed = True
            st.rerun()

    # --- RESULTS SECTION ---
    if st.session_state.process_completed:
        st.success("✅ Sequence Completed.")
        
        # Telemetri Geçmişi
        st.subheader("System Telemetry (History)")
        st.markdown(f"<div class='telemetry-box'>{''.join(reversed(st.session_state.telemetry_logs))}</div>", unsafe_allow_html=True)
        
        st.divider()
        st.subheader("Data Export")
        out_col1, out_col2 = st.columns(2)
        
        # Zip İndirme
        if st.session_state.zip_buffer:
            out_col1.download_button(
                label=f"📦 Download ZIP ({st.session_state.zip_filename})",
                data=st.session_state.zip_buffer,
                file_name=st.session_state.zip_filename,
                mime="application/zip",
                type="primary"
            )
        else:
            out_col1.warning("İndirilebilir veri bulunamadı.")
            
        # Rapor İndirme
        if st.session_state.report_df is not None:
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                st.session_state.report_df.to_excel(writer, index=False)
                
            out_col2.download_button(
                label="📄 Download Log Report (.xlsx)",
                data=buffer.getvalue(),
                file_name="acquisition_report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        # --- GÖRSELLEŞTİRİLMİŞ TABLO (YENİ KISIM) ---
        st.divider()
        st.subheader("Process Summary & Manual Recovery")
        
        if st.session_state.report_df is not None:
            # 1. Tablonun bir kopyasını alıp düzenleyelim
            display_df = st.session_state.report_df.copy()
            
            # 2. Sadece FAILED olanlar için link sütunu oluştur (SUCCESS olanlar boş kalsın)
            # Eğer Status FAILED ise URL'yi koy, değilse None koy
            display_df["Manuel Link"] = display_df.apply(
                lambda row: row["Source URL"] if row["Status"] != "SUCCESS" else None, 
                axis=1
            )
            
            # 3. Görsel Düzenleme (Styler)
            # FAILED olan satırların tamamını kırmızımsı yap
            def highlight_fails(row):
                if row.Status != 'SUCCESS':
                    return ['background-color: #ffe6e6; color: #b30000; font-weight: bold'] * len(row)
                else:
                    return ['color: green'] * len(row)

            # 4. Tabloyu Çizdir (LinkColumn kullanarak)
            st.dataframe(
                display_df.style.apply(highlight_fails, axis=1),
                column_config={
                    "Source URL": None, # Orijinal uzun URL sütununu gizleyelim (kalabalık yapmasın)
                    "Manuel Link": st.column_config.LinkColumn(
                        "Kurtarma Linki",
                        display_text="🔗 Sayfaya Git", # Buton üzerinde yazacak metin
                        help="İndirilemeyen dosyayı manuel indirmek için tıklayın."
                    ),
                    "Status": st.column_config.TextColumn(
                        "Durum",
                        width="small"
                    )
                },
                use_container_width=True,
                hide_index=True
            )

else:
    st.info("Lütfen başlamak için sol menüden bir Pfam İçeren Excel dosyası yükleyin.")
