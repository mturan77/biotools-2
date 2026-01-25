import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.decomposition import PCA
import io

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="RNA-Seq Final Fix", layout="wide")
st.title("🧬 RNA-Seq Analiz Hattı (Manuel R-Mantığı)")

# --- CSS DÜZELTME ---
st.markdown("""
<style>
    .stButton>button { width: 100%; border-radius: 5px; }
    div[data-testid="stExpander"] div[role="button"] p { font-size: 1.1rem; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- OTURUM YÖNETİMİ ---
if 'hisat_df' not in st.session_state: st.session_state.hisat_df = None
if 'salmon_df' not in st.session_state: st.session_state.salmon_df = None
if 'processed' not in st.session_state: st.session_state.processed = False
if 'meta_df' not in st.session_state: st.session_state.meta_df = None
if 'design_col' not in st.session_state: st.session_state.design_col = None

# --- İNDİRME FONKSİYONU ---
def save_plot_hq(fig, format="png"):
    buf = io.BytesIO()
    fig.savefig(buf, format=format, bbox_inches="tight", dpi=300)
    buf.seek(0)
    return buf

# --- R MANTIĞI İLE NORMALİZASYON VE PCA ---
def r_style_normalization(counts_df):
    """
    R DESeq2'nin 'estimateSizeFactors' ve 'log2' mantığını manuel uygular.
    Kütüphane hatasından etkilenmez.
    """
    # 1. 0 olan değerleri filtrelemeden önce log al (Geometrik ortalama için)
    # R mantığı: log(counts) -> rowMeans -> exp -> median(counts/geo_means)
    
    # Sıfırları maskele (log(0) hatası olmasın diye +1 eklemiyoruz, R sıfırları atlar)
    log_counts = np.log(counts_df.replace(0, np.nan))
    geo_means = np.exp(log_counts.mean(axis=1))
    
    # Size Factor Hesapla
    ratios = counts_df.div(geo_means, axis=0)
    size_factors = ratios.median(axis=0)
    
    # 2. Normalize Et (Counts / SizeFactor)
    norm_counts = counts_df.div(size_factors, axis=1)
    
    # 3. Log2 Dönüşümü (R'daki vst/rlog yerine geçen en sağlam manuel yöntem: log2(n + 1))
    log_norm_counts = np.log2(norm_counts + 1)
    
    return log_norm_counts

def calculate_pca_r_style(log_norm_df, ntop=500):
    """
    R plotPCA fonksiyonunun birebir aynısı:
    1. Row varyanslarını hesapla (N-1)
    2. En yüksek varyanslı ntop geni seç
    3. PCA yap
    """
    # R 'var' fonksiyonu N-1 kullanır (ddof=1)
    rv = log_norm_df.var(axis=1, ddof=1)
    
    # En yüksek varyanslı genleri seç
    select = rv.sort_values(ascending=False).head(ntop).index
    
    # PCA uygula (Transpoze edilmiş matris üzerinde)
    pca_input = log_norm_df.loc[select].T
    
    pca = PCA(n_components=2)
    pca_res = pca.fit_transform(pca_input)
    percentVar = pca.explained_variance_ratio_ * 100
    
    return pca_res, percentVar, select

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Veri Yükleme")
    f_hisat = st.file_uploader("HISAT CSV", type=["csv"], key="hisat")
    f_salmon = st.file_uploader("SALMON CSV", type=["csv"], key="salmon")
    st.markdown("---")
    f_samples = st.file_uploader("Samples CSV", type=["csv"], key="samples")
    f_genes = st.file_uploader("Gen Listesi (TXT)", type=["txt"], key="genes")
    
    st.markdown("---")
    ref_grp = st.text_input("Referans Grup", "Control")
    
    if st.button("Analizi Başlat", type="primary"):
        st.session_state.processed = False
        st.session_state.run_trigger = True
    else:
        st.session_state.run_trigger = False

# --- İŞLEM AKIŞI ---
if st.session_state.run_trigger:
    if not f_samples:
        st.error("Samples dosyası eksik!"); st.stop()
        
    # Metadata Oku
    samp = pd.read_csv(f_samples, index_col=0)
    d_col = "condition" 
    if "condition" not in samp.columns: d_col = samp.columns[0]
    samp[d_col] = samp[d_col].astype(str)
    
    st.session_state.meta_df = samp
    st.session_state.design_col = d_col
    
    # Verileri Oku ve İşle
    try:
        if f_hisat:
            h_df = pd.read_csv(f_hisat, index_col=0)
            # Kesişim al
            common = list(set(h_df.columns) & set(samp.index))
            st.session_state.hisat_df = h_df[common]
            
        if f_salmon:
            s_df = pd.read_csv(f_salmon, index_col=0)
            common = list(set(s_df.columns) & set(samp.index))
            st.session_state.salmon_df = s_df[common]
            
        st.session_state.processed = True
    except Exception as e:
        st.error(f"Dosya okuma hatası: {e}")

# --- SONUÇLAR ---
if st.session_state.processed:
    meta = st.session_state.meta_df
    d_col = st.session_state.design_col
    
    tabs = st.tabs(["📊 HISAT2 Analizi", "📊 SALMON Analizi"])
    datasets = []
    
    if st.session_state.hisat_df is not None: 
        datasets.append(("HISAT2", st.session_state.hisat_df, tabs[0]))
    if st.session_state.salmon_df is not None: 
        datasets.append(("SALMON", st.session_state.salmon_df, tabs[1]))
    
    for name, raw_counts, tab in datasets:
        with tab:
            # 1. MANUEL NORMALİZASYON (R STİLİ)
            log_norm = r_style_normalization(raw_counts)
            
            # --- PCA BÖLÜMÜ ---
            st.subheader(f"PCA Analizi - {name}")
            
            # Kontroller
            c1, c2, c3, c4 = st.columns(4)
            use_custom = c1.checkbox(f"Gen Listesi Kullan", key=f"uc_{name}")
            inv_x = c2.checkbox("X Ters Çevir", value=False, key=f"ix_{name}")
            inv_y = c3.checkbox("Y Ters Çevir", value=False, key=f"iy_{name}")
            
            # PCA Hesapla
            if use_custom and f_genes:
                f_genes.seek(0)
                targets = [l.decode("utf-8").strip() for l in f_genes]
                valid = [t for t in targets if t in log_norm.index]
                if not valid: st.error("Genler bulunamadı!"); st.stop()
                
                # Özel listede varyans seçimi yapılmaz, hepsi kullanılır
                pca_input = log_norm.loc[valid].T
                pca = PCA(n_components=2)
                pca_res = pca.fit_transform(pca_input)
                percentVar = pca.explained_variance_ratio_ * 100
                title_suffix = f"(User List: {len(valid)})"
            else:
                # Standart R Mantığı (Top 500)
                pca_res, percentVar, _ = calculate_pca_r_style(log_norm, ntop=500)
                title_suffix = "(Top 500 Genes)"

            # Yön Düzeltme
            if inv_x: pca_res[:,0] *= -1
            if inv_y: pca_res[:,1] *= -1
            
            # Plot Dataframe
            plot_df = pd.DataFrame(pca_res, columns=["PC1", "PC2"], index=log_norm.columns)
            plot_df['group'] = meta.loc[plot_df.index, d_col]
            
            # GRAFİK ÇİZİMİ (KARE FORMAT - 8x8)
            fig, ax = plt.subplots(figsize=(8, 8)) 
            sns.scatterplot(data=plot_df, x="PC1", y="PC2", hue="group", s=150, alpha=0.9, ax=ax, edgecolor="black", linewidth=0.5)
            
            # Eksen Etiketleri (R Formatı)
            ax.set_xlabel(f"PC1: {int(round(percentVar[0]))}% variance", fontsize=12)
            ax.set_ylabel(f"PC2: {int(round(percentVar[1]))}% variance", fontsize=12)
            ax.set_title(f"PCA Plot {title_suffix} - {name}", fontsize=14)
            
            # Izgara ve Legend
            ax.grid(True, linestyle='--', alpha=0.4)
            ax.legend(bbox_to_anchor=(1.02, 1), loc='upper left', frameon=True)
            
            # Ekrana Bas
            col_graph, col_dl = st.columns([3, 1])
            with col_graph:
                st.pyplot(fig, use_container_width=False)
            with col_dl:
                st.markdown("### İndir")
                st.download_button("PNG (HQ)", save_plot_hq(fig, "png"), f"PCA_{name}.png", "image/png")
                st.download_button("SVG (Vektör)", save_plot_hq(fig, "svg"), f"PCA_{name}.svg", "image/svg+xml")
            plt.close(fig)
            
            st.divider()
            
            # --- HEATMAP BÖLÜMÜ ---
            st.subheader("Heatmap Analizi")
            
            # Gen Seçimi
            if use_custom and f_genes:
                hm_genes = valid # Yukarıda hesaplananı kullan
                hm_title = "Özel Gen Listesi"
            else:
                # Top 50 Varyans
                rv = log_norm.var(axis=1, ddof=1)
                hm_genes = rv.sort_values(ascending=False).head(50).index
                hm_title = "Top 50 Değişken Gen"
            
            mat = log_norm.loc[hm_genes]
            
            # Z-Score Hesapla (Row-based)
            # (Değer - Ortalama) / Std
            mat_z = mat.apply(lambda x: (x - x.mean()) / x.std(), axis=1)
            
            # Grafik
            fig_hm = sns.clustermap(mat_z, 
                                   cmap="vlag", 
                                   center=0, 
                                   col_cluster=False, 
                                   figsize=(8, 10),
                                   cbar_kws={'label': 'Z-Score'})
            
            col_hm_g, col_hm_d = st.columns([3, 1])
            with col_hm_g:
                st.pyplot(fig_hm)
            with col_hm_d:
                st.markdown("### İndir")
                st.download_button("Heatmap PNG", save_plot_hq(fig_hm.fig, "png"), f"Heatmap_{name}.png", "image/png")
            plt.close(fig_hm.fig)
