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
st.set_page_config(page_title="Phyre2 Smart Manager", page_icon="🧬", layout="wide")

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
    driver = get_driver()
    zip_buffer = io.BytesIO()
    success = False
    
    try:
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as single_zip:
            folder = f"{protein_id}/"
            driver.get(url)
            time.sleep(2)
            
            # Screenshot
            try:
                png_data = driver.get_screenshot_as_png()
                single_zip.writestr(f"{folder}status_view.png", png_data)
            except: pass
            
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
            
            found_any = False
            if pdb_url:
                c = download_content(pdb_url)
                if c: 
                    single_zip.writestr(f"{folder}{protein_id}.pdb", c)
                    found_any = True
            
            if zip_url:
                c = download_content(zip_url)
                if c: 
                    ext = ".tar.gz" if ".tar.gz" in zip_url else ".zip"
                    single_zip.writestr(f"{folder}{protein_id}{ext}", c)
                    found_any = True
            
            if found_any:
                success = True
            
    except Exception as e:
        print(e)
    finally:
        driver.quit()
        
    return success, zip_buffer.getvalue()

# --- ANALİZ FONKSİYONU ---
def analyze_page_status(driver, url):
    try:
        driver.get(url)
        time.sleep(1)
        page_source = driver.page_source
        page_text = driver.find_element(By.TAG_NAME, "body").text
        
        time_match = re.search(r"Estimated total processing time.*?:(.*?)(<|\n)", page_source, re.IGNORECASE)
        step_match = re.search(r"(\d+\.\s+[^\n\r]+)", page_text)
        
        status_data = {"status": "Unknown", "details": "-", "est_time": "-", "is_complete": False}

        if "FAILED" in page_text:
            status_data["status"] = "FAILED"; status_data["details"] = "Error"
        elif "Job Status" in page_text or "Queue" in page_text or "Estimated" in page_text:
            if "Download zip of all results" not in page_text:
                status_data["status"] = "RUNNING"
                status_data["est_time"] = time_match.group(1).strip() if time_match else "Calculating..."
                status_data["details"] = step_match.group(1).strip() if step_match else "Init..."
            else:
                status_data["status"] = "COMPLETE"; status_data["details"] = "Ready"; status_data["is_complete"] = True
        else:
            status_data["status"] = "COMPLETE"; status_data["details"] = "Ready"; status_data["is_complete"] = True
            
        return status_data
    except Exception as e:
        return {"status": "ERROR", "details": str(e), "est_time": "-", "is_complete": False}

# --- SESSION STATE (AKILLI HAFIZA) ---
if 'monitor_active' not in st.session_state: st.session_state.monitor_active = False
if 'last_scan_time' not in st.session_state: st.session_state.last_scan_time = None
if 'latest_results_list' not in st.session_state: st.session_state.latest_results_list = []
if 'cycle_count' not in st.session_state: st.session_state.cycle_count = 0

# Dosya Yöneticisi: { 'ProteinID': {'data': binary, 'status': 'saved'/'deleted'} }
if 'file_manager' not in st.session_state: st.session_state.file_manager = {}

# Tamamlanan Görevler Listesi (Tekrar taramamak için)
if 'completed_ids' not in st.session_state: st.session_state.completed_ids = set()

# --- SIDEBAR ---
st.sidebar.title("🎮 Control Panel")
operation_mode = st.sidebar.radio("Select Protocol:", ("🔍 Monitor Mode", "⬇️ Downloader Mode"))

# YENİ ÖZELLİK: Tamamlananları Atla
skip_completed = st.sidebar.checkbox("✅ Bitenleri Tekrar Tarama", value=True, help="İşaretliyse, daha önce bitmiş olan genleri tekrar kontrol etmez.")

st.title("🧬 Phyre2 Smart Manager")

# ==========================================
# AKILLI TABLO ÇİZİCİ
# ==========================================
def render_results_table(data_list, show_buttons=True):
    """
    show_buttons=False -> Tarama sırasında çalışır. Hata vermemesi için butonları gizler.
    show_buttons=True -> Bekleme modunda çalışır. İndirme butonlarını gösterir.
    """
    # Tablo Başlıkları
    h1, h2, h3, h4, h5 = st.columns([2, 1.5, 2, 1, 2.5])
    h1.markdown("**Protein ID**")
    h2.markdown("**Status**")
    h3.markdown("**Current Stage**")
    h4.markdown("**Link**")
    h5.markdown("**File Manager**") 
    st.markdown("---")

    for item in data_list:
        pid = item["Protein ID"]
        safe_pid = pid.replace(" ", "_")
        status = item["Status"]
        
        c1, c2, c3, c4, c5 = st.columns([2, 1.5, 2, 1, 2.5])
        
        c1.write(pid)
        
        # Renkli Durum
        color = "orange" if status == "RUNNING" else "green" if status == "COMPLETE" else "red"
        c2.markdown(f":{color}[{status}]")
        
        c3.write(item["Current Stage"])
        c4.markdown(f"[🔗 Open]({item['Result Link']})")
        
        # --- BUTON YÖNETİMİ ---
        if status == "COMPLETE":
            file_record = st.session_state.file_manager.get(pid)
            
            # --- DURUM 1: İNDİRİLMİŞ VE KAYITLI ---
            if file_record and file_record['status'] == 'saved':
                if show_buttons:
                    btn_col1, btn_col2 = c5.columns([1, 1])
                    btn_col1.download_button(
                        label="💾 İndir",
                        data=file_record['data'],
                        file_name=f"{safe_pid}_result.zip",
                        mime="application/zip",
                        key=f"dl_{safe_pid}"
                    )
                    if btn_col2.button("🗑️ Sil", key=f"del_{safe_pid}"):
                        st.session_state.file_manager[pid]['status'] = 'deleted'
                        st.session_state.file_manager[pid]['data'] = None 
                        st.rerun()
                else:
                    c5.markdown("💾 *Hazır (Saved)*") # Tarama sırasında sadece yazı

            # --- DURUM 2: SİLİNMİŞ ---
            elif file_record and file_record['status'] == 'deleted':
                if show_buttons:
                    c5.write("🗑️ *Silindi*")
                    if c5.button("♻️ Tekrar Çek", key=f"refetch_{safe_pid}"):
                        with st.spinner("Getiriliyor..."):
                            success, data = fetch_single_protein_data(item["Result Link"], safe_pid)
                            if success:
                                st.session_state.file_manager[pid] = {'data': data, 'status': 'saved'}
                                st.rerun()
                else:
                    c5.markdown("🗑️ *Silindi*")

            # --- DURUM 3: HENÜZ İNDİRİLMEMİŞ ---
            else:
                if show_buttons:
                    if c5.button("📥 Getir (Fetch)", key=f"fetch_{safe_pid}"):
                        with st.spinner("Veriler toplanıyor..."):
                            success, data = fetch_single_protein_data(item["Result Link"], safe_pid)
                            if success:
                                st.session_state.file_manager[pid] = {'data': data, 'status': 'saved'}
                                st.rerun()
                            else:
                                st.error("Hata.")
                else:
                    c5.caption("⏳ Bekliyor...") # Tarama sırasında buton yok
        else:
            c5.write("-")

