import streamlit as st
import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType

st.set_page_config(page_title="SMART Final Çözüm", layout="wide")
st.title("🎯 SMART: Nihai Çözüm (HTML Analizli)")

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

if st.button("Final Testi Başlat"):
    driver = get_driver()
    if driver:
        log_col, img_col = st.columns([1, 1])
        
        with log_col:
            st.info("1. Siteye gidiliyor...")
            driver.get("https://smart.embl-heidelberg.de/")
            time.sleep(3)
            
            st.info("2. Ortadaki büyük 'Normal Mode' butonu (linki) aranıyor...")
            
            # --- HTML ANALİZİNE GÖRE HEDEFLEME ---
            # Hedefimiz: <a class="btn..." href="change_mode.cgi?mode=normal">Normal mode</a>
            
            try:
                # 1. CSS Selector ile bulmaya çalış (En kesin yöntem)
                # href değeri tam olarak "change_mode.cgi?mode=normal" olan 'a' etiketi
                normal_mode_btn = driver.find_element(By.CSS_SELECTOR, "a[href='change_mode.cgi?mode=normal']")
                
                if normal_mode_btn:
                    st.success("🎯 HEDEF BULUNDU! (CSS Selector ile)")
                    st.info("3. Tıklanıyor...")
                    
                    # Butonun görünür olduğundan emin ol (Bazen scroll gerekir)
                    driver.execute_script("arguments[0].scrollIntoView();", normal_mode_btn)
                    time.sleep(0.5)
                    normal_mode_btn.click()
                    time.sleep(5) # Sayfa geçişi için bekle
                    
                    # --- SONUÇ KONTROLÜ ---
                    # Artık "Sequence SMART" yazan o büyük butonu arıyoruz.
                    # Bu butonun varlığı, doğru sayfada olduğumuzun kesin kanıtıdır.
                    try:
                        # Görseldeki "Sequence SMART" butonu
                        seq_smart_btn = driver.find_element(By.XPATH, "//button[contains(., 'Sequence SMART')]")
                        
                        if seq_smart_btn:
                            st.balloons()
                            st.success("🎉 MÜKEMMEL! 'Sequence SMART' butonu bulundu. Giriş sayfası hazır!")
                        else:
                            st.warning("⚠️ Tıklama yapıldı ama 'Sequence SMART' butonu görünmüyor.")
                    except:
                        # Yedek kontrol: Textarea var mı?
                        if "SEQUENCE" in driver.page_source:
                            st.balloons()
                            st.success("🎉 ALTERNATİF BAŞARI: Sekans giriş kutusu (Textarea) bulundu.")
                        else:
                            st.error("⚠️ Tıklama yapıldı ama beklenen sayfa ögeleri bulunamadı.")
                            
                else:
                    st.error("❌ Buton CSS Selector ile bulunamadı.")

            except Exception as e:
                st.error(f"Hata oluştu: {e}")
                st.warning("XPath ile yedek deneme yapılıyor...")
                # Yedek Plan: XPath ile metin arama
                try:
                    btn_xpath = driver.find_element(By.XPATH, "//a[contains(text(), 'Normal mode') and contains(@class, 'btn-primary')]")
                    btn_xpath.click()
                    st.success("✅ XPath ile bulundu ve tıklandı.")
                    time.sleep(4)
                except:
                    st.error("❌ XPath denemesi de başarısız.")

            driver.save_screenshot("final_result.png")

        with img_col:
            st.subheader("Sonuç Ekranı")
            if os.path.exists("final_result.png"):
                st.image("final_result.png", caption="Tıklama Sonrası Görüntü (Giriş Sayfası Olmalı)")
                
        driver.quit()
