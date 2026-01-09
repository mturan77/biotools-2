import streamlit as st
import pandas as pd
import time
import random
from datetime import datetime

# --- AYARLAR & STİL ---
st.set_page_config(page_title="Genomic Pipeline", page_icon="🧬", layout="wide")

st.markdown("""
<style>
    .stDataFrame { border: 1px solid #444; }
    .reportview-container { background: #0e1117; }
</style>
""", unsafe_allow_html=True)

# --- SAHTE VERİ & DURUM ---
GENE_LIST = ["Mdom002531.1", "Mdom003083.1", "Mdom004200.1", "Mdom008091.1", "Mdom009999.1"]
LOGS = []

# --- FONKSİYONLAR ---

def add_log(message, level="INFO"):
    """Sisteme zaman damgalı log ekler."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    icon = "ℹ️" if level == "INFO" else "⚠️" if level == "WARN" else "❌"
    LOGS.insert(0, f"[{timestamp}] {icon} {message}") # En yeniyi en üste ekle
    return LOGS

def simulate_processing(gene_id, status_container):
    """
    Retry mekanizmalı işlem simülasyonu.
    Burayı kendi indirme/parse kodunla değiştireceksin.
    """
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            # 1. Adım: Bağlantı
            status_container.write(f"📡 {gene_id}: API Bağlantısı kuruluyor (Deneme {attempt}/{max_retries})...")
            time.sleep(random.uniform(0.5, 1.5))
            
            # Hata Simülasyonu (Belli genler hata versin diye)
            if gene_id == "Mdom008091.1" and attempt < 3:
                raise ConnectionError("Sunucu yanıt vermedi (Timeout).")
            
            # 2. Adım: İndirme
            status_container.write(f"⬇️ {gene_id}: Veri paketi indiriliyor...")
            time.sleep(0.8)
            
            # 3. Adım: Doğrulama
            status_container.write(f"🔍 {gene_id}: Checksum doğrulanıyor...")
            time.sleep(0.5)
            
            return True, "SUCCESS", "İşlem Tamamlandı"
            
        except Exception as e:
            add_log(f"{gene_id} - Hata: {str(e)}", "WARN")
            if attempt < max_retries:
                status_container.warning(f"⚠️ {gene_id}: Hata alındı. {2} saniye içinde tekrar deneniyor...")
                time.sleep(2) # Backoff süresi
            else:
                return False, "FAILED", str(e)

# --- ARAYÜZ (UI) ---

st.title("🧬 Genomic Data Acquisition Pipeline")
st.markdown("---")

col1, col2 = st.columns([2, 1])

# Sol Taraf: Canlı Tablo
with col1:
    st.subheader("📋 Batch Processing Queue")
    table_placeholder = st.empty()
    
    # Başlangıç Tablosu
    df = pd.DataFrame({
        "Gene ID": GENE_LIST,
        "Status": ["PENDING"] * len(GENE_LIST),
        "Details": ["Waiting..."] * len(GENE_LIST)
    })
    table_placeholder.dataframe(df, use_container_width=True)

# Sağ Taraf: Canlı Terminal Log
with col2:
    st.subheader("📟 System Telemetry")
    log_placeholder = st.empty()
    log_placeholder.code("System ready. Waiting for start command...", language="bash")

# --- İŞLEM BAŞLATMA ---
if st.button("▶️ Start Sequence", type="primary"):
    
    progress_bar = st.progress(0)
    
    # STREAMLIT STATUS CONTAINER (Burası o 'Processing' yazısını güzelleştiren yer)
    with st.status("🚀 Pipeline Başlatıldı...", expanded=True) as status:
        
        for i, gene in enumerate(GENE_LIST):
            # Durum güncellemesi (Kullanıcıya ne olduğunu söyle)
            status.update(label=f"Processing Record {i+1}/{len(GENE_LIST)}: **{gene}**", state="running")
            
            # Tabloda 'Processing' işaretle
            df.loc[df["Gene ID"] == gene, "Status"] = "⏳ PROCESSING"
            df.loc[df["Gene ID"] == gene, "Details"] = "Initializing..."
            table_placeholder.dataframe(df, use_container_width=True)
            
            # İşlemi Yap (Retry mantığı burada çalışıyor)
            success, result_status, msg = simulate_processing(gene, status)
            
            # Sonuçları Tabloya Yaz
            if success:
                df.loc[df["Gene ID"] == gene, "Status"] = "✅ COMPLETED"
                df.loc[df["Gene ID"] == gene, "Details"] = "Indexed in DB"
                add_log(f"{gene} başarıyla işlendi.", "INFO")
            else:
                df.loc[df["Gene ID"] == gene, "Status"] = "❌ FAILED"
                df.loc[df["Gene ID"] == gene, "Details"] = "Max retries exceeded"
                add_log(f"{gene} için tüm denemeler başarısız oldu.", "ERROR")
            
            # UI Güncelle
            table_placeholder.dataframe(df, use_container_width=True)
            log_placeholder.code("\n".join(LOGS[:10]), language="bash") # Son 10 logu göster
            progress_bar.progress((i + 1) / len(GENE_LIST))
            
        status.update(label="🏁 Batch İşlemi Tamamlandı", state="complete", expanded=False)

    st.success("Tüm kuyruk tamamlandı.")
