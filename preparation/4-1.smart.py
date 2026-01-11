import streamlit as st
import pandas as pd
import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys  # ENTER tuşu için gerekli
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType
from bs4 import BeautifulSoup

st.set_page_config(page_title="SMART Analiz v2", layout="wide")
st.title("🧬 SMART: Gerçek Analiz (Garantili Gönderim)")

# Test Sekansı (Kinesin)
TEST_SEQUENCE = "MKLKGNMNTSAQNQSQSQPPRKTNEHIQVYVRVRPLNRREKCIHSTEIVEVVSHKEIVARHSLESKLTKKFTFDRTFGPESKQVDVYAAVVGPLIEEVLSGYNCTVFAYGQTGTGKTHTMVGNECAELKSSWEDDSDIGIIPRALCHLFDELRMMELEFSMRISYLELYNEELFDLLSTDDSTKIRIFDDSTKKGSVIIQGLEEIPVHSKDDVYKLLEKGKERRRTASTLMNAQSSRSHTVFSIVVHIKENGIDGEEMLKIGKLNLVDLAGSENVSKAGNEKGVRVRETVNINQSLLTLGRVITALVERTPHIPYRESKLTRLLQESLGGRTKTSIIATISPGHKDIEETLSTLEYAHRAKNIQNKPEVNQKLTKKTVLKEYTEEIDKLKRDLMAARDKNGVYLATETYNEMTLKMDSQTRELNEKVHLLKALKDELASKEKIFNEVSLNLIEKTAELQQKDNRLRSTKGELIETKKVLKNTKRRYKEKKVLLESHAKTEEVLKDQATQILEVADIATKDTEALHETIDRRKDVDVKIQTACERFTERMNENFDQMDETLKQYEGKQISLTRCMDEELTKTSSVQSKLIDATSEQIKSIKQILDSYETSMSSMTENLCSTLTNTGQQQNTSIINFLKQLKEKELQFKTQIKENLEAIECTNEQQQIALSGMRDSIKEKLEESNTKLQQHTKRIQTEMDAIKQKTLENSQELQKISTNLTEQRTLVEEEQKLLEDFQNKMQELHKKHTACSNNINTNVETLEKAQQFVTTQLEGSSKLQQVFLEKNAKALENNCLLVDKLRDQIELHIDQNVAKCSTLTIQLDNKVQETSKALESQIVIADQHYTQTTETLKVYGPQVKRICSERREQHNGKTDLILNSLQNHVKQTVENVSIIKGFNCSLQQKLKDYSKVYKEQMQSCAQDVEIFRKSEIKTYTATGATPSKKDFKYPRVLAATSPHSNIVKRFRQENDWSDLDMTIPLDEESETDIENSISDTETILNSTPVETEIVPPKRNSYVTQRKSDRNSNLLKVPPQSNSRSGSPAGSISPRKGSSRTNSPAYLKQNKENITT"

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

