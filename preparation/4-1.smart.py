import streamlit as st
import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType

st.set_page_config(page_title="SMART Navigasyon Testi", layout="wide")
st.title("🕵️ SMART: Adım Adım Navigasyon Testi")

# --- Driver Ayarları ---
def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080") # Ekran boyutu önemli
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

    try:
        service = Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    except Exception as e:
        st.error(f"Driver hatası: {e}")
        return None

# --- Test Başlat ---
if st.button("Testi Başlat"):
    driver = get_driver()
    
    if driver:
        log_col, img_col = st.columns([1, 1])
        
        with log_col:
            st.info("1. Siteye gidiliyor: https://smart.embl-heidelberg.de/")
            driver.get("https://smart.embl-heidelberg.de/")
            time.sleep(2)
            
            # --- FOTOĞRAF 1: İLK GİRİŞ ---
            driver.save_screenshot("step1_entry.png")
            st.success("✅ Siteye erişildi. Ekran görüntüsü sağda.")
            
            st.info("2. 'Normal Mode' butonu aranıyor...")
            
            # Butonu bulmaya çalışalım
            try:
                # Linkin içinde "Normal mode" geçen bir 'a' tagı veya görsel arıyoruz
                # Genellikle href içinde change_mode.pl?to=NORMAL olur
                mode_btn = driver.find_element(By.XPATH, "//a[contains(@href, 'change_mode.pl?to=NORMAL')]")
                
                if mode_btn:
                    st.success(f"✅ Buton bulundu! Link: {mode_btn.get_attribute('href')}")
                    st.info("3. Butona tıklanıyor...")
                    mode_btn.click()
                    time.sleep(3) # Yüklenmesini bekle
                    
                    # --- FOTOĞRAF 2: TIKLAMA SONRASI ---
                    driver.save_screenshot("step2_after_click.png")
                    st.success("✅ Tıklama işlemi yapıldı. Sonuç sağda.")
                    
                    # Giriş kutusu kontrolü
                    page_source = driver.page_source
                    if "paste your sequence here" in page_source.lower() or "sequence" in page_source.lower():
                        st.balloons()
                        st.success("🎉 BAŞARILI! Sekans giriş sayfası açıldı.")
                    else:
                        st.warning("⚠️ Tıkladık ama sekans giriş kutusunu göremedim. Fotoğrafı kontrol et.")
                        
                else:
                    st.error("❌ 'Normal Mode' butonu bulunamadı.")
                    
            except Exception as e:
                st.error(f"❌ Bir hata oluştu veya buton bulunamadı: {e}")
                # Hata anının fotosu
                driver.save_screenshot("step_error.png")
                st.image("step_error.png", caption="Hata Anı")

        # --- GÖRSELLERİ GÖSTER ---
        with img_col:
            st.subheader("📸 Botun Gözünden")
            
            if os.path.exists("step1_entry.png"):
                st.image("step1_entry.png", caption="1. Siteye İlk Giriş Anı")
            
            if os.path.exists("step2_after_click.png"):
                st.divider()
                st.image("step2_after_click.png", caption="2. 'Normal Mode' Tıklandıktan Sonra")

        driver.quit()
