import streamlit as st
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import openpyxl
import io
import re
import time
import shutil

# --- Yardımcı Fonksiyonlar (Senin mantığın aynen korundu) ---

def read_fasta_content(file_content):
    # Dosya içeriği byte olarak gelir, stringe çeviriyoruz
    content = file_content.decode("utf-8")
    sequences = []
    title, seq = None, ''
    for line in content.splitlines():
        if line.startswith('>'):
            if title and seq:
                sequences.append((title, seq))
            title = line.strip().lstrip('>')
            seq = ''
        else:
            seq += line.strip()
    if title and seq:
        sequences.append((title, seq))
    return sequences

def parse_second_pre_block(page_source):
    soup = BeautifulSoup(page_source, "html.parser")
    pre_blocks = soup.find_all("pre")
    if len(pre_blocks) < 2:
        return ["Hata"] * 8

    lines = list(pre_blocks[1].stripped_strings)

    def extract_value(label):
        for i, line in enumerate(lines):
            if label in line:
                if i + 1 < len(lines):
                    return lines[i + 1].replace('"', '').strip()
        return "Hata"

    def extract_instability_index():
        for line in lines:
            if "The instability index" in line:
                match = re.search(r"computed to be ([\d.]+)", line)
                return match.group(1) if match else "Hata"
        return "Hata"

    def extract_stability():
        for line in lines:
            if "This classifies the protein as" in line:
                if "unstable" in line.lower():
                    return "Unstable"
                elif "stable" in line.lower():
                    return "Stable"
        return "Hata"

    num_aa = extract_value("Number of amino acids:")
    mw = extract_value("Molecular weight:")
    mw_kda = round(float(mw) / 1000, 3) if mw != "Hata" else "Hata"
    pI = extract_value("Theoretical pI:")
    instability = extract_instability_index()
    stability = extract_stability()
    aliphatic = extract_value("Aliphatic index:")
    gravy = extract_value("Grand average of hydropathicity")

    return [num_aa, mw, mw_kda, pI, instability, stability, aliphatic, gravy]

def get_protparam_results(sequence, driver):
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
        return ["Hata"] * 8

# --- Web Arayüzü (Tkinter yerine Streamlit) ---

st.title("FASTA → ProtParam Otomasyonu")
st.write("Bu araç ExPASy ProtParam sitesine bağlanarak protein özelliklerini çeker.")

uploaded_file = st.file_uploader("FASTA Dosyasını Seçin", type=["fasta", "fa", "txt"])

if uploaded_file is not None:
    if st.button("Analizi Başlat"):
        sequences = read_fasta_content(uploaded_file.getvalue())
        st.info(f"Toplam {len(sequences)} dizi bulundu. İşlem başlıyor...")

        # İlerleme çubuğu
        progress_bar = st.progress(0)
        status_text = st.empty()

        # Selenium Ayarları (Sunucuda çalışması için kritik)
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Arayüzsüz mod
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        # Streamlit Cloud'da driver otomatik bulunur, localde hata verirse path gerekebilir
        try:
            driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            st.error(f"Chrome Driver başlatılamadı: {e}")
            st.stop()

        all_results = []
        
        for i, (title, seq) in enumerate(sequences):
            status_text.text(f"İşleniyor ({i+1}/{len(sequences)}): {title}")
            res = get_protparam_results(seq, driver)
            all_results.append([title] + res)
            progress_bar.progress((i + 1) / len(sequences))
            time.sleep(1) # Siteyi spamlamamak için bekleme

        driver.quit()
        status_text.text("İşlem tamamlandı!")

        # Excel Oluşturma (RAM üzerinde)
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "ProtParam Results"
        headers = [
            "Sequence Name", "Number of Amino Acids", "Molecular Weight (Da)",
            "Molecular Weight (kDa)", "Theoretical pI", "Instability Index",
            "Stability", "Aliphatic Index", "GRAVY"
        ]
        ws.append(headers)
        for row in all_results:
            ws.append(row)
        
        # Excel'i belleğe kaydet
        excel_buffer = io.BytesIO()
        wb.save(excel_buffer)
        excel_buffer.seek(0)

        st.success("Analiz bitti! Dosyayı aşağıdan indirebilirsiniz.")
        st.download_button(
            label="Excel Dosyasını İndir",
            data=excel_buffer,
            file_name="protparam_results.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )