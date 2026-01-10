import streamlit as st
import pandas as pd
import requests
import time
import zipfile
import io
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Phyre2 Scraper Pro", page_icon="🧬", layout="wide")

# --- OTURUM (SESSION) BAŞLATMA ---
if 'processed_data' not in st.session_state:
    st.session_state.processed_data = None
if 'logs' not in st.session_state:
    st.session_state.logs = []
if 'is_finished' not in st.session_state:
    st.session_state.is_finished = False

# --- SELENIUM KURULUMU ---
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

# --- İNDİRME FONKSİYONU ---
def download_content(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, stream=True, timeout=60, headers=headers)
        if r.status_code == 200:
            return r.content
    except:
        return None
    return None

# --- YENİ ANALİZ BUTONU ---
def reset_app():
    st.session_state.processed_data = None
    st.session_state.logs = []
    st.session_state.is_finished = False
    st.rerun()

# --- ARAYÜZ ---
st.title("🧬 Phyre2 Gelişmiş Sonuç Toplayıcı")

# İşlem bittiyse "Yeni Analiz" butonu göster
if st.session_state.is_finished:
    st.warning("⚠️ Mevcut sonuçlar ekranda. Yeni bir dosya yüklemek için aşağıdaki butona basın.")
    st.button("🔄 Yeni Analiz Başlat (Temizle)", on_click=reset_app, type="secondary")

uploaded_file = st.file_uploader("CSV dosyasını yükleyin", type=["csv"], disabled=st.session_state.is_finished)

if uploaded_file and not st.session_state.is_finished:
    df = pd.read_csv(uploaded_file)
    
    if "Result Link" not in df.columns:
        st.error("Hata: 'Result Link' sütunu bulunamadı.")
    else:
        df = df.dropna(subset=["Result Link"])
        df = df[df["Result Link"].str.contains("http")]
        
        st.write(f"**İşlenecek Bağlantı Sayısı:** {len(df)}")
        
        if st.button("🚀 Scraper'ı Başlat", type="primary"):
            
            master_zip_buffer = io.BytesIO()
            progress_bar = st.progress(0)
            status_container = st.empty()
            log_container = st.empty()
            
            logs = []
            driver = None
            
            try:
                with zipfile.ZipFile(master_zip_buffer, "w", zipfile.ZIP_DEFLATED) as master_zip:
                    
                    total = len(df)
                    driver = get_driver()
                    
                    for i, row in df.iterrows():
                        # Protein ID Temizleme (Dosya Adı İçin)
                        protein_id = str(row.get("Protein ID", f"Protein_{i}")).strip()
                        safe_id = protein_id.replace(" ", "_").replace("/", "-") 
                        
                        url = row["Result Link"]
                        folder = f"{safe_id}/"
                        
                        status_container.info(f"⏳ İşleniyor ({i+1}/{total}): {safe_id}")
                        progress_bar.progress((i+1)/total)
                        
                        try:
                            driver.get(url)
                            time.sleep(3) 
                            
                            # Sayfa verilerini al
                            page_source = driver.page_source
                            page_text = driver.find_element(By.TAG_NAME, "body").text
                            
                            # 1. Screenshot Al
                            png_data = driver.get_screenshot_as_png()
                            master_zip.writestr(f"{folder}status_view.png", png_data)
                            
                            # 2. DURUM ANALİZİ
                            is_running = False
                            
                            # Tahmini süre ve Adım okuma
                            time_match = re.search(r"Estimated total processing time.*?:(.*?)(<|\n)", page_source, re.IGNORECASE)
                            step_match = re.search(r"(\d+\.\s+[A-Za-z\s]+)", page_text)
                            
                            if "Job Status" in page_text or "Queue" in page_text:
                                is_running = True
                                est_time = time_match.group(1).strip() if time_match else "Bilinmiyor"
                                step_info = step_match.group(1).strip() if step_match else "Hazırlanıyor"
                                
                                logs.append(f"⏳ {protein_id}: {step_info} | Tahmini Süre: {est_time}")
                            
                            elif "FAILED" in page_text:
                                logs.append(f"❌ {protein_id}: Analiz HATA (Failed) vermiş.")
                                
                            else:
                                # İŞLEM BİTMİŞ
                                logs.append(f"✅ {protein_id}: Tamamlandı. Dosyalar indiriliyor...")
                                
                                elements = driver.find_elements(By.TAG_NAME, "a")
                                zip_url = None
                                pdb_url = None
                                
                                for elem in elements:
                                    href = elem.get_attribute("href")
                                    if href:
                                        # PDB Linki
                                        if ".pdb" in href and "model" in href: 
                                            pdb_url = href
                                        # ZIP/TAR.GZ Linki
                                        elif ("download" in elem.text.lower() or "zip" in href or "tar.gz" in href) and "phyre" in href:
                                            # Görselin altındaki tekli dosyalar yerine paket indirme linkini bulmaya çalış
                                            if ".zip" in href or ".tar.gz" in href:
                                                zip_url = href
                                
                                # --- İNDİRME VE KAYDETME ---
                                
                                # 1. PDB (İsim: Mdom-N-CATPase-05.pdb)
                                if pdb_url:
                                    pdb_data = download_content(pdb_url)
                                    if pdb_data:
                                        master_zip.writestr(f"{folder}{safe_id}.pdb", pdb_data)
                                        logs[-1] += " [PDB İndi]"
                                
                                # 2. Arşiv Dosyası (İsim: Mdom-N-CATPase-05.tar.gz)
                                if zip_url:
                                    zip_data = download_content(zip_url)
                                    if zip_data:
                                        # Uzantı tespiti (tar.gz mi zip mi?)
                                        extension = ".zip" # Varsayılan
                                        if ".tar.gz" in zip_url:
                                            extension = ".tar.gz"
                                        elif ".tgz" in zip_url:
                                            extension = ".tar.gz"
                                            
                                        # Dosyayı yeni ismiyle kaydet
                                        master_zip.writestr(f"{folder}{safe_id}{extension}", zip_data)
                                        logs[-1] += f" [Arşiv İndi: {extension}]"
                                    else:
                                        logs[-1] += " [Arşiv Linki Bozuk]"

                        except Exception as e:
                            logs.append(f"⚠️ {protein_id} Hata: {str(e)}")
                            if "refused" in str(e) or "session" in str(e):
                                try: driver.quit()
                                except: pass
                                driver = get_driver()
                        
                        log_container.code("\n".join(reversed(logs)), language="text")

                if driver: driver.quit()
                
                # Session State Kaydı
                st.session_state.processed_data = master_zip_buffer.getvalue()
                st.session_state.logs = logs
                st.session_state.is_finished = True
                st.rerun()
                
            except Exception as main_e:
                st.error(f"Kritik Hata: {main_e}")
                if driver: driver.quit()

# --- SONUÇ EKRANI ---
if st.session_state.is_finished and st.session_state.processed_data:
    st.success("Tüm işlemler tamamlandı!")
    
    st.write("### 📝 İşlem Özeti")
    st.code("\n".join(reversed(st.session_state.logs)), language="text")
    
    st.download_button(
        label="📦 TOPLU DOSYALARI İNDİR (ZIP)",
        data=st.session_state.processed_data,
        file_name="Phyre2_Results_Pack.zip",
        mime="application/zip",
        type="primary"
    )
