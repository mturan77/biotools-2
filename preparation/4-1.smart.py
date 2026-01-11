import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from Bio import SeqIO
import io
import time
import urllib3

# SSL uyarılarını kapat
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="SMART Debugger", layout="wide")
st.title("🧬 SMART Analizörü - Detaylı Log Modu")

# --- Yardımcı Fonksiyonlar ---

def query_smart_debug(sequence, protein_id):
    url = "https://smart.embl-heidelberg.de/smart/show_motifs.pl"
    payload = {
        'SEQUENCE': sequence,
        'DO_PFAM': 'DO_PFAM',
        'INCLUDE_SIGNALP': 'OFF',
        'INCLUDE_REPEATS': 'OFF',
        'TEXTONLY': 1
    }
    
    try:
        # Sunucuya istek
        response = requests.post(url, data=payload, timeout=60, verify=False)
        return response
    except Exception as e:
        return str(e)

def parse_and_log(html_content, protein_id, log_container):
    """
    Hem parse eder hem de log_container içine detay yazar.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    results = []
    
    # Sayfa başlığını kontrol et (Hata var mı?)
    page_title = soup.title.string if soup.title else "Başlık Yok"
    log_container.write(f"**Sayfa Başlığı:** {page_title}")

    # Hata mesajı kontrolü
    if "Error" in html_content or "problem" in html_content.lower():
        log_container.error("⚠️ HTML içeriğinde 'Error' veya 'problem' kelimesi tespit edildi.")

    tables = soup.find_all("table")
    log_container.write(f"📄 Sayfada **{len(tables)}** adet tablo bulundu.")
    
    target_table = None
    
    # Tabloları gez ve başlıklarını logla
    for idx, table in enumerate(tables):
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        
        # Sadece potansiyel adayları detaylı gösterelim
        if headers:
            # log_container.code(f"Tablo {idx} Başlıkları: {headers}") # Çok kalabalık olmasın diye kapattım
            pass

        if "Feature" in headers and ("Start" in headers or "Begin" in headers):
            target_table = table
            log_container.success(f"✅ Hedef tablo bulundu! (Tablo Index: {idx})")
            break
            
    if target_table:
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
        log_container.warning("⚠️ 'Feature', 'Start', 'End' başlıklarına sahip tablo bulunamadı.")
        # HTML'in bir kısmını göster ki sorunu anlayalım
        with log_container.expander("Gelen HTML İçeriği (İlk 2000 karakter)"):
            st.code(html_content[:2000], language='html')

    return results

# --- Arayüz ---

uploaded_file = st.file_uploader("Protein FASTA Yükle", type=["fa", "fasta", "txt"])

if uploaded_file and st.button("Loglu Analizi Başlat"):
    stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
    sequences = list(SeqIO.parse(stringio, "fasta"))
    
    all_features = []
    
    # Ana log alanı
    log_area = st.container()
    
    with log_area:
        for i, seq_record in enumerate(sequences):
            prot_id = seq_record.id
            prot_seq = str(seq_record.seq)
            
            # Her protein için açılır/kapanır bir kutu yapalım
            with st.expander(f"[{i+1}/{len(sequences)}] İşleniyor: {prot_id}", expanded=False):
                st.write(f"**Sekans Uzunluğu:** {len(prot_seq)}")
                
                # 1. İstek Gönder
                response = query_smart_debug(prot_seq, prot_id)
                
                if isinstance(response, str): # Hata mesajı döndüyse
                    st.error(f"Bağlantı Hatası: {response}")
                    continue
                
                st.write(f"**HTTP Durum Kodu:** {response.status_code}")
                
                if response.status_code == 200:
                    # 2. Parse Et ve Logla
                    features = parse_and_log(response.text, prot_id, st)
                    
                    if features:
                        st.write(f"🎉 **{len(features)}** özellik bulundu: {[f['Feature'] for f in features]}")
                        all_features.extend(features)
                    else:
                        st.warning("Bu sekans için özellik çıkarılamadı.")
                else:
                    st.error("Sunucu 200 OK döndürmedi.")
            
            # Sunucuyu boğmamak için bekleme
            time.sleep(1.0)

    st.divider()
    if all_features:
        st.success("✅ Tüm işlemler bitti. Sonuçlar aşağıda.")
        df = pd.DataFrame(all_features)
        st.dataframe(df)
        
        # Excel İndir
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='SMART_Results')
        
        st.download_button("Excel İndir", output.getvalue(), "smart_loglu_sonuc.xlsx")
    else:
        st.error("Hiçbir sonuç üretilemedi. Lütfen yukarıdaki genişletilebilir logları (expander) açıp HTML içeriklerini kontrol edin.")
