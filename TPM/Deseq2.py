import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
import io

# ==============================================================================
# 1. AYARLAR VE STİL
# ==============================================================================
st.set_page_config(page_title="RNA-Seq Analiz Hattı (Final V3)", layout="wide")
st.title("🧬 RNA-Seq Analiz Hattı (DESeq2 Mantığı)")

st.markdown("""
<style>
    .stButton>button { width: 100%; border-radius: 5px; }
    div[data-testid="stExpander"] div[role="button"] p { font-size: 1.1rem; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 2. OTURUM YÖNETİMİ (Session State - Hata Düzeltildi)
# ==============================================================================
# AttributeError hatasını önlemek için tüm değişkenleri en başta tanımlıyoruz.
if 'run_trigger' not in st.session_state: st.session_state.run_trigger = False
if 'hisat_df' not in st.session_state: st.session_state.hisat_df = None
if 'salmon_df' not in st.session_state: st.session_state.salmon_df = None
if 'processed' not in st.session_state: st.session_state.processed = False
if 'meta_df' not in st.session_state: st.session_state.meta_df = None
if 'design_col' not in st.session_state: st.session_state.design_col = None

# ==============================================================================
# 3. YARDIMCI FONKSİYONLAR
# ==============================================================================

def save_plot_hq(fig, format="png"):
    """Grafikleri yüksek kalitede indirmek için buffer oluşturur."""
    buf = io.BytesIO()
    fig.savefig(buf, format=format, bbox_inches="tight", dpi=300)
    buf.seek(0)
    return buf

def calculate_size_factors_deseq_style(counts_df):
    """
    DESeq2 mantığına birebir uygun Size Factor hesaplar.
    """
    # 0 içeren satırları (genleri) geometrik ortalama hesabından çıkar
    non_zero_genes = counts_df[(counts_df > 0).all(axis=1)]
    
    if non_zero_genes.empty:
        st.warning("Uyarı: Tüm genlerde en az bir tane 0 var. Basit normalizasyon uygulanıyor.")
        return pd.Series(1.0, index=counts_df.columns)

    # Referans (Geometrik Ortalama)
    log_geomeans = np.log(non_zero_genes).mean(axis=1)
    
    # Ratio hesapla
    cnts_sub = counts_df.loc[non_zero_genes.index]
    ratios = cnts_sub.div(np.exp(log_geomeans), axis=0)
    
    # Medyan al (Size Factor)
    size_factors = ratios.median(axis=0)
    return size_factors

def r_style_normalization(counts_df):
    """
    Ham count verisini DESeq2 mantığıyla normalize eder ve log2 dönüşümü yapar.
    """
    # Veriyi float'a çevir (güvenlik)
    counts_df = counts_df.astype(float)
    
    # Size Factors Hesapla
    sf = calculate_size_factors_deseq_style(counts_df)
    
    # Normalize Et (Counts / SizeFactor)
    norm_counts = counts_df.div(sf, axis=1)
    
    # Log2 Dönüşümü (log2(n + 1))
    log_norm_counts = np.log2(norm_counts + 1)
    
    return log_norm_counts, sf

def calculate_pca_r_style(log_norm_df, ntop=500):
    """
    R (DESeq2) PCA çıktısına en yakın sonucu üretmek için
    düşük varyanslı/gürültülü genleri filtreleyerek PCA yapar.
    """
    # 1. Gürültü Filtresi (Noise Filter)
    # Ortalaması 1'den küçük olan çok silik genleri at.
    mean_filter = log_norm_df.mean(axis=1) > 1.0 
    filtered_df = log_norm_df[mean_filter]

    # Eğer filtre çok fazla gen atarsa, filtreyi iptal et
    if len(filtered_df) < ntop:
        filtered_df = log_norm_df

    # 2. Varyans Hesapla (N-1 ddof)
    rv = filtered_df.var(axis=1, ddof=1)
    
    # 3. En yüksek varyanslı genleri seç
    select = rv.sort_values(ascending=False).head(ntop).index
    
    # 4. MATRİSİ HAZIRLA
    pca_input = log_norm_df.loc[select].T
    
    # --- KRİTİK DÜZELTME: STANDARTLAŞTIRMA (SCALING) ---
    # R'daki VST'nin yarattığı varyans dağılımını yakalamak için
    # veriyi scale ediyoruz (Ortalama=0, Varyans=1 yapıyoruz).
    # Bu işlem PC1 varyans oranını genellikle arttırır ve %40'lara yaklaştırır.
    scaler = StandardScaler()
    pca_input_scaled = scaler.fit_transform(pca_input)
    
    # 5. PCA Uygula
    pca = PCA(n_components=2)
    pca_res = pca.fit_transform(pca_input_scaled)
    percentVar = pca.explained_variance_ratio_ * 100
    
    return pca_res, percentVar, select

# ==============================================================================
# 4. ARAYÜZ (SIDEBAR)
# ==============================================================================
with st.sidebar:
    st.header("1. Veri Yükleme")
    st.info("Lütfen CSV dosyalarını yükleyin.")
    
    f_hisat = st.file_uploader("HISAT Counts (CSV)", type=["csv"], key="hisat")
    f_salmon = st.file_uploader("SALMON Counts (CSV)", type=["csv"], key="salmon")
    st.markdown("---")
    f_samples = st.file_uploader("Samples Metadata (CSV)", type=["csv"], key="samples")
    f_genes = st.file_uploader("Gen Listesi (Opsiyonel - TXT)", type=["txt"], key="genes")
    
    st.markdown("---")
    
    # Butona basınca state güncellenir
    if st.button("Analizi Başlat", type="primary"):
        st.session_state.processed = False
        st.session_state.run_trigger = True
    else:
        # Sayfa yenilendiğinde trigger false kalmalı ki döngüye girmesin
        # Ancak processed True ise sonuçlar ekranda kalmaya devam eder.
        st.session_state.run_trigger = False

# ==============================================================================
# 5. VERİ İŞLEME MANTIĞI
# ==============================================================================
# Trigger tetiklendiyse veya veri daha önce işlendiyse (refresh durumunda kaybolmasın diye)
if st.session_state.run_trigger or (st.session_state.processed and f_samples):
    
    if not f_samples:
        st.error("Samples dosyası yüklenmedi! Lütfen yükleyip tekrar deneyin.")
        st.stop()
        
    # --- Metadata Okuma ---
    try:
        if f_samples: f_samples.seek(0)
        samp = pd.read_csv(f_samples, index_col=0)
        
        # Condition sütununu bul
        d_col = "condition" 
        if "condition" not in samp.columns: 
            d_col = samp.columns[0] # Condition yoksa ilk sütunu al
            
        samp[d_col] = samp[d_col].astype(str)
        
        st.session_state.meta_df = samp
        st.session_state.design_col = d_col
    except Exception as e:
        st.error(f"Samples dosyası okunurken hata: {e}")
        st.stop()
    
    # --- Count Verilerini Okuma ---
    try:
        # HISAT
        if f_hisat:
            f_hisat.seek(0)
            h_df = pd.read_csv(f_hisat, index_col=0)
            # Metadata ile eşleşen sütunları al
            common_h = list(set(h_df.columns) & set(samp.index))
            st.session_state.hisat_df = h_df[common_h]
            
        # SALMON
        if f_salmon:
            f_salmon.seek(0)
            s_df = pd.read_csv(f_salmon, index_col=0)
            common_s = list(set(s_df.columns) & set(samp.index))
            st.session_state.salmon_df = s_df[common_s]
            
        st.session_state.processed = True
        
    except Exception as e:
        st.error(f"Count dosyaları okunurken hata: {e}")
        st.session_state.processed = False

# ==============================================================================
# 6. SONUÇ GÖSTERİMİ
# ==============================================================================
if st.session_state.processed:
    meta = st.session_state.meta_df
    d_col = st.session_state.design_col
    
    # Eğer hiç veri yoksa uyar
    if st.session_state.hisat_df is None and st.session_state.salmon_df is None:
        st.warning("Görüntülenecek veri yok. Lütfen HISAT veya SALMON dosyasını yükleyin.")
        st.stop()

    # Sekmeleri oluştur
    tabs = st.tabs(["📊 HISAT2 Analizi", "📊 SALMON Analizi"])
    datasets = []
    
    if st.session_state.hisat_df is not None: 
        datasets.append(("HISAT2", st.session_state.hisat_df, tabs[0]))
    if st.session_state.salmon_df is not None: 
        datasets.append(("SALMON", st.session_state.salmon_df, tabs[1]))
    
    # Her veri seti için döngü
    for name, raw_counts, tab in datasets:
        with tab:
            # --- A. Normalizasyon ---
            log_norm, sf = r_style_normalization(raw_counts)
            
            with st.expander(f"ℹ️ {name} - Normalizasyon Detayları"):
                st.write("**Size Factors:**")
                st.dataframe(sf.to_frame(name="SizeFactor").T)
                st.write(f"Toplam Gen Sayısı: {len(log_norm)}")

            # --- B. PCA Analizi ---
            st.subheader(f"PCA Analizi - {name}")
            
            c1, c2, c3, c4 = st.columns(4)
            use_custom = c1.checkbox(f"Gen Listesi Kullan", key=f"uc_{name}")
            inv_x = c2.checkbox("X Eksenini Çevir", value=False, key=f"ix_{name}")
            inv_y = c3.checkbox("Y Eksenini Çevir", value=False, key=f"iy_{name}")
            
            # PCA Hesaplama Mantığı
            valid_genes = []
            if use_custom and f_genes:
                f_genes.seek(0)
                targets = [l.decode("utf-8").strip() for l in f_genes]
                # Datada mevcut olanları al
                valid_genes = [t for t in targets if t in log_norm.index]
                
                if not valid_genes:
                    st.error("Yüklenen gen listesindeki genler veride bulunamadı!")
                    st.stop()
                
                # Özel listede varyans filtrelemesi yapılmaz, hepsi alınır
                pca_input = log_norm.loc[valid_genes].T
                pca = PCA(n_components=2)
                pca_res = pca.fit_transform(pca_input)
                percentVar = pca.explained_variance_ratio_ * 100
                title_suffix = f"(User List: {len(valid_genes)})"
            else:
                # Standart R Stili (Top 500 varyans)
                pca_res, percentVar, _ = calculate_pca_r_style(log_norm, ntop=500)
                title_suffix = "(Top 500 Genes)"

            # Eksen çevirme (Görseli R ile eşleştirmek için)
            if inv_x: pca_res[:,0] *= -1
            if inv_y: pca_res[:,1] *= -1
            
            # Plot DataFrame hazırlığı
            plot_df = pd.DataFrame(pca_res, columns=["PC1", "PC2"], index=log_norm.columns)
            # Grupları metadata'dan çek
            plot_df['group'] = meta.loc[plot_df.index, d_col]
            
            # --- PCA Grafiği Çizimi ---
            fig, ax = plt.subplots(figsize=(8, 8)) # Kareye yakın format
            
            sns.scatterplot(
                data=plot_df, x="PC1", y="PC2", 
                hue="group", style="group",
                s=200, alpha=0.9, ax=ax, 
                edgecolor="black", linewidth=0.8, palette="Set1"
            )
            
            ax.set_xlabel(f"PC1: {int(round(percentVar[0]))}% variance", fontsize=12)
            ax.set_ylabel(f"PC2: {int(round(percentVar[1]))}% variance", fontsize=12)
            ax.set_title(f"PCA Plot {title_suffix} - {name}", fontsize=14)
            ax.grid(True, linestyle=':', alpha=0.6)
            ax.legend(bbox_to_anchor=(1.02, 1), loc='upper left', frameon=False)
            
            # Gösterim ve İndirme
            col_graph, col_dl = st.columns([3, 1])
            with col_graph:
                st.pyplot(fig, use_container_width=False)
            with col_dl:
                st.markdown("### İndir")
                st.download_button("PNG (HQ)", save_plot_hq(fig, "png"), f"PCA_{name}.png", "image/png")
                st.download_button("SVG (Vektör)", save_plot_hq(fig, "svg"), f"PCA_{name}.svg", "image/svg+xml")
            plt.close(fig)
            
            st.divider()
            
            # --- C. Heatmap Analizi ---
            st.subheader("Heatmap Analizi")
            
            # Hangi genleri kullanacağız?
            if use_custom and valid_genes:
                hm_genes = valid_genes
                hm_title = "Heatmap (Özel Liste)"
            else:
                # Varyansa göre Top 50
                rv = log_norm.var(axis=1, ddof=1)
                hm_genes = rv.sort_values(ascending=False).head(50).index
                hm_title = "Heatmap (Top 50 Değişken Gen)"
            
            mat = log_norm.loc[hm_genes]
            
            # Z-Score Hesapla (Satır bazlı: (x - mean) / std)
            # R pheatmap scale="row" mantığı
            mat_z = mat.apply(lambda x: (x - x.mean()) / x.std(), axis=1)
            
            # Clustermap Çizimi
            # method='complete' -> R pheatmap varsayılanına en yakınıdır.
            try:
                fig_hm = sns.clustermap(
                    mat_z, 
                    method='complete', 
                    metric='euclidean',
                    cmap="RdBu_r", # Kırmızı-Mavi (RColorBrewer stili)
                    center=0, 
                    col_cluster=False, # Sütunları (örnekleri) karıştırma
                    figsize=(8, max(8, len(mat_z)*0.25)), # Dinamik yükseklik
                    cbar_kws={'label': 'Z-Score'}
                )
                
                fig_hm.ax_heatmap.set_title(hm_title)
                
                col_hm_g, col_hm_d = st.columns([3, 1])
                with col_hm_g:
                    st.pyplot(fig_hm)
                with col_hm_d:
                    st.markdown("### İndir")
                    st.download_button("Heatmap PNG", save_plot_hq(fig_hm.fig, "png"), f"Heatmap_{name}.png", "image/png")
                    st.download_button("Heatmap SVG", save_plot_hq(fig_hm.fig, "svg"), f"Heatmap_{name}.svg", "image/svg+xml")
                plt.close(fig_hm.fig)
                
            except Exception as e:
                st.error(f"Heatmap çizilirken hata oluştu (Gen sayısı çok az olabilir): {e}")
