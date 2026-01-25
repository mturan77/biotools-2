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
st.set_page_config(page_title="RNA-Seq Final (R Match)", layout="wide")
st.title("🧬 RNA-Seq Analiz Hattı (R ile Tam Uyumlu)")

# --- OTURUM YÖNETİMİ ---
if 'hisat_dds' not in st.session_state: st.session_state.hisat_dds = None
if 'salmon_dds' not in st.session_state: st.session_state.salmon_dds = None
if 'processed' not in st.session_state: st.session_state.processed = False
if 'design_col' not in st.session_state: st.session_state.design_col = None

# --- YARDIMCI FONKSİYONLAR ---
def save_plot_to_memory(fig, format="png"):
    buf = io.BytesIO()
    fig.savefig(buf, format=format, bbox_inches="tight", dpi=300)
    buf.seek(0)
    return buf

def download_buttons_for_plot(fig, filename_prefix):
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1: st.download_button("📷 PNG", save_plot_to_memory(fig, "png"), f"{filename_prefix}.png", "image/png", use_container_width=True)
    with col2: st.download_button("✒️ SVG", save_plot_to_memory(fig, "svg"), f"{filename_prefix}.svg", "image/svg+xml", use_container_width=True)
    with col3: st.download_button("📄 PDF", save_plot_to_memory(fig, "pdf"), f"{filename_prefix}.pdf", "application/pdf", use_container_width=True)

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
    # 1. Kesişim
    common = list(set(counts_df.columns) & set(samples_df.index))
    if not common: return None, "Samples ve Counts arasında ortak örnek yok!"
    
    counts_df = counts_df[common]
    samples_df = samples_df.loc[common]
    
    # 2. Transpose
    counts_T = counts_df.T 
    
    # 3. Filtreleme
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
        
        # DESeq2 Analizi
        inference.deseq2()
        
        # --- ÖNEMLİ DEĞİŞİKLİK: VST HESAPLAMA ---
        # R'daki vst() fonksiyonunun karşılığıdır. 
        # Logaritma yerine bunu kullanırsak varyanslar R ile eşleşir.
        try:
            inference.vst(blind=False) # R scriptinizdeki blind=FALSE ayarı
        except:
            # Eğer VST başarısız olursa (çok az örnek varsa) log1p'ye düşer ama uyarı veririz
            st.warning("VST hesaplanamadı, Log dönüşümü kullanılıyor (Sonuçlar R'dan biraz sapabilir).")
        
        return inference, None
    except Exception as e:
        return None, str(e)

def run_contrast_analysis(dds, g1, g2, design_col):
    stat_res = DeseqStats(dds, contrast=[design_col, g1, g2], quiet=True)
    stat_res.summary()
    return stat_res.results_df

def get_norm_counts(dds):
    # R İLE EŞLEŞMEK İÇİN VST ÖNCELİKLİ
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
    file_samples = st.file_uploader("Samples CSV (Metadata)", type=["csv"], key="samples")
    file_genes = st.file_uploader("Gen Listesi TXT (Opsiyonel)", type=["txt"], key="genes")
    
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
            
            with st.status("Analiz Yapılıyor... VST Normalizasyonu biraz zaman alabilir.", expanded=True) as status:
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
                t1, t2, t3 = st.tabs(["📊 PCA (Tam Kontrol)", "🌋 Volcano", "🔥 Heatmap"])
                
                # --- 1. PCA (R MANTIĞI + YÖN AYARI) ---
                with t1:
                    col_ctrl1, col_ctrl2 = st.columns(2)
                    inv_x = col_ctrl1.checkbox(f"X Eksenini Ters Çevir (Ayna) - {method_name}", value=False)
                    inv_y = col_ctrl2.checkbox(f"Y Eksenini Ters Çevir (Ayna) - {method_name}", value=False)
                    
                    # 1. Varyansı Hesapla
                    variances = norm_counts.var(axis=0)
                    # 2. En yüksek varyansa sahip 500 geni seç
                    top_500_genes = variances.sort_values(ascending=False).head(500).index
                    pca_input = norm_counts[top_500_genes]
                    
                    # 3. PCA Uygula
                    pca = PCA(n_components=2)
                    pca_res = pca.fit_transform(pca_input)
                    var_exp = pca.explained_variance_ratio_ * 100
                    
                    # 4. Yön Çevirme (Manuel Ayar)
                    if inv_x: pca_res[:, 0] = pca_res[:, 0] * -1
                    if inv_y: pca_res[:, 1] = pca_res[:, 1] * -1
                    
                    pca_df = pd.DataFrame(pca_res, columns=["PC1", "PC2"], index=norm_counts.index)
                    pca_df['condition'] = metadata[design_col]
                    
                    # 5. Çizim
                    fig_pca, ax = plt.subplots(figsize=(8, 6))
                    sns.scatterplot(data=pca_df, x="PC1", y="PC2", hue="condition", s=150, ax=ax, alpha=0.9)
                    
                    ax.set_xlabel(f"PC1: {int(var_exp[0])}% variance")
                    ax.set_ylabel(f"PC2: {int(var_exp[1])}% variance")
                    ax.set_title(f"PCA Plot (Top 500 VST Genes) - {method_name}")
                    # Izgara çizgileri ekleyelim R'a benzesin
                    ax.grid(True, linestyle='--', alpha=0.6) 
                    
                    st.pyplot(fig_pca)
                    st.info("💡 Not: Eğer noktaların yerleri R'daki ile ters ise (Sağ/Sol veya Yukarı/Aşağı), üstteki kutucukları işaretleyerek düzeltebilirsiniz. Matematiksel sonuç değişmez.")
                    download_buttons_for_plot(fig_pca, f"PCA_{method_name}")
                    plt.close(fig_pca)

                # --- 2. VOLCANO ---
                with t2:
                    c1, c2 = st.columns(2)
                    grps = metadata[design_col].unique()
                    
                    def_idx_ref = 0
                    if ref_group in grps: def_idx_ref = list(grps).index(ref_group)
                    
                    test_opts = [g for g in grps if g != ref_group]
                    g_test = c1.selectbox(f"Test Grubu ({method_name})", test_opts, key=f"t_{method_name}")
                    g_ref = c2.text_input(f"Referans Grup", value=ref_group, disabled=True, key=f"r_{method_name}")
                    
                    if st.button(f"Karşılaştır: {g_test} vs {g_ref}", key=f"b
