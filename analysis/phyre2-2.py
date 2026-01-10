import streamlit as st
import pandas as pd
import requests
import time
import zipfile
import io
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Phyre2 Automated Retrieval System", page_icon="🧬", layout="wide")

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

# --- CORE FUNCTION: ANALYZE STATUS ONLY ---
def analyze_page_status(driver, url):
    """
    Analyzes the page content without downloading files.
    Returns a dictionary with status details.
    """
    try:
        driver.get(url)
        time.sleep(2) # Short wait for DOM
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

        # Logic
        if "FAILED" in page_text:
            status_data["status"] = "FAILED"
            status_data["details"] = "Processing Error Detected"
        
        elif "Job Status" in page_text or "Queue" in page_text or "Estimated" in page_text:
            # Check if download button is missing (Double check for running status)
            if "Download zip of all results" not in page_text:
                status_data["status"] = "RUNNING"
                status_data["est_time"] = time_match.group(1).strip() if time_match else "Calculating..."
                status_data["details"] = step_match.group(1).strip() if step_match else "Initializing..."
            else:
                # Text says status but download button exists -> Actually Complete
                status_data["status"] = "COMPLETE"
                status_data["details"] = "Analysis Finalized"
                status_data["is_complete"] = True
        else:
            # Assume complete if no status text found
            status_data["status"] = "COMPLETE"
            status_data["details"] = "Ready for Retrieval"
            status_data["is_complete"] = True
            
        return status_data

    except Exception as e:
        return {"status": "ERROR", "details": str(e), "est_time": "-", "is_complete": False}

# --- SIDEBAR: MODE SELECTION ---
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
    st.info("This mode monitors the progress of your jobs without downloading files. It auto-refreshes the status table.")
    
    uploaded_file = st.file_uploader("Upload CSV for Monitoring", type=["csv"], key="monitor_csv")
    
    # Refresh Interval Selection
    refresh_rate = st.sidebar.slider("Auto-Refresh Interval (Minutes)", min_value=5, max_value=60, value=15)
    
    if uploaded_file:
        df = pd.read_csv(uploaded_file)
        if "Result Link" in df.columns:
            st.write(f"**Targets Identified:** {len(df)}")
            
            # Start Button
            if st.button("▶️ Initiate Monitoring Loop", type="primary"):
                
                status_placeholder = st.empty()
                log_placeholder = st.empty()
                driver = get_driver()
                
                # Create a container for the dataframe to update in-place
                df_results = pd.DataFrame(columns=["Protein ID", "Status", "Current Stage", "Est. Time", "Last Checked"])
                table_container = st.empty()
                
                try:
                    # Infinite Loop for Monitoring (User stops by closing tab or clicking stop)
                    iteration = 0
                    while True:
                        iteration += 1
                        current_time = datetime.now().strftime("%H:%M:%S")
                        log_placeholder.info(f"🔄 Cycle {iteration}: Scanning started at {current_time}...")
                        
                        temp_results = []
                        
                        for i, row in df.iterrows():
                            protein_id = str(row.get("Protein ID", f"Protein_{i}")).strip()
                            url = row["Result Link"]
                            
                            # Analyze
                            res = analyze_page_status(driver, url)
                            
                            # Add to list
                            temp_results.append({
                                "Protein ID": protein_id,
                                "Status": res["status"],
                                "Current Stage": res["details"],
                                "Est. Time": res["est_time"],
                                "Last Checked": current_time
                            })
                        
                        # Update Table
                        df_results = pd.DataFrame(temp_results)
                        
                        # Styling the dataframe
                        def color_status(val):
                            color = 'black'
                            if val == 'RUNNING': color = 'orange'
                            elif val == 'COMPLETE': color = 'green'
                            elif val == 'FAILED': color = 'red'
                            return f'color: {color}; font-weight: bold'

                        table_container.dataframe(df_results.style.applymap(color_status, subset=['Status']), use_container_width=True)
                        
                        # Wait for next cycle
                        log_placeholder.success(f"✅ Cycle {iteration} complete. Next scan in {refresh_rate} minutes.")
                        time.sleep(refresh_rate * 60)
                        
                except Exception as e:
                    st.error(f"Monitoring Interrupted: {e}")
                    if driver: driver.quit()
                finally:
                    if driver: driver.quit()

# ==========================================
# MODE 2: DOWNLOADER MODE (HARVEST)
# ==========================================
elif operation_mode == "⬇️ Downloader Mode (Harvest)":
    st.markdown("### 📦 Data Acquisition & Packaging Module")
    st.info("This mode executes the final retrieval protocol: downloading PDB/Archive files and generating a Master ZIP.")
    
    # Session State for Download
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
                                # Re-using the analyze function for status check
                                status_res = analyze_page_status(driver, url)
                                
                                # Screenshot (Always take evidence)
                                png_data = driver.get_screenshot_as_png()
                                master_zip.writestr(f"{folder}status_view.png", png_data)
                                
                                if status_res["status"] == "RUNNING":
                                    logs.append(f"⏳ {safe_id}: {status_res['details']} | Time: {status_res['est_time']}")
                                elif status_res["status"] == "FAILED":
                                    logs.append(f"❌ {safe_id}: Analysis FAILED.")
                                else:
                                    # COMPLETE - DOWNLOAD
                                    status_msg = f"✅ {safe_id}: Complete. "
                                    elements = driver.find_elements(By.TAG_NAME, "a")
                                    
                                    # Pinpoint Logic (Same as before)
                                    pdb_url, zip_url = None, None
                                    
                                    # PDB Search
                                    for elem in elements:
                                        href = elem.get_attribute("href")
                                        if href and "final.casp.pdb" in href:
                                            pdb_url = href
                                            break
                                    if not pdb_url:
                                        for elem in elements:
                                            href = elem.get_attribute("href")
                                            if href and "final_model.pdb" in href:
                                                pdb_url = href
                                                break
                                    
                                    # Archive Search
                                    for elem in elements:
                                        href = elem.get_attribute("href")
                                        if href:
                                            if href.endswith(".tar.gz") and "phyre" in href:
                                                zip_url = href
                                                break
                                            elif href.endswith(".zip") and "results" in href and not zip_url:
                                                zip_url = href
                                    
                                    # Actions
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
                                            
                                    if files_found:
                                        logs.append(status_msg)
                                    else:
                                        logs.append(f"⚠️ {safe_id}: Finished but files not found.")

                            except Exception as e:
                                logs.append(f"⚠️ {safe_id} Error: {str(e)}")
                                # Driver recovery logic
                                if "refused" in str(e) or "session" in str(e):
                                    try: driver.quit()
                                    except: pass
                                    driver = get_driver()
                            
                            log_cont.code("\n".join(reversed(logs)), language="text")
                
                    if driver: driver.quit()
                    
                    st.session_state.dl_processed_data = master_zip_buffer.getvalue()
                    st.session_state.dl_logs = logs
                    st.session_state.dl_finished = True
                    st.rerun()

                except Exception as e:
                    st.error(f"Critical Error: {e}")
                    if driver: driver.quit()

    # Results Display
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
