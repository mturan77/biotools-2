import streamlit as st
import pandas as pd
import time
import datetime
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType
from bs4 import BeautifulSoup

st.set_page_config(page_title="SMART Canlı İzleme", layout="wide")
st.title("🔴 SMART: Canlı Bot İzleme ve Analiz")

# --- Test Sekansı ---
TEST_SEQUENCE = "MKLKGNMNTSAQNQSQSQPPRKTNEHIQVYVRVRPLNRREKCIHSTEIVEVVSHKEIVARHSLESKLTKKFTFDRTFGPESKQVDVYAAVVGPLIEEVLSGYNCTVFAYGQTGTGKTHTMVGNECAELKSSWEDDSDIGIIPRALCHLFDELRMMELEFSMRISYLELYNEELFDLLSTDDSTKIRIFDDSTKKGSVIIQGLEEIPVHSKDDVYKLLEKGKERRRTASTLMNAQSSRSHTVFSIVVHIKENGIDGEEMLKIGKLNLVDLAGSENVSKAGNEKGVRVRETVNINQSLLTLGRVITALVERTPHIPYRESKLTRLLQESLGGRTKTSIIATISPGHKDIEETLSTLEYAHRAKNIQNKPEVNQKLTKKTVLKEYTEEIDKLKRDLMAARDKNGVYLATETYNEMTLKMDSQTRELNEKVHLLKALKDELASKEKIFNEVSLNLIEKTAELQQKDNRLRSTKGELIETKKVLKNTKRRYKEKKVLLESHAKTEEVLKDQATQILEVADIATKDTEALHETIDRRKDVDVKIQTACERFTERMNENFDQMDETLKQYEGKQISLTRCMDEELTKTSSVQSKLIDATSEQIKSIKQILDSYETSMSSMTENLCSTLTNTGQQQNTSIINFLKQLKEKELQFKTQIKENLEAIECTNEQQQIALSGMRDSIKEKLEESNTKLQQHTKRIQTEMDAIKQKTLENSQELQKISTNLTEQRTLVEEEQKLLEDFQNKMQELHKKHTACSNNINTNVETLEKAQQFVTTQLEGSSKLQQVFLEKNAKALENNCLLVDKLRDQIELHIDQNVAKCSTLTIQLDNKVQETSKALESQIVIADQHYTQTTETLKVYGPQVKRICSERREQHNGKTDLILNSLQNHVKQTVENVSIIKGFNCSLQQKLKDYSKVYKEQMQSCAQDVEIFRKSEIKTYTATGATPSKKDFKYPRVLAATSPHSNIVKRFRQENDWSDLDMTIPLDEESETDIENSISDTETILNSTPVETEIVPPKRNSYVTQRKSDRNSNLLKVPPQSNSRSGSPAGSISPRKGSSRTNSPAYLKQNKENITT"

# --- Driver Ayarları ---
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

# --- Yardımcı: Loglama ve Görüntüleme ---
def update_status(log_placeholder, img_placeholder, message, driver=None, step_name="step"):
    # Log Yaz
    now = datetime.datetime.now().strftime("%H:%M:%S")
    log_placeholder.markdown(f"`[{now}]` {message}")
    
    # Fotoğraf Çek ve Göster
    if driver:
        filename = f"{step_name}.png"
        driver.save_screenshot(filename)
        if os.path.exists(filename):
            img_placeholder.image(filename, caption=f"Bot Gözü: {step_name}", use_column_width=True)

