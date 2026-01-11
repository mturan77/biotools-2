import streamlit as st
import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType

st.set_page_config(page_title="SMART Form Doldurucu", layout="wide")
st.title("📝 SMART: Form Doldurma Testi")

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

if st.button("Form Testini Başlat"):
    driver = get_driver()
    if driver:
        log_col, img_col = st.columns([1, 1])
        
        with log_col:
            st.info("1. Siteye gidiliyor...")
            driver.get("https://smart.embl-heidelberg.de/")
            time.sleep(2)
            
            # --- ADIM 1: MOD KONTROLÜ (Gerekirse Yap) ---
            try:
                # Mod seçimi butonu sayfada var mı? (Kısa timeout ile kontrol)
                driver.implicitly_wait(3) 
                normal_mode_links = driver.find_elements(By.CSS_SELECTOR, "a[href='change_mode.cgi?mode=normal']")
                
                if normal_mode_links:
                    st.warning("⚠️ Mod seçimi ekranı tespit edildi. 'Normal Mode' seçiliyor...")
                    
                    # Butona tıkla
                    btn = normal_mode_links[0]
                    # Görünür olduğundan emin ol
                    driver.execute_script("arguments[0].scrollIntoView();", btn)
                    btn.click()
                    time.sleep(3) # Sayfa yenilenmesi için bekle
                    st.success("✅ Mod seçimi geçildi.")
                else:
                    st.success("✅ Sayfa doğrudan analiz modunda açıldı (Mod seçimine gerek kalmadı).")
                    
            except Exception as e:
                st.error(f"Mod kontrolünde hata: {e}")
            
            finally:
                driver.implicitly_wait(10) # Normal beklemeye dön

            # --- ADIM 2: PFAM DOMAINS SEÇİMİ ---
            st.info("2. 'Pfam domains' kutucuğu ayarlanıyor...")
            try:
                # Pfam kutucuğunu bul (Value değeri genellikle 'DO_PFAM' olur veya metinden buluruz)
                # SMART kaynak kodunda checkbox name="DO_PFAM" şeklindedir.
                pfam_checkbox = driver.find_element(By.XPATH, "//input[@value='DO_PFAM']")
                
                # Seçili değilse tıkla
                if not pfam_checkbox.is_selected():
                    # Checkbox bazen görünmez olabilir, Javascript ile tıklamak daha garantidir
                    driver.execute_script("arguments[0].click();", pfam_checkbox)
                    st.success("✅ 'Pfam domains' işaretlendi.")
                else:
                    st.info("ℹ️ 'Pfam domains' zaten seçili.")
                    
            except Exception as e:
                st.error(f"❌ Pfam kutucuğu bulunamadı: {e}")

            # --- ADIM 3: SEKANS GİRİŞİ ---
            st.info("3. Test sekansı giriliyor...")
            try:
                seq_box = driver.find_element(By.NAME, "SEQUENCE")
                seq_box.clear()
                # Test için kısa bir protein sekansı
                test_seq = "MKTLLILAVSLIAAGLSQG" 
                seq_box.send_keys(test_seq)
                st.success(f"✅ Sekans kutuya yazıldı: {test_seq}")
                
            except Exception as e:
                st.error(f"❌ Sekans kutusu bulunamadı: {e}")

            # Ekran Görüntüsü Al
            time.sleep(1)
            driver.save_screenshot("form_filled.png")
            st.info("⏹️ İşlem durduruldu. 'Analizi Başlat' butonuna TIKLANMADI.")

        with img_col:
            st.subheader("Formun Son Hali")
            if os.path.exists("form_filled.png"):
                st.image("form_filled.png", caption="Pfam Seçili + Sekans Girilmiş")
                
        driver.quit()
