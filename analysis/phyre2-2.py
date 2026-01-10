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
st.set_page_config(page_title="Phyre2 Smart Monitor", page_icon="🧬", layout="wide")

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

# --- CORE FUNCTION: ANALYZE STATUS ---
def analyze_page_status(driver, url):
    try:
        driver.get(url)
        time.sleep(1.5) # Short wait
        page_source = driver.page_source
        page_text = driver.find_element(By.TAG_NAME, "body").text
        
        # Regex Extraction
        time_match = re.search(r"Estimated total processing time.*?:(.*?)(<|\n)", page_source, re.IGNORECASE)
        step_match = re.search(r"(\d+\.\s+[^\n\r]+)", page_text)
        
        status_data = {
            "status": "Unknown",
            "details": "-",
            "est_time": "-",
            "is_complete": False
        }

        if "FAILED" in page_text:
            status_data["status"] = "FAILED"
            status_data["details"] = "Processing Error Detected"
        
        elif "Job Status" in page_text or "Queue" in page_text or "Estimated" in page_text:
            if "Download zip of all results" not in page_text:
                status_data["status"] = "RUNNING"
                status_data["est_time"] = time_match.group(1).strip() if time_match else "Calculating..."
                status_data["details"] = step_match.group(1).strip() if step_match else "Initializing..."
            else:
                status_data["status"] = "COMPLETE"
                status_data["details"] = "Analysis Finalized"
                status_data["is_complete"] = True
        else:
            status_data["status"] = "COMPLETE"
            status_data["details"] = "Ready for Retrieval"
            status_data["is_complete"] = True
            
        return status_data

    except Exception as e:
        return {"status": "ERROR", "details": str(e), "est_time": "-", "is_complete": False}

# --- SESSION STATE INITIALIZATION ---
if 'monitor_active' not in st.session_state: st.session_state.monitor_active = False
if 'last_scan_time' not in st.session_state: st.session_state.last_scan_time = None
if 'latest_results_df' not in st.session_state: st.session_state.latest_results_df = None
if 'cycle_count' not in st.session_state: st.session_state.cycle_count = 0

# --- SIDEBAR ---
st.sidebar.title("🎮 Control Panel")
operation_mode = st.sidebar.radio(
    "Select Operation Protocol:",
    ("🔍 Monitor Mode (Watch Only)", "⬇️ Downloader Mode (Harvest)")
)

st.title("🧬 Phyre2 Automated Retrieval System")

