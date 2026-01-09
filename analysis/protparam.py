import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import pandas as pd
import io
import time

# --- 1. CONFIGURATION & STYLING ---
st.set_page_config(
    page_title="ProtParam Analyzer",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Session State
if 'results' not in st.session_state:
    st.session_state.results = None
if 'running' not in st.session_state:
    st.session_state.running = False

# CSS: Phyre2 Style (Clean Sidebar & Red Buttons)
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
    /* Metric Cards */
    .metric-container {
        background-color: white;
        padding: 15px;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        text-align: center;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. BACKEND LOGIC ---
def get_driver():
    """Headless Driver for Streamlit Cloud"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    return webdriver.Chrome(options=chrome_options)

def read_fasta(file):
    sequences = []
    content = file.getvalue().decode("utf-8")
    header = None
    sequence = []
    for line in content.splitlines():
        line = line.strip()
        if not line: continue
        if line.startswith(">"):
            if header: sequences.append((header, "".join(sequence)))
            header = line[1:]
            sequence = []
        else: sequence.append(line)
    if header: sequences.append((header, "".join(sequence)))
    return sequences

def scrape_protparam(driver, sequence):
    url = "https://web.expasy.org/protparam/"
    
    # Initialize dictionary with None to prevent KeyError later
    data = {
        "Molecular Weight (Da)": None,
        "Theoretical pI": None,
        "GRAVY": None,
        "Instability Index": None,
        "Error": None
    }
    
    try:
        driver.get(url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "sequence"))).send_keys(sequence)
        driver.find_element(By.XPATH, "//input[@type='submit' and @value='Compute parameters']").click()
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "pre")))
        
        soup = BeautifulSoup(driver.page_source, "html.parser")
        content = soup.find("pre").text
        
        lines = content.split('\n')
        for line in lines:
            if "Molecular weight:" in line: 
                try: data["Molecular Weight (Da)"] = float(line.split("Molecular weight:")[1].strip())
                except: pass
            if "Theoretical pI:" in line: 
                try: data["Theoretical pI"] = float(line.split("Theoretical pI:")[1].strip())
                except: pass
            if "Grand average of hydropathicity (GRAVY):" in line: 
                try: data["GRAVY"] = float(line.split("(GRAVY):")[1].strip())
                except: pass
            if "Instability index:" in line:
                 parts = line.split("Instability index:")
                 if len(parts) > 1: 
                     try: data["Instability Index"] = float(parts[1].split()[0].strip())
                     except: pass
        return data
        
    except Exception as e: 
        data["Error"] = str(e)
        return data

# --- 3. UI LAYOUT ---

# --- SIDEBAR ---
with st.sidebar:
    st.title("⚙️ Control Panel")
    st.markdown("Upload your FASTA file here.")
    
    uploaded_file = st.file_uploader("Select FASTA File", type=["fasta", "fa", "txt"])
    
    if uploaded_file:
        st.write("---")
        if st.button("🚀 Start Analysis"):
            st.session_state.running = True
        
    if st.session_state.results is not None:
        st.write("---")
        if st.button("🔄 Reset Analysis"):
            st.session_state.results = None
            st.rerun()

    st.markdown("---")
    st.caption("ProtParam Automation v1.3 (Stable)")

# --- MAIN PANEL ---
st.title("🧬 ProtParam Automation Tool")
st.markdown("Automated physicochemical property extraction from **ExPASy ProtParam**.")
st.divider()

# Case 1: No File
if not uploaded_file:
    st.info("👈 Please upload a FASTA file from the left sidebar.")

# Case 2: Running
elif st.session_state.running and st.session_state.results is None:
    sequences = read_fasta(uploaded_file)
    results = []
    
    progress_bar = st.progress(0)
    status_box = st.empty()
    
    try:
        with st.spinner('Connecting to ExPASy server...'):
            driver = get_driver()
        
        for i, (header, seq) in enumerate(sequences):
            status_box.markdown(f"**⏳ Processing:** `{header[:40]}...` ({i+1}/{len(sequences)})")
            
            prot_data = scrape_protparam(driver, seq)
            prot_data["Accession ID"] = header.split()[0]
            results.append(prot_data)
            
            progress_bar.progress((i + 1) / len(sequences))
            
        driver.quit()
        st.session_state.results = pd.DataFrame(results)
        st.session_state.running = False
        st.rerun()
        
    except Exception as e:
        st.error(f"System Error: {e}")
        st.session_state.running = False

# Case 3: Results
if st.session_state.results is not None:
    df = st.session_state.results
    
    st.success("✅ Analysis Completed.")
    
    # SAFE METRIC CALCULATION (Prevents KeyError)
    col1, col2, col3, col4 = st.columns(4)
    
    col1.metric("Total Sequences", len(df))
    
    # Calculate means only if columns exist and have data
    if "Molecular Weight (Da)" in df.columns and df["Molecular Weight (Da)"].notna().any():
        mw_mean = df["Molecular Weight (Da)"].mean()
        col2.metric("Mean MW", f"{mw_mean:.0f} Da")
    else:
        col2.metric("Mean MW", "N/A")

    if "Theoretical pI" in df.columns and df["Theoretical pI"].notna().any():
        pi_mean = df["Theoretical pI"].mean()
        col3.metric("Mean pI", f"{pi_mean:.2f}")
    else:
        col3.metric("Mean pI", "N/A")

    if "GRAVY" in df.columns and df["GRAVY"].notna().any():
        gravy_mean = df["GRAVY"].mean()
        col4.metric("Mean GRAVY", f"{gravy_mean:.3f}")
    else:
        col4.metric("Mean GRAVY", "N/A")
    
    st.divider()
    
    tab1, tab2 = st.tabs(["📄 Data Table", "📥 Export"])
    
    with tab1:
        st.dataframe(df.style.highlight_max(axis=0), use_container_width=True)
        
    with tab2:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='ProtParam Results')
        
        st.download_button(
            label="📥 Download Excel Report",
            data=buffer.getvalue(),
            file_name="ProtParam_Results.xlsx",
            mime="application/vnd.ms-excel"
        )
