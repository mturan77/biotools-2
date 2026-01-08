import streamlit as st
import requests
import time
from io import StringIO
import re
import pandas as pd
from datetime import datetime
import os

st.set_page_config(page_title="Phyre2 Pro History", page_icon="📜")

# --- AYARLAR ---
HISTORY_FILE = "phyre_history.csv"
MAX_HISTORY = 20  # <-- BURASI SINIR: En son 20 kaydı tutar, eskileri siler.

# --- GEÇMİŞ YÖNETİMİ ---
def load_history():
    if os.path.exists(HISTORY_FILE):
        return pd.read_csv(HISTORY_FILE)
    else:
        return pd.DataFrame(columns=["Tarih", "Protein", "Job_ID", "Link"])

def save_to_history(protein_name, job_id, link):
    df = load_history()
    tarih = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # Yeni satırı oluştur
    new_row = pd.DataFrame([{
        "Tarih": tarih,
        "Protein": protein_name,
        "Job_ID": job_id,
        "Link": link
    }])
    
    # Yeni satırı en başa ekle (Eskiler aşağı kayar)
    df = pd.concat([new_row, df], ignore_index=True)
    
    # --- TEMİZLİK MEKANİZMASI ---
    # Eğer sayı 20'yi geçerse, sadece ilk 20 tanesini al (gerisini çöpe at)
    if len(df) > MAX_HISTORY:
        df = df.head(MAX_HISTORY)
    
    df.to_csv(HISTORY_FILE, index=False)

# --- SIFIRLAMA ---
if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

def reset_app():
    st.session_state.uploader_key += 1

st.title("🧬 Phyre2 - Akıllı Geçmiş Modu")
st.markdown(f"Geçmişiniz otomatik kaydedilir ve **son {MAX_HISTORY} analiz** ile sınırlı tutulur (Dosya şişmez).")

# --- SIDEBAR ---
with st.sidebar:
    st.button("🔄 Yeni Analiz / Temizle", on_click=reset_app, type="primary")
    st.divider()
    
    # --- GEÇMİŞ TABLOSU ---
    st.subheader("📜 Son İşlemler")
    history_df = load_history()
    
    if not history_df.empty:
        st.dataframe(
            history_df,
            column_config={
                "Link": st.column_config.LinkColumn("Sonuç Linki"), # Tıklanabilir Link
                "Tarih": st.column_config.TextColumn("Saat", width="small"),
                "Job_ID": st.column_config.TextColumn("ID", width="small"),
            },
            hide_index=True,
            use_container_width=True
        )
        # Geçmişi İndir
        csv_history = history_df.to_csv(index=False).encode('utf-8')
        st.download_button("💾 Geçmişi Yedekle (CSV)", csv_history, "gecmis_yedek.csv", "text/csv")
    else:
        st.caption("Henüz kayıtlı işlem yok.")

    st.divider()
    st.header("Ayarlar")
    email = st.text_input("E-mail Adresiniz", value="muratturan077@gmail.com")
    mode = st.selectbox("Modelleme Modu", ["normal", "intensive"])
    
    user_type = st.radio("Kullanım Amacı", ["Academic", "Commercial"], index=0)
    bekleme_suresi = st.number_input("Bekleme (sn)", 0.5, 30.0, 2.0, 0.1, "%.2f")

# --- DOSYA YÜKLEME ---
uploaded_file = st.file_uploader(
    "Protein FASTA Dosyası Seçin", 
    type=["fa", "fasta", "txt"],
    key=f"uploader_{st.session_state.uploader_key}" 
)

if uploaded_file and email:
    stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
    content = stringio.read()
    raw_entries = [x for x in content.split('>') if x.strip()]
    
    st.info(f"📂 {len(raw_entries)} sekans yüklendi. Analize hazır.")
    
    if st.button("🚀 Gönderimi Başlat"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        results_container = st.container()
        
        report_data = []

        for i, entry in enumerate(raw_entries):
            lines = entry.strip().split('\n')
            header = lines[0].strip()
            sequence = "".join(lines[1:]).replace(" ", "") 
            
            status_text.text(f"İşleniyor ({i+1}/{len(raw_entries)}): {header}...")
            progress_bar.progress((i + 1) / len(raw_entries))
            
            url = "http://www.sbg.bio.ic.ac.uk/phyre2/webscripts/phyre2_submit.cgi"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'http://www.sbg.bio.ic.ac.uk/phyre2/html/page.cgi?id=index'
            }

            payload = {
                'usr-email': email,      
                'seq-desc': header,      
                'sequence': sequence,    
                'modelmode': mode,
                'private': 'no', 
                'type': 'academic' if 'Academic' in user_type else 'commercial' 
            }
            
            try:
                response = requests.post(url, data=payload, headers=headers, timeout=45)
                resp_text_lower = response.text.lower()
                success_keywords = ["submitted", "success", "job id", "queue"]
                
                if response.status_code == 200 and any(x in resp_text_lower for x in success_keywords):
                    
                    job_match = re.search(r"jobid=([a-zA-Z0-9]+)", response.text)
                    
                    if job_match:
                        job_id = job_match.group(1)
                        monitor_link = f"http://www.sbg.bio.ic.ac.uk/phyre2/webscripts/jobmonitor-harry.cgi?jobid={job_id}"
                        
                        # GEÇMİŞE KAYDET (Otomatik Temizlemeli)
                        save_to_history(header, job_id, monitor_link)
                        
                        report_data.append({"Sıra": i+1, "Protein": header, "Job ID": job_id, "Link": monitor_link, "Durum": "Başarılı"})
                        
                        with results_container.container():
                            st.success(f"✅ [{i+1}] **{header}**")
                            st.markdown(f"👉 **[🔗 Takip Linki]({monitor_link})**")
                    else:
                        results_container.success(f"✅ [{i+1}] Gönderildi (Link yok): {header}")
                        report_data.append({"Sıra": i+1, "Protein": header, "Durum": "Link Yok"})
                        
                else:
                    results_container.warning(f"⚠️ [{i+1}] GÖNDERİLEMEDİ: {header}")
                    report_data.append({"Sıra": i+1, "Protein": header, "Durum": "Hata"})
                    
            except Exception as e:
                results_container.error(f"❌ Hata: {str(e)}")
            
            time.sleep(bekleme_suresi)
            
        st.balloons()
        st.success(f"🏁 İşlem Bitti! Sonuçlar geçmişe kaydedildi.")
        
        if report_data:
            df = pd.DataFrame(report_data)
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Bu Oturumu İndir (Excel/CSV)", csv, 'session_report.csv', 'text/csv', type="primary")

elif not email and uploaded_file:
    st.warning("Lütfen e-mail adresinizi girin.")
