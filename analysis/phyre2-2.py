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

# --- SELENIUM AYARLARI ---
# @st.cache_resource KULLANMIYORUZ. Scraper işlemlerinde driver'ın taze olması önemlidir.
def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1200")
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except:
        driver = webdriver.Chrome(options=chrome_options)
        
    return driver

# --- DOSYA İNDİRME FONKSİYONU ---
def download_content(url):
    try:
        # User-agent eklemek bazen bağlantı reddini engeller
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        r = requests.get(url, stream=True, timeout=60, headers=headers)
        if r.status_code == 200:
            return r.content
    except Exception as e:
        return None
    return None

# --- DOSYA YÜKLEME ALANI ---
uploaded_file = st.file_uploader("Önceki adımda indirdiğiniz CSV dosyasını yükleyin", type=["csv"])

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    
    if "Result Link" not in df.columns:
        st.error("Hata: CSV dosyasında 'Result Link' sütunu bulunamadı.")
    else:
        df = df.dropna(subset=["Result Link"])
        df = df[df["Result Link"].str.contains("http")]
        
        st.write(f"**İşlenecek Toplam Protein:** {len(df)}")
        
        if st.button("🚀 Scraper'ı Başlat", type="primary"):
            
            master_zip_buffer = io.BytesIO()
            progress_bar = st.progress(0)
            status_text = st.empty()
            log_box = st.expander("Detaylı İşlem Logları", expanded=True)
            logs = []
            
            # Driver'ı başlat
            driver = None
            
            try:
                with zipfile.ZipFile(master_zip_buffer, "w", zipfile.ZIP_DEFLATED) as master_zip:
                    
                    total = len(df)
                    
                    for i, row in df.iterrows():
                        protein_id = str(row.get("Protein ID", f"Protein_{i}")).replace(" ", "_")
                        url = row["Result Link"]
                        folder = f"{protein_id}/"
                        
                        status_text.text(f"Processing ({i+1}/{total}): {protein_id}...")
                        progress_bar.progress((i+1)/total)
                        
                        # --- DRIVER YÖNETİMİ VE HATA TOLERANSI ---
                        try:
                            # Eğer driver çökmüşse veya hiç açılmamışsa yeniden başlat
                            if driver is None:
                                driver = get_driver()

                            # 1. Sayfaya Git
                            driver.get(url)
                            time.sleep(3) # Bekleme süresini biraz artırdık
                            
                            # 2. Screenshot Al
                            png_data = driver.get_screenshot_as_png()
                            master_zip.writestr(f"{folder}view.png", png_data)
                            logs.append(f"✅ {protein_id}: Screenshot alındı.")
                            
                            # 3. Linkleri Bul
                            elements = driver.find_elements(By.TAG_NAME, "a")
                            zip_link = None
                            pdb_link = None
                            
                            for elem in elements:
                                href = elem.get_attribute("href")
                                if href:
                                    if href.endswith(".zip") and "phyre" in href:
                                        zip_link = href
                                    elif "final_model.pdb" in href:
                                        pdb_link = href
                            
                            # 4. İndir
                            if zip_link:
                                z_content = download_content(zip_link)
                                if z_content:
                                    master_zip.writestr(f"{folder}results.zip", z_content)
                            
                            if pdb_link:
                                p_content = download_content(pdb_link)
                                if p_content:
                                    master_zip.writestr(f"{folder}model.pdb", p_content)
                                    
                        except Exception as e:
                            # HATA YÖNETİMİ: Driver hatası ise driver'ı öldür ki sonraki döngüde yenisi açılsın
                            error_msg = str(e)
                            logs.append(f"❌ {protein_id} Hata: {error_msg}")
                            
                            # Eğer bağlantı hatası varsa driver'ı sıfırla
                            if "Connection refused" in error_msg or "disconnected" in error_msg or "invalid session" in error_msg:
                                logs.append("⚠️ Driver bağlantısı koptu, yeniden başlatılıyor...")
                                try:
                                    driver.quit()
                                except:
                                    pass
                                driver = None # Bu değişkeni None yaparak bir sonraki turda yeniden açılmasını sağlıyoruz
                        
                        # Logları güncelle
                        if i % 2 == 0: 
                             log_box.write("\n".join(logs[-10:])) # Sadece son 10 logu göster (performans için)

                status_text.success("Tüm işlemler tamamlandı! Aşağıdan indirebilirsiniz.")
                
                master_zip_buffer.seek(0)
                st.download_button(
                    label="📦 TOPLU İNDİR (ZIP)",
                    data=master_zip_buffer,
                    file_name="Phyre2_Full_Results.zip",
                    mime="application/zip",
                    type="primary"
                )
                
            except Exception as main_e:
                st.error(f"Genel Hata: {main_e}")
            finally:
                # En sonda driver açıksa kapat
                if driver:
                    try:
                        driver.quit()
                    except:
                        pass
