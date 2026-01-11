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
import io
import datetime

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="InsectBase Data Acquisition Protocol",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- SESSION STATE INITIALIZATION ---
# Initialize persistent state variables to handle re-runs and data retention
if 'process_completed' not in st.session_state:
    st.session_state.process_completed = False
if 'report_df' not in st.session_state:
    st.session_state.report_df = None
if 'zip_buffer' not in st.session_state:
    st.session_state.zip_buffer = None
if 'telemetry_logs' not in st.session_state:
    st.session_state.telemetry_logs = []
if 'zip_filename' not in st.session_state:
    st.session_state.zip_filename = "genomic_data.zip"

# --- CUSTOM CSS STYLING ---
st.markdown("""
    <style>
    .stProgress > div > div > div > div {
        background-color: #2b7af1;
    }
    .telemetry-box {
        background-color: #f0f2f6;
        border-radius: 5px;
        padding: 10px;
        font-family: 'Courier New', Courier, monospace;
        font-size: 12px;
        height: 300px;
        overflow-y: auto;
        border: 1px solid #d6d6d6;
    }
    /* Log Levels for Visual Distinction */
    .log-info { color: #0052cc; }
    .log-warn { color: #b38600; }
    .log-success { color: #00703c; }
    .log-error { color: #cc0000; }
    </style>
""", unsafe_allow_html=True)

# --- DIRECTORY MANAGEMENT ---
# Base repository path
BASE_REPO_DIR = os.path.join(os.getcwd(), "temp_data_repository")

# --- UTILITY FUNCTIONS ---

def get_timestamp():
    """Returns current server time formatted for logging."""
    return datetime.datetime.now().strftime("[%H:%M:%S]")

def initialize_driver(download_folder_path):
    """
    Initializes a headless Chrome Selenium driver with a dynamic download path.
    Args:
        download_folder_path (str): The specific directory for the current species.
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    
    prefs = {
        "download.default_directory": download_folder_path,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    driver = webdriver.Chrome(options=chrome_options)
    return driver

def create_archive_bytes_and_cleanup(source_dir):
    """
    Archives the directory content into an in-memory ZIP buffer and 
    immediately deletes the source directory from the disk to ensure hygiene.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                # Add file to zip (flat structure to avoid nesting issues)
                zipf.write(os.path.join(root, file), arcname=file)
    
    buffer.seek(0)
    
    # --- CLEANUP PROCEDURE ---
    try:
        if os.path.exists(source_dir):
            shutil.rmtree(source_dir)
            # print(f"Cleanup Protocol: Directory {source_dir} purged.")
    except Exception as e:
        st.error(f"Cleanup Error: {e}")
        
    return buffer

