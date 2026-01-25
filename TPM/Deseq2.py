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
st.set_page_config(page_title="RNA-Seq Full Analiz", layout="wide")
st.title("🧬 RNA-Seq Analiz Hattı: HISAT & SALMON (Hatasız Versiyon)")

# --- 1. SIDEBAR: DOSYA YÜKLEME ---
with st.sidebar:
    st.header("1. Veri Dosyaları")
    st.info("R kodunuzdaki mantıkla birebir çalışır. HISAT ve SALMON dosyalarını yükleyin.")
    
    file_hisat = st.file_uploader("HISAT CSV Yükle", type=["csv"], key="hisat")
    file_salmon = st.file_uploader("SALMON CSV Yükle", type=["csv"], key="salmon")
    
    st.markdown("---")
    file_samples = st.file_uploader("Samples.csv (Metadata)", type=["csv"], key="samples")
    file_genes = st.file_uploader("Gen Listesi.txt (Opsiyonel)", type=["txt"], key="genes")
    
    st.markdown("---")
    st.header("2. Parametreler")
    padj_cut = st.number_input("P-adj Cutoff", 0.0, 1.0, 0.05, 0.01)
    lfc_cut = st.number_input("Log2FoldChange Cutoff", 0.0, 10.0, 1.0, 0.5)
    min_count = st.number_input("Min Count (Row Sums)", 0, 100, 10)
    
    btn_run = st.button("Analizleri Başlat", type="primary", use_container_width=True)

# --- YARDIMCI FONKSİYONLAR ---

def save_plot_to_memory(fig, format="png"):
    """ Grafikleri indirmek için belleğe kaydeder """
    buf = io.BytesIO()
    fig.savefig(buf, format=format, bbox_inches="tight", dpi=300)
    buf.seek(0)
    return buf

def download_buttons_for_plot(fig, filename_prefix):
    """ Her grafik için PNG, SVG, PDF butonları """
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        st.download_button("📷 PNG", save_plot_to_memory(fig, "png"), f"{filename_prefix}.png", "image/png", use_container_width=True)
    with col2:
        st.download_button("✒️ SVG", save_plot_to_memory(fig, "svg"), f"{filename_prefix}.svg", "image/svg+xml", use_container_width=True)
    with col3:
        st.download_button("📄 PDF", save_plot_to_memory(fig, "pdf"), f"{filename_prefix}.pdf", "application/pdf", use_container_width=True)

def add_interpretation(df, lfc_limit, padj_limit):
    """ R kodundaki 'add_interpretation' fonksiyonunun aynısı """
    conditions = [
        (df['log2FoldChange'] > lfc_limit) & (df['padj'] < padj_limit),
        (df['log2FoldChange'] < -lfc_limit) & (df['padj'] < padj_limit),
        (df['log2FoldChange'] > 0) & (df['log2FoldChange'] <= lfc_limit) & (df['padj'] < padj_limit),
        (df['log2FoldChange'] < 0) & (df['log2FoldChange'] >= -lfc_limit) & (df['padj'] < padj_limit)
    ]
    choices = ["GUCLU ARTIS (UP)", "GUCLU AZALIS (DOWN)", "Hafif Artis", "Hafif Azalis"]
    df['Yorum'] = np.select(conditions, choices, default="Degisim Yok / Anlamsiz")
    return df

@st.cache_resource
def run_deseq_fit(counts_df, samples_df, design_col, min_cnt):
    """ DESeq2 Modelini Kurar """
    # Kesişim Al
    common = list(set(counts_df.columns) & set(samples_df.index))
    if not common: return None, "Samples ve Counts arasında ortak örnek yok!"
    
    counts_df = counts_df[common]
    samples_df = samples_df.loc[common]
    
    # Transpose 
    counts_T = counts_df.T 
    
    # Filtreleme
    genes_keep = counts_T.columns[counts_T.sum(axis=0) >= min_cnt]
    counts_T = counts_T[genes_keep]
    
    # Modeli Kur
    inference = DeseqDataSet(counts=counts_T, metadata=samples_df, design_factors=design_col, quiet=True)
    inference.deseq2()
    return inference, None

def run_contrast_analysis(dds, g1, g2, design_col):
    """ İstatistiksel Test (Contrast) """
    stat_res = DeseqStats(dds, contrast=[design_col, g1, g2], quiet=True)
    stat_res.summary()
    return stat_res.results_df

