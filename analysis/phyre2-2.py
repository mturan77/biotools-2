import streamlit as st
import time
import pandas as pd

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Monitoring Loop", layout="wide")

# --- SESSION STATE (DURUM YÖNETİMİ) ---
# Streamlit her çalıştığında hafıza sıfırlanmasın diye değişkenleri burada tutuyoruz.
if 'is_running' not in st.session_state:
    st.session_state.is_running = False
if 'cycle_count' not in st.session_state:
    st.session_state.cycle_count = 0

# --- ARAYÜZ ---
st.title("🛡️ System Monitoring Loop")

# Sidebar - Ayarlar
with st.sidebar:
    st.header("⚙️ Loop Settings")
    # Kullanıcı süreyi değiştirdiğinde script baştan çalışır ve yeni süreyi alır.
    wait_minutes = st.number_input("Wait Time (Minutes)", min_value=0.1, value=1.0, step=0.5)
    
    # Başlat / Durdur Butonları
    if st.button("▶ Initiate Monitoring Loop", type="primary"):
        st.session_state.is_running = True
        st.rerun()
    
    if st.button("⏹ Stop System"):
        st.session_state.is_running = False
        st.rerun()

# --- ANA MANTIK ---
if st.session_state.is_running:
    
    # Yer tutucular (Placeholders): 
    # Streamlit'te akıcı animasyon için boş kutular oluşturup içini dolduruyoruz.
    status_header = st.empty()
    progress_bar = st.progress(0)
    log_area = st.empty()
    timer_area = st.empty()

    # Hedef Listesi (Simülasyon)
    targets = [f"Target_Server_{i+1:02d}" for i in range(13)]
    
    # ---------------------------------------------------------
    # BÖLÜM 1: TARAMA DÖNGÜSÜ (DOWNLOAD MODE GİBİ GÖSTERİM)
    # ---------------------------------------------------------
    st.session_state.cycle_count += 1
    cycle_num = st.session_state.cycle_count
    
    status_header.markdown(f"### 🔄 Cycle {cycle_num}: Scanning Started...")
    
    for i, target in enumerate(targets):
        # 1. UI Güncelle: "Şu an bunu tarıyorum" efekti
        current_progress = (i + 1) / len(targets)
        progress_bar.progress(current_progress)
        
        # Log alanını dinamik güncelle
        # HTML kullanarak o an tarananı kalın (bold) ve renkli gösteriyoruz
        log_html = f"""
        <div style="border:1px solid #ddd; padding:10px; border-radius:5px;">
            Scanning: <b style="color:blue;">{target}</b><br>
            <span style="color:gray; font-size:0.8em;">Processed {i+1}/{len(targets)} targets</span>
        </div>
        """
        log_area.markdown(log_html, unsafe_allow_html=True)
        
        # 2. İşlem Simülasyonu (Gerçek işlem kodunu buraya koyacaksın)
        time.sleep(0.3)  # Her hedef için 0.3 saniye bekle (Hızlı geçiş hissi)

    # Tarama bitti, logu sabitle
    log_area.success(f"✅ Cycle {cycle_num} Completed successfully. {len(targets)} targets scanned.")
    
    # ---------------------------------------------------------
    # BÖLÜM 2: AKILLI BEKLEME (GERİ SAYIM ANIMASYONU)
    # ---------------------------------------------------------
    
    # Saniye cinsinden toplam süre
    total_wait_seconds = int(wait_minutes * 60)
    
    # Geri sayım döngüsü
    for remaining in range(total_wait_seconds, 0, -1):
        # "Durdur" butonuna basılırsa döngüden hemen çıkması için kontrol (Zorunlu değil ama iyi pratik)
        if not st.session_state.is_running:
            break

        # Yüzdelik hesapla
        percent_complete = 1.0 - (remaining / total_wait_seconds)
        
        # Dakika:Saniye formatı
        mins, secs = divmod(remaining, 60)
        time_str = f"{mins:02d}:{secs:02d}"
        
        # Timer animasyonu (Turuncu bar ve metin)
        status_header.markdown(f"### ⏳ Sleeping... Next scan in: `{time_str}`")
        progress_bar.progress(percent_complete) # Dolum efekti
        
        # Burası önemli: 1 saniye bekle
        time.sleep(1)
    
    # ---------------------------------------------------------
    # BÖLÜM 3: LOOP (YENİDEN BAŞLATMA)
    # ---------------------------------------------------------
    if st.session_state.is_running:
        st.rerun()  # Scripti en baştan tekrar çalıştırır -> Yeni Cycle başlar

else:
    # Sistem kapalıyken görünecek ekran
    st.info("System is IDLE. Click 'Initiate' to start the monitoring loop.")
    st.metric(label="Total Cycles Completed", value=st.session_state.cycle_count)
