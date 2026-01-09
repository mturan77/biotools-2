import streamlit as st
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import openpyxl
import io
import re
import time

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="ProtParam Otomasyon", page_icon="🧬")

st.title("FASTA → ProtParam Otomasyonu")

# --- MANUEL (BİLGİLENDİRME KUTUSU) ---
st.warning("""
**📌 Bu Araç Ne İşe Yarar?**

1.  **Girdi:** Bilgisayarınızdan içinde protein dizileri olan bir **FASTA** dosyası seçersiniz.
2.  **İşlem:** Araç, arka planda görünmez bir tarayıcı açar, **ExPASy ProtParam** sitesine bağlanır ve listedeki her protein için tek tek hesaplama yapar.
3.  **Çıktı:** Moleküler Ağırlık, pI, GRAVY, Kararsızlık İndeksi gibi verileri toparlar ve **Excel** dosyası olarak indirmenizi sağlar.
""")

# --- YARDIMCI FONKSİYONLAR ---

def read_fasta_content(file_content):
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
        # Eğer sonuç bulunamazsa hatayı anlamak için boş dön
        return None

    lines = list(pre_blocks[1].stripped_strings)

    def extract_value(label):
        for i, line in enumerate(lines):
            if label in line:
                if i + 1 < len(lines):
                    return lines[i + 1].replace('"', '').strip()
        return "Bulunamadı"

    def extract_instability_index():
        for line in lines:
            if "The instability index" in line:
                match = re.search(r"computed to be ([\d.]+)", line)
                return match.group(1) if match else "Bulunamadı"
        return "Bulunamadı"

    def extract_stability():
        for line in lines:
            if "This classifies the protein as" in line:
                if "unstable" in line.lower():
                    return "Unstable"
                elif "stable" in line.lower():
                    return "Stable"
        return "Bulunamadı"

    num_aa = extract_value("Number of amino acids:")
    mw = extract_value("Molecular weight:")
    mw_kda = round(float(mw) / 1000, 3) if mw != "Bulunamadı" and mw != "Hata" else "Hata"
    pI = extract_value("Theoretical pI:")
    instability = extract_instability_index()
    stability = extract_stability()
    aliphatic = extract_value("Aliphatic index:")
    gravy = extract_value("Grand average of hydropathicity")

    return [num_aa, mw, mw_kda, pI, instability, stability, aliphatic, gravy]

def get_protparam_results(sequence, driver):
    driver.get("https://web.expasy.org/protparam/")
    try:
        # 1. Metin kutusunu bul
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.NAME, "sequence")))
        textarea = driver.find_element(By.NAME, "sequence")
        textarea.clear()
        textarea.send_keys(sequence)

        # 2. Gönder butonuna bas
        submit = driver.find_element(By.XPATH, "//input[@type='submit' and @value='Compute parameters']")
        submit.click()

        # 3. Sonuç sayfasının yüklenmesini bekle (Timeout süresi artırıldı)
        WebDriverWait(driver, 20).until(lambda d: "<pre>" in d.page_source)
        
        result = parse_second_pre_block(driver.page_source)
        if result is None:
            return ["Site Yapısı Farklı"] * 8
        return result

    except Exception as e:
        # Hata mesajını ekrana bas (Debugging için çok önemli)
        st.error(f"Hata Detayı: {str(e)}")
        return ["Hata"] * 8

# --- ARAYÜZ ---

uploaded_file = st.file_uploader("FASTA Dosyasını Yükleyin", type=["fasta", "fa", "txt"])

if uploaded_file is not None:
    if st.button("Analizi Başlat"):
        sequences = read_fasta_content(uploaded_file.getvalue())
        st.info(f"Toplam {len(sequences)} dizi bulundu. İşlem başlıyor...")

        progress_bar = st.progress(0)
        status_text = st.empty()

        # --- GÜÇLENDİRİLMİŞ SELENIUM AYARLARI ---
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        # Siteyi kandırmak için Ekran Boyutu ve User-Agent ekliyoruz:
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        
        try:
            driver = webdriver.Chrome(options=chrome_options)
        except Exception as e:
            st.error(f"Chrome Driver hatası: {e}")
            st.stop()

        all_results = []
        
        for i, (title, seq) in enumerate(sequences):
            status_text.text(f"İşleniyor ({i+1}/{len(sequences)}): {title}")
            
            # Sonuçları çek
            res = get_protparam_results(seq, driver)
            
            # Eğer hala Hata dönüyorsa ekrana uyarısını bas
            if res[0] == "Hata":
                st.warning(f"⚠️ '{title}' için veri çekilemedi. Site yanıt vermedi.")
            
            all_results.append([title] + res)
            progress_bar.progress((i + 1) / len(sequences))
            
            # Spam korumasına takılmamak için biraz daha uzun bekle
            time.sleep(2)

        driver.quit()
        status_text.success("✅ İşlem tamamlandı!")

        # Excel Kaydetme
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
        
        excel_buffer = io.BytesIO()
        wb.save(excel_buffer)
        excel_buffer.seek(0)

        st.download_button(
            label="📥 Excel Dosyasını İndir",
            data=excel_buffer,
            file_name="protparam_sonuclar.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