# ==========================================
# MODE 1: MONITOR MODE (WATCH ONLY)
# ==========================================
if operation_mode == "🔍 Monitor Mode (Watch Only)":
    st.markdown("### 📡 Real-time Status Monitoring Dashboard")
    
    # 1. Dosya Yükleme ve Ayarlar
    uploaded_file = st.file_uploader("Upload CSV for Monitoring", type=["csv"], key="monitor_csv")
    
    # Refresh Rate Slider (Dinamik Süre Ayarı için)
    refresh_minutes = st.sidebar.slider("Cycle Wait Time (Minutes)", min_value=1, max_value=120, value=15)
    
    if uploaded_file:
        df = pd.read_csv(uploaded_file)
        if "Result Link" in df.columns:
            st.write(f"**Targets Identified:** {len(df)}")
            
            # Start / Stop Logic
            col1, col2 = st.columns([1, 4])
            with col1:
                if not st.session_state.monitor_active:
                    if st.button("▶️ Start Loop", type="primary"):
                        st.session_state.monitor_active = True
                        st.session_state.last_scan_time = None # Force immediate scan
                        st.rerun()
                else:
                    if st.button("⏹️ Stop Loop", type="secondary"):
                        st.session_state.monitor_active = False
                        st.rerun()
            
            with col2:
                if st.session_state.monitor_active:
                    st.success("🟢 System Active: Monitoring cycle engaged.")
                else:
                    st.info("⚪ System Idle.")

            st.divider()

            # --- MONITORING LOOP LOGIC ---
            if st.session_state.monitor_active:
                
                # Zaman Hesaplaması
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
                        # --- WAITING PHASE (Geri Sayım) ---
                        seconds_left = (target_wait - time_diff).total_seconds()
                        total_seconds = target_wait.total_seconds()
                        progress = max(0.0, min(1.0, 1 - (seconds_left / total_seconds)))
                        
                        st.info(f"⏳ **Next Cycle in:** {int(seconds_left // 60)}m {int(seconds_left % 60)}s")
                        st.progress(progress, text=f"Waiting... (Cycle {st.session_state.cycle_count} complete)")
                        
                        # Son sonuçları bekleme ekranında da göster
                        if st.session_state.latest_results_df is not None:
                            st.subheader("📊 Last Cycle Results")
                            st.dataframe(
                                st.session_state.latest_results_df,
                                column_config={
                                    "Result Link": st.column_config.LinkColumn(
                                        "Phyre2 Link",
                                        display_text="Open Result 🔗"
                                    ),
                                    "Status": st.column_config.TextColumn(
                                        "Status",
                                        help="Current status of the job"
                                    )
                                },
                                use_container_width=True,
                                hide_index=True
                            )
                        
                        # 1 Saniye bekle ve sayfayı yenile (Countdown animasyonu için)
                        time.sleep(1)
                        st.rerun()

                # --- SCANNING PHASE (Tarama) ---
                if should_scan:
                    st.session_state.cycle_count += 1
                    current_cycle = st.session_state.cycle_count
                    
                    # Kullanıcıya taramanın başladığını gösteren alan
                    scan_container = st.status(f"🔄 Cycle {current_cycle}: Scanning {len(df)} proteins...", expanded=True)
                    progress_bar = scan_container.progress(0)
                    
                    results_list = []
                    driver = get_driver()
                    
                    try:
                        total_items = len(df)
                        for index, row in df.iterrows():
                            protein_id = str(row.get("Protein ID", f"Protein_{index}")).strip()
                            url = row["Result Link"]
                            
                            # Ekrana anlık ne yaptığını yaz
                            scan_container.write(f"🔎 Checking ({index+1}/{total_items}): **{protein_id}**")
                            progress_bar.progress((index + 1) / total_items)
                            
                            # Analiz
                            res = analyze_page_status(driver, url)
                            
                            # Listeye ekle
                            results_list.append({
                                "Protein ID": protein_id,
                                "Status": res["status"],
                                "Current Stage": res["details"],
                                "Est. Time": res["est_time"],
                                "Last Checked": datetime.now().strftime("%H:%M:%S"),
                                "Result Link": url
                            })
                            
                        # Tarama bitti
                        st.session_state.last_scan_time = datetime.now()
                        st.session_state.latest_results_df = pd.DataFrame(results_list)
                        
                        scan_container.update(label=f"✅ Cycle {current_cycle} Complete!", state="complete", expanded=False)
                        
                    except Exception as e:
                        st.error(f"Error during scan: {e}")
                    finally:
                        driver.quit()
                        st.rerun()

