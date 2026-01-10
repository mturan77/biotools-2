import streamlit as st
import pandas as pd
import requests
import time
import zipfile
import io
import re
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Phyre2 Pro Monitor", page_icon="🧬", layout="wide")

# --- UTILS & DRIVER SETUP ---
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

def download_content(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, stream=True, timeout=60, headers=headers)
        if r.status_code == 200:
            return r.content
    except:
        return None
    return None

# --- TEKİL İNDİRME FONKSİYONU ---
def fetch_single_protein_data(url, protein_id):
    """Tek bir protein için indirme işlemini yapar ve zip verisini döner."""
    driver = get_driver()
    zip_buffer = io.BytesIO()
    logs = []
    success = False
    
    try:
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as single_zip:
            folder = f"{protein_id}/"
            
            # Sayfaya git
            driver.get(url)
            time.sleep(2)
            
            # Screenshot al
            png_data = driver.get_screenshot_as_png()
            single_zip.writestr(f"{folder}status_view.png", png_data)
            
            # Linkleri bul
            elements = driver.find_elements(By.TAG_NAME, "a")
            pdb_url, zip_url = None, None
            
            for elem in elements:
                href = elem.get_attribute("href")
                if href and "final.casp.pdb" in href: pdb_url = href; break
            if not pdb_url:
                for elem in elements:
                    href = elem.get_attribute("href")
                    if href and "final_model.pdb" in href: pdb_url = href; break
            
            for elem in elements:
                href = elem.get_attribute("href")
                if href:
                    if href.endswith(".tar.gz") and "phyre" in href: zip_url = href; break
                    elif href.endswith(".zip") and "results" in href and not zip_url: zip_url = href
            
            # Dosyaları indir
            if pdb_url:
                c = download_content(pdb_url)
                if c: single_zip.writestr(f"{folder}{protein_id}.pdb", c)
            
            if zip_url:
                c = download_content(zip_url)
                if c: 
                    ext = ".tar.gz" if ".tar.gz" in zip_url else ".zip"
                    single_zip.writestr(f"{folder}{protein_id}{ext}", c)
            
            success = True
            
    except Exception as e:
        logs.append(str(e))
    finally:
        driver.quit()
        
    return success, zip_buffer.getvalue()

# --- ANALİZ FONKSİYONU ---
def analyze_page_status(driver, url):
    try:
        driver.get(url)
        time.sleep(1.5)
        page_source = driver.page_source
        page_text = driver.find_element(By.TAG_NAME, "body").text
        
        time_match = re.search(r"Estimated total processing time.*?:(.*?)(<|\n)", page_source, re.IGNORECASE)
        step_match = re.search(r"(\d+\.\s+[^\n\r]+)", page_text)
        
        status_data = {"status": "Unknown", "details": "-", "est_time": "-", "is_complete": False}

        if "FAILED" in page_text:
            status_data["status"] = "FAILED"; status_data["details"] = "Error Detected"
        elif "Job Status" in page_text or "Queue" in page_text or "Estimated" in page_text:
            if "Download zip of all results" not in page_text:
                status_data["status"] = "RUNNING"
                status_data["est_time"] = time_match.group(1).strip() if time_match else "Calculating..."
                status_data["details"] = step_match.group(1).strip() if step_match else "Initializing..."
            else:
                status_data["status"] = "COMPLETE"; status_data["details"] = "Ready"; status_data["is_complete"] = True
        else:
            status_data["status"] = "COMPLETE"; status_data["details"] = "Ready"; status_data["is_complete"] = True
            
        return status_data
    except Exception as e:
        return {"status": "ERROR", "details": str(e), "est_time": "-", "is_complete": False}

# --- SESSION STATE ---
if 'monitor_active' not in st.session_state: st.session_state.monitor_active = False
if 'last_scan_time' not in st.session_state: st.session_state.last_scan_time = None
if 'latest_results_list' not in st.session_state: st.session_state.latest_results_list = []
if 'cycle_count' not in st.session_state: st.session_state.cycle_count = 0
if 'download_ready' not in st.session_state: st.session_state.download_ready = {} # ID: Data mapping

# --- SIDEBAR ---
st.sidebar.title("🎮 Control Panel")
operation_mode = st.sidebar.radio("Select Protocol:", ("🔍 Monitor Mode (Watch Only)", "⬇️ Downloader Mode (Harvest)"))

st.title("🧬 Phyre2 Automated Retrieval System")

# ==========================================
# CUSTOM TABLE RENDERER
# ==========================================
def render_results_table(data_list):
    """Verilen listeyi tablo formatında, butonlarla birlikte çizer."""
    # Başlıklar
    h1, h2, h3, h4, h5, h6 = st.columns([2, 1.5, 2, 2, 1, 1.5])
    h1.markdown("**Protein ID**")
    h2.markdown("**Status**")
    h3.markdown("**Current Stage**")
    h4.markdown("**Est. Time**")
    h5.markdown("**Link**")
    h6.markdown("**Action**")
    st.markdown("---")

    for item in data_list:
        c1, c2, c3, c4, c5, c6 = st.columns([2, 1.5, 2, 2, 1, 1.5])
        
        c1.write(item["Protein ID"])
        
        # Renkli Status
        s = item["Status"]
        color = "orange" if s == "RUNNING" else "green" if s == "COMPLETE" else "red"
        c2.markdown(f":{color}[{s}]")
        
        c3.write(item["Current Stage"])
        c4.write(item["Est. Time"])
        c5.markdown(f"[🔗 Link]({item['Result Link']})")
        
        # Aksiyon Butonu
        pid = item["Protein ID"]
        safe_pid = pid.replace(" ", "_")
        
        if s == "COMPLETE":
            # Eğer bu ID için indirme hazırlanmışsa İndir butonu göster, yoksa Fetch butonu
            if pid in st.session_state.download_ready:
                c6.download_button(
                    label="📦 Save",
                    data=st.session_state.download_ready[pid],
                    file_name=f"{safe_pid}_result.zip",
                    mime="application/zip",
                    key=f"dl_final_{pid}"
                )
            else:
                if c6.button("📥 Fetch", key=f"fetch_{pid}"):
                    with st.spinner(f"Harvesting {pid}..."):
                        success, data = fetch_single_protein_data(item["Result Link"], safe_pid)
                        if success:
                            st.session_state.download_ready[pid] = data
                            st.rerun() # Sayfayı yenile ki buton değişsin
                        else:
                            st.error("Failed.")
        else:
            c6.write("-")