if st.button("Garantili Analizi Başlat"):
    driver = get_driver()
    if driver:
        status_box = st.empty()
        status_box.info("🚀 Siteye bağlanılıyor...")
        
        driver.get("https://smart.embl-heidelberg.de/")
        time.sleep(2)
        
        # --- 1. MOD SEÇİMİ ---
        try:
            driver.implicitly_wait(2)
            normal_mode_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='change_mode.cgi?mode=normal']")
            if normal_mode_links:
                status_box.warning("⚠️ Normal Mode seçiliyor...")
                btn = normal_mode_links[0]
                driver.execute_script("arguments[0].scrollIntoView();", btn)
                btn.click()
                time.sleep(2)
        except:
            pass
        finally:
            driver.implicitly_wait(10)

        # --- 2. FORM DOLDURMA ---
        status_box.info("📝 Form dolduruluyor...")
        try:
            # Pfam Seçimi (Akıllı)
            try:
                pfam_checkbox = driver.find_element(By.NAME, "DO_PFAM")
            except:
                # Bulamazsa text ile dene
                pfam_checkbox = driver.find_element(By.XPATH, "//input[parent::*[contains(text(), 'Pfam')]]")
                
            if not pfam_checkbox.is_selected():
                driver.execute_script("arguments[0].click();", pfam_checkbox)
            
            # Sekans Girişi
            seq_box = driver.find_element(By.NAME, "SEQUENCE")
            seq_box.clear()
            seq_box.send_keys(TEST_SEQUENCE)
            
        except Exception as e:
            st.error(f"Form doldurma hatası: {e}")
            driver.quit()
            st.stop()

        # --- 3. GÖNDERİM (GARANTİLİ YÖNTEM) ---
        status_box.info("📡 Sunucuya gönderiliyor (Form Submit Yöntemi)...")
        try:
            # YÖNTEM 1: Butonu Text ile bulmaya çalış (Daha güvenli)
            # XPath: İçinde 'Sequence SMART' yazan herhangi bir tıklanabilir öge
            try:
                submit_btn = driver.find_element(By.XPATH, "//*[contains(text(), 'Sequence SMART')]")
                # Eğer bulduğu şey bir span ise ve tıklanabilir değilse, üst elemente (button/a) çık
                if submit_btn.tag_name == "span":
                    submit_btn = submit_btn.find_element(By.XPATH, "..")
                submit_btn.click()
                st.success("✅ Butona tıklandı.")
            except:
                # YÖNTEM 2: Eğer butonu bulamazsa, SEKANS KUTUSUNDA ENTER'A BAS
                st.warning("⚠️ Buton bulunamadı, ENTER tuşu ile gönderiliyor...")
                seq_box.send_keys(Keys.ENTER)
                # Veya formu direkt submit et
                # seq_box.submit() 
            
            # BEKLEME DÖNGÜSÜ
            max_wait = 90 # Biraz daha uzun süre tanıyalım
            start_time = time.time()
            found_results = False
            
            while time.time() - start_time < max_wait:
                page_source = driver.page_source
                
                # Başarı Kontrolü
                if "Confidently predicted domains" in page_source:
                    status_box.success("✅ Sonuç sayfası yüklendi! Tablo ayrıştırılıyor...")
                    found_results = True
                    break
                
                # Boş Sonuç Kontrolü
                if "No domains found" in page_source:
                    status_box.warning("⚠️ Analiz bitti ancak domain bulunamadı.")
                    found_results = True
                    break
                
                # Bekleme mesajı
                elapsed = int(time.time() - start_time)
                status_box.info(f"⏳ Sunucu hesaplıyor... Lütfen bekleyin ({elapsed} sn)")
                time.sleep(2)
            
            if not found_results:
                st.error("❌ Zaman aşımı: Sunucu yanıt vermedi.")
                driver.save_screenshot("timeout_v2.png")
                st.image("timeout_v2.png")
                driver.quit()
                st.stop()

        except Exception as e:
            st.error(f"Gönderim hatası: {e}")
            driver.quit()
            st.stop()

        # --- 4. SONUÇLARI GÖSTER ---
        if found_results:
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            target_table = None
            tables = soup.find_all("table")
            for table in tables:
                headers = [th.get_text(strip=True) for th in table.find_all("th")]
                if "Feature" in headers and "Start" in headers:
                    target_table = table
                    break
            
            if target_table:
                data = []
                rows = target_table.find_all("tr")[1:] 
                for row in rows:
                    cols = row.find_all("td")
                    if len(cols) >= 3:
                        f_name = cols[0].get_text(strip=True)
                        if cols[0].find('a'):
                            f_name = cols[0].find('a').get_text(strip=True)
                        
                        start = cols[1].get_text(strip=True)
                        end = cols[2].get_text(strip=True)
                        e_val = cols[3].get_text(strip=True) if len(cols) > 3 else "-"
                        
                        if start.isdigit():
                            data.append({
                                "Feature": f_name,
                                "Start": int(start),
                                "End": int(end),
                                "E-value": e_val
                            })
                
                if data:
                    df = pd.DataFrame(data)
                    st.divider()
                    st.subheader(f"📊 Analiz Sonucu: {len(data)} Domain")
                    st.dataframe(df, use_container_width=True)
                    
                    driver.save_screenshot("final_success.png")
                    st.image("final_success.png", caption="Başarılı Sonuç Sayfası")
                else:
                    st.warning("Tablo bulundu ama boş.")
            else:
                st.error("Sonuç tablosu bulunamadı.")
                driver.save_screenshot("no_table.png")
                st.image("no_table.png")

        driver.quit()
