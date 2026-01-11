import streamlit as st
import pandas as pd
import time
import datetime
import os
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType
from bs4 import BeautifulSoup

st.set_page_config(page_title="SMART Ultimate Live", layout="wide")
st.title("🔴 SMART: Canlı Yayın + JavaScript Tablo Bekleme")

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

def update_monitor(log_box, img_box, message, driver, img_suffix):
    """Canlı log ve görüntü güncelleme"""
    now = datetime.datetime.now().strftime("%H:%M:%S")
    log_box.markdown(f"`[{now}]` {message}")
    if driver:
        fname = f"live_{img_suffix}_{int(time.time())}.png"
        driver.save_screenshot(fname)
        img_box.image(fname, caption=f"Bot Gözü: {message}", use_container_width=True)

def extract_number(text):
    match = re.search(r'\d+', text)
    return int(match.group()) if match else None

if st.button("🔴 CANLI ANALİZİ BAŞLAT"):
    driver = get_driver()
    if driver:
        # EKRANI İKİYE BÖL (İstediğin Gibi)
        col1, col2 = st.columns([1, 1])
        with col1:
            st.subheader("📜 Sistem Logları")
            log_box = st.empty()
        with col2:
            st.subheader("👀 Bot Gözünden")
            img_box = st.empty()

        # --- 1. GİRİŞ ---
        update_monitor(log_box, img_box, "Siteye bağlanılıyor...", driver, "init")
        driver.get("https://smart.embl-heidelberg.de/")
        
        # --- 2. MOD SEÇİMİ ---
        try:
            driver.implicitly_wait(2)
            links = driver.find_elements(By.CSS_SELECTOR, "a[href*='change_mode.cgi?mode=normal']")
            if links:
                update_monitor(log_box, img_box, "Mod seçimi yapılıyor...", driver, "mode_select")
                driver.execute_script("arguments[0].click();", links[0])
                time.sleep(2)
        except: pass
        
        # --- 3. FORM DOLDURMA ---
        try:
            # Pfam
            try: pfam = driver.find_element(By.NAME, "DO_PFAM")
            except: pfam = driver.find_element(By.XPATH, "//input[contains(@name, 'PFAM')]")
            if not pfam.is_selected(): driver.execute_script("arguments[0].click();", pfam)
            
            # Sekans
            seq_box = driver.find_element(By.NAME, "SEQUENCE")
            seq_box.clear()
            seq_box.send_keys(TEST_SEQUENCE)
            
            update_monitor(log_box, img_box, "Form dolduruldu. ZORLA GÖNDERİLİYOR...", driver, "form_ready")
            
            # FORCE SUBMIT
            driver.execute_script("arguments[0].form.submit();", seq_box)
            
        except Exception as e:
            st.error(f"Form hatası: {e}")
            driver.quit()
            st.stop()

        # --- 4. BEKLEME ve TABLO YAKALAMA (YENİ MANTIK) ---
        start_time = time.time()
        results_found = False
        
        while time.time() - start_time < 90:
            elapsed = int(time.time() - start_time)
            
            # Her 5 saniyede bir güncelleme
            if elapsed % 4 == 0:
                update_monitor(log_box, img_box, f"⏳ Sonuç bekleniyor ({elapsed}sn)...", driver, f"waiting_{elapsed}")

            page_src = driver.page_source
            
            # Sayfa yüklendi mi?
            if "Confidently predicted domains" in page_src:
                update_monitor(log_box, img_box, "✅ Başlık görüldü! Tablo verilerinin yüklenmesi bekleniyor (JS)...", driver, "header_seen")
                
                # İŞTE ÇÖZÜM: Tablonun içi (tr) dolana kadar bekle!
                try:
                    # 'Start' içeren tablonun içindeki satırları (tr) bekle
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "table.dataTable tbody tr"))
                    )
                    # Boş olmayan bir satır görene kadar bekle
                    time.sleep(2) 
                    update_monitor(log_box, img_box, "✅ Tablo satırları yüklendi! Veri çekiliyor...", driver, "table_loaded")
                    results_found = True
                    break
                except:
                    update_monitor(log_box, img_box, "⚠️ Tablo başlığı var ama satırlar yüklenmedi (Timeout).", driver, "table_timeout")
                    # Yine de devam edip ne var ne yok bakalım
                    results_found = True 
                    break
            
            if "No domains found" in page_src:
                update_monitor(log_box, img_box, "⚠️ Sonuç: Domain bulunamadı.", driver, "no_domains")
                results_found = True
                break
            
            time.sleep(1)

        # --- 5. VERİ ÇEKME ---
        if results_found:
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            tables = soup.find_all("table")
            target_table = None
            
            # Tabloyu bul
            for tbl in tables:
                headers = [th.get_text(strip=True) for th in tbl.find_all("th")]
                if "Start" in headers and "End" in headers:
                    target_table = tbl
                    break
            
            if target_table:
                data = []
                # tbody kontrolü
                tbody = target_table.find("tbody")
                if tbody:
                    rows = tbody.find_all("tr")
                else:
                    rows = target_table.find_all("tr")[1:] # tbody yoksa direk tr'leri al
                
                log_box.info(f"Tabloda {len(rows)} satır veri bulundu.")
                
                for row in rows:
                    cols = row.find_all("td")
                    col_texts = [td.get_text(strip=True) for td in cols]
                    
                    if len(cols) >= 3:
                        f_name = col_texts[0]
                        start_val = extract_number(col_texts[1])
                        end_val = extract_number(col_texts[2])
                        
                        if start_val is not None:
                            e_val = col_texts[3] if len(cols) > 3 else "-"
                            data.append({
                                "Feature": f_name,
                                "Start": start_val,
                                "End": end_val,
                                "E-value": e_val
                            })
                
                if data:
                    df = pd.DataFrame(data)
                    st.success(f"🎉 {len(data)} Domain Bulundu!")
                    st.dataframe(df, use_container_width=True)
                else:
                    st.warning("Tablo var ama satırlardan veri çıkarılamadı.")
                    st.code(target_table.prettify()) # HTML'i göster
            else:
                st.error("Tablo yapısı eşleşmedi.")
        else:
            st.error("Zaman aşımı.")
        
        driver.quit()
