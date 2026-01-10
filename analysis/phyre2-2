import streamlit as st
import pandas as pd
import requests
import time
import zipfile
import io
import re
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Phyre2 Scraper & Downloader", page_icon="🕷️", layout="wide")

st.markdown("""
<style>
    .stProgress > div > div > div > div { background-color: #4CAF50; }
</style>
""", unsafe_allow_html=True)

st.title("🕷️ Phyre2 Sonuç Toplayıcı (Scraper)")
st.info("Bu modül, yüklenen CSV'deki linklere giderek; Screenshot, ZIP ve PDB dosyalarını tek pakette toplar.")

# --- SELENIUM AYARLARI (CLOUD UYUMLU) ---
@st.cache_resource
def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Arayüzsüz mod (Cloud için şart)
    chrome_options.add_argument("--no-sandbox") # Linux container için şart
    chrome_options.add_argument("--disable-dev-shm-usage") # Hafıza yönetimi için şart
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1200")
    
    # Streamlit Cloud üzerinde Chromium genelde bu yollarda olur,
    # ama webdriver_manager da kullanabiliriz. En garantisi budur:
    try:
        # Önce otomatik deniyoruz
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except:
        # Cloud'da bazen manuel path gerekebilir, eğer yukarıdaki çalışmazsa
        # bu bloğu aktifleştirmek gerekebilir ama genelde yukarıdaki yeterlidir.
        # Cloud environment'ında chromium-driver path'i değişebilir.
        driver = webdriver.Chrome(options=chrome_options)
        
    return driver

# --- DOSYA İNDİRME FONKSİYONU ---
def download_content(url, cookies=None):
    """URL'den dosya içeriğini binary olarak çeker"""
    try:
        # Phyre2 bazen session cookie isteyebilir, selenium'dan cookie alıp request'e verebiliriz
        # ama genelde public link verir.
        r = requests.get(url, stream=True, timeout=60)
        if r.status_code == 200:
            return r.content
    except Exception as e:
        return None
    return None

# --- DOSYA YÜKLEME ALANI ---
uploaded_file = st.file_uploader("Önceki adımda indirdiğiniz CSV dosyasını yükleyin", type=["csv"])

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    
    # Gerekli sütun kontrolü
    if "Result Link" not in df.columns:
        st.error("Hata: CSV dosyasında 'Result Link' sütunu bulunamadı.")
    else:
        # Boş linkleri temizle
        df = df.dropna(subset=["Result Link"])
        df = df[df["Result Link"].str.contains("http")]
        
        st.write(f"**İşlenecek Toplam Protein:** {len(df)}")
        
        if st.button("🚀 Scraper'ı Başlat", type="primary"):
            
            # Master ZIP için hafızada yer aç
            master_zip_buffer = io.BytesIO()
            
            # UI Elementleri
            progress_bar = st.progress(0)
            status_text = st.empty()
            log_box = st.expander("Detaylı İşlem Logları", expanded=True)
            
            logs = []
            
            try:
                driver = get_driver()
                
                with zipfile.ZipFile(master_zip_buffer, "w", zipfile.ZIP_DEFLATED) as master_zip:
                    
                    total = len(df)
                    
                    for i, row in df.iterrows():
                        protein_id = str(row.get("Protein ID", f"Protein_{i}")).replace(" ", "_")
                        url = row["Result Link"]
                        
                        # Klasör Adı
                        folder = f"{protein_id}/"
                        
                        status_text.text(f"Processing ({i+1}/{total}): {protein_id}...")
                        progress_bar.progress((i+1)/total)
                        
                        try:
                            # 1. Sayfaya Git
                            driver.get(url)
                            time.sleep(2) # Sayfanın render olması için bekle
                            
                            # 2. Screenshot Al
                            png_data = driver.get_screenshot_as_png()
                            master_zip.writestr(f"{folder}view.png", png_data)
                            logs.append(f"✅ {protein_id}: Screenshot alındı.")
                            
                            # 3. Linkleri Bul (Scraping)
                            # Phyre2 sayfasındaki indirme linklerini buluyoruz
                            elements = driver.find_elements(By.TAG_NAME, "a")
                            
                            zip_link = None
                            pdb_link = None
                            
                            for elem in elements:
                                href = elem.get_attribute("href")
                                if href:
                                    # ZIP Linki (Genelde result.zip veya benzeri biter)
                                    if href.endswith(".zip") and "phyre" in href:
                                        zip_link = href
                                    # PDB Linki (final_model.pdb)
                                    elif "final_model.pdb" in href:
                                        pdb_link = href
                            
                            # 4. Dosyaları İndir ve ZIP'e Ekle
                            if zip_link:
                                z_content = download_content(zip_link)
                                if z_content:
                                    master_zip.writestr(f"{folder}results.zip", z_content)
                                    logs.append(f"  ⬇️ {protein_id}: ZIP indirildi.")
                            
                            if pdb_link:
                                p_content = download_content(pdb_link)
                                if p_content:
                                    master_zip.writestr(f"{folder}model.pdb", p_content)
                                    logs.append(f"  ⬇️ {protein_id}: PDB indirildi.")
                                    
                        except Exception as e:
                            logs.append(f"❌ {protein_id} Hata: {str(e)}")
                            
                        # Logları güncelle
                        if i % 5 == 0: # Her 5 adımda bir logu ekrana bas (performans için)
                             log_box.write("\n".join(logs[-5:]))

                # İşlem Bitti
                driver.quit()
                progress_bar.empty()
                status_text.success("Tüm işlemler tamamlandı! Aşağıdan indirebilirsiniz.")
                
                # İndirme Butonu
                master_zip_buffer.seek(0)
                st.download_button(
                    label="📦 TOPLU İNDİR (ZIP)",
                    data=master_zip_buffer,
                    file_name="Phyre2_Full_Results.zip",
                    mime="application/zip",
                    type="primary"
                )
                
            except Exception as main_e:
                st.error(f"Selenium Driver Başlatılamadı: {main_e}")
                st.warning("Lütfen 'packages.txt' dosyasında 'chromium' ve 'chromium-driver' olduğundan emin olun.")
