import streamlit as st
import pandas as pd
from Bio import SeqIO
import io
import time
import datetime
import os

# Selenium Kütüphaneleri
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType
from bs4 import BeautifulSoup

st.set_page_config(page_title="SMART Final Analiz", layout="wide", initial_sidebar_state="collapsed")

# --- CSS: Dashboard Görünümü ---
st.markdown("""
<style>
    .stCodeBlock {border: 1px solid #4CAF50;}
    div[data-testid="stMetricValue"] {font-size: 1.2rem;}
</style>
""", unsafe_allow_html=True)

st.title("🧬 SMART Tam Otomatik Analizör")
st.markdown("Normal Mode > Form Doldurma > Pfam Seçimi > Sonuç Ayrıştırma işlemleri birleştirildi.")

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

# --- Loglama Fonksiyonu ---
def log_telemetry(placeholder, log_history, message, type="info"):
    now = datetime.datetime.now().strftime("%H:%M:%S")
    icon = "✅" if type == "success" else "❌" if type == "error" else "⚠️" if type == "warning" else "ℹ️"
    new_line = f"[{now}] {icon} {message}"
    log_history.insert(0, new_line)
    placeholder.code("\n".join(log_history), language="bash")
    return log_history

# --- ANA İŞLEM FONKSİYONU ---
def process_protein(driver, sequence, protein_id, logs, log_placeholder):
    """
    Tek bir protein için tüm süreci yönetir.
    """
    base_url = "https://smart.embl-heidelberg.de/"
    
    # 1. Siteye Git
    driver.get(base_url)
    
    # 2. MOD KONTROLÜ (Test ettiğimiz yöntem)
    try:
        driver.implicitly_wait(2) # Kısa bekleme
        # href içinde 'mode=normal' geçen linki arıyoruz (CSS Selector)
        normal_mode_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='change_mode.cgi?mode=normal']")
        
        if normal_mode_links:
            logs = log_telemetry(log_placeholder, logs, f"[{protein_id}] Mod seçimi ekranı geçiliyor...", "warning")
            btn = normal_mode_links[0]
            driver.execute_script("arguments[0].scrollIntoView();", btn)
            driver.execute_script("arguments[0].click();", btn)
            time.sleep(2)
    except:
        pass
    finally:
        driver.implicitly_wait(10) # Normale dön

    # 3. FORM DOLDURMA (Pfam ve Sekans)
    try:
        # Pfam Seçimi
        pfam_checkbox = driver.find_element(By.NAME, "DO_PFAM")
        if not pfam_checkbox.is_selected():
            driver.execute_script("arguments[0].click();", pfam_checkbox)
        
        # Sekans Girişi
        seq_box = driver.find_element(By.NAME, "SEQUENCE")
        seq_box.clear()
        seq_box.send_keys(sequence)
        
    except Exception as e:
        logs = log_telemetry(log_placeholder, logs, f"[{protein_id}] Form doldurma hatası: {e}", "error")
        return None, logs

    # 4. BUTONA TIKLA (Analizi Başlat)
    try:
        logs = log_telemetry(log_placeholder, logs, f"[{protein_id}] Analiz başlatılıyor...", "info")
        # 'Sequence SMART' değerine sahip butonu bul
        submit_btn = driver.find_element(By.XPATH, "//input[@value='Sequence SMART']")
        driver.execute_script("arguments[0].click();", submit_btn)
        
    except Exception as e:
        # Alternatif buton arama
        try:
            submit_btn = driver.find_element(By.XPATH, "//button[contains(., 'Sequence SMART')]")
            driver.execute_script("arguments[0].click();", submit_btn)
        except:
            logs = log_telemetry(log_placeholder, logs, f"[{protein_id}] Başlat butonu bulunamadı!", "error")
            return None, logs

    # 5. BEKLEME VE SONUÇ ALMA
    attempt = 0
    max_wait = 60 # 60 saniye bekleme süresi
    
    while attempt < max_wait:
        time.sleep(2) # Her döngüde 2 saniye bekle
        page_source = driver.page_source
        
        # A) Başarılı Sonuç
        if "Confidently predicted domains" in page_source:
            logs = log_telemetry(log_placeholder, logs, f"[{protein_id}] Sonuçlar geldi! Ayrıştırılıyor...", "success")
            
            # Parse Et
            soup = BeautifulSoup(page_source, 'html.parser')
            tables = soup.find_all("table")
            features = []
            
            for table in tables:
                headers = [th.get_text(strip=True) for th in table.find_all("th")]
                if "Feature" in headers and ("Start" in headers or "Begin" in headers):
                    rows = table.find_all("tr")[1:]
                    for row in rows:
                        cols = row.find_all("td")
                        if len(cols) >= 3 and cols[1].get_text(strip=True).isdigit():
                            f_name = cols[0].get_text(strip=True)
                            if cols[0].find('a'): f_name = cols[0].find('a').get_text(strip=True)
                            
                            features.append({
                                "Protein_ID": protein_id,
                                "Feature": f_name,
                                "Start": int(cols[1].get_text(strip=True)),
                                "End": int(cols[2].get_text(strip=True)),
                                "E-value": cols[3].get_text(strip=True) if len(cols)>3 else "N/A"
                            })
                    return features, logs
            return [], logs # Tablo bulunamadı ama sayfa açıldı

        # B) Sonuç Yok (No domains)
        elif "No domains found" in page_source:
            logs = log_telemetry(log_placeholder, logs, f"[{protein_id}] Domain bulunamadı.", "warning")
            return [], logs
            
        # C) Bekleme Ekranı (Job running...)
        elif "Job is running" in page_source or "wait" in page_source.lower():
            # Beklemeye devam et
            pass
        
        attempt += 2

    logs = log_telemetry(log_placeholder, logs, f"[{protein_id}] Zaman aşımı!", "error")
    return None, logs

