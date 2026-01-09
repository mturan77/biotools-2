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
from datetime import datetime

# --- 1. CONFIGURATION & STATE MANAGEMENT ---
st.set_page_config(
    page_title="ProtParam Automation Tool",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize Session State for Data Persistence
if 'results' not in st.session_state:
    st.session_state.results = None
if 'history' not in st.session_state:
    st.session_state.history = []

# --- 2. CUSTOM CSS (PHYRE2 STYLE) ---
st.markdown("""
    <style>
    /* Sidebar Styling */
    [data-testid="stSidebar"] {
        background-color: #f4f6f9;
        border-right: 1px solid #e0e0e0;
    }
    
    /* Primary Button (Red/Pink like Phyre2) */
    div.stButton > button:first-child {
        background-color: #ff4b4b;
        color: white;
        border-radius: 6px;
        border: none;
        font-weight: 600;
        padding: 0.5rem 1rem;
    }
    div.stButton > button:first-child:hover {
        background-color: #ff3333;
        color: white;
    }

    /* Secondary Buttons (Gray) */
    .secondary-button {
        background-color: #6c757d;
    }

    /* Card Styling */
    .css-1r6slb0 {
        background-color: white;
        padding: 2rem;
        border-radius: 10px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
    }
    
    /* Header Styling */
    h1 {
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        color: #2c3e50;
        font-weight: 700;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 3. SELENIUM BACKEND ---
def get_driver():
    """Headless Chrome Driver for Streamlit Cloud."""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
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
    driver.get(url)
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "sequence"))).send_keys(sequence)
        driver.find_element(By.XPATH, "//input[@type='submit' and @value='Compute parameters']").click()
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "pre")))
        soup = BeautifulSoup(driver.page_source, "html.parser")
        content = soup.find("pre").text
        
        data = {}
        lines = content.split('\n')
        for line in lines:
            if "Molecular weight:" in line: data["Molecular Weight (Da)"] = float(line.split("Molecular weight:")[1].strip())
            if "Theoretical pI:" in line: data["Theoretical pI"] = float(line.split("Theoretical pI:")[1].strip())
            if "Grand average of hydropathicity (GRAVY):" in line: data["GRAVY"] = float(line.split("(GRAVY):")[1].strip())
            if "Instability index:" in line:
                 parts = line.split("Instability index:")
                 if len(parts) > 1: data["Instability Index"] = float(parts[1].split()[0].strip())
        return data
    except Exception as e: return {"Error": str(e)}

# --- 4. SIDEBAR (CONTROLS) ---
with st.sidebar:
    # 4.1. Reset Button
    if st.button("🔄 New Analysis / Reset", use_container_width=True):
        st.session_state.results = None
        st.experimental_rerun()

    st.markdown("---")
    
    # 4.2. Analysis History (Visual Mockup)
    st.markdown("#### 📂 Analysis Sessions")
    if len(st.session_state.history) == 0:
        st.caption("No history available.")
    else:
        for item in st.session_state.history[-3:]: # Show last 3
            st.text(f"🕒 {item}")

    st.markdown("---")

    # 4.3. Configuration
    st.markdown("#### ⚙️ Configuration")
    user_email = st.text_input("E-mail Address (Optional)", placeholder="researcher@university.edu")
    
    analysis_mode = st.selectbox("Analysis Mode", ["Standard (ProtParam)", "Deep Scan (Future Dev)"])
    
    st.radio("User Type", ["Academic", "Commercial"], index=0)
    
    delay_sec = st.number_input("Request Delay (sec)", min_value=0.5, value=1.0, step=0.5)

# --- 5. MAIN PANEL ---
col_spacer, col_main, col_spacer2 = st.columns([0.5, 4, 0.5])

with col_main:
    # 5.1. Header Section
    st.image("https://web.expasy.org/images/expasy.png", width=120) # Logo placeholder
    st.title("ProtParam Automation Suite")
    st.markdown("""
    Automated tool with **Real-time Processing**. Retrieves physicochemical data directly from ExPASy servers.
    Data is processed securely in a headless browser environment.
    """)
    
    st.markdown("---")

    # 5.2. File Upload Section
    st.subheader("Upload Protein FASTA File")
    uploaded_file = st.file_uploader("", type=["fasta", "fa", "txt"], help="Drag and drop your FASTA file here")

    # 5.3. Execution Logic
    if uploaded_file and st.session_state.results is None:
        sequences = read_fasta(uploaded_file)
        st.info(f"📄 **{uploaded_file.name}** loaded. Contains {len(sequences)} sequences.")
        
        if st.button("🚀 Start Analysis Pipeline", use_container_width=False):
            results = []
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try:
                with st.spinner('Initializing Selenium WebDriver...'):
                    driver = get_driver()
                
                for i, (header, seq) in enumerate(sequences):
                    status_text.markdown(f"**Processing:** `{header[:30]}...`")
                    prot_data = scrape_protparam(driver, seq)
                    prot_data["Accession ID"] = header.split()[0]
                    results.append(prot_data)
                    progress_bar.progress((i + 1) / len(sequences))
                    time.sleep(delay_sec) # Use the delay from sidebar
                
                driver.quit()
                
                # Save to Session State
                st.session_state.results = pd.DataFrame(results)
                st.session_state.history.append(datetime.now().strftime("%Y-%m-%d %H:%M"))
                st.experimental_rerun()
                
            except Exception as e:
                st.error(f"System Error: {e}")

    # 5.4. Results Display (Only if results exist)
    if st.session_state.results is not None:
        df = st.session_state.results
        
        st.success("Analysis Complete.")
        
        # Summary Metrics
        st.markdown("### 📊 Executive Summary")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Mean MW", f"{df['Molecular Weight (Da)'].mean():.0f} Da")
        m2.metric("Mean pI", f"{df['Theoretical pI'].mean():.2f}")
        m3.metric("Stable Proteins", f"{len(df[df['Instability Index'] < 40])}")
        m4.metric("Unstable Proteins", f"{len(df[df['Instability Index'] >= 40])}")

        # Data & Export
        tab1, tab2 = st.tabs(["Data View", "Export"])
        
        with tab1:
            st.dataframe(df.style.highlight_max(axis=0), use_container_width=True)
            
        with tab2:
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Results')
            
            st.download_button(
                label="📥 Download Excel Report",
                data=buffer.getvalue(),
                file_name="ProtParam_Results.xlsx",
                mime="application/vnd.ms-excel",
                type="primary"
            )