# --- ANA UYGULAMA ---
if st.button("🔴 CANLI YAYINI BAŞLAT"):
    driver = get_driver()
    
    if driver:
        # Ekranı İkiye Böl
        col_log, col_img = st.columns([1, 1])
        
        with col_log:
            st.subheader("📜 Sistem Logları")
            log_box = st.empty() # Dinamik log alanı
            
        with col_img:
            st.subheader("👀 Bot Gözünden")
            img_box = st.empty() # Dinamik resim alanı

        # --- ADIM 1: GİRİŞ ---
        update_status(log_box, img_box, "Siteye bağlanılıyor...", driver, "1_init")
        driver.get("https://smart.embl-heidelberg.de/")
        time.sleep(2)
        
        # --- ADIM 2: MOD KONTROLÜ ---
        update_status(log_box, img_box, "Mod seçimi kontrol ediliyor...", driver, "2_mode_check")
        try:
            driver.implicitly_wait(2)
            normal_mode_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='change_mode.cgi?mode=normal']")
            if normal_mode_links:
                update_status(log_box, img_box, "⚠️ Mod ekranı tespit edildi. Tıklanıyor...", driver, "2a_clicking_mode")
                btn = normal_mode_links[0]
                driver.execute_script("arguments[0].scrollIntoView();", btn)
                btn.click()
                time.sleep(3)
        except:
            pass
        finally:
            driver.implicitly_wait(10)

        # --- ADIM 3: FORM DOLDURMA ---
        update_status(log_box, img_box, "Form dolduruluyor (Pfam + Sekans)...", driver, "3_filling_form")
        try:
            # Pfam Seç
            try:
                pfam_checkbox = driver.find_element(By.NAME, "DO_PFAM")
            except:
                pfam_checkbox = driver.find_element(By.XPATH, "//input[parent::*[contains(text(), 'Pfam')]]")
            
            if not pfam_checkbox.is_selected():
                driver.execute_script("arguments[0].click();", pfam_checkbox)
            
            # Sekans Gir
            seq_box = driver.find_element(By.NAME, "SEQUENCE")
            seq_box.clear()
            seq_box.send_keys(TEST_SEQUENCE)
            
            # Formun son halini çek
            update_status(log_box, img_box, "Form hazır. Gönderim yapılıyor...", driver, "4_form_ready")
            
        except Exception as e:
            st.error(f"Form hatası: {e}")
            driver.quit()
            st.stop()

        # --- ADIM 4: GÖNDERİM ---
        try:
            # Enter tuşu ile gönder
            seq_box.send_keys(Keys.ENTER)
            time.sleep(1)
        except Exception as e:
            st.error(f"Gönderim hatası: {e}")
            driver.quit()
            st.stop()
            
        # --- ADIM 5: BEKLEME VE TAKİP ---
        max_wait = 60
        start_time = time.time()
        found_results = False
        
        while time.time() - start_time < max_wait:
            elapsed = int(time.time() - start_time)
            page_source = driver.page_source
            
            # Anlık durum fotosu (Her 5 saniyede bir)
            if elapsed % 5 == 0:
                update_status(log_box, img_box, f"⏳ Bekleniyor... ({elapsed}sn)", driver, f"5_waiting_{elapsed}")

            if "Confidently predicted domains" in page_source:
                update_status(log_box, img_box, "✅ SONUÇ SAYFASI YAKALANDI!", driver, "6_result_page")
                found_results = True
                break
            
            if "No domains found" in page_source:
                update_status(log_box, img_box, "⚠️ Sonuç sayfası geldi ancak domain yok.", driver, "6_empty_result")
                found_results = True
                break
            
            time.sleep(1)

        # --- ADIM 6: DERİN PARSE (DETAILED DEBUG) ---
        if found_results:
            st.divider()
            st.info("🔍 DETAYLI TABLO ANALİZİ BAŞLIYOR")
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            tables = soup.find_all("table")
            
            st.write(f"Sayfada toplam **{len(tables)}** adet tablo bulundu.")
            
            target_table = None
            
            # Tüm tabloları gez ve içeriklerini göster (Debug için kritik!)
            for i, table in enumerate(tables):
                headers = [th.get_text(strip=True) for th in table.find_all("th")]
                st.text(f"Tablo #{i} Başlıkları: {headers}")
                
                # Hedef tablo mu?
                if "Feature" in headers and "Start" in headers:
                    target_table = table
                    st.success(f"🎯 HEDEF TABLO BULUNDU: Tablo #{i}")
                    
                    # Tablo içeriğini satır satır basalım ki hatayı görelim
                    rows = table.find_all("tr")[1:]
                    st.markdown("### Tablo Ham Verisi:")
                    parsed_data = []
                    
                    for row_idx, row in enumerate(rows):
                        cols = row.find_all("td")
                        col_texts = [td.get_text(strip=True) for td in cols]
                        st.code(f"Satır {row_idx}: {col_texts}") # Burası hatayı gösterecek
                        
                        if len(cols) >= 3:
                            start_val = col_texts[1]
                            # Sayı kontrolü
                            if start_val.isdigit():
                                parsed_data.append(col_texts)
                            else:
                                st.warning(f"⚠️ Satır {row_idx} atlandı çünkü 'Start' değeri ({start_val}) sayı değil.")
                    
                    if parsed_data:
                        df = pd.DataFrame(parsed_data, columns=["Feature", "Start", "End", "E-value", "...", "..."][:len(parsed_data[0])])
                        st.dataframe(df)
                    else:
                        st.error("Tablo bulundu ama geçerli veri satırı çıkarılamadı.")

            # Eğer hedef tablo bulunamadıysa HTML'i dök
            if not target_table:
                st.error("❌ Hedef başlıkları ('Feature', 'Start') içeren tablo bulunamadı.")
                with st.expander("Sayfa HTML Kaynağı (İnceleme İçin)"):
                    st.code(driver.page_source, language='html')

        else:
            st.error("❌ Zaman aşımı! Sonuç sayfası gelmedi.")
            update_status(log_box, img_box, "Zaman aşımı hatası.", driver, "99_timeout")

        driver.quit()