# --- ARAYÜZ ---

uploaded_file = st.file_uploader("Protein FASTA Dosyası", type=["fa", "fasta", "txt"])

if uploaded_file and st.button("🚀 ÜRETİM ANALİZİNİ BAŞLAT"):
    stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
    sequences = list(SeqIO.parse(stringio, "fasta"))
    
    # Kuyruk Tablosu Hazırlığı
    queue_data = [{"Gene ID": s.id, "Status": "QUEUED", "Result": "-"} for s in sequences]
    df_queue = pd.DataFrame(queue_data)
    
    # Layout
    col1, col2 = st.columns([3, 2])
    with col1:
        st.subheader("İşlem Kuyruğu")
        queue_placeholder = st.empty()
        queue_placeholder.dataframe(df_queue, use_container_width=True, hide_index=True)
    with col2:
        st.subheader("Canlı Loglar")
        log_placeholder = st.empty()
        
    logs = []
    all_results = []
    
    # Driver Başlat
    logs = log_telemetry(log_placeholder, logs, "Chrome Driver başlatılıyor...", "info")
    driver = get_driver()
    
    if driver:
        progress_bar = st.progress(0)
        
        for i, seq_record in enumerate(sequences):
            prot_id = seq_record.id
            prot_seq = str(seq_record.seq)
            
            # Durum Güncelle: PROCESSING
            df_queue.loc[df_queue['Gene ID'] == prot_id, 'Status'] = '⏳ WORKING'
            queue_placeholder.dataframe(df_queue, use_container_width=True, hide_index=True)
            
            # İşlem Yap
            features, logs = process_protein(driver, prot_seq, prot_id, logs, log_placeholder)
            
            # Sonucu İşle
            if features is not None:
                if len(features) > 0:
                    all_results.extend(features)
                    status = "✅ DONE"
                    res_msg = f"{len(features)} Domains"
                else:
                    status = "⚠️ EMPTY"
                    res_msg = "0 Domains"
            else:
                status = "❌ ERROR"
                res_msg = "Failed"
                
            # Durum Güncelle: COMPLETED
            df_queue.loc[df_queue['Gene ID'] == prot_id, 'Status'] = status
            df_queue.loc[df_queue['Gene ID'] == prot_id, 'Result'] = res_msg
            queue_placeholder.dataframe(df_queue, use_container_width=True, hide_index=True)
            
            progress_bar.progress((i + 1) / len(sequences))
            
        driver.quit()
        st.success("Tüm işlemler tamamlandı!")
        
        # EXCEL İNDİRME
        if all_results:
            df_final = pd.DataFrame(all_results)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_final.to_excel(writer, index=False, sheet_name='SMART_Data')
            
            st.download_button(
                label="📥 SONUÇLARI İNDİR (EXCEL)",
                data=output.getvalue(),
                file_name="SMART_Final_Results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("Hiçbir sonuç bulunamadı.")
