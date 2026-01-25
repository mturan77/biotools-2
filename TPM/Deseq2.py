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
st.title("🧬 RNA-Seq Analiz Hattı (Stabil Versiyon)")

# --- OTURUM YÖNETİMİ (Session State) ---
# Analiz sonuçlarını hafızada tutmak için gerekli
if 'hisat_dds' not in st.session_state:
    st.session_state.hisat_dds = None
if 'salmon_dds' not in st.session_state:
    st.session_state.salmon_dds = None
if 'processed' not in st.session_state:
    st.session_state.processed = False

# --- YARDIMCI FONKSİYONLAR ---

def save_plot_to_memory(fig, format="png"):
    buf = io.BytesIO()
    fig.savefig(buf, format=format, bbox_inches="tight", dpi=300)
    buf.seek(0)
    return buf

def download_buttons_for_plot(fig, filename_prefix):
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        st.download_button("📷 PNG", save_plot_to_memory(fig, "png"), f"{filename_prefix}.png", "image/png", use_container_width=True)
    with col2:
        st.download_button("✒️ SVG", save_plot_to_memory(fig, "svg"), f"{filename_prefix}.svg", "image/svg+xml", use_container_width=True)
    with col3:
        st.download_button("📄 PDF", save_plot_to_memory(fig, "pdf"), f"{filename_prefix}.pdf", "application/pdf", use_container_width=True)

def add_interpretation(df, lfc_limit, padj_limit):
    # R ile aynı mantık
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
    """ DESeq2 Modelini Kurar """
    # 1. Kesişim Al
    common = list(set(counts_df.columns) & set(samples_df.index))
    if not common: return None, "Samples ve Counts arasında ortak örnek yok!"
    
    counts_df = counts_df[common]
    samples_df = samples_df.loc[common]
    
    # 2. Transpose (PyDESeq2 Samples x Genes ister)
    counts_T = counts_df.T 
    
    # 3. Filtreleme
    genes_keep = counts_T.columns[counts_T.sum(axis=0) >= min_cnt]
    counts_T = counts_T[genes_keep]
    
    # 4. Modeli Kur (Reference Level Önemli!)
    try:
        inference = DeseqDataSet(
            counts=counts_T, 
            metadata=samples_df, 
            design_factors=design_col,
            ref_level=[design_col, ref_level], # R sonuçlarıyla eşleşmesi için kritik!
            quiet=True
        )
        inference.deseq2()
        return inference, None
    except Exception as e:
        return None, str(e)

def run_contrast_analysis(dds, g1, g2, design_col):
    # Contrast: Test Grubu (g1) vs Referans Grubu (g2)
    stat_res = DeseqStats(dds, contrast=[design_col, g1, g2], quiet=True)
    stat_res.summary()
    return stat_res.results_df

def get_norm_counts(dds):
    # Versiyon hatasını önlemek için güvenli normalizasyon
    if hasattr(dds, 'layers') and 'log1norm' in dds.layers:
        data = dds.layers['log1norm']
    elif hasattr(dds, 'layers') and 'normed_counts' in dds.layers:
        data = np.log1p(dds.layers['normed_counts'])
    else:
        data = np.log1p(dds.X) # Fallback
        
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
    
    # Referans Seviyesi Seçimi (Sonuçların doğruluğu için)
    ref_group = st.text_input("Referans Grup Adı (Örn: Control)", value="Control", 
                              help="Samples dosyanızdaki 'condition' sütununda kontrol grubunuzun adı tam olarak neyse buraya yazın.")
    
    padj_cut = st.number_input("P-adj Cutoff", 0.0, 1.0, 0.05, 0.01)
    lfc_cut = st.number_input("Log2FC Cutoff", 0.0, 10.0, 1.0, 0.5)
    min_count = st.number_input("Min Count", 0, 100, 10)
    
    # Butona basınca session state'i temizle ki yeniden çalışsın
    if st.button("Analizi Başlat", type="primary"):
        st.session_state.processed = False # Reset
        st.session_state.run_trigger = True
    else:
        st.session_state.run_trigger = False

# --- ANA AKIŞ ---

