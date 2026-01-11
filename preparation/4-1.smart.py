import streamlit as st
import pandas as pd
from Bio import SeqIO
import io
import time
import sys
import os

# Selenium ve Webdriver Manager
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType
from bs4 import BeautifulSoup

st.set_page_config(page_title="SMART Selenium Analizörü", layout="wide")
st.title("🧬 SMART Analizörü (Cloud Uyumlu Selenium)")

# --- Tarayıcı Ayarları (Kritik Bölüm) ---
def get_driver():
    """
    Streamlit Cloud ve Local ortam için optimize edilmiş Chrome Driver ayarları.
    """
    chrome_options = Options()
    
    # --- Headless Mod (Sunucu için şart) ---
    chrome_options.add_argument("--headless")  # Ekransız çalıştır
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--ignore-certificate-errors")
    
    # User Agent (Bot gibi görünmemek için)
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

    try:
        # Streamlit Cloud üzerinde Chromium genelde bu yollarda olur, kontrol edelim.
        # webdriver-manager otomatik bulmaya çalışacak ama biz ChromeType.CHROMIUM diyerek işi garantiye alıyoruz.
        
        service = Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    except Exception as e:
        st.error(f"Driver başlatılamadı. Hata: {e}")
        return None

# --- Analiz Fonksiyonları ---

def run_smart_analysis(driver, sequences, progress_bar, log_area):
    all_features = []
    
    # 1. Siteye Git ve Mod Seç
    base_url = "https://smart.embl-heidelberg.de/smart/show_motifs.pl"
    
    # Önce Modu Ayarla
    try:
        log_area.info("🌍 SMART sunucusuna bağlanılıyor (Normal Mode)...")
        driver.get("https://smart.embl-heidelberg.de/smart/change_mode.pl?to=NORMAL")
        time.sleep(2)
    except Exception as e:
        log_area.error(f"Mod seçim hatası: {e}")

    # 2. Döngüye Başla
    for i, seq_record in enumerate(sequences):
        prot_id = seq_record.id
        prot_seq = str(seq_record.seq)
        
        log_area.write(f"🧬 İşleniyor: **{prot_id}** ({i+1}/{len(sequences)})")
        
        # URL oluştur ve git
        final_url = f"{base_url}?SEQUENCE={prot_seq}&DO_PFAM=DO_PFAM&INCLUDE_SIGNALP=OFF&INCLUDE_REPEATS=OFF"
        driver.get(final_url)
        
        # Bekleme Mantığı
        attempt = 0
        found = False
        
        while attempt < 15: # Maksimum 30 saniye bekle
            page_source = driver.page_source
            
            # Sonuç geldi mi?
            if "Confidently predicted domains" in page_source:
                # Parse et
                soup = BeautifulSoup(page_source, 'html.parser')
                tables = soup.find_all("table")
                target_table = None
                
                for table in tables:
                    headers = [th.get_text(strip=True) for th in table.find_all("th")]
                    if "Feature" in headers and ("Start" in headers or "Begin" in headers):
                        target_table = table
                        break
                
                if target_table:
                    rows = target_table.find_all("tr")[1:]
                    for row in rows:
                        cols = row.find_all("td")
                        if len(cols) >= 3:
                            f_name = cols[0].get_text(strip=True)
                            if cols[0].find('a'): f_name = cols[0].find('a').get_text(strip=True)
                            start = cols[1].get_text(strip=True)
                            end = cols[2].get_text(strip=True)
                            e_val = cols[3].get_text(strip=True) if len(cols) > 3 else "N/A"
                            
                            if start.isdigit():
                                all_features.append({
                                    "Protein_ID": prot_id,
                                    "Feature": f_name,
                                    "Start": int(start),
                                    "End": int(end),
                                    "E-value": e_val
                                })
                    found = True
                break # While döngüsünden çık
            
            elif "No domains found" in page_source:
                found = True # Boş ama işlem tamam
                break
            
            elif "Select your preferred SMART mode" in page_source:
                 driver.get("https://smart.embl-heidelberg.de/smart/change_mode.pl?to=NORMAL")
                 time.sleep(1)
                 driver.get(final_url)
            
            # Beklemeye devam et
            time.sleep(2)
            attempt += 1
            
        progress_bar.progress((i + 1) / len(sequences))
        
    return all_features

# --- Arayüz ---

uploaded_file = st.file_uploader("Protein FASTA Dosyası", type=["fa", "fasta", "txt"])

if uploaded_file and st.button("🚀 Analizi Başlat"):
    stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
    sequences = list(SeqIO.parse(stringio, "fasta"))
    
    st.info(f"Toplam {len(sequences)} sekans işlenecek. Cloud ortamında Chrome başlatılıyor...")
    
    log_box = st.empty()
    p_bar = st.progress(0)
    
    driver = get_driver()
    
    if driver:
        try:
            results = run_smart_analysis(driver, sequences, p_bar, log_box)
            
            log_box.success("✅ İşlem Tamamlandı!")
            
            if results:
                df = pd.DataFrame(results)
                st.dataframe(df)
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name='SMART_Results')
                
                st.download_button("📥 Excel İndir", output.getvalue(), "smart_sonuclar.xlsx")
            else:
                st.warning("Hiçbir sonuç bulunamadı.")
                
        except Exception as e:
            st.error(f"Bir hata oluştu: {e}")
        finally:
            driver.quit()
