import streamlit as st
import pandas as pd
import requests
import time
import zipfile
import io
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Phyre2 Scraper & Downloader", page_icon="🕷️", layout="wide")

st.title("🕷️ Phyre2 Sonuç Toplayıcı (Scraper)")
st.info("Bu modül, Phyre2 sonuç sayfalarını kontrol eder. İşlem bitmişse dosyaları indirir, bitmemişse durumunu raporlar.")

# --- SELENIUM DRIVER KURULUMU ---
def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1200")
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except:
        driver = webdriver.Chrome(options=chrome_options)
    return driver

# --- DOSYA İNDİRME FONKSİYONU ---
def download_content(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, stream=True, timeout=60, headers=headers)
        if r.status_code == 200:
            return r.content
    except:
        return None
    return None

# --- DOSYA YÜKLEME ---
uploaded_file = st.file_uploader("CSV dosyasını yükleyin", type=["csv"])

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    
    if "Result Link" not in df.columns:
        st.error("Hata: 'Result Link' sütunu bulunamadı.")
    else:
        df = df.dropna(subset=["Result Link"])
        df = df[df["Result Link"].str.contains("http")]
        
        st.write(f"**Kontrol Edilecek Link:** {len(df)}")
        
        if st.button("🚀 Başlat", type="primary"):
            
            master_zip_buffer = io.BytesIO()
            
            # İlerleme Çubuğu
            progress_bar = st.progress(0)
            
            # Anlık Durum Metni (Üstte görünür)
            status_text = st.empty()
            
            # Log Alanı (Sürekli güncellenen tek bir kutu)
            st.write("### 📝 İşlem Logları")
            log_placeholder = st.empty() 
            
            logs = []
            driver = None
            
            try:
                with zipfile.ZipFile(master_zip_buffer, "w", zipfile.ZIP_DEFLATED) as master_zip:
                    
                    total = len(df)
                    
                    for i, row in df.iterrows():
                        protein_id = str(row.get("Protein ID", f"Protein_{i}")).replace(" ", "_")
                        url = row["Result Link"]
                        folder = f"{protein_id}/"
                        
                        # Kullanıcıya şu an ne yaptığımızı göster
                        status_text.info(f"İşleniyor ({i+1}/{total}): {protein_id}")
                        progress_bar.progress((i+1)/total)
                        
                        try:
                            if driver is None:
                                driver = get_driver()

                            # 1. Sayfaya Git
                            driver.get(url)
                            time.sleep(2)
                            
                            # Sayfa içeriğini metin olarak al (Kontrol için)
                            page_text = driver.find_element(By.TAG_NAME, "body").text
                            
                            # 2. Screenshot Al (Her durumda alıyoruz, kanıt olsun)
                            png_data = driver.get_screenshot_as_png()
                            master_zip.writestr(f"{folder}status_view.png", png_data)
                            
                            # 3. DURUM KONTROLÜ (Kritik Bölüm)
                            # Phyre2 bitmemiş işlerde "Job Status", "Queue" veya "Estimated" kelimelerini gösterir.
                            is_finished = True
                            if "Job Status" in page_text or "Estimated total processing time" in page_text:
                                is_finished = False
                                logs.append(f"⏳ {protein_id}: HENÜZ BİTMEMİŞ. (Screenshot alındı, dosya yok)")
                            
                            elif "FAILED" in page_text:
                                is_finished = False
                                logs.append(f"❌ {protein_id}: Phyre2 işlemi HATA (Failed) vermiş.")
                            
                            else:
                                logs.append(f"✅ {protein_id}: İşlem tamamlanmış. Dosyalar aranıyor...")

                            # 4. Dosyaları İndir (Sadece bitmişse)
                            if is_finished:
                                elements = driver.find_elements(By.TAG_NAME, "a")
                                zip_link = None
                                pdb_link = None
                                
                                for elem in elements:
                                    href = elem.get_attribute("href")
                                    if href:
                                        if href.endswith(".zip") and "phyre" in href:
                                            zip_link = href
                                        elif "final_model.pdb" in href:
                                            pdb_link = href
                                
                                # İndirme İşlemleri
                                if zip_link:
                                    z_content = download_content(zip_link)
                                    if z_content:
                                        master_zip.writestr(f"{folder}results.zip", z_content)
                                        logs[-1] += " [ZIP İndi]" # Son log satırına ekle
                                
                                if pdb_link:
                                    p_content = download_content(pdb_link)
                                    if p_content:
                                        master_zip.writestr(f"{folder}model.pdb", p_content)
                                        logs[-1] += " [PDB İndi]"

                        except Exception as e:
                            logs.append(f"⚠️ {protein_id} Hata: {str(e)}")
                            # Driver hatası ise resetle
                            if "refused" in str(e) or "session" in str(e):
                                try:
                                    driver.quit()
                                except:
                                    pass
                                driver = None
                        
                        # Logları Ekrana Bas (Placeholder kullanarak temiz görüntü)
                        # Listeyi ters çevirip basıyoruz ki en son işlem en üstte görünsün
                        log_text = "\n".join(reversed(logs))
                        log_placeholder.code(log_text, language="text")

                status_text.success("İşlem Tamamlandı!")
                
                master_zip_buffer.seek(0)
                st.download_button(
                    label="📦 SONUÇLARI İNDİR (ZIP)",
                    data=master_zip_buffer,
                    file_name="Phyre2_Scan_Results.zip",
                    mime="application/zip",
                    type="primary"
                )
                
            except Exception as main_e:
                st.error(f"Genel Hata: {main_e}")
            finally:
                if driver:
                    driver.quit()
