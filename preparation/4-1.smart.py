import streamlit as st
import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType

st.set_page_config(page_title="SMART Buton Avcısı v3", layout="wide")
st.title("🎯 SMART: Hedef - Ortadaki Büyük Buton")

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

if st.button("Testi Başlat (v3)"):
    driver = get_driver()
    if driver:
        log_col, img_col = st.columns([1, 1])
        
        with log_col:
            st.info("1. Siteye gidiliyor...")
            driver.get("https://smart.embl-heidelberg.de/")
            time.sleep(3)
            
            # --- YÖNTEM: Görsel (Image) Üzerinden Gitmek ---
            # O buton büyük ihtimalle bir resim ve 'src' özelliğinde veya 'alt' özelliğinde ipucu var.
            st.write("🔍 Ortadaki 'Normal Mode' Görsel Butonu aranıyor...")
            
            found_button = None
            
            # Strateji A: Resmin alt yazısında (alt text) "Normal" aramak
            try:
                # Sayfadaki tüm resimleri tara
                images = driver.find_elements(By.TAG_NAME, "img")
                for img in images:
                    alt_text = img.get_attribute("alt")
                    src_text = img.get_attribute("src")
                    
                    # Eğer resmin açıklamasında veya dosya isminde "Normal" geçiyorsa ve "mode" geçiyorsa
                    if alt_text and "Normal" in alt_text:
                        st.info(f"Olası buton bulundu (Alt Text): {alt_text}")
                        # Bu resmin tıklanabilir bir link (parent a tag) içinde olup olmadığına bak
                        parent = img.find_element(By.XPATH, "..")
                        if parent.tag_name == 'a':
                            found_button = parent
                            break
                    
                    # Yedek plan: Dosya isminde "normal" geçiyorsa (örn: btn_normal.gif)
                    if src_text and "normal" in src_text.lower() and not "logo" in src_text.lower():
                         st.info(f"Olası buton bulundu (Src): {src_text}")
                         parent = img.find_element(By.XPATH, "..")
                         if parent.tag_name == 'a':
                            found_button = parent
                            break

                if found_button:
                    st.success("🎯 HEDEF KİLİTLENDİ: Ortadaki buton bulundu!")
                    found_button.click()
                    time.sleep(4) # Sayfa geçişi için bekle
                else:
                    st.error("❌ Resim tabanlı buton bulunamadı. CSS Selector deneniyor...")
                    
                    # Strateji B: CSS Selector ile ortadaki geniş kutuları hedefle
                    # Genellikle 'smart_mode_selection' gibi ID'ler olur.
                    # Deneme: Doğrudan URL'deki parametreyi içeren linki tekrar ama daha spesifik arayalım
                    buttons = driver.find_elements(By.XPATH, "//a[contains(@href, 'to=NORMAL')]")
                    # Genellikle sayfada 2 tane vardır, biri üstte biri ortada. İkincisine tıklayalım.
                    if len(buttons) > 1:
                        st.info(f"Sayfada {len(buttons)} adet Normal Mode linki var. Ortadakine (2.) tıklanıyor.")
                        buttons[1].click() 
                    elif len(buttons) == 1:
                        buttons[0].click()
                    else:
                        st.error("Hiçbir buton bulunamadı.")

            except Exception as e:
                st.error(f"Hata: {e}")

            # --- SONUÇ KONTROLÜ ---
            driver.save_screenshot("step3_result.png")
            
            # Artık "sequence" kelimesine güvenmiyoruz, doğrudan KUTUYU arıyoruz.
            try:
                # Sequence giriş kutusunun 'name' özelliği genellikle 'SEQUENCE' olur.
                input_box = driver.find_element(By.NAME, "SEQUENCE")
                if input_box:
                    st.balloons()
                    st.success("🎉 MÜKEMMEL! Sekans giriş kutusu (Textarea) bulundu. Artık hazırsın.")
            except:
                st.warning("⚠️ Tıklama yaptık ama hala giriş kutusunu (textarea) göremiyorum.")
                # HTML Dump (Son çare)
                with st.expander("Sayfa HTML Kaynağı"):
                    st.code(driver.page_source, language='html')

        with img_col:
            st.subheader("Son Görüntü")
            if os.path.exists("step3_result.png"):
                st.image("step3_result.png", caption="Tıklama Sonrası Ekran")
                
        driver.quit()