# 1. ANALİZ TETİKLEME (Sadece butona basınca çalışır)
if st.session_state.run_trigger:
    if not file_samples:
        st.error("Samples dosyası yüklenmedi!")
    elif not (file_hisat or file_salmon):
        st.error("En az bir count dosyası yükleyin.")
    else:
        try:
            samples_data = pd.read_csv(file_samples, index_col=0)
            design_col = "condition"
            if "condition" not in samples_data.columns: design_col = samples_data.columns[0]
            samples_data[design_col] = samples_data[design_col].astype(str)
            
            # Referans grup kontrolü
            unique_groups = samples_data[design_col].unique()
            if ref_group not in unique_groups:
                st.error(f"HATA: Yazdığınız referans grup ('{ref_group}') samples dosyasında bulunamadı! Mevcut gruplar: {unique_groups}")
                st.stop()
            
            with st.status("Analiz Yapılıyor... Lütfen bekleyin...", expanded=True) as status:
                
                # HISAT Analizi
                if file_hisat:
                    st.write("HISAT2 verisi işleniyor...")
                    counts = pd.read_csv(file_hisat, index_col=0)
                    dds, err = run_deseq_fit(counts, samples_data, design_col, ref_group, min_count)
                    if err: st.error(f"HISAT Hatası: {err}")
                    else: st.session_state.hisat_dds = dds
                
                # SALMON Analizi
                if file_salmon:
                    st.write("SALMON verisi işleniyor...")
                    counts = pd.read_csv(file_salmon, index_col=0)
                    dds, err = run_deseq_fit(counts, samples_data, design_col, ref_group, min_count)
                    if err: st.error(f"SALMON Hatası: {err}")
                    else: st.session_state.salmon_dds = dds
                
                st.session_state.processed = True
                status.update(label="Analiz Tamamlandı!", state="complete", expanded=False)
                
        except Exception as e:
            st.error(f"Genel Hata: {e}")

