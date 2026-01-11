import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from Bio import SeqIO
import io
import time
import urllib3

# SSL Uyarılarını Gizle (verify=False kullanacağımız için terminal kirlenmesin)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- Sayfa Ayarları ---
st.set_page_config(page_title="SMART Domain Analizörü", layout="wide")

st.title("🧬 SMART Protein Domain Analizörü")
st.markdown("""
Bu araç, yüklediğiniz **FASTA (.fa)** dosyasındaki protein sekanslarını alır, 
**SMART** veritabanında (Pfam dahil) taratır ve **"Confidently predicted domains"** tablosunu Excel formatına dönüştürür.
""")

# --- Yan Fonksiyonlar ---

def query_smart(sequence, protein_id):
    """
    SMART sunucusuna istek atar ve HTML içeriğini döndürür.
    SSL doğrulaması devre dışı bırakılmıştır.
    """
    url = "https://smart.embl-heidelberg.de/smart/show_motifs.pl"
    
    payload = {
        'SEQUENCE': sequence,
        'DO_PFAM': 'DO_PFAM',
        'INCLUDE_SIGNALP': 'OFF',
        'INCLUDE_REPEATS': 'OFF',
        'TEXTONLY': 1
    }
    
    try:
        time.sleep(1.0) # Sunucuya nazik davranmak için bekleme
        
        # DÜZELTME BURADA YAPILDI: verify=False eklendi
        response = requests.post(url, data=payload, timeout=60, verify=False)
        
        response.raise_for_status()
        return response.text
    except Exception as e:
        # Hata mesajını biraz daha temiz gösterelim
        st.error(f"Hata ({protein_id}): Sunucuya bağlanılamadı. (Detay: {str(e)[:100]}...)")
        return None

def parse_smart_results(html_content, protein_id):
    """
    Dönen HTML sayfasındaki 'Confidently predicted domains' tablosunu bulur.
    """
    if not html_content:
        return []

    soup = BeautifulSoup(html_content, 'html.parser')
    results = []
    
    tables = soup.find_all("table")
    target_table = None
    
    # Doğru tabloyu bulmak için başlıkları kontrol et
    for table in tables:
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        # SMART tablosunda genellikle bu başlıklar bulunur
        if "Feature" in headers and "Start" in headers and "End" in headers:
            target_table = table
            break
    
    if target_table:
        rows = target_table.find_all("tr")[1:] # Başlığı atla
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 3:
                feature_name = cols[0].get_text(strip=True)
                
                # Link içindeki ismi almayı dene (bazen daha temizdir)
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
    
    return results

# --- Ana Uygulama Akışı ---

uploaded_file = st.file_uploader("Protein Sekans Dosyasını Yükleyin (.fa / .fasta)", type=["fa", "fasta", "txt"])

if uploaded_file is not None:
    stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
    sequences = list(SeqIO.parse(stringio, "fasta"))
    
    st.info(f"📂 Toplam **{len(sequences)}** adet sekans yüklendi.")
    
    if st.button("Analizi Başlat"):
        all_features = []
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Hata sayacı
        error_count = 0
        
        for i, seq_record in enumerate(sequences):
            prot_id = seq_record.id
            prot_seq = str(seq_record.seq)
            
            status_text.text(f"İşleniyor: {prot_id} ({i+1}/{len(sequences)})")
            
            html_result = query_smart(prot_seq, prot_id)
            
            if html_result:
                features = parse_smart_results(html_result, prot_id)
                all_features.extend(features)
            else:
                error_count += 1
            
            progress_bar.progress((i + 1) / len(sequences))
        
        status_text.text("✅ İşlem tamamlandı!")
        
        if error_count > 0:
            st.warning(f"{error_count} adet sekans sunucu hatası nedeniyle işlenemedi.")

        if all_features:
            df = pd.DataFrame(all_features)
            
            st.subheader("📊 Sonuç Tablosu")
            st.dataframe(df)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='SMART_Results')
            
            processed_data = output.getvalue()
            
            st.download_button(
                label="📥 Excel İndir",
                data=processed_data,
                file_name="smart_analiz_sonuclari.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            if error_count == len(sequences):
                st.error("Hiçbir sonuç alınamadı. Lütfen internet bağlantınızı kontrol edin veya SMART sunucusunun erişilebilir olduğundan emin olun.")
            else:
                st.info("İşlenen proteinlerde confident domain bulunamadı.")