# ==========================================
# MODE 1: MONITOR MODE
# ==========================================
if operation_mode == "🔍 Monitor Mode (Watch Only)":
    uploaded_file = st.file_uploader("Upload CSV", type=["csv"], key="monitor_csv")
    refresh_minutes = st.sidebar.slider("Cycle Wait Time (Minutes)", 1, 120, 15)
    
    # --- ÜST BİLGİ PANELİ ---
    info_col1, info_col2 = st.columns([3, 1])
    with info_col1:
        st.info(f"⏱️ **Current Loop Interval:** {refresh_minutes} Minutes")
    
    if uploaded_file:
        df = pd.read_csv(uploaded_file)
        
        col1, col2 = st.columns([1, 4])
        with col1:
            if not st.session_state.monitor_active:
                if st.button("▶️ Start Loop", type="primary"):
                    st.session_state.monitor_active = True
                    st.session_state.last_scan_time = None
                    st.rerun()
            else:
                if st.button("⏹️ Stop Loop", type="secondary"):
                    st.session_state.monitor_active = False
                    st.rerun()

        st.divider()

        # --- MONITOR LOOP ---
        if st.session_state.monitor_active:
            now = datetime.now()
            should_scan = False
            
            if st.session_state.last_scan_time is None:
                should_scan = True
            else:
                time_diff = now - st.session_state.last_scan_time
                target_wait = timedelta(minutes=refresh_minutes)
                
                if time_diff >= target_wait:
                    should_scan = True
                else:
                    # BEKLEME MODU
                    seconds_left = (target_wait - time_diff).total_seconds()
                    st.caption(f"⏳ Next cycle in: {int(seconds_left // 60)}m {int(seconds_left % 60)}s")
                    
                    # Sonuçları göster (Beklerken de tabloyu ve butonları render et)
                    if st.session_state.latest_results_list:
                        render_results_table(st.session_state.latest_results_list)
                    
                    time.sleep(1)
                    st.rerun()

            # --- TARAMA MODU ---
            if should_scan:
                st.session_state.cycle_count += 1
                st.session_state.latest_results_list = [] # Listeyi sıfırla
                
                # İlerleme ve Durum Alanları
                progress_bar = st.progress(0)
                status_text = st.empty() # "Checking..." yazısı için
                table_container = st.empty() # Tablo için
                
                driver = get_driver()
                try:
                    total_items = len(df)
                    
                    # Tablonun boş iskeletini başlat (opsiyonel, veya döngü içinde doldur)
                    
                    for index, row in df.iterrows():
                        protein_id = str(row.get("Protein ID", f"Protein_{index}")).strip()
                        url = row["Result Link"]
                        
                        # 1. "Checking" yazısını güncelle
                        status_text.markdown(f"### 🔎 Checking ({index+1}/{total_items}): **{protein_id}**...")
                        progress_bar.progress((index + 1) / total_items)
                        
                        # 2. Analizi yap
                        res = analyze_page_status(driver, url)
                        
                        # 3. Listeye ekle
                        st.session_state.latest_results_list.append({
                            "Protein ID": protein_id,
                            "Status": res["status"],
                            "Current Stage": res["details"],
                            "Est. Time": res["est_time"],
                            "Result Link": url
                        })
                        
                        # 4. TABLOYU ANINDA GÜNCELLE (Her satır eklendiğinde yeniden çizilir)
                        with table_container.container():
                            render_results_table(st.session_state.latest_results_list)
                    
                    # Döngü bitti
                    status_text.success(f"✅ Cycle {st.session_state.cycle_count} Complete!")
                    time.sleep(1) # Kullanıcı "Complete" yazısını görsün
                    status_text.empty() # Yazıyı kaldır
                    
                    st.session_state.last_scan_time = datetime.now()
                    
                except Exception as e:
                    st.error(f"Scan Error: {e}")
                finally:
                    driver.quit()
                    st.rerun()

# ==========================================
# MODE 2: DOWNLOADER MODE (Aynen korundu)
# ==========================================
elif operation_mode == "⬇️ Downloader Mode (Harvest)":
    # (Bu kısım önceki kodun aynısıdır, değişiklik yapmaya gerek yok)
    st.markdown("### 📦 Data Acquisition & Packaging Module")
    # ... (Downloader kod bloğu buraya gelecek, önceki kodun aynısı) ...
    # Kodu kısaltmak için burayı tekrar kopyalamadım, Downloader modunu değiştirmedik.
    # Eğer istersen orayı da eklerim ama monitor modu isteğinle bağımsız.
    st.info("Switch to Monitor Mode to see the new individual download features.")
