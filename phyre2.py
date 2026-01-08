import streamlit as st
import requests
import time
from io import StringIO
import re  # Metin içinden Link avlamak için gerekli kütüphane
import streamlit.components.v1 as components

st.set_page_config(page_title="Phyre2 Linkli Takip", page_icon="🔗")

if st.sidebar.button("🔄 Sayfayı Yenile"):
    st.rerun()

st.title("🧬 Phyre2 - Canlı Takip Linkli")
st.markdown("Bu versiyon, gönderim sonrası oluşan **Takip Linkini** (Job ID) otomatik olarak yakalar ve size sunar.")

with st.sidebar:
    st.header("Ayarlar")
    email = st.text_input("E-mail Adresiniz", value="muratturan077@gmail.com")
    mode = st.selectbox("Modelleme Modu", ["normal", "intensive"])
    
    st.caption("Kullanıcı Tipi")
    user_type = st.radio("Kullanım Amacı", ["Academic (Kâr Amacı Yok)", "Commercial (Ticari)"], index=0)
    
    bekleme_suresi = st.number_input("Bekleme (sn)", 0.5, 30.0, 2.0, 0.1, "%.2f")

uploaded_file = st.file_uploader("Protein FASTA Dosyası Seçin", type=["fa", "fasta", "txt"])

if uploaded_file and email:
    stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
    content = stringio.read()
    raw_entries = [x for x in content.split('>') if x.strip()]
    
    st.info(f"📂 {len(raw_entries)} sekans yüklendi.")
    
    if st.button("🚀 Gönderimi Başlat"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        results = st.container()

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
                    
                    # --- YENİ EKLENEN KISIM: LINK AVLAMA (REGEX) ---
                    # Sunucudan gelen HTML içinde 'jobid=xxxx' desenini arıyoruz
                    job_match = re.search(r"jobid=([a-zA-Z0-9]+)", response.text)
                    
                    if job_match:
                        # Job ID bulunduysa linki oluştur
                        job_id = job_match.group(1)
                        monitor_link = f"http://www.sbg.bio.ic.ac.uk/phyre2/webscripts/jobmonitor-harry.cgi?jobid={job_id}"
                        
                        # Tıklanabilir Link ile Yeşil Mesaj
                        results.success(f"✅ [{i+1}] BAŞARILI: **{header}**")
                        results.markdown(f"👉 **[🔗 Buraya Tıklayarak Sonucu İzle]({monitor_link})** (Job ID: `{job_id}`)")
                    else:
                        # ID bulunamazsa standart mesaj (Link oluşmadı ama gitti)
                        results.success(f"✅ [{i+1}] Gönderildi (Link yakalanamadı): {header}")
                        
                else:
                    results.warning(f"⚠️ [{i+1}] GÖNDERİLEMEDİ: {header}")
                    with results.expander("Hata Detayı"):
                         components.html(response.text, height=200, scrolling=True)
                    
            except Exception as e:
                results.error(f"❌ Bağlantı Hatası: {str(e)}")
            
            time.sleep(bekleme_suresi)
            
        st.balloons()
        st.success("🏁 Tüm işlemler tamamlandı!")

elif not email and uploaded_file:
    st.warning("Lütfen e-mail adresinizi girin.")
