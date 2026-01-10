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

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Phyre2 Automated Retrieval System", page_icon="🧬", layout="wide")

# --- SESSION STATE INITIALIZATION ---
if 'processed_data' not in st.session_state:
    st.session_state.processed_data = None
if 'logs' not in st.session_state:
    st.session_state.logs = []
if 'is_finished' not in st.session_state:
    st.session_state.is_finished = False

# --- SELENIUM DRIVER SETUP ---
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

# --- DOWNLOAD UTILITY ---
def download_content(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        r = requests.get(url, stream=True, timeout=60, headers=headers)
        if r.status_code == 200:
            return r.content
    except:
        return None
    return None

# --- RESET CALLBACK FUNCTION ---
# FIXED: Removed st.rerun() to prevent "no-op" error. 
# Streamlit automatically reruns the script after a callback.
def reset_app():
    st.session_state.processed_data = None
    st.session_state.logs = []
    st.session_state.is_finished = False

# --- UI HEADER ---
st.title("🧬 Phyre2 Automated Retrieval System")
st.markdown("*High-Throughput Protein Structure Modelling Data Harvester*")

# --- CONTROL PANEL ---
if st.session_state.is_finished:
    st.warning("⚠️ Analysis sequence complete. To process a new dataset, please reset the system.")
    # The callback handles the reset, then the script naturally reruns.
    st.button("🔄 Initiate New Analysis Sequence", on_click=reset_app, type="secondary")

uploaded_file = st.file_uploader("Upload Source Data (CSV Format)", type=["csv"], disabled=st.session_state.is_finished)

if uploaded_file and not st.session_state.is_finished:
    df = pd.read_csv(uploaded_file)
    
    if "Result Link" not in df.columns:
        st.error("Error: The uploaded dataset is missing the required 'Result Link' column.")
    else:
        df = df.dropna(subset=["Result Link"])
        df = df[df["Result Link"].str.contains("http")]
        
        st.write(f"**Total Entries for Processing:** {len(df)}")
        
        if st.button("🚀 Execute Scraper Protocol", type="primary"):
            
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
                        
                        # Update status UI
                        status_container.info(f"⏳ Processing Accession ({i+1}/{total}): {safe_id}")
                        progress_bar.progress((i+1)/total)
                        
                        try:
                            driver.get(url)
                            time.sleep(3) 
                            
                            page_source = driver.page_source
                            page_text = driver.find_element(By.TAG_NAME, "body").text
                            
                            # 1. Capture Status Screenshot
                            png_data = driver.get_screenshot_as_png()
                            master_zip.writestr(f"{folder}status_view.png", png_data)
                            
                            # 2. STATUS ANALYSIS (Regex)
                            time_match = re.search(r"Estimated total processing time.*?:(.*?)(<|\n)", page_source, re.IGNORECASE)
                            # Improved Regex: Captures the full line of the step description
                            step_match = re.search(r"(\d+\.\s+[^\n\r]+)", page_text)
                            
                            # Determine if Job is still running
                            if "Job Status" in page_text or "Queue" in page_text or "Estimated" in page_text:
                                est_time = time_match.group(1).strip() if time_match else "Calculating..."
                                
                                if step_match:
                                    step_info = step_match.group(1).strip()
                                else:
                                    step_info = "Initializing Protocol"
                                
                                # Check if download button is absent (confirmation of running status)
                                if "Download zip of all results" not in page_text:
                                    # ACADEMIC FORMAT LOG
                                    logs.append(f"⏳ {safe_id}: Current Protocol Stage: [{step_info}] | Est. Completion: {est_time}")
                            
                            if "FAILED" in page_text:
                                logs.append(f"❌ {safe_id}: Processing FAILED. Check Phyre2 logs.")
                            
                            # 3. FILE RETRIEVAL (Pinpoint Strategy)
                            elements = driver.find_elements(By.TAG_NAME, "a")
                            zip_url = None
                            pdb_url = None
                            
                            # Priority 1: casp-formatted PDB
                            for elem in elements:
                                href = elem.get_attribute("href")
                                if href and "final.casp.pdb" in href:
                                    pdb_url = href
                                    break 
                            
                            # Priority 2: Standard model PDB
                            if not pdb_url:
                                for elem in elements:
                                    href = elem.get_attribute("href")
                                    if href and "final_model.pdb" in href:
                                        pdb_url = href
                                        break
                                        
                            # Archive (TAR.GZ/ZIP) Identification
                            for elem in elements:
                                href = elem.get_attribute("href")
                                if href:
                                    if href.endswith(".tar.gz") and "phyre" in href:
                                        zip_url = href
                                        break 
                                    elif href.endswith(".zip") and "results" in href and not zip_url:
                                        zip_url = href

                            # --- DOWNLOADING SEQUENCE ---
                            found_files = False
                            status_msg = f"✅ {safe_id}: Analysis Complete. "
                            
                            # PDB Download
                            if pdb_url:
                                p_content = download_content(pdb_url)
                                if p_content:
                                    master_zip.writestr(f"{folder}{safe_id}.pdb", p_content)
                                    status_msg += "[PDB Retrieved] "
                                    found_files = True
                                else:
                                    status_msg += "[PDB Error] "
                            
                            # Archive Download
                            if zip_url:
                                z_content = download_content(zip_url)
                                if z_content:
                                    ext = ".tar.gz" if ".tar.gz" in zip_url else ".zip"
                                    master_zip.writestr(f"{folder}{safe_id}{ext}", z_content)
                                    status_msg += f"[Archive Retrieved: {ext}]"
                                    found_files = True
                            
                            if found_files:
                                logs.append(status_msg)
                            elif "Job Status" not in page_text:
                                logs.append(f"⚠️ {safe_id}: Status indicates completion, but output files are ambiguous.")

                        except Exception as e:
                            logs.append(f"⚠️ {safe_id} Exception: {str(e)}")
                            if "refused" in str(e) or "session" in str(e):
                                try: driver.quit()
                                except: pass
                                driver = get_driver()
                        
                        # Real-time Log Update
                        log_container.code("\n".join(reversed(logs)), language="text")

                if driver: driver.quit()
                
                # Update Session State
                st.session_state.processed_data = master_zip_buffer.getvalue()
                st.session_state.logs = logs
                st.session_state.is_finished = True
                st.rerun()
                
            except Exception as main_e:
                st.error(f"Critical System Error: {main_e}")
                if driver: driver.quit()

# --- RESULTS DISPLAY ---
if st.session_state.is_finished and st.session_state.processed_data:
    st.success("Data Retrieval Protocol Successfully Executed.")
    
    st.write("### 📝 Execution Log")
    st.code("\n".join(reversed(st.session_state.logs)), language="text")
    
    st.download_button(
        label="📦 Download Accumulated Results (ZIP)",
        data=st.session_state.processed_data,
        file_name="Phyre2_Final_Results_Pack.zip",
        mime="application/zip",
        type="primary"
    )
