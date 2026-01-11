import streamlit as st
import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType

st.set_page_config(page_title="SMART Form Testi v2", layout="wide")
st.title("📝 SMART: Form Doldurma Testi (Pfam Düzeltilmiş)")

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

if st.button("Form Testini Başlat (v2)"):
    driver = get_driver()
    if driver:
        log_col, img_col = st.columns([1, 1])
        
        with log_col:
            st.info("1. Siteye gidiliyor...")
            driver.get("https://smart.embl-heidelberg.de/")
            time.sleep(2)
            
            # --- ADIM 1: MOD KONTROLÜ ---
            try:
                driver.implicitly_wait(3) 
                # CSS Selector ile daha kesin hedefleme
                normal_mode_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='change_mode.cgi?mode=normal']")
                
                if normal_mode_links:
                    st.warning("⚠️ Mod seçimi ekranı tespit edildi. 'Normal Mode' seçiliyor...")
                    btn = normal_mode_links[0]
                    driver.execute_script("arguments[0].scrollIntoView();", btn)
                    btn.click()
                    time.sleep(3)
                    st.success("✅ Mod seçimi geçildi.")
                else:
                    st.success("✅ Doğrudan analiz sayfası açıldı.")
            except:
                pass
            finally:
                driver.implicitly_wait(10)

            # --- ADIM 2: PFAM DOMAINS SEÇİMİ (YENİ STRATEJİ) ---
            st.info("2. 'Pfam domains' kutucuğu aranıyor...")
            pfam_found = False
            
            try:
                # YÖNTEM A: İsim (Name) ile arama (En standart yöntem)
                pfam_checkbox = driver.find_element(By.NAME, "DO_PFAM")
                st.write("🔹 Yöntem A (By Name) ile bulundu.")
                pfam_found = True
            except:
                # YÖNTEM B: Metin bazlı XPath (Yazısı 'Pfam domains' olan input)
                try:
                    # Input, "Pfam domains" metninin hemen öncesinde veya sonrasında olabilir
                    # Bu XPath, sayfa içinde "Pfam domains" metnini içeren bir elementin yakınındaki inputu arar
                    pfam_checkbox = driver.find_element(By.XPATH, "//input[parent::*[contains(text(), 'Pfam domains')]] | //input[following-sibling::text()[contains(., 'Pfam domains')]]")
                    st.write("🔹 Yöntem B (By Text) ile bulundu.")
                    pfam_found = True
                except:
                    st.error("❌ Pfam kutusu standart yöntemlerle bulunamadı.")

            if pfam_found and pfam_checkbox:
                try:
                    # Tikli değilse tıkla
                    if not pfam_checkbox.is_selected():
                        # Javascript ile tıklamak en garantisidir (Görünmez olsa bile tıklar)
                        driver.execute_script("arguments[0].click();", pfam_checkbox)
                        st.success("✅ 'Pfam domains' işaretlendi.")
                    else:
                        st.info("ℹ️ 'Pfam domains' zaten seçili.")
                except Exception as e:
                    st.error(f"Tıklama hatası: {e}")
            else:
                # Bulamazsa HTML yapısını görelim
                st.warning("Sayfa yapısı beklenenden farklı. HTML analizi:")
                with st.expander("HTML Kaynağı"):
                    st.code(driver.page_source[:5000], language='html')

            # --- ADIM 3: SEKANS GİRİŞİ ---
            st.info("3. Test sekansı giriliyor...")
            try:
                seq_box = driver.find_element(By.NAME, "SEQUENCE")
                seq_box.clear()
                test_seq = "MKTLLILAVSLIAAGLSQG" 
                seq_box.send_keys(test_seq)
                st.success(f"✅ Sekans yazıldı: {test_seq}")
            except Exception as e:
                st.error(f"❌ Sekans kutusu hatası: {e}")

            # Fotoğraf Al
            time.sleep(1)
            driver.save_screenshot("step4_fix.png")
            st.info("⏹️ Hazırlık tamam. (Butona henüz tıklanmadı)")

        with img_col:
            st.subheader("Form Son Durum")
            if os.path.exists("step4_fix.png"):
                st.image("step4_fix.png", caption="Pfam Seçili mi? (Tik işaretini kontrol et)")
                
        driver.quit()
