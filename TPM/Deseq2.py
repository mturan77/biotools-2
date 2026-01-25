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
st.title("🧬 RNA-Seq Analiz Hattı (Final)")

# --- OTURUM YÖNETİMİ ---
if 'hisat_dds' not in st.session_state: st.session_state.hisat_dds = None
if 'salmon_dds' not in st.session_state: st.session_state.salmon_dds = None
if 'processed' not in st.session_state: st.session_state.processed = False
if 'design_col' not in st.session_state: st.session_state.design_col = None

# --- HQ İNDİRME FONKSİYONLARI ---
def save_plot_high_quality(fig, format="png"):
    buf = io.BytesIO()
    # dpi=300: Baskı kalitesi (Yüksek Çözünürlük)
    fig.savefig(buf, format=format, bbox_inches="tight", dpi=300)
    buf.seek(0)
    return buf

def download_buttons_for_plot(fig, filename_prefix):
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1: 
        st.download_button("📷 PNG (HQ)", save_plot_high_quality(fig, "png"), f"{filename_prefix}.png", "image/png")
    with col2: 
        st.download_button("✒️ SVG (Vektör)", save_plot_high_quality(fig, "svg"), f"{filename_prefix}.svg", "image/svg+xml")
    with col3: 
        st.download_button("📄 PDF (Rapor)", save_plot_high_quality(fig, "pdf"), f"{filename_prefix}.pdf", "application/pdf")

def add_interpretation(df, lfc_limit, padj_limit):
    conditions = [
        (df['log2FoldChange'] > lfc_limit) & (df['padj'] < padj_limit),
        (df['log2FoldChange'] < -lfc_limit) & (df['padj'] < padj_limit),
        (df['log2FoldChange'] > 0) & (df['log2FoldChange'] <= lfc_limit) & (df['padj'] < padj_limit),
        (df['log2FoldChange'] < 0) & (df['log2FoldChange'] >= -lfc_limit) & (df['padj'] < padj_limit)
    ]
    choices = ["GUCLU ARTIS (UP)", "GUCLU AZALIS (DOWN)", "Hafif Artis", "Hafif Azalis"]
    df['Yorum'] = np.select(conditions, choices, default="Degisim Yok / Anlamsiz")
    return df

def run_deseq_fit(counts_df, samples_df, design_col, ref_level, min_cnt):
    # Kesişim
    common = list(set(counts_df.columns) & set(samples_df.index))
    if not common: return None, "Samples ve Counts arasında ortak örnek yok!"
    
    counts_df = counts_df[common]
    samples_df = samples_df.loc[common]
    
    # Transpose
    counts_T = counts_df.T 
    
    # Filtreleme
    genes_keep = counts_T.columns[counts_T.sum(axis=0) >= min_cnt]
    counts_T = counts_T[genes_keep]
    
    try:
        inference = DeseqDataSet(
            counts=counts_T, 
            metadata=samples_df, 
            design_factors=design_col,
            ref_level=[design_col, ref_level],
            quiet=True
        )
        inference.deseq2()
        
        # --- DÜZELTME BURADA ---
        # 'blind' parametresi kaldırıldı. PyDESeq2 artık bunu otomatik algılar.
        try:
            inference.vst()  # Argümansız çalıştırıyoruz
        except Exception as vst_err:
            st.warning(f"VST uyarısı: {vst_err}. Log dönüşümü kullanılıyor.")
        
        return inference, None
    except Exception as e:
        return None, str(e)

def run_contrast_analysis(dds, g1, g2, design_col):
    stat_res = DeseqStats(dds, contrast=[design_col, g1, g2], quiet=True)
    stat_res.summary()
    return stat_res.results_df

def get_norm_counts(dds):
    # VST öncelikli
    if hasattr(dds, 'layers') and 'vst_counts' in dds.layers:
        data = dds.layers['vst_counts']
    elif hasattr(dds, 'layers') and 'log1norm' in dds.layers:
        data = dds.layers['log1norm']
    elif hasattr(dds, 'layers') and 'normed_counts' in dds.layers:
        data = np.log1p(dds.layers['normed_counts'])
    else:
        data = np.log1p(dds.X)
        
    if not isinstance(data, pd.DataFrame):
        data = pd.DataFrame(data, index=dds.obs_names, columns=dds.var_names)
    return data

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Veri ve Ayarlar")
    file_hisat = st.file_uploader("HISAT CSV", type=["csv"], key="hisat")
    file_salmon = st.file_uploader("SALMON CSV", type=["csv"], key="salmon")
    st.markdown("---")
    file_samples = st.file_uploader("Samples CSV", type=["csv"], key="samples")
    file_genes = st.file_uploader("Gen Listesi", type=["txt"], key="genes")
    
    st.markdown("---")
    st.subheader("2. Kritik Ayarlar")
    ref_group = st.text_input("Referans Grup Adı", value="Control", help="Örn: Control")
    padj_cut = st.number_input("P-adj Cutoff", 0.0, 1.0, 0.05, 0.01)
    lfc_cut = st.number_input("Log2FC Cutoff", 0.0, 10.0, 1.0, 0.5)
    min_count = st.number_input("Min Count", 0, 100, 10)
    
    if st.button("Analizi Başlat", type="primary"):
        st.session_state.processed = False
        st.session_state.run_trigger = True
    else:
        st.session_state.run_trigger = False

