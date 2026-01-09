import streamlit as st
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import urllib.parse
import os
import shutil
import zipfile
import io  # Critical for file buffer handling

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="InsectBase Data Acquisition Tool",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- DIRECTORY MANAGEMENT ---
# Define a temporary repository for downloaded datasets
REPO_DIR = os.path.join(os.getcwd(), "temp_data_repository")

# Clean and recreate the repository to ensure a fresh state
if os.path.exists(REPO_DIR):
    shutil.rmtree(REPO_DIR)
os.makedirs(REPO_DIR)

# --- SELENIUM DRIVER INITIALIZATION ---
def initialize_driver():
    """
    Initializes a headless Chrome driver configured for automated file downloads.
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    
    # Configure download preferences to bypass prompts
    prefs = {
        "download.default_directory": REPO_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    driver = webdriver.Chrome(options=chrome_options)
    return driver

# --- UTILITY: ARCHIVE GENERATION ---
def create_archive(source_dir):
    """
    Compresses the retrieved JSON files into a single ZIP archive.
    """
    archive_name = "genomic_data_archive.zip"
    with zipfile.ZipFile(archive_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                zipf.write(os.path.join(root, file), file)
    return archive_name

# --- UI HEADER & DESCRIPTION ---
st.title("🧬 Automated Insect Genome Data Acquisition Tool")
st.markdown("""
**Abstract:** This utility facilitates the high-throughput retrieval of genomic datasets from the *InsectBase* repository. 
It automates the navigation, extraction, and aggregation of JSON-formatted gene metadata based on provided Accession IDs.

**Methodology:**
1.  **Input:** Accepts an Excel/CSV manifest containing Gene/Sequence IDs.
2.  **Processing:** Iteratively accesses gene profiles via a headless browser engine (Selenium).
3.  **Extraction:** Triggers the asynchronous 'Export JSON' event for each record.
4.  **Output:** Generates a comprehensive ZIP archive and a detailed acquisition report.
""")
st.divider()

# --- SIDEBAR: CONFIGURATION ---
with st.sidebar:
    st.header("1. Data Import")
    uploaded_file = st.file_uploader("Upload Manifest (.xlsx)", type=['xlsx', 'xls'])
    
    st.divider()
    
    st.header("2. Search Parameters")
    species_input = st.text_input(
        "Target Species (Scientific Name)", 
        value="musca domestica",
        help="Ensure the spelling matches the database index (e.g., 'musca domestica')."
    )

    st.info("ℹ️ **Note:** The process runs in the cloud backend. Processing time depends on the number of records and server latency.")

# --- MAIN EXECUTION LOGIC ---
if uploaded_file:
    # Load Data
    try:
        df = pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f"File Parsing Error: {e}")
        st.stop()

    # Column Mapping
    st.subheader("Configuration")
    cols = df.columns.tolist()
    
    # Auto-detect column logic
    default_idx = 0
    for i, col in enumerate(cols):
        if any(keyword in str(col).lower() for keyword in ['id', 'seq', 'gen', 'accession']):
            default_idx = i
            break
            
    col1, col2 = st.columns([1, 2])
    with col1:
        target_col = st.selectbox("Select Accession ID Column:", cols, index=default_idx)
    
    st.divider()

    # Execution Button
    if st.button("🚀 Initialize Batch Extraction", type="primary"):
        
        # UI Elements for Feedback
        progress_bar = st.progress(0)
        status_container = st.empty()
        log_container = st.container()
        
        # Data Containers
        report_data = []
        total_records = len(df)
        success_count = 0
        
        # Initialize Driver
        with st.spinner("Initializing browser engine..."):
            driver = initialize_driver()
        
        # Processing Loop
        status_container.info("Batch processing started...")
        
        for i, row in df.iterrows():
            gene_id = str(row[target_col]).strip()
            
            # URL Encoding
            encoded_species = urllib.parse.quote(species_input.strip())
            target_url = f"https://www.insect-genome.com/gene/{encoded_species}/{gene_id}"
            
            # Update Status
            status_container.markdown(f"**Processing Record {i+1}/{total_records}:** `{gene_id}`")
            
            # Operation Variables
            op_status = "FAILED"
            acquired_filename = "N/A"
            error_detail = "-"
            
            try:
                driver.get(target_url)
                wait = WebDriverWait(driver, 10) # 10s Timeout
                
                # Locate and Click Export Button
                try:
                    # Wait for the button to be interactive
                    export_btn = wait.until(EC.element_to_be_clickable(
                        (By.XPATH, "//button[contains(text(), 'Export JSON')] | //a[contains(text(), 'Export JSON')]")
                    ))
                    
                    # Snapshot of directory before click
                    files_pre = set(os.listdir(REPO_DIR))
                    
                    export_btn.click()
                    
                    # Verify Download (Polling)
                    download_success = False
                    for attempt in range(6): # Poll for 6 seconds
                        time.sleep(1)
                        files_post = set(os.listdir(REPO_DIR))
                        if len(files_post) > len(files_pre):
                            new_files = list(files_post - files_pre)
                            current_file = new_files[0]
                            
                            # Check if download is complete (not .crdownload)
                            if not current_file.endswith('.crdownload'):
                                acquired_filename = current_file
                                op_status = "SUCCESS"
                                download_success = True
                                success_count += 1
                                break
                    
                    if not download_success:
                        error_detail = "Download Timeout (File generation latency)"

                except Exception as e:
                    error_detail = "Export Trigger Not Found / Not Interactive"
            
            except Exception as e:
                error_detail = f"Navigation Error: {str(e)}"
            
            # Append to Report
            report_data.append({
                "Accession ID": gene_id,
                "Acquisition Status": op_status,
                "Filename": acquired_filename,
                "Error Details": error_detail,
                "Source URL": target_url
            })
            
            # Update Progress
            progress_bar.progress((i + 1) / total_records)
        
        # Cleanup
        driver.quit()
        status_container.success(f"✅ Processing Complete. Successfully retrieved **{success_count}** datasets.")
        
        # --- OUTPUT GENERATION ---
        
        st.subheader("Data Export")
        out_col1, out_col2 = st.columns(2)
        
        # 1. Archive Download
        if success_count > 0:
            archive_path = create_archive(REPO_DIR)
            with open(archive_path, "rb") as f:
                out_col1.download_button(
                    label="📦 Download Data Archive (.zip)",
                    data=f,
                    file_name=f"{species_input.replace(' ', '_')}_dataset.zip",
                    mime="application/zip",
                    type="primary",
                    help="Contains all successfully retrieved JSON files."
                )
        else:
            out_col1.warning("No files were retrieved to archive.")

        # 2. Report Download
        report_df = pd.DataFrame(report_data)
        buffer = io.BytesIO()
        
        # Using openpyxl for reliable writing
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            report_df.to_excel(writer, index=False, sheet_name="Acquisition Log")
            
        out_col2.download_button(
            label="📄 Download Acquisition Report (.xlsx)",
            data=buffer.getvalue(),
            file_name="acquisition_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="Detailed log of successes and errors."
        )

        # Preview
        with st.expander("View Acquisition Log", expanded=True):
            st.dataframe(
                report_df.style.map(
                    lambda x: 'color: green; font-weight: bold;' if x == 'SUCCESS' else ('color: red;' if x == 'FAILED' else ''),
                    subset=['Acquisition Status']
                )
            )

else:
    st.info("Please upload a target manifest via the sidebar to begin.")
