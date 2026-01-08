import streamlit as st
import requests
import time
from io import StringIO

st.set_page_config(page_title="Phyre2 Tanı Modu", page_icon="🔧")

# --- YENİLEME BUTONU ---
if st.sidebar.button("🔄 Sayfayı Yenile"):
    st.rerun()

st.title("🧬 Phyre2 Gelişmiş Gönderici")
st.markdown("Bu versiyon, sunucunun 'robot' korumasını aşmak için tarayıcı taklidi yapar ve detaylı hata raporu sunar.")

# --- AYARLAR ---
with st.sidebar:
    st.header("Ayarlar")
    email = st.text_input("E-mail Adresiniz", value="muratturan077@gmail.com")
    mode = st.selectbox("Modelleme Modu", ["normal", "intensive"])
    
    # Kullanıcı Tipi (Sunucunun reddetme ihtimaline karşı)
    st.caption("Kullanıcı Tipi (Genelde 'Academic' seçilir)")
    user_type = st.radio("Kullanım Amacı", ["Academic (Kâr Amacı Yok)", "Commercial (Ticari)"], index=0)
    
    bekleme_suresi = st.number_input(
        "Bekleme Süresi (sn)", 
        min_value=0.5, max_value=30.0, value=2.0, step=0.1, format="%.2f"
    )

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
            
            # --- ÖNEMLİ GÜNCELLEME: Headers (Tarayıcı Taklidi) ---
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'http://www.sbg.bio.ic.ac.uk/phyre2/html/page.cgi?id=index'
            }

            payload = {
                'usr-email': email,      
                'seq-desc': header,      
                'sequence': sequence,    
                'modelmode': mode,
                # Ekstra alanlar (Şansımızı artırmak için)
                'private': 'no', 
                'type': 'academic' if 'Academic' in user_type else 'commercial' 
            }
            
            try:
                # Headers ekleyerek gönderiyoruz
                response = requests.post(url, data=payload, headers=headers, timeout=45)
                
                # --- GELİŞMİŞ HATA ANALİZİ ---
                is_success = False
                # Başarı kelimeleri
                success_keywords = ["submitted", "success", "job id", "queue"]
                
                if response.status_code == 200:
                    # Gelen HTML'i küçük harfe çevirip kontrol et
                    resp_text_lower = response.text.lower()
                    
                    if any(x in resp_text_lower for x in success_keywords) and "error" not in resp_text_lower[:500]:
                        is_success = True
                        results.success(f"✅ [{i+1}] BAŞARILI: {header}")
                    else:
                        # BAŞARISIZ OLDUYSA SEBEBİNİ GÖSTER
                        results.warning(f"⚠️ [{i+1}] GÖNDERİLEMEDİ: {header}")
                        
                        # Hata Detay Kutusu
                        with results.expander("🔍 Sunucu Ne Cevap Verdi? (Tıkla ve Oku)"):
                            st.write("Sunucu isteği reddetti. İşte cevabı:")
                            # HTML içindeki yazıları temizlemeden ham halini göster ki hatayı okuyabilelim
                            st.components.v1.html(response.text, height=300, scrolling=True)
                            
                else:
                    results.error(f"❌ Sunucu Hatası ({response.status_code})")
                    
            except Exception as e:
                results.error(f"❌ Bağlantı Hatası: {str(e)}")
            
            time.sleep(bekleme_suresi)
            
        st.success("İşlem bitti.")

elif not email and uploaded_file:
    st.warning("Lütfen e-mail adresinizi girin.")