def render_analysis_section(dds, samples_df, design_col, method_name, gene_list_file):
    """ Tek bir yöntemin tüm çıktılarını basar """
    
    st.success(f"✅ {method_name} Analizi Hazır")
    
    # Log Norm Düzeltmesi (Versiyon Hatasına Karşı)
    if 'log1norm' in dds.layers:
        norm_counts = dds.layers['log1norm']
    elif 'normed_counts' in dds.layers:
        norm_counts = np.log1p(dds.layers['normed_counts'])
    else:
        norm_counts = np.log1p(dds.X)
        
    if not isinstance(norm_counts, pd.DataFrame):
        norm_counts = pd.DataFrame(norm_counts, index=dds.obs_names, columns=dds.var_names)
    
    t1, t2, t3 = st.tabs(["📊 1. PCA", "🌋 2. Volcano & CSV", "🔥 3. Heatmaps"])
    
    # --- 1. PCA ---
    with t1:
        st.subheader(f"PCA Grafiği ({method_name})")
        pca = PCA(n_components=2)
        pca_res = pca.fit_transform(norm_counts)
        var_exp = pca.explained_variance_ratio_ * 100
        
        pca_df = pd.DataFrame(pca_res, columns=["PC1", "PC2"], index=norm_counts.index)
        pca_df['condition'] = samples_df[design_col]
        
        fig_pca, ax = plt.subplots(figsize=(8, 6))
        sns.scatterplot(data=pca_df, x="PC1", y="PC2", hue="condition", s=150, ax=ax, alpha=0.8)
        ax.set_title(f"PCA - {method_name}")
        ax.set_xlabel(f"PC1: {int(var_exp[0])}%")
        ax.set_ylabel(f"PC2: {int(var_exp[1])}%")
        st.pyplot(fig_pca)
        
        st.caption("Grafiği İndir:")
        download_buttons_for_plot(fig_pca, f"PCA_{method_name}")

    # --- 2. VOLCANO & CSV ---
    with t2:
        st.subheader("Karşılaştırma ve Sonuç Dosyaları")
        gruplar = samples_df[design_col].unique()
        c1, c2 = st.columns(2)
        g1 = c1.selectbox("Grup 1", gruplar, key=f"{method_name}_g1")
        g2 = c2.selectbox("Grup 2", [x for x in gruplar if x != g1], key=f"{method_name}_g2")
        
        if st.button(f"Karşılaştır: {g1} vs {g2}", key=f"{method_name}_btn"):
            res_df = run_contrast_analysis(dds, g1, g2, design_col)
            res_df = add_interpretation(res_df, lfc_cut, padj_cut)
            
            # Volcano Plot
            colors_map = {"GUCLU ARTIS (UP)": "blue", "GUCLU AZALIS (DOWN)": "red", 
                          "Hafif Artis": "lightblue", "Hafif Azalis": "salmon", 
                          "Degisim Yok / Anlamsiz": "grey"}
            
            fig_vol, ax = plt.subplots(figsize=(8, 6))
            sns.scatterplot(data=res_df, x='log2FoldChange', y=-np.log10(res_df['padj']),
                            hue='Yorum', palette=colors_map, alpha=0.7, ax=ax)
            ax.axvline(lfc_cut, ls="--", c="black"); ax.axvline(-lfc_cut, ls="--", c="black")
            ax.axhline(-np.log10(padj_cut), ls="--", c="black")
            ax.set_title(f"Volcano: {g1} vs {g2}")
            st.pyplot(fig_vol)
            
            st.caption("Volcano Grafiğini İndir:")
            download_buttons_for_plot(fig_vol, f"Volcano_{method_name}_{g1}_{g2}")
            
            st.divider()
            
            # CSV İndirme
            st.markdown("### 📥 Sonuç Tablolarını İndir")
            col_d1, col_d2 = st.columns(2)
            
            csv_full = res_df.to_csv().encode('utf-8')
            col_d1.download_button(
                label=f"📄 TÜM LİSTE İndir ({g1}vs{g2})",
                data=csv_full,
                file_name=f"Sonuc_TUMU_{method_name}_{g1}_{g2}.csv",
                mime="text/csv"
            )
            
            if gene_list_file:
                gene_list_file.seek(0)
                target_list = [line.decode("utf-8").strip() for line in gene_list_file]
                subset_df = res_df[res_df.index.isin(target_list)]
                
                if not subset_df.empty:
                    csv_sub = subset_df.to_csv().encode('utf-8')
                    col_d2.download_button(
                        label=f"⭐ ÖZEL LİSTE İndir",
                        data=csv_sub,
                        file_name=f"Sonuc_OZEL_LISTE_{method_name}_{g1}_{g2}.csv",
                        mime="text/csv"
                    )
                else:
                    col_d2.warning("Özel listedeki genler sonuçlarda bulunamadı.")
            else:
                col_d2.info("Özel liste yüklemediğiniz için bu buton pasif.")

    # --- 3. HEATMAPS ---
    with t3:
        st.subheader("Isı Haritaları (Heatmaps)")
        target_genes = []
        if gene_list_file:
            gene_list_file.seek(0)
            target_genes = [line.decode("utf-8").strip() for line in gene_list_file]
        
        if not target_genes:
            target_genes = norm_counts.var(axis=0).sort_values(ascending=False).head(50).index.tolist()
            st.info("ℹ️ Top 50 Değişken Gen (Varyans) Gösteriliyor.")

        mat_subset = norm_counts[target_genes].T 
        
        if not mat_subset.empty:
            # A) BİREYSEL HEATMAP (Clustermap Z-Score destekler)
            st.markdown("#### A) Bireysel Heatmap")
            fig_ind = sns.clustermap(mat_subset, z_score=0, cmap="vlag", col_cluster=False, figsize=(6, 8))
            st.pyplot(fig_ind)
            st.caption("Bireysel Heatmap İndir:")
            download_buttons_for_plot(fig_ind, f"Heatmap_Bireysel_{method_name}")
            
            st.divider()
            
            # B) ORTALAMA HEATMAP (Heatmap Z-Score desteklemez, manuel yapıyoruz)
            st.markdown("#### B) Ortalama Heatmap (Gruplar)")
            norm_counts_subset = norm_counts[target_genes]
            norm_counts_subset['condition'] = samples_df[design_col]
            grouped_mean = norm_counts_subset.groupby('condition').mean().T 
            
            # Verisini İndir (Normal değerler)
            csv_heatmap = grouped_mean.to_csv().encode('utf-8')
            st.download_button("📊 Ortalama Verisini İndir (CSV)", csv_heatmap, f"Heatmap_ORTALAMA_VERISI_{method_name}.csv", "text/csv")
            
            # Grafiği Çiz (Önce Z-Score hesabı yapıyoruz: Row scaling)
            # R mantığı: (Value - Mean) / Std
            grouped_mean_scaled = grouped_mean.apply(lambda x: (x - x.mean()) / x.std(), axis=1).fillna(0)
            
            fig_avg, ax = plt.subplots(figsize=(6, 6))
            # DÜZELTME: z_score parametresini kaldırdık, scale edilmiş veriyi verdik
            sns.heatmap(grouped_mean_scaled, cmap="vlag", center=0, ax=ax)
            st.pyplot(fig_avg)
            st.caption("Ortalama Heatmap İndir:")
            download_buttons_for_plot(fig_avg, f"Heatmap_Ortalama_{method_name}")

