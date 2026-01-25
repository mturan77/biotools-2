import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.decomposition import PCA
import io

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="RNA-Seq Analiz Hattı (V2)", layout="wide")
st.title("🧬 RNA-Seq Analiz Hattı (DESeq2-Style)")

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

# --- DESEQ2 STİLİ NORMALİZASYON (DÜZELTİLMİŞ) ---
def calculate_size_factors_deseq_style(counts_df):
    """
    DESeq2 mantığına birebir uygun Size Factor hesaplar:
    Sadece TÜM örneklerde sıfırdan büyük olan genler geometrik ortalama için kullanılır.
    """
    # 1. Sadece her örnekte dolu (0 olmayan) genleri seç
    # DESeq2 geometric mean hesabına 0 içeren satırları katmaz.
    non_zero_genes = counts_df[(counts_df > 0).all(axis=1)]
    
    # 2. Referans (Geometrik Ortalama) hesapla (log uzayında aritmetik ortalama)
    log_geomeans = np.log(non_zero_genes).mean(axis=1)
    
    # 3. Ratio hesapla (Sadece geçerli genler için)
    # Orijinal count matrisindeki bu genlerin değerlerini referansa böl
    cnts_sub = counts_df.loc[non_zero_genes.index]
    ratios = cnts_sub.div(np.exp(log_geomeans), axis=0)
    
    # 4. Medyan al (Size Factor)
    size_factors = ratios.median(axis=0)
    return size_factors

def r_style_normalization(counts_df):
    # Veriyi float'a zorla
    counts_df = counts_df.astype(float)
    
    # DESeq2 Size Factors Hesapla
    sf = calculate_size_factors_deseq_style(counts_df)
    
    # Normalize Et
    norm_counts = counts_df.div(sf, axis=1)
    
    # Log2 Dönüşümü (R'daki VST yerine Log2(n+1))
    # Not: VST tam olarak taklit edilemez, ama bu en yakın standart yaklaşımdır.
    log_norm_counts = np.log2(norm_counts + 1)
    
    return log_norm_counts, sf

