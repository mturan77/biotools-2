import streamlit as st
import pandas as pd
import time
import datetime
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType

st.set_page_config(page_title="SMART Live DOM", layout="wide")
st.title("🔴 SMART: Canlı DOM Okuyucu (JavaScript Uyumlu)")

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
        return webdriver.Chrome(service=service, options=chrome_options)
    except Exception as e:
        st.error(f"Driver hatası: {e}")
        return None

def update_monitor(log_box, img_box, message, driver, suffix):
    now = datetime.datetime.now().strftime("%H:%M:%S")
    log_box.markdown(f"`[{now}]` {message}")
    if driver:
        fname = f"monitor_{suffix}_{int(time.time())}.png"
        driver.save_screenshot(fname)
        img_box.image(fname, caption=f"Bot Gözü: {message}", use_container_width=True)

if st.button("🔴 CANLI ANALİZİ BAŞLAT"):
    driver = get_driver()
    if driver:
        col1, col2 = st.columns([1, 1])
        with col1:
            st.subheader("📜 Loglar")
            log_box = st.empty()
        with col2:
            st.subheader("👀 Ekran")
            img_box = st.empty()

        # 1. GİRİŞ
        update_monitor(log_box, img_box, "Siteye gidiliyor...", driver, "init")
        driver.get("https://smart.embl-heidelberg.de/")
        
        # 2. MOD
        try:
            driver.implicitly_wait(2)
            links = driver.find_elements(By.CSS_SELECTOR, "a[href*='change_mode.cgi?mode=normal']")
            if links: 
                driver.execute_script("arguments[0].click();", links[0])
                time.sleep(2)
        except: pass
        
        # 3. FORM
        try:
            try: pfam = driver.find_element(By.NAME, "DO_PFAM")
            except: pfam = driver.find_element(By.XPATH, "//input[contains(@name, 'PFAM')]")
            if not pfam.is_selected(): driver.execute_script("arguments[0].click();", pfam)
            
            seq_box = driver.find_element(By.NAME, "SEQUENCE")
            seq_box.clear()
            seq_box.send_keys(TEST_SEQUENCE)
            
            # SUBMIT
            driver.execute_script("arguments[0].form.submit();", seq_box)
            update_monitor(log_box, img_box, "Form gönderildi...", driver, "sent")
            
        except Exception as e:
            st.error(f"Hata: {e}")
            driver.quit()
            st.stop()

        # 4. TABLO BEKLEME (KRİTİK BÖLÜM)
        start_time = time.time()
        table_ready = False
        
        while time.time() - start_time < 90:
            elapsed = int(time.time() - start_time)
            
            if "Confidently predicted domains" in driver.page_source:
                # Tablo başlığı geldi ama satırlar (tbody tr) geldi mi?
                # Canlı DOM kontrolü yapıyoruz:
                try:
                    # DataTables genellikle "odd" veya "even" class'lı satırlar ekler
                    # CSS Selector ile tablonun BODY kısmındaki satırları arıyoruz
                    rows = driver.find_elements(By.CSS_SELECTOR, "table.dataTable tbody tr")
                    
                    if len(rows) > 0:
                        # Boş bir satır olup olmadığını kontrol edelim ("No data available" yazabilir)
                        first_row_text = rows[0].text
                        if "No data available" not in first_row_text and len(first_row_text.strip()) > 0:
                            update_monitor(log_box, img_box, f"✅ Tablo DOLU! ({len(rows)} satır tespit edildi)", driver, "table_filled")
                            table_ready = True
                            break
                        else:
                            if elapsed % 2 == 0: update_monitor(log_box, img_box, "⏳ Tablo boş, JS yüklemesi bekleniyor...", driver, "waiting_js")
                    else:
                        if elapsed % 2 == 0: update_monitor(log_box, img_box, "⏳ Tablo iskeleti var, satırlar bekleniyor...", driver, "waiting_rows")
                except:
                    pass
            else:
                 if elapsed % 5 == 0: update_monitor(log_box, img_box, f"⏳ Sonuç sayfası bekleniyor ({elapsed}sn)...", driver, "waiting_page")
            
            time.sleep(1)

        # 5. VERİ OKUMA (SELENIUM İLE)
        if table_ready:
            data = []
            # Canlı elementleri tekrar bul
            rows = driver.find_elements(By.CSS_SELECTOR, "table.dataTable tbody tr")
            
            for row in rows:
                # Her satırın içindeki hücreleri (td) bul
                cols = row.find_elements(By.TAG_NAME, "td")
                
                if len(cols) >= 3:
                    # İsim (KISc gibi) genellikle ilk hücrededir.
                    # Senin resmine göre: <td> <div> <a ...>KISc</a> </div> </td>
                    # .text özelliği gizli olmayan tüm yazıları getirir.
                    feature_text = cols[0].text.strip()
                    
                    # Eğer boşsa veya alt satırlara inmemiz gerekirse
                    if not feature_text:
                        try:
                            feature_text = cols[0].find_element(By.TAG_NAME, "a").text
                        except: pass
                    
                    start_text = cols[1].text.strip()
                    end_text = cols[2].text.strip()
                    e_value = cols[3].text.strip() if len(cols) > 3 else "-"
                    
                    # Sadece sayısal başlangıç değeri olanları al (Gereksiz başlıkları ele)
                    if start_text.isdigit():
                        data.append({
                            "Feature": feature_text,
                            "Start": int(start_text),
                            "End": int(end_text),
                            "E-value": e_value
                        })
            
            if data:
                df = pd.DataFrame(data)
                st.success(f"🎉 {len(data)} Domain Başarıyla Çekildi!")
                st.dataframe(df, use_container_width=True)
                
                # İndirme Butonu
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button("CSV İndir", csv, "smart_results.csv", "text/csv")
            else:
                st.warning("Tablo satırları bulundu ama metin okunamadı.")
                st.write("İlk satırın ham metni:", rows[0].get_attribute("innerHTML"))
        else:
            st.error("Zaman aşımı veya tablo yüklenemedi.")

        driver.quit()
