import streamlit as st
import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType

st.set_page_config(page_title="SMART Buton Avcısı", layout="wide")
st.title("🕵️ SMART: Adım 2 - Buton Yakalama")

def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

    try:
        service = Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    except Exception as e:
        st.error(f"Driver hatası: {e}")
        return None

if st.button("Testi Başlat (v2)"):
    driver = get_driver()
    if driver:
        log_col, img_col = st.columns([1, 1])
        
        with log_col:
            st.info("1. Siteye gidiliyor...")
            driver.get("https://smart.embl-heidelberg.de/")
            time.sleep(3)
            
            # HTML Kaynağını Al (Hata ayıklamak için)
            page_source = driver.page_source
            
            # --- YÖNTEM 1: Görsel İçeren Link Araması ---
            st.write("🔍 Yöntem 1: Görsel Linki aranıyor...")
            try:
                # "change_mode.pl?to=NORMAL" içeren herhangi bir elemanı bul
                btn = driver.find_element(By.XPATH, "//a[contains(@href, 'to=NORMAL')]")
                btn.click()
                st.success("✅ Yöntem 1 İşe Yaradı!")
            except:
                st.warning("🔸 Yöntem 1 başarısız.")
                
                # --- YÖNTEM 2: Metin Bazlı Arama ---
                st.write("🔍 Yöntem 2: 'Normal mode' yazısı aranıyor...")
                try:
                    # İçinde "Normal mode" yazan herhangi bir tıklanabilir öge
                    btn = driver.find_element(By.XPATH, "//*[contains(text(), 'Normal mode')]")
                    btn.click()
                    st.success("✅ Yöntem 2 İşe Yaradı!")
                except:
                    st.warning("🔸 Yöntem 2 başarısız.")
                    
                    # --- YÖNTEM 3: Form Input Araması ---
                    st.write("🔍 Yöntem 3: Form Butonu aranıyor...")
                    try:
                        # Value değeri "Normal mode" olan input
                        btn = driver.find_element(By.XPATH, "//input[@value='Normal mode']")
                        btn.click()
                        st.success("✅ Yöntem 3 İşe Yaradı!")
                    except:
                         st.error("❌ Hiçbir yöntem çalışmadı.")
                         
                         # HTML'i göster ki görelim
                         with st.expander("Sayfa HTML Kodları (Hata Analizi İçin)"):
                             st.code(page_source, language='html')

            time.sleep(3)
            driver.save_screenshot("step2_result.png")
            
            # Kontrol
            if "paste your sequence" in driver.page_source.lower() or "sequence" in driver.page_source.lower():
                st.balloons()
                st.success("🎉 GİRİŞ BAŞARILI! Sekans kutusu tespit edildi.")
            else:
                st.error("⚠️ Tıklama denemeleri bitti ama hala giriş sayfasında değiliz.")

        with img_col:
            st.subheader("Son Durum")
            if os.path.exists("step2_result.png"):
                st.image("step2_result.png", caption="İşlem Sonrası Ekran")
                
        driver.quit()
