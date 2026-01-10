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

# --- OTURUM (SESSION) ---
if 'processed_data' not in st.session_state:
    st.session_state.processed_data = None
if 'logs' not in st.session_state:
    st.session_state.logs = []
if 'is_finished' not in st.session_state:
    st.session_state.is_finished = False

# --- SELENIUM ---
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

# --- İNDİRME ---
def download_content(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, stream=True, timeout=60, headers=headers)
        if r.status_code == 200:
            return r.content
    except:
        return None
    return None

# --- SIFIRLAMA ---
def reset_app():
    st.session_state.processed_data = None
    st.session_state.logs = []
    st.session_state.is_finished = False
    st.rerun()

# --- ARAYÜZ ---
st.title("🧬 Phyre2 Kesin Sonuç Toplayıcı")

if st.session_state.is_finished:
    st.warning("⚠️ İşlem tamamlandı. Yeni dosya yüklemek için aşağıdaki butona basın.")
    st.button("🔄 Yeni Analiz Başlat (Temizle)", on_click=reset_app, type="secondary")

uploaded_file = st.file_uploader("CSV dosyasını yükleyin", type=["csv"], disabled=st.session_state.is_finished)

if uploaded_file and not st.session_state.is_finished:
    df = pd.read_csv(uploaded_file)
    
    if "Result Link" not in df.columns:
        st.error("Hata: 'Result Link' sütunu bulunamadı.")
    else:
        df = df.dropna(subset=["Result Link"])
        df = df[df["Result Link"].str.contains("http")]
        
        st.write(f"**İşlenecek Link Sayısı:** {len(df)}")
        
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
                        protein_id = str(row.get("Protein ID", f"Protein_{i}")).strip()
                        safe_id = protein_id.replace(" ", "_").replace("/", "-") 
                        
                        url = row["Result Link"]
                        folder = f"{safe_id}/"
                        
                        status_container.info(f"⏳ Taranıyor ({i+1}/{total}): {safe_id}")
                        progress_bar.progress((i+1)/total)
                        
                        try:
                            driver.get(url)
                            time.sleep(3) 
                            
                            page_source = driver.page_source
                            page_text = driver.find_element(By.TAG_NAME, "body").text
                            
                            # 1. Screenshot
                            png_data = driver.get_screenshot_as_png()
                            master_zip.writestr(f"{folder}status_view.png", png_data)
                            
                            # 2. DURUM KONTROLÜ
                            time_match = re.search(r"Estimated total processing time.*?:(.*?)(<|\n)", page_source, re.IGNORECASE)
                            step_match = re.search(r"(\d+\.\s+[A-Za-z\s]+)", page_text)
                            
                            if "Job Status" in page_text or "Queue" in page_text or "Estimated" in page_text:
                                est_time = time_match.group(1).strip() if time_match else "Hesaplanıyor..."
                                step_info = step_match.group(1).strip() if step_match else "Sırada/Başlıyor"
                                
                                # Eğer gerçekten indirme butonu yoksa bitmemiş say:
                                if "Download zip of all results" not in page_text:
                                    logs.append(f"⏳ {safe_id}: {step_info} | Süre: {est_time}")
                            
                            if "FAILED" in page_text:
                                logs.append(f"❌ {safe_id}: Analiz BAŞARISIZ (Failed).")
                            
                            # 3. LİNKLERİ BUL (ÖNCELİK: final.casp.pdb)
                            elements = driver.find_elements(By.TAG_NAME, "a")
                            zip_url = None
                            pdb_url = None
                            
                            # --- PDB BULMA STRATEJİSİ ---
                            # 1. Öncelik: final.casp.pdb
                            for elem in elements:
                                href = elem.get_attribute("href")
                                if href and "final.casp.pdb" in href:
                                    pdb_url = href
                                    break # En iyisini bulduk, döngüden çık.
                            
                            # 2. Öncelik (Eğer ilki bulunamazsa): final_model.pdb
                            if not pdb_url:
                                for elem in elements:
                                    href = elem.get_attribute("href")
                                    if href and "final_model.pdb" in href:
                                        pdb_url = href
                                        break
                                        
                            # --- ARŞİV (TAR/ZIP) BULMA STRATEJİSİ ---
                            for elem in elements:
                                href = elem.get_attribute("href")
                                if href:
                                    # Kesinlikle .tar.gz olanı bul
                                    if href.endswith(".tar.gz") and "phyre" in href:
                                        zip_url = href
                                        break # Bulduk
                                    # Yoksa .zip olup içinde results geçen
                                    elif href.endswith(".zip") and "results" in href and not zip_url:
                                        zip_url = href

                            # --- İNDİRME İŞLEMİ ---
                            found_files = False
                            status_msg = f"✅ {safe_id}: "
                            
                            # PDB İNDİR (İsim: Mdom-N-CATPase-05.pdb)
                            if pdb_url:
                                p_content = download_content(pdb_url)
                                if p_content:
                                    master_zip.writestr(f"{folder}{safe_id}.pdb", p_content)
                                    status_msg += "[PDB İndi (casp)] "
                                    found_files = True
                                else:
                                    status_msg += "[PDB Hata] "
                            
                            # ARŞİV İNDİR (İsim: Mdom-N-CATPase-05.tar.gz)
                            if zip_url:
                                z_content = download_content(zip_url)
                                if z_content:
                                    ext = ".tar.gz" if ".tar.gz" in zip_url else ".zip"
                                    master_zip.writestr(f"{folder}{safe_id}{ext}", z_content)
                                    status_msg += f"[Arşiv İndi: {ext}]"
                                    found_files = True
                            
                            if found_files:
                                logs.append(status_msg)
                            elif "Job Status" not in page_text:
                                logs.append(f"⚠️ {safe_id}: İşlem bitmiş ama dosyalar bulunamadı.")

                        except Exception as e:
                            logs.append(f"⚠️ {safe_id} Hata: {str(e)}")
                            if "refused" in str(e) or "session" in str(e):
                                try: driver.quit()
                                except: pass
                                driver = get_driver()
                        
                        log_container.code("\n".join(reversed(logs)), language="text")

                if driver: driver.quit()
                
                st.session_state.processed_data = master_zip_buffer.getvalue()
                st.session_state.logs = logs
                st.session_state.is_finished = True
                st.rerun()
                
            except Exception as main_e:
                st.error(f"Kritik Hata: {main_e}")
                if driver: driver.quit()

# --- SONUÇ ---
if st.session_state.is_finished and st.session_state.processed_data:
    st.success("Tüm işlemler tamamlandı!")
    st.write("### 📝 İşlem Özeti")
    st.code("\n".join(reversed(st.session_state.logs)), language="text")
    
    st.download_button(
        label="📦 DOSYALARI İNDİR (ZIP)",
        data=st.session_state.processed_data,
        file_name="Phyre2_Result_Files.zip",
        mime="application/zip",
        type="primary"
    )