# ==========================================
# MODE 2: DOWNLOADER MODE (HARVEST)
# ==========================================
elif operation_mode == "⬇️ Downloader Mode (Harvest)":
    st.markdown("### 📦 Data Acquisition & Packaging Module")
    st.info("This mode executes the final retrieval protocol: downloading PDB/Archive files and generating a Master ZIP.")
    
    if 'dl_processed_data' not in st.session_state: st.session_state.dl_processed_data = None
    if 'dl_logs' not in st.session_state: st.session_state.dl_logs = []
    if 'dl_finished' not in st.session_state: st.session_state.dl_finished = False

    def reset_downloader():
        st.session_state.dl_processed_data = None
        st.session_state.dl_logs = []
        st.session_state.dl_finished = False

    if st.session_state.dl_finished:
        st.warning("⚠️ Retrieval sequence complete.")
        st.button("🔄 Reset Downloader", on_click=reset_downloader, type="secondary")

    uploaded_file = st.file_uploader("Upload CSV for Downloading", type=["csv"], key="download_csv", disabled=st.session_state.dl_finished)

    if uploaded_file and not st.session_state.dl_finished:
        df = pd.read_csv(uploaded_file)
        if "Result Link" in df.columns:
            st.write(f"**Targets:** {len(df)}")
            
            if st.button("🚀 Execute Retrieval Protocol", type="primary"):
                master_zip_buffer = io.BytesIO()
                progress_bar = st.progress(0)
                status_cont = st.empty()
                log_cont = st.empty()
                logs = []
                driver = get_driver()
                
                try:
                    with zipfile.ZipFile(master_zip_buffer, "w", zipfile.ZIP_DEFLATED) as master_zip:
                        total = len(df)
                        for i, row in df.iterrows():
                            protein_id = str(row.get("Protein ID", f"Protein_{i}")).strip()
                            safe_id = protein_id.replace(" ", "_").replace("/", "-") 
                            url = row["Result Link"]
                            folder = f"{safe_id}/"
                            
                            status_cont.info(f"⏳ Processing ({i+1}/{total}): {safe_id}")
                            progress_bar.progress((i+1)/total)
                            
                            try:
                                status_res = analyze_page_status(driver, url)
                                png_data = driver.get_screenshot_as_png()
                                master_zip.writestr(f"{folder}status_view.png", png_data)
                                
                                if status_res["status"] == "RUNNING":
                                    logs.append(f"⏳ {safe_id}: {status_res['details']} | Time: {status_res['est_time']}")
                                elif status_res["status"] == "FAILED":
                                    logs.append(f"❌ {safe_id}: Analysis FAILED.")
                                else:
                                    status_msg = f"✅ {safe_id}: Complete. "
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
                                    
                                    files_found = False
                                    if pdb_url:
                                        content = download_content(pdb_url)
                                        if content:
                                            master_zip.writestr(f"{folder}{safe_id}.pdb", content)
                                            status_msg += "[PDB Saved] "
                                            files_found = True
                                    
                                    if zip_url:
                                        content = download_content(zip_url)
                                        if content:
                                            ext = ".tar.gz" if ".tar.gz" in zip_url else ".zip"
                                            master_zip.writestr(f"{folder}{safe_id}{ext}", content)
                                            status_msg += f"[Archive Saved] "
                                            files_found = True
                                            
                                    if files_found: logs.append(status_msg)
                                    else: logs.append(f"⚠️ {safe_id}: Finished but files not found.")

                            except Exception as e:
                                logs.append(f"⚠️ {safe_id} Error: {str(e)}")
                                if "refused" in str(e) or "session" in str(e):
                                    # --- FIX IS HERE ---
                                    try: 
                                        driver.quit()
                                    except: 
                                        pass
                                    driver = get_driver()
                                    # -------------------
                            
                            log_cont.code("\n".join(reversed(logs)), language="text")
                
                    if driver: driver.quit()
                    
                    st.session_state.dl_processed_data = master_zip_buffer.getvalue()
                    st.session_state.dl_logs = logs
                    st.session_state.dl_finished = True
                    st.rerun()

                except Exception as e:
                    st.error(f"Critical Error: {e}")
                    if driver: driver.quit()

    if st.session_state.dl_finished and st.session_state.dl_processed_data:
        st.success("Retrieval Protocol Complete.")
        st.code("\n".join(reversed(st.session_state.dl_logs)), language="text")
        st.download_button(
            label="📦 Download Master Archive (ZIP)",
            data=st.session_state.dl_processed_data,
            file_name="Phyre2_Harvest_Results.zip",
            mime="application/zip",
            type="primary"
        )