def reset_analysis():
    """Resets the session state to allow a new analysis cycle."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# --- UI HEADER ---
st.title("🧬 InsectBase Genomic Data Acquisition Protocol")
st.markdown("##### Automated High-Throughput Retrieval System for Insect Genome Database")
st.divider()

# --- SIDEBAR CONFIGURATION ---
with st.sidebar:
    st.header("1. Input Configuration")
    uploaded_file = st.file_uploader("Upload Source File (Excel)", type=['xlsx', 'xls'])
    
    st.divider()
    
    st.header("2. Query Parameters")
    species_input = st.text_input(
        "Target Species (Scientific Binomial)", 
        value="musca domestica",
        help="Must match the exact taxonomic nomenclature used in the database index."
    )
    
    st.divider()
    
    # Reset Button Logic
    if st.session_state.process_completed:
        st.warning("⚠️ System State: Analysis Concluded")
        if st.button("🔄 Initialize New Analysis", type="secondary"):
            reset_analysis()
    
    st.info("ℹ️ **Note:** Processing is dependent on external server latency. Please maintain browser connectivity.")

# --- MAIN EXECUTION LOGIC ---
if uploaded_file:
    # Load and Validate Data
    try:
        df = pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f"File Parsing Error: {e}")
        st.stop()

    # Column Mapping Logic
    cols = df.columns.tolist()
    default_idx = 0
    for i, col in enumerate(cols):
        # Heuristic search for ID columns
        if any(keyword in str(col).lower() for keyword in ['id', 'seq', 'gen', 'accession']):
            default_idx = i
            break
            
    target_col = st.selectbox("Select Accession ID Column:", cols, index=default_idx)
    st.divider()

    # --- EXECUTION BLOCK ---
    if not st.session_state.process_completed:
        start_btn = st.button("▶ Initiate Acquisition Sequence", type="primary")
        
        if start_btn:
            # --- PREPARATION PHASE ---
            
            # 1. Sanitize species name for directory creation
            safe_species_name = species_input.strip().replace(" ", "_")
            
            # 2. Define isolated path: temp_data_repository/Species_Name
            current_species_dir = os.path.join(BASE_REPO_DIR, safe_species_name)
            
            # 3. Purge existing artifacts if any
            if os.path.exists(current_species_dir):
                shutil.rmtree(current_species_dir)
            os.makedirs(current_species_dir)

            # Dashboard Layout
            col_queue, col_telemetry = st.columns([3, 2])
            with col_queue:
                st.subheader("📋 Batch Processing Queue")
                queue_placeholder = st.empty()
            with col_telemetry:
                st.subheader("📟 System Telemetry")
                telemetry_placeholder = st.empty()

            # Progress Indicators
            progress_bar = st.progress(0)
            status_container = st.container()

            # Initialization
            total_records = len(df)
            success_count = 0
            temp_report_data = []
            
            # Queue DataFrame Visualization
            queue_df = df[[target_col]].copy()
            queue_df.columns = ["Gene ID"]
            queue_df["Status"] = "QUEUED"
            queue_df["Details"] = "-"
            queue_placeholder.dataframe(queue_df, use_container_width=True, hide_index=True)

            # Logging
            logs = []
            logs.append(f"<div class='log-info'>{get_timestamp()} ℹ Workspace initialized: {safe_species_name}</div>")
            telemetry_placeholder.markdown(f"<div class='telemetry-box'>{''.join(reversed(logs))}</div>", unsafe_allow_html=True)

            # Driver Initialization
            with st.spinner(f"Initializing Headless Browser Engine for {safe_species_name}..."):
                driver = initialize_driver(current_species_dir)
            
            logs.append(f"<div class='log-success'>{get_timestamp()} ✅ WebDriver handshake established.</div>")

            # --- BATCH PROCESSING LOOP ---
            for i, row in df.iterrows():
                gene_id = str(row[target_col]).strip()
                
                # Visual Update: Processing
                queue_df.at[i, "Status"] = "⏳ PROCESSING"
                queue_placeholder.dataframe(queue_df, use_container_width=True, hide_index=True)
                
                with status_container:
                    st.info(f"Querying Database: **{gene_id}** ({i+1}/{total_records})")
                
                # URL Construction
                encoded_species = urllib.parse.quote(species_input.strip())
                target_url = f"https://www.insect-genome.com/gene/{encoded_species}/{gene_id}"
                
                op_status = "FAILED"
                acquired_filename = "N/A"
                
                try:
                    driver.get(target_url)
                    wait = WebDriverWait(driver, 5) # Timeout threshold
                    
                    try:
                        # Attempt to locate Export Button
                        export_btn = wait.until(EC.element_to_be_clickable(
                            (By.XPATH, "//button[contains(text(), 'Export JSON')] | //a[contains(text(), 'Export JSON')]")
                        ))
                        
                        # Snapshot of directory before click
                        files_pre = set(os.listdir(current_species_dir))
                        export_btn.click()
                        
                        # Payload Verification Loop
                        download_success = False
                        for _ in range(6): # 6 seconds max wait for download
                            time.sleep(1)
                            if not os.path.exists(current_species_dir): continue
                            
                            files_post = set(os.listdir(current_species_dir))
                            if len(files_post) > len(files_pre):
                                new_files = list(files_post - files_pre)
                                # Check if file is fully downloaded (not .crdownload)
                                if not new_files[0].endswith('.crdownload'):
                                    acquired_filename = new_files[0]
                                    op_status = "SUCCESS"
                                    download_success = True
                                    success_count += 1
                                    break
                        
                        if download_success:
                            logs.append(f"<div class='log-success'>{get_timestamp()} ℹ ID {gene_id}: Payload secured.</div>")
                        else:
                            logs.append(f"<div class='log-warn'>{get_timestamp()} ⚠️ ID {gene_id}: Download timeout.</div>")

                    except:
                        logs.append(f"<div class='log-error'>{get_timestamp()} ❌ ID {gene_id}: Element not found / 404.</div>")
                
                except Exception as e:
                    logs.append(f"<div class='log-error'>{get_timestamp()} ❌ ID {gene_id}: Connection Reset.</div>")

                # Visual Update: Final Status
                if op_status == "SUCCESS":
                    queue_df.at[i, "Status"] = "✅ COMPLETED"
                else:
                    queue_df.at[i, "Status"] = "❌ FAILED"
                
                queue_placeholder.dataframe(queue_df, use_container_width=True, hide_index=True)
                telemetry_placeholder.markdown(f"<div class='telemetry-box'>{''.join(reversed(logs))}</div>", unsafe_allow_html=True)
                
                temp_report_data.append({
                    "Accession ID": gene_id,
                    "Status": op_status,
                    "Filename": acquired_filename,
                    "Source URL": target_url
                })
                
                progress_bar.progress((i + 1) / total_records)
            
            # --- FINALIZATION & CLEANUP ---
            driver.quit()
            status_container.empty()
            
            # Persist Data to Session State
            st.session_state.telemetry_logs = logs
            st.session_state.report_df = pd.DataFrame(temp_report_data)
            
            if success_count > 0:
                # Zip the specific species folder to RAM, then delete the folder from Disk
                st.session_state.zip_buffer = create_archive_bytes_and_cleanup(current_species_dir)
                st.session_state.zip_filename = f"{safe_species_name}_genomic_dataset.zip"
            
            # Mark as completed and rerun to render results view
            st.session_state.process_completed = True
            st.rerun()

    # --- RESULTS & EXPORT INTERFACE ---
    if st.session_state.process_completed:
        st.success("✅ Data Acquisition Sequence Completed Successfully.")
        
        # Telemetry Display
        st.subheader("System Telemetry (History)")
        st.markdown(f"<div class='telemetry-box'>{''.join(reversed(st.session_state.telemetry_logs))}</div>", unsafe_allow_html=True)
        
        st.divider()
        st.subheader("Data Export Protocols")
        out_col1, out_col2 = st.columns(2)
        
        # 1. Zip Download
        if st.session_state.zip_buffer:
            out_col1.download_button(
                label=f"📦 Download Dataset ({st.session_state.zip_filename})",
                data=st.session_state.zip_buffer,
                file_name=st.session_state.zip_filename,
                mime="application/zip",
                type="primary",
                help="Contains all JSON files retrieved during this session."
            )
        else:
            out_col1.warning("No downloadable artifacts generated.")
            
        # 2. Report Download
        if st.session_state.report_df is not None:
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                st.session_state.report_df.to_excel(writer, index=False)
                
            out_col2.download_button(
                label="📄 Download Acquisition Report (.xlsx)",
                data=buffer.getvalue(),
                file_name="acquisition_audit_report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                help="Detailed audit log of successful and failed retrievals."
            )

        # --- SUMMARY TABLE WITH MANUAL RECOVERY ---
        st.divider()
        st.subheader("Process Summary & Error Recovery")
        
        if st.session_state.report_df is not None:
            # Prepare Display DataFrame
            display_df = st.session_state.report_df.copy()
            
            # Create Conditional Link Logic
            display_df["Recovery Link"] = display_df.apply(
                lambda row: row["Source URL"] if row["Status"] != "SUCCESS" else None, 
                axis=1
            )
            
            # Styling Function: Highlight Failures
            def style_dataframe(row):
                if row.Status != 'SUCCESS':
                    return ['background-color: #ffe6e6; color: #b30000; font-weight: bold'] * len(row)
                else:
                    return ['color: #0f5132'] * len(row)

            # Render Table
            st.dataframe(
                display_df.style.apply(style_dataframe, axis=1),
                column_config={
                    "Source URL": None, # Hide raw URL
                    "Recovery Link": st.column_config.LinkColumn(
                        "Manual Recovery",
                        display_text="🔗 Open External Link", 
                        help="Click to open the database entry manually for failed retrievals."
                    ),
                    "Status": st.column_config.TextColumn(
                        "Acquisition Status",
                        width="small"
                    ),
                    "Filename": st.column_config.TextColumn(
                        "Artifact Name"
                    )
                },
                use_container_width=True,
                hide_index=True
            )

else:
    st.info("Please upload a Pfam-containing Excel file via the side panel to initialize the protocol.")