# ==========================================
# MONITOR MODE
# ==========================================
if operation_mode == "🔍 Monitor Mode":
    uploaded_file = st.file_uploader("Upload CSV", type=["csv"], key="monitor_csv")
    refresh_minutes = st.sidebar.slider("Cycle Wait Time (Minutes)", 1, 120, 15)
    
    info_col1, info_col2 = st.columns([3, 1])
    with info_col1:
        st.info(f"⏱️ **Döngü Süresi:** {refresh_minutes} Dakika")
    
    if uploaded_file:
        df = pd.read_csv(uploaded_file)
        
        col1, col2 = st.columns([1, 4])
        with col1:
            if not st.session_state.monitor_active:
                if st.button("▶️ Başlat", type="primary"):
                    st.session_state.monitor_active = True
                    st.session_state.last_scan_time = None
                    st.rerun()
            else:
                if st.button("⏹️ Durdur", type="secondary"):
                    st.session_state.monitor_active = False
                    st.rerun()

        st.divider()

        # --- DÖNGÜ MANTIĞI ---
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
                    # === BEKLEME MODU (BUTONLAR AKTİF) ===
                    # Bu aşamada show_buttons=True olduğu için indirme yapabilirsin
                    seconds_left = (target_wait - time_diff).total_seconds()
                    st.caption(f"⏳ Bir sonraki tarama: {int(seconds_left // 60)}dk {int(seconds_left % 60)}sn")
                    
                    if st.session_state.latest_results_list:
                        render_results_table(st.session_state.latest_results_list, show_buttons=True)
                    
                    time.sleep(1)
                    st.rerun()

            # === TARAMA MODU (BUTONLAR KAPALI) ===
            # Bu aşamada show_buttons=False olduğu için HATA VERMEZ
            if should_scan:
                st.session_state.cycle_count += 1
                
                temp_results_list = [] 
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                table_container = st.empty() 
                
                driver = get_driver()
                try:
                    total_items = len(df)
                    
                    for index, row in df.iterrows():
                        protein_id = str(row.get("Protein ID", f"Protein_{index}")).strip()
                        url = row["Result Link"]
                        
                        # --- SKIP LOGIC (ATLAMAA MANTIĞI) ---
                        if skip_completed and protein_id in st.session_state.completed_ids:
                            # Daha önce bitmişse, siteye gitme, hafızadan yaz
                            temp_results_list.append({
                                "Protein ID": protein_id,
                                "Status": "COMPLETE",
                                "Current Stage": "Hazır (Önbellek)",
                                "Result Link": url
                            })
                            # Çok hızlı geçtiği için anlık bilgi ver
                            status_text.markdown(f"### ⏭️ Atlanıyor ({index+1}/{total_items}): **{protein_id}**")
                            time.sleep(0.05) 
                        
                        else:
                            # --- NORMAL TARAMA ---
                            status_text.markdown(f"### 🔎 Kontrol Ediliyor ({index+1}/{total_items}): **{protein_id}**...")
                            
                            res = analyze_page_status(driver, url)
                            
                            if res["status"] == "COMPLETE":
                                st.session_state.completed_ids.add(protein_id)
                            
                            temp_results_list.append({
                                "Protein ID": protein_id,
                                "Status": res["status"],
                                "Current Stage": res["details"],
                                "Result Link": url
                            })
                        
                        progress_bar.progress((index + 1) / total_items)

                        # TABLOYU GÜNCELLE (BUTONLAR KAPALI)
                        with table_container.container():
                            render_results_table(temp_results_list, show_buttons=False)
                    
                    # Tarama Bitti
                    status_text.success(f"✅ Döngü {st.session_state.cycle_count} Tamamlandı!")
                    time.sleep(1)
                    status_text.empty()
                    
                    st.session_state.latest_results_list = temp_results_list
                    st.session_state.last_scan_time = datetime.now()
                    
                except Exception as e:
                    st.error(f"Scan Error: {e}")
                finally:
                    driver.quit()
                    st.rerun()

# ==========================================
# DOWNLOADER MODE (Toplu İndirme)
# ==========================================
elif operation_mode == "⬇️ Downloader Mode":
    st.info("Bu mod toplu indirme içindir. Tekli yönetim için Monitor modunu kullanın.")
