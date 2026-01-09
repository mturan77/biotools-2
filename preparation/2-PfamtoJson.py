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

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="JSON Toplu İndirici", page_icon="📦", layout="wide")

# --- İNDİRME KLASÖRÜ AYARLARI ---
DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloaded_jsons")

# Klasörü temizle ve yeniden oluştur (Her seferinde temiz başla)
if os.path.exists(DOWNLOAD_DIR):
    shutil.rmtree(DOWNLOAD_DIR)
os.makedirs(DOWNLOAD_DIR)

# --- SELENIUM AYARLARI ---
def get_driver_with_download():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    
    # Chrome'a "Dosyaları bu klasöre indir ve soru sorma" diyoruz
    prefs = {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    driver = webdriver.Chrome(options=chrome_options)
    return driver

# --- ZIP OLUŞTURMA FONKSİYONU ---
def zip_files(directory_path):
    zip_path = "all_genes_json.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(directory_path):
            for file in files:
                zipf.write(os.path.join(root, file), file)
    return zip_path

# --- ARAYÜZ ---
st.title("📦 Toplu JSON İndirme ve Paketleme Aracı")
st.markdown("""
Bu araç her gen sayfasına gider, **'Export JSON'** butonuna basar, inen dosyayı alır ve 
hepsini tek bir **ZIP** dosyası olarak size verir.
""")

with st.sidebar:
    uploaded_file = st.file_uploader("Excel Listesi", type=['xlsx', 'xls'])
    species_input = st.text_input("Tür (Species)", value="musca domestica")

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    cols = df.columns.tolist()
    target_col = st.selectbox("Gen ID Sütunu:", cols)
    
    if st.button("🚀 İndirmeyi Başlat", type="primary"):
        st.warning("İşlem başladı. Dosyalar arka planda indiriliyor, lütfen bekleyin...")
        
        progress_bar = st.progress(0)
        status_area = st.empty()
        report_data = []
        
        driver = get_driver_with_download()
        
        total = len(df)
        success_count = 0
        
        for i, row in df.iterrows():
            g_id = str(row[target_col]).strip()
            safe_species = urllib.parse.quote(species_input.strip())
            url = f"https://www.insect-genome.com/gene/{safe_species}/{g_id}"
            
            status_area.text(f"İşleniyor ({i+1}/{total}): {g_id} -> Sayfaya gidiliyor...")
            
            status = "Başarısız"
            file_name = "-"
            
            try:
                driver.get(url)
                wait = WebDriverWait(driver, 8) # Maksimum bekleme
                
                # 'Export JSON' butonunu bul ve TIKLA
                try:
                    # Butonu bul
                    json_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Export JSON')] | //a[contains(text(), 'Export JSON')]")))
                    
                    # Tıklamadan önce mevcut dosya sayısını al
                    files_before = set(os.listdir(DOWNLOAD_DIR))
                    
                    # Tıkla
                    json_btn.click()
                    
                    # İndirmenin bitmesini bekle (Dosya sayısının artmasını bekle)
                    # Basit bir bekleme döngüsü (Max 5 saniye bekle)
                    for _ in range(5):
                        time.sleep(1)
                        files_after = set(os.listdir(DOWNLOAD_DIR))
                        if len(files_after) > len(files_before):
                            # Yeni inen dosyayı bul
                            new_file = list(files_after - files_before)[0]
                            # Dosya .crdownload (Chrome geçici dosyası) ise bitmesini bekle
                            if not new_file.endswith('.crdownload'):
                                file_name = new_file
                                status = "İNDİRİLDİ"
                                success_count += 1
                                break
                    
                    if status == "Başarısız":
                        status = "Zaman Aşımı (Dosya inemedi)"
                        
                except Exception as e:
                    status = "Buton Bulunamadı / Tıklanamadı"
            
            except Exception as e:
                status = f"Sayfa Hatası: {str(e)}"
            
            # Rapor listesine ekle
            report_data.append({
                "Gen ID": g_id,
                "Durum": status,
                "İnen Dosya": file_name,
                "URL": url
            })
            
            progress_bar.progress((i+1)/total)
        
        driver.quit()
        status_area.success(f"✅ İşlem Bitti! Toplam {success_count} dosya indirildi.")
        
        # --- SONUÇLARI GÖSTER VE İNDİR ---
        
        col1, col2 = st.columns(2)
        
        # 1. ZIP DOSYASI (JSONLAR)
        if success_count > 0:
            zip_file_path = zip_files(DOWNLOAD_DIR)
            with open(zip_file_path, "rb") as f:
                with col1:
                    st.download_button(
                        label="📦 TÜM JSONLARI İNDİR (.ZIP)",
                        data=f,
                        file_name="gen_json_arsivi.zip",
                        mime="application/zip",
                        type="primary"
                    )
        
        # 2. RAPOR DOSYASI (EXCEL)
        report_df = pd.DataFrame(report_data)
        
        # Excel oluştur (Openpyxl ile)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            report_df.to_excel(writer, index=False)
            
        with col2:
            st.download_button(
                label="📄 Raporu İndir (.xlsx)",
                data=buffer.getvalue(),
                file_name="indirme_raporu.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
        st.write("Detaylı Rapor Önizlemesi:")
        st.dataframe(report_df)
