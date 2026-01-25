import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pydeseq2.dds import DeseqDataSet
from pydeseq2.ds import DeseqStats
from sklearn.decomposition import PCA
import io

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="RNA-Seq Final", layout="wide")
st.title("🧬 RNA-Seq Analiz Hattı (R-Style Variance)")

# --- SESSION STATE ---
if 'hisat_dds' not in st.session_state: st.session_state.hisat_dds = None
if 'salmon_dds' not in st.session_state: st.session_state.salmon_dds = None
if 'processed' not in st.session_state: st.session_state.processed = False
if 'design_col' not in st.session_state: st.session_state.design_col = None

# --- HQ İNDİRME ---
def save_plot_high_quality(fig, format="png"):
    buf = io.BytesIO()
    fig.savefig(buf, format=format, bbox_inches="tight", dpi=300)
    buf.seek(0)
    return buf

def download_buttons_for_plot(fig, filename_prefix):
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1: st.download_button("📷 PNG (HQ)", save_plot_high_quality(fig, "png"), f"{filename_prefix}.png", "image/png")
    with col2: st.download_button("✒️ SVG", save_plot_high_quality(fig, "svg"), f"{filename_prefix}.svg", "image/svg+xml")
    with col3: st.download_button("📄 PDF", save_plot_high_quality(fig, "pdf"), f"{filename_prefix}.pdf", "application/pdf")

# --- ANALİZ MOTORU ---
def run_deseq_fit(counts_df, samples_df, design_col, min_cnt):
    # Ortak örnekler
    common = list(set(counts_df.columns) & set(samples_df.index))
    counts_df = counts_df[common]
    samples_df = samples_df.loc[common]
    
    # Filtreleme (Genes rows)
    counts_df = counts_df[counts_df.sum(axis=1) >= min_cnt]
    
    # Transpose (PyDESeq2 için)
    counts_T = counts_df.T 
    
    try:
        inference = DeseqDataSet(
            counts=counts_T, 
            metadata=samples_df, 
            design_factors=design_col,
            quiet=True
        )
        inference.deseq2()
        
        # --- ÖNEMLİ DEĞİŞİKLİK ---
        # VST hatası almamak ve R ile benzerlik için 'normed_counts' üzerinden 
        # log2(x + 1) dönüşümü yapıyoruz. Bu, blind=TRUE VST'ye çok yakındır.
        if 'normed_counts' in inference.layers:
            inference.layers['log1p'] = np.log2(inference.layers['normed_counts'] + 1)
        else:
            inference.layers['log1p'] = np.log2(inference.X + 1)
            
        return inference, None
    except Exception as e:
        return None, str(e)

def get_norm_data(dds):
    # Log dönüşümlü veriyi çek
    if hasattr(dds, 'layers') and 'log1p' in dds.layers:
        data = dds.layers['log1p']
    else:
        data = np.log2(dds.X + 1)
    
    return pd.DataFrame(data, index=dds.obs_names, columns=dds.var_names)

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Veri Yükleme")
    file_hisat = st.file_uploader("HISAT CSV", type=["csv"], key="hisat")
    file_salmon = st.file_uploader("SALMON CSV", type=["csv"], key="salmon")
    st.markdown("---")
    file_samples = st.file_uploader("Samples CSV", type=["csv"], key="samples")
    file_genes = st.file_uploader("Gen Listesi", type=["txt"], key="genes")
    
    st.markdown("---")
    st.subheader("2. Parametreler")
    ref_group = st.text_input("Referans Grup", value="Control")
    lfc_cut = st.number_input("Log2FC Cutoff", value=1.0)
    padj_cut = st.number_input("Padj Cutoff", value=0.05)
    
    if st.button("Analizi Başlat", type="primary"):
        st.session_state.processed = False
        st.session_state.run_trigger = True
    else:
        st.session_state.run_trigger = False

# --- ANA AKIŞ ---
if st.session_state.run_trigger:
    if not file_samples:
        st.error("Samples dosyası eksik!")
        st.stop()
    
    samples_data = pd.read_csv(file_samples, index_col=0)
    design_col = "condition"
    if "condition" not in samples_data.columns: design_col = samples_data.columns[0]
    samples_data[design_col] = samples_data[design_col].astype(str)
    st.session_state.design_col = design_col
    
    with st.status("Analiz yapılıyor...", expanded=True):
        if file_hisat:
            c = pd.read_csv(file_hisat, index_col=0)
            dds, err = run_deseq_fit(c, samples_data, design_col, 10)
            st.session_state.hisat_dds = dds
        if file_salmon:
            c = pd.read_csv(file_salmon, index_col=0)
            dds, err = run_deseq_fit(c, samples_data, design_col, 10)
            st.session_state.salmon_dds = dds
        st.session_state.processed = True