def calculate_pca_r_style(log_norm_df, ntop=500):
    """
    R-Style PCA with Noise Filtering
    """
    # 1. GÜRÜLTÜ FİLTRESİ (R sonucuna yaklaşmak için kritik adım)
    # DESeq2 VST işlemi düşük count'lu genlerin varyansını bastırır.
    # Log2 bunu yapamadığı için, biz manuel olarak çok düşük ifade edilen genleri
    # varyans sıralamasına sokmadan eliyoruz.
    
    # Ortalama ifadesi çok düşük olanları (log2 scale'de < 1 gibi) yoksay
    # Bu genler genelde PC1 varyansını düşüren gürültülerdir.
    mean_filter = log_norm_df.mean(axis=1) > 1.0 
    filtered_df = log_norm_df[mean_filter]

    # Eğer filtre sonrası gen sayısı 500'den az kalırsa filtreyi gevşet
    if len(filtered_df) < ntop:
        filtered_df = log_norm_df

    # 2. R 'var' fonksiyonu N-1 kullanır (ddof=1)
    rv = filtered_df.var(axis=1, ddof=1)
    
    # 3. En yüksek varyanslı genleri seç
    select = rv.sort_values(ascending=False).head(ntop).index
    
    # 4. PCA uygula
    pca_input = log_norm_df.loc[select].T # Orijinal datadan seçilenleri al
    
    pca = PCA(n_components=2)
    pca_res = pca.fit_transform(pca_input)
    percentVar = pca.explained_variance_ratio_ * 100
    
    return pca_res, percentVar, select

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
            # 1. MANUEL NORMALİZASYON (R DESeq2 STİLİ)
            log_norm, sf = r_style_normalization(raw_counts)
            
            # Size Factors Kontrol (Opsiyonel Bilgi)
            with st.expander(f"{name} - Size Factors (Genişlet)"):
                st.dataframe(sf.to_frame(name="SizeFactor").T)

            # --- PCA BÖLÜMÜ ---
            st.subheader(f"PCA Analizi - {name}")
            
            c1, c2, c3, c4 = st.columns(4)
            use_custom = c1.checkbox(f"Gen Listesi Kullan", key=f"uc_{name}")
            inv_x = c2.checkbox("X Ters Çevir", value=False, key=f"ix_{name}")
            inv_y = c3.checkbox("Y Ters Çevir", value=False, key=f"iy_{name}")
            
            if use_custom and f_genes:
                f_genes.seek(0)
                targets = [l.decode("utf-8").strip() for l in f_genes]
                valid = [t for t in targets if t in log_norm.index]
                if not valid: st.error("Genler bulunamadı!"); st.stop()
                
                pca_input = log_norm.loc[valid].T
                pca = PCA(n_components=2)
                pca_res = pca.fit_transform(pca_input)
                percentVar = pca.explained_variance_ratio_ * 100
                title_suffix = f"(User List: {len(valid)})"
            else:
                pca_res, percentVar, _ = calculate_pca_r_style(log_norm, ntop=500)
                title_suffix = "(Top 500 Genes)"

            # Yön Düzeltme
            if inv_x: pca_res[:,0] *= -1
            if inv_y: pca_res[:,1] *= -1
            
            plot_df = pd.DataFrame(pca_res, columns=["PC1", "PC2"], index=log_norm.columns)
            plot_df['group'] = meta.loc[plot_df.index, d_col]
            
            # GRAFİK (R stiline yakınlaştırma)
            fig, ax = plt.subplots(figsize=(7, 7)) 
            sns.scatterplot(data=plot_df, x="PC1", y="PC2", hue="group", style="group",
                            s=200, alpha=0.9, ax=ax, edgecolor="black", linewidth=0.8, palette="Set1")
            
            ax.set_xlabel(f"PC1: {int(round(percentVar[0]))}% variance", fontsize=12)
            ax.set_ylabel(f"PC2: {int(round(percentVar[1]))}% variance", fontsize=12)
            ax.set_title(f"PCA Plot {title_suffix} - {name}", fontsize=14)
            ax.grid(True, linestyle=':', alpha=0.6)
            ax.legend(bbox_to_anchor=(1.02, 1), loc='upper left', frameon=False)
            
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
            
            if use_custom and f_genes:
                hm_genes = valid
                hm_title = "Özel Gen Listesi"
            else:
                rv = log_norm.var(axis=1, ddof=1)
                hm_genes = rv.sort_values(ascending=False).head(50).index
                hm_title = "Top 50 Değişken Gen"
            
            mat = log_norm.loc[hm_genes]
            
            # Z-Score Hesapla (Satır bazlı)
            mat_z = mat.apply(lambda x: (x - x.mean()) / x.std(), axis=1)
            
            # Seaborn Clustermap (R pheatmap 'complete' metoduna benzetme)
            # R varsayılanı genellikle clustering_method="complete", distance="euclidean"
            fig_hm = sns.clustermap(mat_z, 
                                   method='complete', # R varsayılanına daha yakın
                                   metric='euclidean',
                                   cmap="RdBu_r", # RColorBrewer benzeri
                                   center=0, 
                                   col_cluster=False, 
                                   figsize=(8, 10),
                                   cbar_kws={'label': 'Z-Score'})
            
            fig_hm.ax_heatmap.set_title(hm_title)
            
            col_hm_g, col_hm_d = st.columns([3, 1])
            with col_hm_g:
                st.pyplot(fig_hm)
            with col_hm_d:
                st.markdown("### İndir")
                st.download_button("Heatmap PNG", save_plot_hq(fig_hm.fig, "png"), f"Heatmap_{name}.png", "image/png")
            plt.close(fig_hm.fig)
