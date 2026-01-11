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

st.set_page_config(page_title="SMART Analizörü (Final)", layout="wide")
st.title("🧬 SMART Protein Domain Analizörü (Tam Otomatik)")

# --- Yardımcı Fonksiyonlar ---

def get_smart_response(sequence, protein_id, log_container):
    """
    SMART sunucusuna bağlanır, gerekirse bekleme (queue) sayfalarını takip eder
    ve nihai sonuç sayfasını getirir.
    """
    base_url = "https://smart.embl-heidelberg.de/smart/show_motifs.pl"
    domain = "https://smart.embl-heidelberg.de"
    
    # Tarayıcı gibi görünmek için Header
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    payload = {
        'SEQUENCE': sequence,
        'DO_PFAM': 'DO_PFAM',
        'INCLUDE_SIGNALP': 'OFF',
        'INCLUDE_REPEATS': 'OFF',
        # 'TEXTONLY': 1  <-- BU KALDIRILDI, ARTIK HTML İSTİYORUZ
    }
    
    session = requests.Session()
    
    try:
        # 1. İlk İsteği Gönder
        response = session.post(base_url, data=payload, headers=headers, verify=False, timeout=60)
        
        # 2. Döngü: "Meta Refresh" var mı? (Bekleme sayfası kontrolü)
        # SMART bazen sonucu hemen vermez, "Wait" sayfası verir ve sizi yönlendirir.
        attempt = 0
        max_attempts = 10 # Maksimum bekleme denemesi
        
        while attempt < max_attempts:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Sayfa başlığını kontrol et
            page_title = soup.title.string if soup.title else ""
            
            # Eğer "Job running" veya meta refresh varsa takip et
            meta_refresh = soup.find("meta", attrs={"http-equiv": re.compile("refresh", re.I)})
            
            if meta_refresh:
                # Refresh içeriğini al: content="5; URL=job_status.pl?..."
                content = meta_refresh.get("content")
                if content and "URL=" in content:
                    wait_time = 2 # Varsayılan bekleme
                    next_url_part = content.split("URL=")[1].strip()
                    
                    # URL bazen tırnak içinde olabilir, temizleyelim
                    next_url_part = next_url_part.replace("'", "").replace('"', "")
                    
                    # Tam URL oluştur
                    if next_url_part.startswith("http"):
                        next_url = next_url_part
                    else:
                        # job_status.pl genellikle /smart/ klasöründedir
                        next_url = f"https://smart.embl-heidelberg.de/smart/{next_url_part}"
                    
                    log_container.info(f"⏳ ({protein_id}) Sunucu bekletiyor, sıraya alındı... ({attempt+1}/{max_attempts})")
                    time.sleep(wait_time + 1) # Biraz bekle
                    
                    # Yeni adrese git
                    response = session.get(next_url, headers=headers, verify=False, timeout=60)
                    attempt += 1
                    continue
            
            # Eğer buraya geldiysek, artık bekleme sayfası değildir, sonuç sayfasıdır.
            break
            
        return response.text

    except Exception as e:
        log_container.error(f"Bağlantı Hatası ({protein_id}): {e}")
        return None

def parse_smart_html(html_content, protein_id):
    """
    HTML içinden tabloyu çeker.
    """
    if not html_content:
        return []

    soup = BeautifulSoup(html_content, 'html.parser')
    results = []
    
    tables = soup.find_all("table")
    target_table = None
    
    # Doğru tabloyu bul
    for table in tables:
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        # "Feature" başlığını arıyoruz
        if "Feature" in headers and ("Start" in headers or "Begin" in headers):
            target_table = table
            break
            
    if target_table:
        # Satırları gez
        rows = target_table.find_all("tr")[1:] 
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 3:
                # Özellik adını temizle
                feature_name = cols[0].get_text(strip=True)
                if cols[0].find('a'): # Link varsa içindeki metni al
                    feature_name = cols[0].find('a').get_text(strip=True)

                start_pos = cols[1].get_text(strip=True)
                end_pos = cols[2].get_text(strip=True)
                e_value = cols[3].get_text(strip=True) if len(cols) > 3 else "N/A"
                
                # Sayısal değer kontrolü (Gereksiz satırları elemek için)
                if start_pos.isdigit():
                    results.append({
                        "Protein_ID": protein_id,
                        "Feature": feature_name,
                        "Start": int(start_pos),
                        "End": int(end_pos),
                        "E-value": e_value
                    })
    
    return results

# --- Ana Uygulama ---

uploaded_file = st.file_uploader("Protein FASTA Dosyasını Yükle", type=["fa", "fasta", "txt"])

if uploaded_file is not None:
    stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
    sequences = list(SeqIO.parse(stringio, "fasta"))
    
    st.info(f"📂 **{len(sequences)}** adet sekans bulundu.")
    
    if st.button("🚀 Analizi Başlat (Güçlendirilmiş Mod)"):
        all_features = []
        progress_bar = st.progress(0)
        log_box = st.empty() # Anlık durum mesajı kutusu
        
        # Detaylı loglar için container
        details = st.expander("İşlem Detayları", expanded=True)

        for i, seq_record in enumerate(sequences):
            prot_id = seq_record.id
            prot_seq = str(seq_record.seq)
            
            log_box.markdown(f"**İşleniyor:** `{prot_id}` ({i+1}/{len(sequences)})")
            
            # 1. Sunucudan HTML al (Bekleme mantığı dahil)
            html_result = get_smart_response(prot_seq, prot_id, details)
            
            # 2. Parse et
            if html_result:
                features = parse_smart_html(html_result, prot_id)
                if features:
                    all_features.extend(features)
                    # details.write(f"✅ {prot_id}: {len(features)} özellik bulundu.") # Çok kalabalık olmasın diye kapalı
                else:
                    pass
                    # details.warning(f"⚠️ {prot_id}: Domain bulunamadı.")
            
            # Progress güncelle
            progress_bar.progress((i + 1) / len(sequences))
            
            # Sunucuya yüklenmemek için kısa mola
            time.sleep(1.0)
            
        log_box.success("Tüm işlemler tamamlandı!")
        
        # --- Sonuç Ekranı ---
        if all_features:
            df = pd.DataFrame(all_features)
            
            st.divider()
            st.subheader("📊 Sonuç Tablosu")
            st.dataframe(df)
            
            # Excel İndir
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='SMART_Results')
            
            st.download_button(
                label="📥 Sonuçları Excel Olarak İndir",
                data=output.getvalue(),
                file_name="smart_final_sonuclar.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.error("Hiçbir proteinde confident domain bulunamadı. (Ya proteinlerde domain yok ya da sunucu yanıtı çok farklı)")