# 2. SONUÇLARI GÖSTERME (Sayfa yenilense de gitmez)
if st.session_state.processed:
    
    # Metadata'yı tekrar yüklemeye gerek yok, session'dan alabiliriz ama basit olsun diye tekrar okuyoruz
    # (Dosya objesi sıfırlandığı için en temizi dds içinden almak)
    
    tabs = []
    titles = []
    if st.session_state.hisat_dds: titles.append("📂 HISAT2 Sonuçları")
    if st.session_state.salmon_dds: titles.append("📂 SALMON Sonuçları")
    
    if not titles:
        st.warning("Sonuç üretilemedi.")
        st.stop()
        
    tabs = st.tabs(titles)
    
    # Hangi datayı işleyeceğimizi belirleyelim
    datasets = []
    if st.session_state.hisat_dds: datasets.append(("HISAT2", st.session_state.hisat_dds))
    if st.session_state.salmon_dds: datasets.append(("SALMON", st.session_state.salmon_dds))
    
    for i, (method_name, dds) in enumerate(datasets):
        with tabs[i]:
            # Gerekli verileri dds içinden çek
            norm_counts = get_norm_counts(dds)
            design_col = dds.design_factors[0] # condition
            metadata = dds.obs # samples verisi burada saklı
            
            st.success(f"✅ {method_name} Modeli Hazır. Grafikleri aşağıdan seçin.")
            
            t1, t2, t3 = st.tabs(["📊 PCA", "🌋 Volcano & Tablo", "🔥 Heatmaps"])
            
            # --- PCA ---
            with t1:
                pca = PCA(n_components=2)
                pca_res = pca.fit_transform(norm_counts)
                var_exp = pca.explained_variance_ratio_ * 100
                pca_df = pd.DataFrame(pca_res, columns=["PC1", "PC2"], index=norm_counts.index)
                pca_df['condition'] = metadata[design_col]
                
                fig_pca, ax = plt.subplots(figsize=(8, 6))
                sns.scatterplot(data=pca_df, x="PC1", y="PC2", hue="condition", s=150, ax=ax)
                ax.set_title(f"PCA - {method_name}")
                ax.set_xlabel(f"PC1: {int(var_exp[0])}%")
                ax.set_ylabel(f"PC2: {int(var_exp[1])}%")
                st.pyplot(fig_pca)
                download_buttons_for_plot(fig_pca, f"PCA_{method_name}")
                plt.close(fig_pca) # Bellek temizliği

            # --- VOLCANO ---
            with t2:
                col_sel1, col_sel2 = st.columns(2)
                gruplar = metadata[design_col].unique()
                g1 = col_sel1.selectbox(f"{method_name} - Test Grubu", gruplar, index=0, key=f"g1_{method_name}")
                g2 = col_sel2.selectbox(f"{method_name} - Referans Grup", gruplar, index=1 if len(gruplar)>1 else 0, key=f"g2_{method_name}")
                
                # Hesaplama butonu (Artık tüm sayfa değil sadece burası çalışır)
                if st.button(f"Karşılaştır ({method_name})", key=f"btn_vol_{method_name}"):
                    res_df = run_contrast_analysis(dds, g1, g2, design_col)
                    res_df = add_interpretation(res_df, lfc_cut, padj_cut)
                    
                    colors_map = {"GUCLU ARTIS (UP)": "blue", "GUCLU AZALIS (DOWN)": "red", 
                                  "Hafif Artis": "lightblue", "Hafif Azalis": "salmon", 
                                  "Degisim Yok / Anlamsiz": "grey"}
                    
                    fig_vol, ax = plt.subplots(figsize=(8, 6))
                    sns.scatterplot(data=res_df, x='log2FoldChange', y=-np.log10(res_df['padj']),
                                    hue='Yorum', palette=colors_map, alpha=0.7, ax=ax)
                    ax.axvline(lfc_cut, ls="--", c="black"); ax.axvline(-lfc_cut, ls="--", c="black")
                    ax.axhline(-np.log10(padj_cut), ls="--", c="black")
                    ax.set_title(f"{g1} vs {g2}")
                    st.pyplot(fig_vol)
                    download_buttons_for_plot(fig_vol, f"Volcano_{method_name}")
                    plt.close(fig_vol)
                    
                    # CSV İndirme
                    st.dataframe(res_df.head())
                    csv = res_df.to_csv().encode('utf-8')
                    st.download_button(f"📥 Sonuçları İndir ({g1} vs {g2})", csv, f"Sonuc_{method_name}.csv", "text/csv")

            # --- HEATMAP ---
            with t3:
                # Gen listesi oku
                target_genes = []
                if file_genes:
                    file_genes.seek(0)
                    target_genes = [line.decode("utf-8").strip() for line in file_genes]
                
                if not target_genes:
                    target_genes = norm_counts.var(axis=0).sort_values(ascending=False).head(50).index.tolist()
                    st.info("Top 50 değişken gen gösteriliyor.")
                
                mat_subset = norm_counts[target_genes].T
                
                if not mat_subset.empty:
                    # Bireysel Heatmap
                    st.subheader("Bireysel Heatmap")
                    fig_ind = sns.clustermap(mat_subset, z_score=0, cmap="vlag", col_cluster=False, figsize=(6, 8))
                    st.pyplot(fig_ind)
                    download_buttons_for_plot(fig_ind, f"Heatmap_Ind_{method_name}")
                    plt.close(fig_ind.fig)
                    
                    st.divider()
                    
                    # Ortalama Heatmap
                    st.subheader("Ortalama Heatmap")
                    norm_sub = norm_counts[target_genes]
                    norm_sub['condition'] = metadata[design_col]
                    grouped_mean = norm_sub.groupby('condition').mean().T
                    
                    # Z-score scale
                    grouped_mean_scaled = grouped_mean.apply(lambda x: (x - x.mean()) / x.std(), axis=1).fillna(0)
                    
                    fig_avg, ax = plt.subplots(figsize=(6, 6))
                    sns.heatmap(grouped_mean_scaled, cmap="vlag", center=0, ax=ax)
                    st.pyplot(fig_avg)
                    download_buttons_for_plot(fig_avg, f"Heatmap_Avg_{method_name}")
                    plt.close(fig_avg)

else:
    st.info("👈 Lütfen sol menüden dosyaları yükleyip 'Analizi Başlat'a basın.")
