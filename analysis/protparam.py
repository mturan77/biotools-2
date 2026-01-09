import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import pandas as pd
import io
import re
import time

# --- 1. CONFIGURATION & STYLING (PHYRE2 DESIGN) ---
st.set_page_config(
    page_title="ProtParam Automation",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Session State
if 'results' not in st.session_state:
    st.session_state.results = None
if 'running' not in st.session_state:
    st.session_state.running = False

# CSS: Clean Sidebar & Red Buttons (Phyre2 Style)
st.markdown("""
    <style>
    /* Sidebar Background */
    [data-testid="stSidebar"] {
        background-color: #f4f6f9;
        border-right: 1px solid #d1d5db;
    }
    /* Primary Red Button */
    div.stButton > button {
        width: 100%;
        background-color: #dc3545;
        color: white;
        border: none;
        padding: 0.6rem;
        font-weight: bold;
        border-radius: 5px;
    }
    div.stButton > button:hover {
        background-color: #bb2d3b;
        color: white;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. BACKEND LOGIC (YOUR WORKING SCRIPT ADAPTED) ---

def get_driver():
    """Streamlit Cloud Compatible Headless Driver"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    return webdriver.Chrome(options=chrome_options)

def read_fasta(file):
    """Reads FASTA from Streamlit UploadedFile object"""
    sequences = []
    content = file.getvalue().decode("utf-8")
    header = None
    sequence = []
    
    for line in content.splitlines():
        line = line.strip()
        if not line: continue
        if line.startswith(">"):
            if header:
                sequences.append((header, "".join(sequence)))
            header = line[1:] # remove >
            sequence = []
        else:
            sequence.append(line)
    if header:
        sequences.append((header, "".join(sequence)))
        
    return sequences

# --- CORE PARSING LOGIC (EXACTLY FROM YOUR SCRIPT) ---
def parse_second_pre_block(page_source):
    soup = BeautifulSoup(page_source, "html.parser")
    pre_blocks = soup.find_all("pre")
    if len(pre_blocks) < 2:
        return ["Error"] * 8

    lines = list(pre_blocks[1].stripped_strings)

    def extract_value(label):
        for i, line in enumerate(lines):
            if label in line:
                if i + 1 < len(lines):
                    return lines[i + 1].replace('"', '').strip()
        return "Error"

    def extract_instability_index():
        for line in lines:
            if "The instability index" in line:
                match = re.search(r"computed to be ([\d.]+)", line)
                return match.group(1) if match else "Error"
        return "Error"

    def extract_stability():
        for line in lines:
            if "This classifies the protein as" in line:
                if "unstable" in line.lower():
                    return "Unstable"
                elif "stable" in line.lower():
                    return "Stable"
        return "Error"

    num_aa = extract_value("Number of amino acids:")
    mw = extract_value("Molecular weight:")
    
    try:
        mw_kda = round(float(mw) / 1000, 3) if mw != "Error" else "Error"
    except:
        mw_kda = "Error"
        
    pI = extract_value("Theoretical pI:")
    instability = extract_instability_index()
    stability = extract_stability()
    aliphatic = extract_value("Aliphatic index:")
    gravy = extract_value("Grand average of hydropathicity")

    return [num_aa, mw, mw_kda, pI, instability, stability, aliphatic, gravy]

def get_protparam_results(driver, sequence):
    driver.get("https://web.expasy.org/protparam/")
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "sequence")))
        textarea = driver.find_element(By.NAME, "sequence")
        textarea.clear()
        textarea.send_keys(sequence)

        submit = driver.find_element(By.XPATH, "//input[@type='submit' and @value='Compute parameters']")
        submit.click()

        WebDriverWait(driver, 15).until(lambda d: "<pre>" in d.page_source)
        return parse_second_pre_block(driver.page_source)
    except Exception as e:
        return ["Error"] * 8

# --- 3. UI LAYOUT (SIDEBAR CONTROLS / MAIN RESULTS) ---

# --- SIDEBAR ---
with st.sidebar:
    st.title("⚙️ Control Panel")
    st.markdown("Upload FASTA file to start.")
    
    # 1. File Upload
    uploaded_file = st.file_uploader("Select FASTA File", type=["fasta", "fa", "txt"])
    
    # 2. Start Button
    if uploaded_file:
        st.write("---")
        if st.button("🚀 Start Analysis"):
            st.session_state.running = True
        
    # Reset Button
    if st.session_state.results is not None:
        st.write("---")
        if st.button("🔄 Reset / New Analysis"):
            st.session_state.results = None
            st.rerun()

    st.markdown("---")
    st.caption("Backend: Custom Parsing Logic")

# --- MAIN PANEL ---
st.title("🧬 ProtParam Automation Tool")
st.markdown("Automated retrieval using your **custom parsing logic**.")
st.divider()

# Case 1: No File
if not uploaded_file:
    st.info("👈 Please upload a FASTA file from the left sidebar.")

# Case 2: Running Analysis
elif st.session_state.running and st.session_state.results is None:
    sequences = read_fasta(uploaded_file)
    results_data = []
    
    progress_bar = st.progress(0)
    status_box = st.empty()
    
    try:
        with st.spinner('Initializing browser...'):
            driver = get_driver()
        
        for i, (header, seq) in enumerate(sequences):
            status_box.markdown(f"**⏳ Processing:** `{header[:40]}...` ({i+1}/{len(sequences)})")
            
            # Use the logic from your script
            row_data = get_protparam_results(driver, seq)
            
            # Create a dictionary row
            entry = {
                "Sequence Name": header,
                "Number of AA": row_data[0],
                "MW (Da)": row_data[1],
                "MW (kDa)": row_data[2],
                "pI": row_data[3],
                "Instability Index": row_data[4],
                "Stability": row_data[5],
                "Aliphatic Index": row_data[6],
                "GRAVY": row_data[7]
            }
            results_data.append(entry)
            
            progress_bar.progress((i + 1) / len(sequences))
            
        driver.quit()
        st.session_state.results = pd.DataFrame(results_data)
        st.session_state.running = False
        st.rerun()
        
    except Exception as e:
        st.error(f"System Error: {e}")
        st.session_state.running = False

# Case 3: Results Display
if st.session_state.results is not None:
    df = st.session_state.results
    
    st.success("✅ Analysis Completed.")
    
    # Display Stats if numeric conversion is possible for mean calculation
    # (Handling errors gracefully)
    try:
        # Convert columns to numeric, coercing errors to NaN
        df["MW (Da)"] = pd.to_numeric(df["MW (Da)"], errors='coerce')
        df["pI"] = pd.to_numeric(df["pI"], errors='coerce')
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Sequences", len(df))
        col2.metric("Mean MW", f"{df['MW (Da)'].mean():.0f} Da")
        col3.metric("Mean pI", f"{df['pI'].mean():.2f}")
    except:
        st.warning("Could not calculate means due to data format.")

    st.divider()
    
    tab1, tab2 = st.tabs(["📄 Data Table", "📥 Export Data"])
    
    with tab1:
        st.dataframe(df, use_container_width=True)
        
    with tab2:
        # Export to Excel
        buffer = io.BytesIO()
        # Using 'openpyxl' engine as you used openpyxl in your script
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='ProtParam Results')
        
        st.download_button(
            label="📥 Download Excel Report",
            data=buffer.getvalue(),
            file_name="ProtParam_Results.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