# --- ANA AKIŞ ---
if btn_run:
    if not file_samples:
        st.error("❌ Samples (Metadata) dosyası eksik!")
    elif not (file_hisat or file_salmon):
        st.error("❌ En az bir Counts dosyası yüklemelisiniz.")
    else:
        try:
            samples_data = pd.read_csv(file_samples, index_col=0)
            design_col = "condition"
            if "condition" not in samples_data.columns: design_col = samples_data.columns[0]
            samples_data[design_col] = samples_data[design_col].astype(str)
        except Exception as e:
            st.error(f"Samples okuma hatası: {e}")
            st.stop()

        tabs_titles = []
        if file_hisat: tabs_titles.append("📂 SONUÇLAR: HISAT2")
        if file_salmon: tabs_titles.append("📂 SONUÇLAR: SALMON")
        
        tabs = st.tabs(tabs_titles)
        current_idx = 0
        
        if file_hisat:
            with tabs[current_idx]:
                counts = pd.read_csv(file_hisat, index_col=0)
                with st.spinner("HISAT2 Hesaplanıyor..."):
                    dds, err = run_deseq_fit(counts, samples_data, design_col, min_count)
                    if err: st.error(err)
                    else: render_analysis_section(dds, samples_data, design_col, "HISAT2", file_genes)
            current_idx += 1
            
        if file_salmon:
            with tabs[current_idx]:
                counts = pd.read_csv(file_salmon, index_col=0)
                with st.spinner("SALMON Hesaplanıyor..."):
                    dds, err = run_deseq_fit(counts, samples_data, design_col, min_count)
                    if err: st.error(err)
                    else: render_analysis_section(dds, samples_data, design_col, "SALMON", file_genes)
