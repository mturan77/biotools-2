import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from Bio import SeqIO
import io
import time

# --- Sayfa Ayarları ---
st.set_page_config(page_title="SMART Domain Analizörü", layout="wide")

st.title("🧬 SMART Protein Domain Analizörü")
st.markdown("""
Bu araç, yüklediğiniz **FASTA (.fa)** dosyasındaki protein sekanslarını alır, 
**[SMART](https://smart.embl-heidelberg.de/)** veritabanında (Pfam dahil) taratır 
ve **"Confidently predicted domains"** tablosunu Excel formatına dönüştürür.
""")

# --- Yan Fonksiyonlar ---

def query_smart(sequence, protein_id):
    """
    SMART sunucusuna istek atar ve HTML içeriğini döndürür.
    """
    url = "https://smart.embl-heidelberg.de/smart/show_motifs.pl"
    
    # SMART Form Parametreleri
    # DO_PFAM=DO_PFAM -> Pfam domainlerini dahil et (Kullanıcı isteği)
    payload = {
        'SEQUENCE': sequence,
        'DO_PFAM': 'DO_PFAM',  # Pfam kutucuğunu işaretler
        'INCLUDE_SIGNALP': 'OFF', # İsteğe bağlı, varsayılan kapalı
        'INCLUDE_REPEATS': 'OFF', # İsteğe bağlı
        'TEXTONLY': 1          # Sonucu daha kolay parse etmek için text/basit HTML modu denemesi (bazen çalışır)
    }
    
    try:
        # Sunucuya yüklenmemek için kısa bir bekleme (Politeness)
        time.sleep(1.5) 
        response = requests.post(url, data=payload, timeout=60)
        response.raise_for_status()
        return response.text
    except Exception as e:
        st.error(f"Hata oluştu ({protein_id}): {e}")
        return None

def parse_smart_results(html_content, protein_id):
    """
    Dönen HTML sayfasındaki 'Confidently predicted domains' tablosunu bulur ve veriyi çeker.
    """
    if not html_content:
        return []

    soup = BeautifulSoup(html_content, 'html.parser')
    results = []

    # SMART sonuçlarında tabloları bulmaya çalışalım.
    # Genellikle "Confidently predicted domains..." başlığından sonra gelir.
    
    # Tüm tabloları gez ve doğru olanı bul
    tables = soup.find_all("table")
    target_table = None
    
    for table in tables:
        # Tablonun önceki elementlerine bakarak başlığı kontrol etmeye çalışabiliriz
        # Ya da tablo başlık satırlarını kontrol edebiliriz
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        if "Feature" in headers and "Start" in headers and "End" in headers:
            target_table = table
            break
    
    if target_table:
        rows = target_table.find_all("tr")[1:] # Başlık satırını atla
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 3:
                # Veri temizliği
                feature_name = cols[0].get_text(strip=True)
                
                # Bazen Feature ismi link içindedir, sadece text'i alalım
                if cols[0].find('a'):
                    feature_name = cols[0].find('a').get_text(strip=True)

                start_pos = cols[1].get_text(strip=True)
                end_pos = cols[2].get_text(strip=True)
                e_value = cols[3].get_text(strip=True) if len(cols) > 3 else "N/A"
                
                # Boş satırları veya görsel satırlarını elemek için kontrol
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
    # Dosyayı Biopython ile oku
    stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
    sequences = list(SeqIO.parse(stringio, "fasta"))
    
    st.write(f"📂 Toplam **{len(sequences)}** adet sekans bulundu. Analiz başlıyor...")
    
    if st.button("Analizi Başlat"):
        all_features = []
        
        # Progress bar
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i, seq_record in enumerate(sequences):
            prot_id = seq_record.id
            prot_seq = str(seq_record.seq)
            
            status_text.text(f"İşleniyor: {prot_id} ({i+1}/{len(sequences)})")
            
            # 1. SMART'a gönder
            html_result = query_smart(prot_seq, prot_id)
            
            # 2. Sonucu Parse et
            if html_result:
                features = parse_smart_results(html_result, prot_id)
                all_features.extend(features)
            
            # Progress güncelle
            progress_bar.progress((i + 1) / len(sequences))
        
        status_text.text("✅ Analiz tamamlandı!")
        
        # --- Sonuçları Göster ve İndir ---
        if all_features:
            df = pd.DataFrame(all_features)
            
            st.subheader("📊 Sonuç Tablosu")
            st.dataframe(df)
            
            # Excel İndirme Butonu
            
            # Pandas ile Excel'e yazma (Hafızada)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='SMART_Results')
            
            processed_data = output.getvalue()
            
            st.download_button(
                label="📥 Sonuçları Excel Olarak İndir",
                data=processed_data,
                file_name="smart_analiz_sonuclari.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("Hiçbir sekans için 'Confidently predicted domain' bulunamadı veya sunucu yanıt vermedi.")
