import streamlit as st
import requests
import time
from io import StringIO

# Sayfa Başlığı ve İkonu
st.set_page_config(page_title="Phyre2 Dedektif Modu", page_icon="🕵️‍♂️")

# --- YENİ EKLENEN KISIM: REFRESH BUTONU ---
# Bu buton sol menüde en üste yerleşir. Basıldığında sayfayı yeniden yükler (F5 gibi).
if st.sidebar.button("🔄 Sayfayı Yenile / Sıfırla"):
    st.rerun()

st.title("🧬 Phyre2 Cloud Gönderici")
st.markdown("Bu araç protein sekanslarını Phyre2 sunucusuna gönderir ve yanıtı kontrol eder.")

# --- Sidebar (Ayarlar) ---
with st.sidebar:
    st.header("Ayarlar")
    # Varsayılan mail adresi
    email = st.text_input("E-mail Adresiniz", value="muratturan077@gmail.com")
    mode = st.selectbox("Modelleme Modu", ["normal", "intensive"])
    
    # Hız Ayarı (İsteğe bağlı kontrol)
    bekleme_suresi = st.slider("İki gönderim arası bekleme (saniye)", 1.0, 10.0, 2.0)
    
    st.info("ℹ️ İşlem çalışırken durdurmak için sayfanın sağ üstündeki 'Stop' butonuna basabilir veya 'Sayfayı Yenile' diyebilirsiniz.")

# --- Dosya Yükleme ---
uploaded_file = st.file_uploader("Protein FASTA Dosyası Seçin", type=["fa", "fasta", "txt"])

if uploaded_file and email:
    # Dosyayı hafızada oku
    stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
    content = stringio.read()
    
    # '>' işaretine göre böl ve boş olanları temizle
    raw_entries = [x for x in content.split('>') if x.strip()]
    
    st.success(f"📂 Dosya okundu. Toplam **{len(raw_entries)}** sekans bulundu.")
    
    # Gönderim Butonu
    if st.button("🚀 Gönderimi Başlat"):
        # İlerleme Çubuğu ve Durum Mesajı
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Sonuçları göstermek için bir alan
        results_container = st.container()

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
                'usr-email': email,      
                'seq-desc': header,      
                'sequence': sequence,    
                'modelmode': mode
            }
            
            try:
                # Sunucu tarafında istek atıyoruz
                response = requests.post(url, data=payload, timeout=30)
                
                # Yanıtı Kontrol Et
                if response.status_code == 200:
                    # Başarı mesajı arıyoruz
                    if "submitted" in response.text.lower() or "success" in response.text.lower():
                        results_container.success(f"✅ [{i+1}] BAŞARILI: {header}")
                        
                        # İstersen burada 'Kanıt' göstergesini de açabilirsin
                        with results_container.expander(f"🔍 Kanıt Detayı ({header})"):
                            st.code(response.text[:300]) # İlk 300 karakter
                            
                    else:
                        results_container.warning(f"⚠️ [{i+1}] Şüpheli Durum: {header}")
                else:
                    results_container.error(f"❌ [{i+1}] Sunucu Hatası ({response.status_code}) -> {header}")
                    
            except Exception as e:
                results_container.error(f"❌ [{i+1}] Bağlantı Hatası: {str(e)}")
            
            # Seçilen süre kadar bekle
            time.sleep(bekleme_suresi)
            
        st.balloons()
        st.success("🏁 Tüm işlemler tamamlandı!")

elif not email and uploaded_file:
    st.warning("Lütfen sol taraftan e-mail adresinizi girin.")