if st.session_state.processed:
    tabs = st.tabs(["📊 HISAT2 Sonuçları", "📊 SALMON Sonuçları"])
    datasets = []
    if st.session_state.hisat_dds: datasets.append(("HISAT2", st.session_state.hisat_dds, tabs[0]))
    if st.session_state.salmon_dds: datasets.append(("SALMON", st.session_state.salmon_dds, tabs[1]))
    
    for name, dds, tab in datasets:
        with tab:
            norm_df = get_norm_data(dds) # Samples x Genes
            meta = dds.obs
            design_col = st.session_state.design_col
            
            # --- 1. PCA (R MANTIĞI) ---
            st.subheader(f"PCA Analizi - {name}")
            
            c1, c2, c3 = st.columns(3)
            use_custom = c1.checkbox(f"Gen Listesi Kullan ({name})", value=False)
            inv_x = c2.checkbox("X Ters Çevir", value=False, key=f"x_{name}")
            inv_y = c3.checkbox("Y Ters Çevir", value=False, key=f"y_{name}")

            # Gen Seçimi
            if use_custom and file_genes:
                file_genes.seek(0)
                targets = [l.decode("utf-8").strip() for l in file_genes]
                valid_targets = [t for t in targets if t in norm_df.columns]
                pca_input = norm_df[valid_targets]
                title_pca = f"PCA (User List: {len(valid_targets)} genes)"
            else:
                # R GİBİ VARYANS HESABI (ddof=1 çok önemli!)
                vars = norm_df.var(axis=0, ddof=1)
                top500 = vars.sort_values(ascending=False).head(500).index
                pca_input = norm_df[top500]
                title_pca = "PCA (Top 500 Variable Genes)"

            # PCA Hesaplama
            pca = PCA(n_components=2)
            pca_res = pca.fit_transform(pca_input)
            var_exp = pca.explained_variance_ratio_ * 100
            
            if inv_x: pca_res[:,0] *= -1
            if inv_y: pca_res[:,1] *= -1
            
            pca_df = pd.DataFrame(pca_res, columns=["PC1", "PC2"], index=norm_df.index)
            pca_df['condition'] = meta[design_col]
            
            # Çizim
            fig, ax = plt.subplots(figsize=(6, 5))
            sns.scatterplot(data=pca_df, x="PC1", y="PC2", hue="condition", s=120, alpha=0.9, ax=ax)
            ax.set_xlabel(f"PC1: {int(var_exp[0])}% variance")
            ax.set_ylabel(f"PC2: {int(var_exp[1])}% variance")
            ax.set_title(title_pca)
            ax.grid(True, ls="--", alpha=0.4)
            ax.legend(bbox_to_anchor=(1.02, 1), loc='upper left')
            
            c_g, c_d = st.columns([3, 1])
            c_g.pyplot(fig, use_container_width=False)
            c_d.markdown("**İndir:**")
            download_buttons_for_plot(fig, f"PCA_{name}")
            plt.close(fig)

            st.divider()
            
            # --- 2. HEATMAP ---
            st.subheader(f"Heatmap - {name}")
            
            # Heatmap Genleri
            if file_genes:
                file_genes.seek(0)
                targets = [l.decode("utf-8").strip() for l in file_genes]
                targets = [t for t in targets if t in norm_df.columns]
                heatmap_input = norm_df[targets].T
                title_hm = "Özel Liste"
            else:
                vars = norm_df.var(axis=0, ddof=1)
                top50 = vars.sort_values(ascending=False).head(50).index
                heatmap_input = norm_df[top50].T
                title_hm = "Top 50 Varyans"
            
            # Bireysel Heatmap
            fig_hm = sns.clustermap(heatmap_input, z_score=0, cmap="vlag", col_cluster=False, figsize=(6, 8))
            c_h1, c_h2 = st.columns([3, 1])
            c_h1.pyplot(fig_hm)
            c_h2.markdown("**İndir:**")
            download_buttons_for_plot(fig_hm, f"Heatmap_{name}")
            plt.close(fig_hm.fig)
