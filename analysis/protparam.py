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

# --- 1. SELENIUM AYARLARI (CRITICAL FIX) ---
def get_driver():
    """Streamlit Cloud uyumlu Chrome Driver ayarları."""
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Arayüzsüz mod (Zorunlu)
    chrome_options.add_argument("--no-sandbox") 
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    driver = webdriver.Chrome(options=chrome_options)
    return driver

# --- 2. YARDIMCI FONKSİYONLAR ---
def read_fasta(file):
    """Yüklenen FASTA dosyasını okur ve (başlık, dizi) listesi döner."""
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
            header = line[1:] # '>' işaretini at
            sequence = []
        else:
            sequence.append(line)
    if header:
        sequences.append((header, "".join(sequence)))
        
    return sequences

def scrape_protparam(driver, sequence):
    """Tek bir dizi için ExPASy ProtParam analizi yapar."""
    url = "https://web.expasy.org/protparam/"
    driver.get(url)
    
    try:
        # Dizi kutusunu bul ve doldur
        text_area = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "sequence"))
        )
        text_area.clear()
        text_area.send_keys(sequence)
        
        # 'Compute parameters' butonuna tıkla
        submit_btn = driver.find_element(By.XPATH, "//input[@type='submit' and @value='Compute parameters']")
        submit_btn.click()
        
        # Sonuçların yüklenmesini bekle (pre etiketi içinde gelir)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "pre"))
        )
        
        # HTML'i al ve parse et
        soup = BeautifulSoup(driver.page_source, "html.parser")
        content = soup.find("pre").text
        
        # --- Basit Veri Çıkarma (Regex yerine basit split mantığı) ---
        data = {}
        lines = content.split('\n')
        for line in lines:
            if "Molecular weight:" in line:
                data["Molecular Weight"] = line.split("Molecular weight:")[1].strip()
            if "Theoretical pI:" in line:
                data["Theoretical pI"] = line.split("Theoretical pI:")[1].strip()
            if "Grand average of hydropathicity (GRAVY):" in line:
                data["GRAVY"] = line.split("(GRAVY):")[1].strip()
            if "Instability index:" in line:
                 # Instability index satırını bazen yakalamak zordur, basit split
                 parts = line.split("Instability index:")
                 if len(parts) > 1:
                     data["Instability Index"] = parts[1].split()[0].strip()

        return data

    except Exception as e:
        return {"Hata": str(e)}

# --- 3. STREAMLIT ARAYÜZÜ ---
st.set_page_config(page_title="ProtParam Otomasyon", page_icon="🧬")

st.title("🧬 ProtParam Otomasyon Aracı")
st.markdown("""
Bu araç, FASTA dosyalarını okur ve her bir protein dizisi için **ExPASy ProtParam** sitesinden fiziksel ve kimyasal parametreleri çeker.
""")

uploaded_file = st.file_uploader("FASTA Dosyası Yükleyin", type=["fasta", "fa", "txt"])

if uploaded_file:
    sequences = read_fasta(uploaded_file)
    st.info(f"Toplam {len(sequences)} adet dizi bulundu. Analiz başlıyor...")
    
    if st.button("Analizi Başlat"):
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        try:
            driver = get_driver() # Tarayıcıyı başlat
            
            for i, (header, seq) in enumerate(sequences):
                status_text.text(f"İşleniyor ({i+1}/{len(sequences)}): {header[:30]}...")
                
                # Analizi yap
                prot_data = scrape_protparam(driver, seq)
                prot_data["Protein ID"] = header
                results.append(prot_data)
                
                # İlerleme çubuğunu güncelle
                progress_bar.progress((i + 1) / len(sequences))
                
            driver.quit() # Tarayıcıyı kapat
            status_text.text("İşlem tamamlandı! 🎉")
            
            # --- Sonuçları Göster ve İndir ---
            df = pd.DataFrame(results)
            
            # Sütun sırasını düzenle (ID en başta olsun)
            cols = ["Protein ID"] + [c for c in df.columns if c != "Protein ID"]
            df = df[cols]
            
            st.dataframe(df)
            
            # Excel İndirme Butonu
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Sonuclar')
                
            st.download_button(
                label="📥 Excel Olarak İndir",
                data=buffer.getvalue(),
                file_name="protparam_results.xlsx",
                mime="application/vnd.ms-excel"
            )
            
        except Exception as e:
            st.error(f"Beklenmeyen bir hata oluştu: {e}")
            if 'driver' in locals():
                driver.quit()
