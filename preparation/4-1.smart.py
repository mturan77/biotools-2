import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from Bio import SeqIO
import io
import time
import urllib3
import re

# SSL Uyarılarını Sustur
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="SMART Analizörü (Auto-Mode)", layout="wide")
st.title("🧬 SMART Protein Domain Analizörü")
st.markdown("Bu araç önce **SMART Normal Mode** seçimini yapar, ardından proteinlerinizi tarar.")

# --- Session ve Mod Ayarları ---

def create_smart_session(log_container):
    """
    Bir oturum açar ve 'Normal Mode'u aktif hale getirir.
    """
    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    session.headers.update(headers)
    
    # Adım 1: Mod Değiştirme URL'sine git (Siteye 'Normal Mode' istediğimizi söylüyoruz)
    # SMART'ın mod değiştirme mekanizmasını tetikliyoruz.
    mode_url = "https://smart.embl-heidelberg.de/smart/change_mode.pl?to=NORMAL"
    
    try:
        log_container.info("🔌 Sunucuya bağlanılıyor ve 'Normal Mode' seçiliyor...")
        resp = session.get(mode_url, verify=False, timeout=30)
        
        if resp.status_code == 200:
            log_container.success("✅ Normal Mode başarıyla seçildi. Oturum hazır.")
        else:
            log_container.warning(f"⚠️ Mod seçimi sırasında beklenmedik durum kodu: {resp.status_code}")
            
    except Exception as e:
        log_container.error(f"❌ Oturum açılırken hata oluştu: {e}")
        return None

    return session

# --- Analiz Fonksiyonları ---

def query_smart_sequence(session, sequence, protein_id, log_container):
    """
    Hazırlanmış session (oturum) ile proteini gönderir.
    """
    base_url = "https://smart.embl-heidelberg.de/smart/show_motifs.pl"
    
    payload = {
        'SEQUENCE': sequence,
        'DO_PFAM': 'DO_PFAM',
        'INCLUDE_SIGNALP': 'OFF',
        'INCLUDE_REPEATS': 'OFF',
    }
    
    try:
        # İsteği gönder
        response = session.post(base_url, data=payload, verify=False, timeout=60)
        
        # Bekleme (Queue) Kontrolü
        attempt = 0
        max_attempts = 15 
        
        while attempt < max_attempts:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Eğer hala "Select your preferred SMART mode" sayfası geliyorsa, zorla tekrar deneyelim
            if "Select your preferred SMART mode" in response.text:
                log_container.warning(f"⚠️ {protein_id}: Mod seçimi ekranı tekrar geldi. Modu zorluyorum...")
                session.get("https://smart.embl-heidelberg.de/smart/change_mode.pl?to=NORMAL", verify=False)
                response = session.post(base_url, data=payload, verify=False, timeout=60)
                attempt += 1
                continue

            # Meta refresh (Bekleme Ekranı) var mı?
            meta_refresh = soup.find("meta", attrs={"http-equiv": re.compile("refresh", re.I)})
            
            if meta_refresh:
                content = meta_refresh.get("content")
                if content and "URL=" in content:
                    # URL'yi temizle
                    next_url_part = content.split("URL=")[1].strip().replace("'", "").replace('"', "")
                    
                    if next_url_part.startswith("http"):
                        next_url = next_url_part
                    else:
                        # Bazen başında /smart/ olur bazen olmaz, kontrol et
                        if next_url_part.startswith("/smart/"):
                            next_url = f"https://smart.embl-heidelberg.de{next_url_part}"
                        else:
                            next_url = f"https://smart.embl-heidelberg.de/smart/{next_url_part}"
                    
                    log_container.info(f"⏳ {protein_id}: Sunucu işliyor... (Sıra {attempt+1})")
                    time.sleep(3) # 3 saniye bekle
                    response = session.get(next_url, verify=False, timeout=60)
                    attempt += 1
                    continue
            
            # Döngüden çıkış (Sonuç geldi)
            break
            
        return response.text

    except Exception as e:
        log_container.error(f"❌ {protein_id} Hatası: {e}")
        return None

def parse_results(html_content, protein_id, log_container):
    if not html_content:
        return []

    soup = BeautifulSoup(html_content, 'html.parser')
    results = []
    
    # Tabloları bul
    tables = soup.find_all("table")
    target_table = None
    
    for table in tables:
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        if "Feature" in headers and ("Start" in headers or "Begin" in headers):
            target_table = table
            break
            
    if target_table:
        log_container.write(f"✅ {protein_id}: Tablo bulundu ve ayrıştırılıyor.")
        rows = target_table.find_all("tr")[1:] 
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 3:
                feature_name = cols[0].get_text(strip=True)
                if cols[0].find('a'):
                    feature_name = cols[0].find('a').get_text(strip=True)

                start_pos = cols[1].get_text(strip=True)
                end_pos = cols[2].get_text(strip=True)
                e_value = cols[3].get_text(strip=True) if len(cols) > 3 else "N/A"
                
                if start_pos.isdigit():
                    results.append({
                        "Protein_ID": protein_id,
                        "Feature": feature_name,
                        "Start": int(start_pos),
                        "End": int(end_pos),
                        "E-value": e_value
                    })
    else:
        # Hata ayıklama için: Eğer sonuç yoksa ve "No domains found" yazmıyorsa HTML'i göster
        if "No domains found" in html_content:
            log_container.warning(f"🔸 {protein_id}: Domain bulunamadı (SMART sonucu).")
        else:
            # log_container.error(f"⚠️ {protein_id}: Beklenmedik sayfa yapısı.")
            # İsteğe bağlı: HTML debug
            pass
            
    return results

# --- Ana Uygulama ---

uploaded_file = st.file_uploader("Protein FASTA Dosyasını Yükle", type=["fa", "fasta", "txt"])

if uploaded_file is not None:
    stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
    sequences = list(SeqIO.parse(stringio, "fasta"))
    
    st.info(f"📂 **{len(sequences)}** adet sekans yüklendi.")
    
    if st.button("🚀 Analizi Başlat"):
        
        # Log Alanı
        log_box = st.container()
        
        # 1. OTURUM BAŞLAT VE MODU SEÇ
        session = create_smart_session(log_box)
        
        if session:
            all_features = []
            progress_bar = st.progress(0)
            
            for i, seq_record in enumerate(sequences):
                prot_id = seq_record.id
                prot_seq = str(seq_record.seq)
                
                # Her protein için küçük bir expander (rahat okunur)
                with log_box.expander(f"[{i+1}/{len(sequences)}] {prot_id}", expanded=False):
                    
                    # Gönder
                    html_result = query_smart_sequence(session, prot_seq, prot_id, st)
                    
                    # Parse Et
                    if html_result:
                        features = parse_results(html_result, prot_id, st)
                        if features:
                            st.success(f"🎉 {len(features)} özellik bulundu.")
                            all_features.extend(features)
                
                progress_bar.progress((i + 1) / len(sequences))
                time.sleep(1.0) # Sunucuya nefes aldır
            
            st.success("🏁 Tüm işlemler tamamlandı!")
            
            # --- Sonuç İndirme ---
            if all_features:
                df = pd.DataFrame(all_features)
                st.divider()
                st.subheader("📊 Sonuç Tablosu")
                st.dataframe(df)
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name='SMART_Results')
                
                st.download_button(
                    label="📥 Excel İndir",
                    data=output.getvalue(),
                    file_name="smart_sonuclar_final.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.warning("Sonuç dosyası boş. Hiçbir domain bulunamadı.")
