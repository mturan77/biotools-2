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

# --- 1. SAYFA VE TASARIM AYARLARI ---
st.set_page_config(
    page_title="BioTools: ProtParam Analyzer",
    page_icon="🧬",
    layout="wide",  # Geniş ekran modu
    initial_sidebar_state="expanded"
)

# Akademik CSS Düzenlemeleri
st.markdown("""
    <style>
    .main {
        background-color: #f8f9fa;
    }
    .stButton>button {
        width: 100%;
        background-color: #2c3e50;
        color: white;
        border-radius: 5px;
        height: 3em;
    }
    .metric-card {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        padding: 15px;
        border-radius: 5px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. SELENIUM AYARLARI ---
def get_driver():
    """Streamlit Cloud uyumlu Headless Chrome Driver."""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    driver = webdriver.Chrome(options=chrome_options)
    return driver

# --- 3. YARDIMCI FONKSİYONLAR ---
def read_fasta(file):
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
            header = line[1:]
            sequence = []
        else:
            sequence.append(line)
    if header:
        sequences.append((header, "".join(sequence)))
        
    return sequences

def scrape_protparam(driver, sequence):
    url = "https://web.expasy.org/protparam/"
    driver.get(url)
    
    try:
        text_area = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "sequence"))
        )
        text_area.clear()
        text_area.send_keys(sequence)
        
        submit_btn = driver.find_element(By.XPATH, "//input[@type='submit' and @value='Compute parameters']")
        submit_btn.click()
        
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "pre"))
        )
        
        soup = BeautifulSoup(driver.page_source, "html.parser")
        content = soup.find("pre").text
        
        data = {}
        lines = content.split('\n')
        for line in lines:
            if "Molecular weight:" in line:
                data["Molecular Weight (Da)"] = float(line.split("Molecular weight:")[1].strip())
            if "Theoretical pI:" in line:
                data["Theoretical pI"] = float(line.split("Theoretical pI:")[1].strip())
            if "Grand average of hydropathicity (GRAVY):" in line:
                data["GRAVY"] = float(line.split("(GRAVY):")[1].strip())
            if "Instability index:" in line:
                 parts = line.split("Instability index:")
                 if len(parts) > 1:
                     data["Instability Index"] = float(parts[1].split()[0].strip())

        return data
    except Exception as e:
        return {"Error": str(e)}

# --- 4. ARAYÜZ (SIDEBAR) ---
with st.sidebar:
    st.image("https://web.expasy.org/images/expasy.png", width=150) # Expasy Logo temsili
    st.header("Hakkında")
    st.info("""
    Bu araç, protein dizilerinin fizikokimyasal özelliklerini **ExPASy ProtParam** algoritması kullanarak otomatik olarak hesaplar.
    """)
    
    st.markdown("---")
    st.subheader("🛠 Metodoloji")
    st.markdown("""
    1. **Girdi:** FASTA formatlı protein dizileri.
    2. **İşlem:** Selenium WebDriver ile ProtParam sunucusuna bağlanılır.
    3. **Çıktı:** Moleküler ağırlık, izoelektrik nokta (pI), kararlılık indeksi ve GRAVY skorları.
    """)
    
    st.markdown("---")
    st.caption("Developed for Scientific Research")
    st.caption("v1.2.0 | Stable Build")

# --- 5. ANA PANEL ---
st.title("🧬 High-Throughput ProtParam Analyzer")
st.markdown("### Fizikokimyasal Protein Karakterizasyonu")
st.markdown("---")

col1, col2 = st.columns([2, 1])

with col1:
    uploaded_file = st.file_uploader("📂 Analiz için FASTA dosyanızı yükleyin", type=["fasta", "fa", "txt"])

with col2:
    st.write("#### ⚡ Hızlı Bakış")
    if uploaded_file:
        sequences = read_fasta(uploaded_file)
        st.success(f"✅ Dosya Yüklendi: {len(sequences)} dizi tespit edildi.")
    else:
        st.info("Lütfen analize başlamak için sol taraftan dosya yükleyin.")

# --- ANALİZ BÖLÜMÜ ---
if uploaded_file and st.button("🚀 Analizi Başlat", help="Analiz süresi dizi sayısına göre değişebilir."):
    results = []
    
    # İlerleme Çubuğu ve Durum
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        with st.spinner('Laboratuvar ortamı hazırlanıyor ve ExPASy sunucularına bağlanılıyor...'):
            driver = get_driver()
            
        for i, (header, seq) in enumerate(sequences):
            status_text.markdown(f"**İşleniyor:** `{header}` ({i+1}/{len(sequences)})")
            
            prot_data = scrape_protparam(driver, seq)
            prot_data["Accession ID"] = header.split()[0] # Genellikle ilk kelime ID'dir
            prot_data["Full Header"] = header
            results.append(prot_data)
            
            progress_bar.progress((i + 1) / len(sequences))
            
        driver.quit()
        status_text.success("Analiz başarıyla tamamlandı!")
        
        # --- SONUÇLARI GÖSTERME ---
        df = pd.DataFrame(results)
        
        # Sütun düzenleme
        main_cols = ["Accession ID", "Molecular Weight (Da)", "Theoretical pI", "Instability Index", "GRAVY"]
        df = df[main_cols] # Sadece önemli sütunları al
        
        st.markdown("---")
        
        # 1. ÖZET İSTATİSTİKLER (METRICS)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Ortalama MW (Da)", f"{df['Molecular Weight (Da)'].mean():.2f}")
        m2.metric("Ortalama pI", f"{df['Theoretical pI'].mean():.2f}")
        m3.metric("Ortalama Kararlılık", f"{df['Instability Index'].mean():.2f}")
        m4.metric("Ortalama GRAVY", f"{df['GRAVY'].mean():.3f}")
        
        st.markdown("---")

        # 2. DETAYLI SEKMELER
        tab1, tab2, tab3 = st.tabs(["📊 Veri Tablosu", "📈 Parametre Açıklamaları", "📥 İndirme"])
        
        with tab1:
            st.subheader("Analiz Sonuçları")
            # Pandas Styler ile renklendirme (Bilimsel görünüm)
            st.dataframe(
                df.style.background_gradient(subset=["Theoretical pI"], cmap="viridis")
                        .format("{:.2f}", subset=["Molecular Weight (Da)", "Instability Index", "GRAVY"]),
                use_container_width=True
            )
            
        with tab2:
            st.markdown("""
            #### Bilimsel Parametrelerin Anlamları
            
            * **Molecular Weight (Da):** Protein zincirindeki atomların toplam ağırlığıdır. Elektroforez (SDS-PAGE) analizlerinde referans olarak kullanılır.
            * **Theoretical pI (İzoelektrik Nokta):** Proteinin net yükünün sıfır olduğu pH değeridir. Protein saflaştırma stratejilerinde kritiktir.
            * **Instability Index (II):** Proteinin test tüpünde ne kadar kararlı olacağını tahmin eder.
                * *II < 40:* Kararlı (Stable)
                * *II > 40:* Kararsız (Unstable)
            * **GRAVY (Grand Average of Hydropathy):** Hidrofobiklik derecesini gösterir. Pozitif değerler hidrofobik, negatif değerler hidrofilik karakteri işaret eder.
            """)
            
        with tab3:
            st.subheader("Verileri Dışa Aktar")
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='ProtParam Results')
                
            st.download_button(
                label="📥 Excel Raporunu İndir (.xlsx)",
                data=buffer.getvalue(),
                file_name="ProtParam_Analysis_Report.xlsx",
                mime="application/vnd.ms-excel"
            )

    except Exception as e:
        st.error(f"Kritik Hata: {e}")
        if 'driver' in locals():
            driver.quit()
