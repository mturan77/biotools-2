import streamlit as st
import pandas as pd
import time
import datetime
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType
from bs4 import BeautifulSoup

st.set_page_config(page_title="SMART Force Submit", layout="wide")
st.title("🔴 SMART: Zorla Gönderim ve Canlı Takip")

# --- Test Sekansı ---
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

def update_monitor(log_box, img_box, message, driver, img_name_suffix):
    """Hem log yazar hem de o anki ekran görüntüsünü yeniler"""
    now = datetime.datetime.now().strftime("%H:%M:%S")
    log_box.markdown(f"`[{now}]` {message}")
    
    if driver:
        # Benzersiz dosya adı oluştur ki Streamlit cache'e takılmasın
        filename = f"screenshot_{img_name_suffix}_{int(time.time())}.png"
        driver.save_screenshot(filename)
        img_box.image(filename, caption=f"Bot Gözünden: {message}", use_container_width=True)
        
        # Temizlik (Opsiyonel)
        # os.remove(filename) 

if st.button("🔴 CANLI ANALİZİ BAŞLAT (FORCE MODE)"):
    driver = get_driver()
    if driver:
        # Ekran Düzeni
        col_log, col_img = st.columns([1, 1])
        with col_log:
            st.subheader("📜 Canlı Loglar")
            log_box = st.empty()
        with col_img:
            st.subheader("👀 Anlık Ekran")
            img_box = st.empty()

        # --- 1. GİRİŞ ---
        update_monitor(log_box, img_box, "Siteye gidiliyor...", driver, "1_init")
        driver.get("https://smart.embl-heidelberg.de/")
        
        # --- 2. MOD KONTROLÜ ---
        try:
            driver.implicitly_wait(2)
            links = driver.find_elements(By.CSS_SELECTOR, "a[href*='change_mode.cgi?mode=normal']")
            if links:
                update_monitor(log_box, img_box, "Mod seçimi yapılıyor...", driver, "2_mode")
                driver.execute_script("arguments[0].click();", links[0])
                time.sleep(2)
        except:
            pass
        finally:
            driver.implicitly_wait(10)

        # --- 3. FORM DOLDURMA ---
        update_monitor(log_box, img_box, "Form dolduruluyor...", driver, "3_form")
        try:
            # Pfam Seç
            try:
                pfam = driver.find_element(By.NAME, "DO_PFAM")
            except:
                pfam = driver.find_element(By.XPATH, "//input[contains(@name, 'PFAM')]")
            
            if not pfam.is_selected():
                driver.execute_script("arguments[0].click();", pfam)
            
            # Sekans Gir
            seq_box = driver.find_element(By.NAME, "SEQUENCE")
            seq_box.clear()
            seq_box.send_keys(TEST_SEQUENCE)
            
        except Exception as e:
            st.error(f"Form hatası: {e}")
            driver.quit()
            st.stop()

        # --- 4. ZORLA GÖNDERİM (JS FORM SUBMIT) ---
        update_monitor(log_box, img_box, "🚀 FORMU ZORLA GÖNDERİYORUM...", driver, "4_pre_submit")
        try:
            # Sekans kutusunun içinde bulunduğu FORMU bul ve submit() komutu ver
            # Bu, butona tıklamaktan çok daha etkilidir.
            driver.execute_script("arguments[0].form.submit();", seq_box)
            
            # Hemen 2 saniye sonra durumu kontrol et
            time.sleep(3)
            update_monitor(log_box, img_box, "Gönderim komutu verildi. URL değişti mi bakılıyor...", driver, "5_post_submit")
            
        except Exception as e:
            st.error(f"Gönderim hatası: {e}")
            driver.quit()
            st.stop()

        # --- 5. BEKLEME DÖNGÜSÜ ---
        start_time = time.time()
        found = False
        
        while time.time() - start_time < 60:
            elapsed = int(time.time() - start_time)
            src = driver.page_source
            
            # Her 5 saniyede bir ekranı güncelle
            if elapsed % 3 == 0:
                update_monitor(log_box, img_box, f"⏳ Bekleniyor... ({elapsed}sn)", driver, f"6_wait_{elapsed}")

            # Başarı Durumu
            if "Confidently predicted domains" in src:
                update_monitor(log_box, img_box, "✅ SONUÇ SAYFASI YÜKLENDİ!", driver, "7_success")
                found = True
                break
            
            # Boş Sonuç
            if "No domains found" in src:
                update_monitor(log_box, img_box, "⚠️ Sonuç geldi ama domain yok.", driver, "7_empty")
                found = True
                break
            
            time.sleep(1)

        # --- 6. SONUÇ ÇIKTI ---
        if found:
            st.success("İşlem tamamlandı, tablo aranıyor...")
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            tables = soup.find_all("table")
            
            target = None
            for tbl in tables:
                headers = [th.get_text(strip=True) for th in tbl.find_all("th")]
                if "Feature" in headers:
                    target = tbl
                    break
            
            if target:
                rows = target.find_all("tr")[1:]
                data = []
                for r in rows:
                    c = r.find_all("td")
                    if len(c) >= 3 and c[1].get_text(strip=True).isdigit():
                        f_name = c[0].get_text(strip=True)
                        if c[0].find('a'): f_name = c[0].find('a').get_text(strip=True)
                        data.append({
                            "Feature": f_name,
                            "Start": c[1].get_text(strip=True),
                            "End": c[2].get_text(strip=True),
                            "E-value": c[3].get_text(strip=True) if len(c)>3 else "-"
                        })
                
                if data:
                    st.dataframe(pd.DataFrame(data))
                else:
                    st.warning("Tablo boş.")
            else:
                st.error("Tablo bulunamadı.")
        else:
            st.error("❌ Süre doldu. Sayfa hala değişmediyse SMART sunucusu yanıt vermiyor demektir.")
        
        driver.quit()
