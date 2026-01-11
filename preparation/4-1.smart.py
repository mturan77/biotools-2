import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from Bio import SeqIO
import io
import time
import urllib3
import re
from urllib.parse import urljoin

# SSL hatalarını gizle
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="SMART Analizörü (Auto-Clicker)", layout="wide")
st.title("🧬 SMART Protein Analizörü (Akıllı Link Takibi)")
st.markdown("Bu sürüm, 'Normal Mode' butonunu sayfada arar, bulur ve tıklar. 404 hatası vermez.")

# --- Yardımcı Fonksiyonlar ---

def get_base_url():
    return "https://smart.embl-heidelberg.de/smart/show_motifs.pl"

def handle_mode_selection(session, html_content, log_container):
    """
    Eğer 'Select Mode' sayfası geldiyse, sayfadaki 'Normal Mode' linkini bulur ve tıklar.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Sayfadaki tüm linkleri tara
    links = soup.find_all('a', href=True)
    normal_mode_link = None
    
    # Linklerin içinde "Normal" kelimesi geçen veya görsellere bak
    for link in links:
        # Metin kontrolü
        if "Normal mode" in link.get_text(strip=True) or "Normal SMART" in link.get_text(strip=True):
            normal_mode_link = link['href']
            break
        
        # Bazen buton görseldir, görselin alt textine bak
        img = link.find('img')
        if img and 'alt' in img.attrs and "Normal" in img['alt']:
            normal_mode_link = link['href']
            break
            
    if normal_mode_link:
        # Link bazen relative (göreceli) olur, onu tam URL'ye çevir
        full_url = urljoin("https://smart.embl-heidelberg.de/smart/", normal_mode_link)
        log_container.info(f"🔗 Normal Mode butonu bulundu: {normal_mode_link}. Tıklanıyor...")
        
        try:
            # Butona sanal tıklama yap
            session.get(full_url, verify=False, timeout=30)
            log_container.success("✅ Mod seçimi yapıldı. Tekrar deneniyor...")
            return True
        except Exception as e:
            log_container.error(f"❌ Butona tıklanamadı: {e}")
            return False
    else:
        log_container.error("❌ Sayfada 'Normal Mode' butonu bulunamadı. HTML yapısı değişmiş olabilir.")
        return False

def query_smart_robust(session, sequence, protein_id, log_container):
    url = get_base_url()
    
    payload = {
        'SEQUENCE': sequence,
        'DO_PFAM': 'DO_PFAM',
        'INCLUDE_SIGNALP': 'OFF',
        'INCLUDE_REPEATS': 'OFF',
    }
    
    try:
        # 1. İstek Gönder
        response = session.post(url, data=payload, verify=False, timeout=60)
        
        # 2. Mod Seçimi Sayfası mı Geldi?
        if "Select your preferred SMART mode" in response.text:
            log_container.warning(f"⚠️ {protein_id}: Sunucu mod seçimi istedi. Otomatik seçiliyor...")
            
            # Mod seçimini hallet
            success = handle_mode_selection(session, response.text, log_container)
            if success:
                # Mod seçildi, isteği TEKRARLA
                time.sleep(1)
                response = session.post(url, data=payload, verify=False, timeout=60)
            else:
                return None # Mod seçilemedi
        
        # 3. Bekleme Sırası (Queue) Kontrolü
        attempt = 0
        max_attempts = 15
        
        while attempt < max_attempts:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Meta Refresh Var mı?
            meta_refresh = soup.find("meta", attrs={"http-equiv": re.compile("refresh", re.I)})
            
            if meta_refresh:
                content = meta_refresh.get("content")
                if content and "URL=" in content:
                    next_url_part = content.split("URL=")[1].strip().replace("'", "").replace('"', "")
                    full_next_url = urljoin("https://smart.embl-heidelberg.de/smart/", next_url_part)
                    
                    log_container.info(f"⏳ {protein_id}: İşleniyor... (Sıra {attempt+1})")
                    time.sleep(3)
                    
                    response = session.get(full_next_url, verify=False, timeout=60)
                    attempt += 1
                    continue
            break
            
        return response.text

    except Exception as e:
        log_container.error(f"💥 Bağlantı koptu ({protein_id}): {e}")
        return None

def parse_final_html(html_content, protein_id):
    if not html_content: return []
    
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
    return results

# --- Arayüz ---

uploaded_file = st.file_uploader("Protein FASTA Dosyası", type=["fa", "fasta", "txt"])

if uploaded_file and st.button("🚀 Analizi Başlat"):
    stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
    sequences = list(SeqIO.parse(stringio, "fasta"))
    
    st.info(f"Toplam {len(sequences)} sekans işlenecek.")
    
    # Session Oluştur (Tarayıcı Gibi Davran)
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })
    
    log_area = st.container()
    progress_bar = st.progress(0)
    all_data = []
    
    for i, seq_record in enumerate(sequences):
        prot_id = seq_record.id
        prot_seq = str(seq_record.seq)
        
        with log_area.expander(f"[{i+1}/{len(sequences)}] {prot_id}", expanded=False):
            html_out = query_smart_robust(session, prot_seq, prot_id, st)
            
            if html_out:
                feats = parse_final_html(html_out, prot_id)
                if feats:
                    st.success(f"🎉 {len(feats)} özellik bulundu.")
                    all_data.extend(feats)
                else:
                    if "No domains found" in html_out:
                        st.warning("Domain bulunamadı.")
                    else:
                        st.warning("Sonuç tablosu parse edilemedi.")
        
        progress_bar.progress((i + 1) / len(sequences))
        time.sleep(1.0)
        
    st.success("Tüm İşlemler Bitti!")
    
    if all_data:
        df = pd.DataFrame(all_data)
        st.dataframe(df)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='SMART_Results')
            
        st.download_button("📥 Excel İndir", output.getvalue(), "smart_sonuclar_v3.xlsx")
    else:
        st.error("Hiçbir sonuç alınamadı.")
