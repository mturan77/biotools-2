import streamlit as st
import requests
import time
from io import StringIO

# Sayfa Başlığı ve İkonu
st.set_page_config(page_title="Phyre2 Otomasyonu", page_icon="🧬")

st.title("🧬 Phyre2 Cloud Gönderici")
st.markdown("""
Bu araç, tarayıcı engellerine takılmadan **Phyre2** sunucusuna doğrudan veri gönderir.
""")

# --- Sidebar (Ayarlar) ---
with st.sidebar:
    st.header("Ayarlar")
    email = st.text_input("E-mail Adresiniz", placeholder="mail@universite.edu.tr")
    mode = st.selectbox("Modelleme Modu", ["normal", "intensive"])
    st.info("ℹ️ Phyre2 sunucusu eski olduğu için her gönderim arasında 2 saniye bekleme süresi konulmuştur.")

# --- Dosya Yükleme ---
uploaded_file = st.file_uploader("Protein FASTA Dosyası Seçin", type=["fa", "fasta", "txt"])

if uploaded_file and email:
    # Dosyayı hafızada oku
    stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
    content = stringio.read()
    
    # '>' işaretine göre böl ve boş olanları temizle
    raw_entries = [x for x in content.split('>') if x.strip()]
    
    st.success(f"📂 Dosya okundu. Toplam **{len(raw_entries)}** sekans bulundu.")
    
    if st.button("🚀 Gönderimi Başlat"):
        # İlerleme Çubuğu
        progress_bar = st.progress(0)
        status_text = st.empty()
        log_area = st.container()
        
        success_count = 0
        fail_count = 0
        
        # Döngü
        for i, entry in enumerate(raw_entries):
            # Header ve Sequence ayrıştırma
            lines = entry.strip().split('\n')
            header = lines[0].strip()
            sequence = "".join(lines[1:]).replace(" ", "") # Boşlukları sil
            
            # Durum güncelleme
            status_text.text(f"İşleniyor ({i+1}/{len(raw_entries)}): {header}...")
            progress_bar.progress((i + 1) / len(raw_entries))
            
            # --- PHYRE2 POST İŞLEMİ ---
            url = "http://www.sbg.bio.ic.ac.uk/phyre2/webscripts/phyre2_submit.cgi"
            
            # HTML analizinden bulduğumuz KESİN parametreler
            payload = {
                'usr-email': email,      # 'email' değil 'usr-email'
                'seq-desc': header,      # 'jobid' değil 'seq-desc'
                'sequence': sequence,    # 'seq' değil 'sequence'
                'modelmode': mode
            }
            
            try:
                # Sunucu tarafında istek atıyoruz (Browser engeli yok)
                response = requests.post(url, data=payload, timeout=30)
                
                # Phyre2 genelde başarılıysa 200 döner ve içinde 'submitted' yazar
                if response.status_code == 200:
                    # Basit bir kontrol: Hata mesajı var mı?
                    if "valid e-mail" in response.text.lower():
                        log_area.error(f"❌ [{i+1}] Hata: E-mail formatı beğenilmedi -> {header}")
                        fail_count += 1
                    else:
                        # Genelde başarılı sayılır
                        log_area.success(f"✅ [{i+1}] Gönderildi -> {header}")
                        success_count += 1
                else:
                    log_area.error(f"❌ [{i+1}] Sunucu Hatası ({response.status_code}) -> {header}")
                    fail_count += 1
                    
            except Exception as e:
                log_area.error(f"❌ [{i+1}] Bağlantı Hatası: {str(e)}")
                fail_count += 1
            
            # Sunucuyu boğmamak için bekleme
            time.sleep(2)
            
        st.balloons()
        st.success(f"🏁 İşlem Tamamlandı! Başarılı: {success_count}, Hata: {fail_count}")

elif not email and uploaded_file:
    st.warning("Lütfen sol taraftan e-mail adresinizi girin.")