# --- ANA AKIŞ ---
if st.session_state.run_trigger:
    if not file_samples:
        st.error("Samples dosyası eksik!")
    elif not (file_hisat or file_salmon):
        st.error("En az bir count dosyası yükleyin.")
    else:
        try:
            samples_data = pd.read_csv(file_samples, index_col=0)
            design_col = "condition"
            if "condition" not in samples_data.columns: design_col = samples_data.columns[0]
            samples_data[design_col] = samples_data[design_col].astype(str)
            st.session_state.design_col = design_col
            
            unique_groups = samples_data[design_col].unique()
            if ref_group not in unique_groups:
                st.error(f"Referans grup ('{ref_group}') bulunamadı! Mevcut: {unique_groups}")
                st.stop()
            
            with st.status("Analiz Yapılıyor... (VST İşlemi)", expanded=True) as status:
                if file_hisat:
                    st.write("HISAT2 işleniyor...")
                    counts = pd.read_csv(file_hisat, index_col=0)
                    dds, err = run_deseq_fit(counts, samples_data, design_col, ref_group, min_count)
                    if err: st.error(err)
                    else: st.session_state.hisat_dds = dds
                
                if file_salmon:
                    st.write("SALMON işleniyor...")
                    counts = pd.read_csv(file_salmon, index_col=0)
                    dds, err = run_deseq_fit(counts, samples_data, design_col, ref_group, min_count)
                    if err: st.error(err)
                    else: st.session_state.salmon_dds = dds
                
                st.session_state.processed = True
                status.update(label="Analiz Tamamlandı!", state="complete", expanded=False)
        except Exception as e:
            st.error(f"Hata: {e}")

