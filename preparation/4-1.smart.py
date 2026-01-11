import streamlit as st
import pandas as pd
import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType
from bs4 import BeautifulSoup

st.set_page_config(page_title="SMART Gerçek Analiz", layout="wide")
st.title("🧬 SMART: Gerçek Sekans Analizi ve Sonuç Tablosu")

# Kullanıcının verdiği test sekansı
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

if st.button("Analizi Başlat ve Sonuçları Getir"):
    driver = get_driver()
    if driver:
        status_box = st.empty()
        status_box.info("🚀 Siteye bağlanılıyor...")
        
        driver.get("https://smart.embl-heidelberg.de/")
        time.sleep(2)
        
        # --- 1. MOD SEÇİMİ (Gerekirse) ---
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
        status_box.info("📝 Form dolduruluyor (Pfam + Sekans)...")
        try:
            # Pfam Seç
            pfam_checkbox = driver.find_element(By.NAME, "DO_PFAM")
            if not pfam_checkbox.is_selected():
                driver.execute_script("arguments[0].click();", pfam_checkbox)
            
            # Sekans Gir
            seq_box = driver.find_element(By.NAME, "SEQUENCE")
            seq_box.clear()
            seq_box.send_keys(TEST_SEQUENCE)
            
        except Exception as e:
            st.error(f"Form hatası: {e}")
            driver.quit()
            st.stop()

        # --- 3. GÖNDER VE BEKLE ---
        status_box.info("📡 Sunucuya gönderiliyor ve sonuç bekleniyor (Bu işlem 30-40sn sürebilir)...")
        try:
            # Sequence SMART butonuna tıkla (Value değeri ile bul)
            submit_btn = driver.find_element(By.XPATH, "//input[@value='Sequence SMART']")
            submit_btn.click()
            
            # BEKLEME DÖNGÜSÜ
            max_wait = 60 # Saniye
            start_time = time.time()
            found_results = False
            
            while time.time() - start_time < max_wait:
                page_source = driver.page_source
                
                # Durum 1: Sonuç Tablosu Geldi mi?
                if "Confidently predicted domains" in page_source:
                    status_box.success("✅ Sonuçlar alındı! Tablo ayrıştırılıyor...")
                    found_results = True
                    break
                
                # Durum 2: Sonuç Yok mu?
                if "No domains found" in page_source:
                    status_box.warning("⚠️ Analiz bitti ancak domain bulunamadı.")
                    found_results = True # İşlem bitti sayılır
                    break
                
                # Beklerken kullanıcıya bilgi ver
                elapsed = int(time.time() - start_time)
                status_box.info(f"⏳ Sunucu hesaplıyor... ({elapsed} sn)")
                time.sleep(2)
            
            if not found_results:
                st.error("❌ Zaman aşımı: Sunucu 60 saniye içinde yanıt vermedi.")
                driver.save_screenshot("timeout_error.png")
                st.image("timeout_error.png")
                driver.quit()
                st.stop()

        except Exception as e:
            st.error(f"Gönderim hatası: {e}")
            driver.quit()
            st.stop()

        # --- 4. SONUCU PARSE ET VE TABLO YAP ---
        if found_results:
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            # Tabloyu bul
            target_table = None
            tables = soup.find_all("table")
            for table in tables:
                headers = [th.get_text(strip=True) for th in table.find_all("th")]
                if "Feature" in headers and "Start" in headers:
                    target_table = table
                    break
            
            if target_table:
                data = []
                rows = target_table.find_all("tr")[1:] # Başlığı atla
                for row in rows:
                    cols = row.find_all("td")
                    if len(cols) >= 3:
                        # Feature ismini temizle (link içindeyse)
                        f_name = cols[0].get_text(strip=True)
                        if cols[0].find('a'):
                            f_name = cols[0].find('a').get_text(strip=True)
                        
                        start = cols[1].get_text(strip=True)
                        end = cols[2].get_text(strip=True)
                        e_val = cols[3].get_text(strip=True) if len(cols) > 3 else "-"
                        
                        # Sadece sayısal veri içerenleri al (çöp satırları at)
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
                    st.subheader(f"📊 Sonuç Tablosu ({len(data)} Domain Bulundu)")
                    st.dataframe(df, use_container_width=True)
                    
                    # Kanıt fotosu
                    driver.save_screenshot("result_page.png")
                    with st.expander("Sonuç Sayfası Görüntüsü"):
                        st.image("result_page.png")
                else:
                    st.warning("Tablo bulundu ama içinde veri okunamadı.")
            else:
                st.warning("Sonuç sayfasında 'Confidently predicted domains' tablosu bulunamadı.")
                driver.save_screenshot("no_table_error.png")
                st.image("no_table_error.png")

        driver.quit()
