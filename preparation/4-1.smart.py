import streamlit as st
import pandas as pd
import time
import re  # Düzenli ifadeler (Sayıları ayıklamak için)
import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType
from bs4 import BeautifulSoup

st.set_page_config(page_title="SMART Final Çıktı", layout="wide")
st.title("🧬 SMART: Sonuç Ayrıştırma ve Excel")

# Test Sekansı
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

def extract_number(text):
    """Metin içindeki sayıyı bulur (Örn: ' 123 ' -> 123)"""
    match = re.search(r'\d+', text)
    if match:
        return int(match.group())
    return None

if st.button("🚀 SONUÇLARI GETİR"):
    driver = get_driver()
    if driver:
        log_box = st.empty()
        
        # --- 1. GİRİŞ ve GÖNDERİM ---
        log_box.info("Siteye gidiliyor ve form gönderiliyor...")
        driver.get("https://smart.embl-heidelberg.de/")
        
        # Mod geçişi
        try:
            driver.implicitly_wait(2)
            links = driver.find_elements(By.CSS_SELECTOR, "a[href*='change_mode.cgi?mode=normal']")
            if links: driver.execute_script("arguments[0].click();", links[0])
        except: pass
        
        # Form doldur
        try:
            time.sleep(2)
            try: pfam = driver.find_element(By.NAME, "DO_PFAM")
            except: pfam = driver.find_element(By.XPATH, "//input[contains(@name, 'PFAM')]")
            if not pfam.is_selected(): driver.execute_script("arguments[0].click();", pfam)
            
            seq_box = driver.find_element(By.NAME, "SEQUENCE")
            seq_box.clear()
            seq_box.send_keys(TEST_SEQUENCE)
            
            # ZORLA GÖNDER
            driver.execute_script("arguments[0].form.submit();", seq_box)
        except Exception as e:
            st.error(f"Hata: {e}")
            driver.quit()
            st.stop()

        # --- 2. SONUÇ BEKLEME ---
        start_time = time.time()
        found = False
        while time.time() - start_time < 60:
            if "Confidently predicted domains" in driver.page_source:
                found = True
                break
            time.sleep(1)
            log_box.info(f"⏳ Sonuç bekleniyor... ({int(time.time()-start_time)}sn)")

        # --- 3. ESNEK AYRIŞTIRMA (PARSING) ---
        if found:
            log_box.success("✅ Sonuç sayfası yüklendi! Veriler çekiliyor...")
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            # Sayfadaki TÜM tabloları bul
            tables = soup.find_all("table")
            target_table = None
            
            # Doğru tabloyu bulmak için başlıkları tara
            for tbl in tables:
                headers = [th.get_text(strip=True) for th in tbl.find_all("th")]
                # "Start" ve "End" başlıkları bizim için anahtar kelimeler
                if "Start" in headers and "End" in headers:
                    target_table = tbl
                    break
            
            if target_table:
                data = []
                rows = target_table.find_all("tr")[1:] # Başlığı atla
                
                st.write("--- Tablo Satır Analizi ---")
                
                for i, row in enumerate(rows):
                    cols = row.find_all("td")
                    col_texts = [td.get_text(strip=True) for td in cols]
                    
                    # Kullanıcıya ne gördüğümüzü gösterelim (Debug)
                    # st.text(f"Satır {i}: {col_texts}") 
                    
                    if len(cols) >= 3:
                        # İsim
                        f_name = cols[0].get_text(strip=True)
                        if cols[0].find('a'): f_name = cols[0].find('a').get_text(strip=True)
                        
                        # Start / End (Regex ile sayı ayıkla)
                        raw_start = cols[1].get_text(strip=True)
                        raw_end = cols[2].get_text(strip=True)
                        
                        start_val = extract_number(raw_start)
                        end_val = extract_number(raw_end)
                        
                        # Eğer Start ve End sayısal bir değer döndürdüyse kaydet
                        if start_val is not None and end_val is not None:
                            e_val = cols[3].get_text(strip=True) if len(cols) > 3 else "-"
                            
                            data.append({
                                "Protein_ID": "Test_Protein",
                                "Feature": f_name,
                                "Start": start_val,
                                "End": end_val,
                                "E-value": e_val
                            })
                
                if data:
                    df = pd.DataFrame(data)
                    st.success(f"🎉 Toplam {len(data)} özellik başarıyla çekildi!")
                    st.dataframe(df, use_container_width=True)
                    
                    # Kanıt
                    driver.save_screenshot("final_success.png")
                    st.image("final_success.png", caption="İşlenen Tablo")
                else:
                    st.warning("Tablo bulundu ancak veri satırları sayısal formatta değil veya boş.")
                    st.code(target_table.prettify()) # HTML'i göster ki görelim
            else:
                st.error("Uygun başlıkları olan tablo bulunamadı.")
        else:
            st.error("Zaman aşımı.")
        
        driver.quit()
