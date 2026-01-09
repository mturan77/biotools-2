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

# --- 1. AYARLAR VE STİL (PHYRE2 TASARIM MANTIĞI) ---
st.set_page_config(
    page_title="ProtParam Analyzer",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Session State (Verilerin kaybolmaması için)
if 'results' not in st.session_state:
    st.session_state.results = None

# CSS: Phyre2 benzeri temiz sol menü ve kırmızı butonlar
st.markdown("""
    <style>
    /* Sol Menü Arka Planı */
    [data-testid="stSidebar"] {
        background-color: #f0f2f6;
        border-right: 1px solid #d1d5db;
    }
    /* Buton Tasarımı (Phyre2 kırmızısı) */
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
    /* Kart Görünümü */
    .metric-container {
        background-color: white;
        padding: 15px;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        text-align: center;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. BACKEND (SENİN KODUN) ---
def get_driver():
    """Streamlit Cloud uyumlu Headless Driver"""
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

# --- 3. ARAYÜZ (PHYRE2 LAYOUT) ---

# --- SOL PANEL (INPUT KISMI) ---
with st.sidebar:
    st.title("⚙️ Kontrol Paneli")
    st.markdown("Analiz dosyasını buradan yükleyip başlatabilirsin.")
    
    # 1. Dosya Yükleme (Phyre2 stili solda)
    uploaded_file = st.file_uploader("FASTA Dosyası Seç", type=["fasta", "fa", "txt"])
    
    # 2. Buton (Dosya varsa aktif olur)
    if uploaded_file:
        st.write("---")
        if st.button("🚀 Analizi Başlat"):
            st.session_state.running = True
        
    # Reset Butonu
    if st.session_state.results is not None:
        st.write("---")
        if st.button("🔄 Sıfırla / Yeni Analiz"):
            st.session_state.results = None
            st.rerun()

    st.markdown("---")
    st.caption("ProtParam Automation v1.2")

# --- SAĞ PANEL (SONUÇ VE DASHBOARD KISMI) ---
st.title("🧬 ProtParam Otomasyonu")
st.markdown("Bu araç ExPASy sunucularını kullanarak yüklenen protein dizilerinin fizikokimyasal özelliklerini çıkarır.")
st.divider()

# Durum 1: Henüz dosya yüklenmedi veya başlatılmadı
if not uploaded_file:
    st.info("👈 Analize başlamak için lütfen sol menüden FASTA dosyası yükleyin.")

# Durum 2: Analiz Çalışıyor (Sidebar butonuna basıldıysa)
elif 'running' in st.session_state and st.session_state.running and st.session_state.results is None:
    sequences = read_fasta(uploaded_file)
    results = []
    
    # İlerleme Çubuğu (Ana ekranda)
    progress_bar = st.progress(0)
    status_box = st.empty()
    
    try:
        with st.spinner('Tarayıcı başlatılıyor ve ExPASy sunucusuna bağlanılıyor...'):
            driver = get_driver()
        
        for i, (header, seq) in enumerate(sequences):
            status_box.markdown(f"**⏳ İşleniyor:** `{header[:40]}...` ({i+1}/{len(sequences)})")
            
            prot_data = scrape_protparam(driver, seq)
            prot_data["Accession ID"] = header.split()[0]
            results.append(prot_data)
            
            progress_bar.progress((i + 1) / len(sequences))
            
        driver.quit()
        st.session_state.results = pd.DataFrame(results)
        st.session_state.running = False
        st.rerun() # Sayfayı yenileyip sonuçları göster
        
    except Exception as e:
        st.error(f"Sistem Hatası: {e}")
        st.session_state.running = False

# Durum 3: Sonuçlar Hazır
if st.session_state.results is not None:
    df = st.session_state.results
    
    st.success("✅ Analiz Başarıyla Tamamlandı.")
    
    # Dashboard Tarzı Özet Kartları
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Toplam Protein", len(df))
    col2.metric("Ortalama MW", f"{df['Molecular Weight (Da)'].mean():.0f} Da")
    col3.metric("Ortalama pI", f"{df['Theoretical pI'].mean():.2f}")
    col4.metric("Ortalama GRAVY", f"{df['GRAVY'].mean():.3f}")
    
    st.divider()
    
    # Sekmeli Görünüm (Veri ve İndirme)
    tab1, tab2 = st.tabs(["📄 Veri Tablosu", "📥 İndir"])
    
    with tab1:
        st.dataframe(df.style.highlight_max(axis=0), use_container_width=True)
        
    with tab2:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='ProtParam Results')
        
        st.download_button(
            label="📥 Excel Raporunu İndir",
            data=buffer.getvalue(),
            file_name="ProtParam_Results.xlsx",
            mime="application/vnd.ms-excel"
        )
