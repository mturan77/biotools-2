import streamlit as st
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import urllib.parse
import io

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Gen Veri Robotu (Selenium)", page_icon="🧬", layout="wide")

# --- SELENIUM AYARLARI (Streamlit Cloud İçin Kritik) ---
def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Arayüzsüz mod (Ekranda pencere açılmaz)
    chrome_options.add_argument("--no-sandbox") # Cloud ortamı için gerekli
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    
    # Tarayıcıyı başlat
    driver = webdriver.Chrome(options=chrome_options)
    return driver

# --- SCRAPING FONKSİYONU ---
def fetch_data_with_selenium(species, gene_id):
    driver = None
    safe_species = urllib.parse.quote(species.strip())
    safe_id = gene_id.strip()
    url = f"https://www.insect-genome.com/gene/{safe_species}/{safe_id}"
    
    data = {
        "Gen ID": gene_id,
        "URL": url,
        "Description": "Bulunamadı",
        "JSON_Link": "-",
        "Durum": "Başarısız"
    }

    try:
        driver = get_driver()
        driver.get(url)
        
        # Sayfanın yüklenmesi için bekle (Max 10 saniye)
        wait = WebDriverWait(driver, 10)
        
        # 1. DESCRIPTION'ı ALMA (Resimde gördüğümüz yeşil alan)
        try:
            # "Description" yazan başlığı bulmaya çalışıyoruz
            # XPath: İçinde 'Description' yazan herhangi bir elementi bul
            desc_element = wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Description')]")))
            
            # Genelde description yazısı bu başlığın hemen altındadır veya yanındadır.
            # O yüzden bulunduğu div'in metnini almaya çalışalım.
            parent = desc_element.find_element(By.XPATH, "..") # Bir üst kapsayıcıya çık
            full_text = parent.text
            
            # "Description" kelimesini temizle
            clean_desc = full_text.replace("Description", "").strip()
            if clean_desc:
                data["Description"] = clean_desc
                data["Durum"] = "Başarılı"
                
        except:
            data["Description"] = "Description Alanı Bulunamadı"

        # 2. EXPORT JSON BUTONUNU BULMA
        try:
            # Butonun üzerinde "Export JSON" yazdığını resimden görüyoruz
            json_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Export JSON')] | //a[contains(text(), 'Export JSON')]")
            
            # Eğer bu bir link ise (href varsa) alalım
            link = json_btn.get_attribute("href")
            if link:
                data["JSON_Link"] = link
            else:
                data["JSON_Link"] = "Buton var ama link değil (JS Trigger)"
                
        except:
            data["JSON_Link"] = "Buton Bulunamadı"

    except Exception as e:
        data["Durum"] = f"Hata: {str(e)}"
    
    finally:
        if driver:
            driver.quit() # Tarayıcıyı kapatmayı unutma
            
    return data

# --- ARAYÜZ ---
st.title("🧬 Insect Genome - Selenium Veri Kazıyıcı")
st.markdown("""
Bu versiyon **Selenium** kullanır. Sayfayı arka planda gerçekten açar, 
Javascript'in yüklenmesini bekler ve ekrandaki veriyi okur.
""")

# Sidebar
with st.sidebar:
    st.header("Veri Girişi")
    uploaded_file = st.file_uploader("Excel Yükle", type=['xlsx', 'xls'])
    species_input = st.text_input("Tür (Species)", value="musca domestica")

# Ana Akış
if uploaded_file:
    df = pd.read_excel(uploaded_file)
    
    # Sütun Seçimi
    cols = df.columns.tolist()
    target_col = st.selectbox("Gen ID Sütunu:", cols)
    
    if st.button("🚀 Taramayı Başlat", type="primary"):
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        total = len(df)
        
        # Döngü
        for i, row in df.iterrows():
            g_id = str(row[target_col])
            
            status_text.text(f"Taranıyor ({i+1}/{total}): {g_id}")
            
            # Selenium ile çek
            scraped_data = fetch_data_with_selenium(species_input, g_id)
            results.append(scraped_data)
            
            progress_bar.progress((i+1)/total)
            # time.sleep(1) # Gerekirse bekleme süresi artırılabilir
            
        status_text.success("✅ İşlem Tamamlandı!")
        
        # Sonuçları Göster
        res_df = pd.DataFrame(results)
        st.dataframe(res_df)
        
        # İndir
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            res_df.to_excel(writer, index=False)
            
        st.download_button(
            label="📥 Sonuçları İndir (Excel)",
            data=buffer.getvalue(),
            file_name="selenium_gen_sonuclari.xlsx",
            mime="application/vnd.ms-excel"
        )