if st.session_state.processed:
    titles = []
    if st.session_state.hisat_dds: titles.append("📂 HISAT2 Sonuçları")
    if st.session_state.salmon_dds: titles.append("📂 SALMON Sonuçları")
    
    if titles:
        tabs = st.tabs(titles)
        datasets = []
        if st.session_state.hisat_dds: datasets.append(("HISAT2", st.session_state.hisat_dds))
        if st.session_state.salmon_dds: datasets.append(("SALMON", st.session_state.salmon_dds))
        
        for i, (method_name, dds) in enumerate(datasets):
            with tabs[i]:
                norm_counts = get_norm_counts(dds)
                design_col = st.session_state.design_col
                metadata = dds.obs
                
                st.success(f"✅ {method_name} Modeli Hazır.")
                t1, t2, t3 = st.tabs(["📊 PCA", "🌋 Volcano", "🔥 Heatmap"])
                
                # --- 1. PCA ---
                with t1:
                    col_ctrl1, col_ctrl2 = st.columns(2)
                    inv_x = col_ctrl1.checkbox(f"X'i Ters Çevir - {method_name}", value=False)
                    inv_y = col_ctrl2.checkbox(f"Y'yi Ters Çevir - {method_name}", value=False)
                    
                    # R Mantığı
                    variances = norm_counts.var(axis=0)
                    top_500_genes = variances.sort_values(ascending=False).head(500).index
                    pca_input = norm_counts[top_500_genes]
                    
                    pca = PCA(n_components=2)
                    pca_res = pca.fit_transform(pca_input)
                    var_exp = pca.explained_variance_ratio_ * 100
                    
                    if inv_x: pca_res[:, 0] = pca_res[:, 0] * -1
                    if inv_y: pca_res[:, 1] = pca_res[:, 1] * -1
                    
                    pca_df = pd.DataFrame(pca_res, columns=["PC1", "PC2"], index=norm_counts.index)
                    pca_df['condition'] = metadata[design_col]
                    
                    # Ekran için küçük boyut (Hız için)
                    fig_pca, ax = plt.subplots(figsize=(6, 5)) 
                    sns.scatterplot(data=pca_df, x="PC1", y="PC2", hue="condition", s=100, ax=ax, alpha=0.9)
                    
                    ax.set_xlabel(f"PC1: {int(var_exp[0])}% variance")
                    ax.set_ylabel(f"PC2: {int(var_exp[1])}% variance")
                    ax.set_title(f"PCA (Top 500 Genes) - {method_name}")
                    ax.grid(True, linestyle='--', alpha=0.5)
                    
                    col_plot, col_dl = st.columns([3, 1])
                    with col_plot:
                        st.pyplot(fig_pca, use_container_width=False)
                    with col_dl:
                        st.markdown("**İndir (HQ):**")
                        download_buttons_for_plot(fig_pca, f"PCA_{method_name}")
                    plt.close(fig_pca)

                # --- 2. VOLCANO ---
                with t2:
                    c1, c2 = st.columns(2)
                    grps = metadata[design_col].unique()
                    test_opts = [g for g in grps if g != ref_group]
                    g_test = c1.selectbox(f"Test Grubu ({method_name})", test_opts, key=f"t_{method_name}")
                    g_ref = c2.text_input(f"Referans", value=ref_group, disabled=True, key=f"r_{method_name}")
                    
                    btn_key = f"b_{method_name}"
                    if st.button(f"Karşılaştır: {g_test} vs {g_ref}", key=btn_key):
                        res_df = run_contrast_analysis(dds, g_test, g_ref, design_col)
                        res_df = add_interpretation(res_df, lfc_cut, padj_cut)
                        
                        colors = {"GUCLU ARTIS (UP)": "blue", "GUCLU AZALIS (DOWN)": "red", 
                                  "Hafif Artis": "lightblue", "Hafif Azalis": "salmon", 
                                  "Degisim Yok / Anlamsiz": "grey"}
                        
                        fig_vol, ax = plt.subplots(figsize=(6, 5))
                        sns.scatterplot(data=res_df, x='log2FoldChange', y=-np.log10(res_df['padj']), 
                                        hue='Yorum', palette=colors, alpha=0.7, ax=ax, legend=False)
                        ax.axvline(lfc_cut, ls="--", c="black"); ax.axvline(-lfc_cut, ls="--", c="black")
                        ax.axhline(-np.log10(padj_cut), ls="--", c="black")
                        ax.set_title(f"{g_test} vs {g_ref}")
                        ax.grid(True, linestyle='--', alpha=0.3)
                        
                        col_v_plot, col_v_dl = st.columns([3, 1])
                        with col_v_plot: st.pyplot(fig_vol, use_container_width=False)
                        with col_v_dl: 
                            st.markdown("**İndir (HQ):**")
                            download_buttons_for_plot(fig_vol, f"Volcano_{method_name}")
                        plt.close(fig_vol)
                        st.download_button(f"📥 CSV İndir", res_df.to_csv().encode('utf-8'), f"Res_{method_name}.csv", "text/csv")

                # --- 3. HEATMAP ---
                with t3:
                    targets = []
                    if file_genes:
                        file_genes.seek(0)
                        targets = [line.decode("utf-8").strip() for line in file_genes]
                    if not targets:
                        targets = norm_counts.var(axis=0).sort_values(ascending=False).head(50).index.tolist()
                        st.info("Top 50 değişken gen gösteriliyor.")
                    
                    mat = norm_counts[targets].T
                    if not mat.empty:
                        # Bireysel Heatmap
                        st.subheader("Bireysel Heatmap")
                        fig_ind = sns.clustermap(mat, z_score=0, cmap="vlag", col_cluster=False, figsize=(6, 7))
                        
                        col_h1, col_h2 = st.columns([3, 1])
                        with col_h1: st.pyplot(fig_ind)
                        with col_h2: 
                            st.markdown("**İndir (HQ):**")
                            download_buttons_for_plot(fig_ind, f"Heatmap_Ind_{method_name}")
                        plt.close(fig_ind.fig)
                        
                        st.divider()
                        
                        # Ortalama Heatmap
                        st.subheader("Ortalama Heatmap")
                        mat_sub = norm_counts[targets]
                        mat_sub['grp'] = metadata[design_col]
                        grp_mean = mat_sub.groupby('grp').mean().T
                        grp_mean_scaled = grp_mean.apply(lambda x: (x - x.mean()) / x.std(), axis=1).fillna(0)
                        
                        fig_avg, ax = plt.subplots(figsize=(6, 6))
                        sns.heatmap(grp_mean_scaled, cmap="vlag", center=0, ax=ax)
                        
                        col_ha1, col_ha2 = st.columns([3, 1])
                        with col_ha1: st.pyplot(fig_avg, use_container_width=False)
                        with col_ha2: 
                            st.markdown("**İndir (HQ):**")
                            download_buttons_for_plot(fig_avg, f"Heatmap_Avg_{method_name}")
                        plt.close(fig_avg)
