import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pydeseq2.dds import DeseqDataSet
from pydeseq2.ds import DeseqStats
from sklearn.decomposition import PCA
import io

# Sayfa Ayarları
st.set_page_config(page_title="RNA-Seq Analizi (PyDESeq2)", layout="wide")

st.title("🧬 RNA-Seq Analiz Paneli")

# --- KULLANIM KILAVUZU (GİZLE/GÖSTER) ---
with st.expander("ℹ️ NASIL KULLANILIR? (Dosya Formatları ve Ayarlar) - Okumak için tıkla"):
    st.markdown("""
    ### 1. Dosya Formatları Nasıl Olmalı?
    
    **A) Counts Matrix (Sayım Matrisi):**
    * **Format:** `.csv` (Virgül ile ayrılmış)
    * **Satırlar:** Gen İsimleri (GeneID)
    * **Sütunlar:** Örnek İsimleri (SampleID)
    * *Değerler:* Ham okuma sayıları (Raw integers). Normalize edilmiş veri yüklemeyin!
    
    | | SRR101 | SRR102 | SRR103 |
    |---|---|---|---|
    | **GeneA** | 150 | 160 | 0 |
    | **GeneB** | 2000 | 2100 | 1950 |

    **B) Metadata / Samples (Örnek Bilgileri):**
    * **Format:** `.csv`
    * **Satırlar:** Örnek İsimleri (Counts dosyasındaki sütunlarla BİREBİR AYNI olmalı)
    * **Sütun:** `condition` adında bir sütun olmalı (Control, Treatment vb. yazar).
    
    | | condition | batch |
    |---|---|---|
    | **SRR101** | Control | 1 |
    | **SRR102** | Treatment | 1 |
    
    ---
    ### 2. Parametreler Ne İşe Yarar?
    * **P-adj Cutoff (0.05):** İstatistiksel olarak ne kadar emin olmak istiyorsunuz? Genelde 0.05 (veya %5 hata payı) kullanılır.
    * **Log2 Fold Change (LFC):** Gen ifadesinin kat değişim eşiği. `1` demek, genin ifadesi 2 katına çıkmış (veya yarıya inmiş) demektir.
    * **Min Count:** Çok az okunan (örneğin toplamda 10'dan az okunan) genleri atarak analizi hızlandırır ve gürültüyü azaltır.
    """)

# --- 1. SIDEBAR: Dosya Yükleme ve Ayarlar ---
with st.sidebar:
    st.header("1. Veri Yükleme")
    
    file_counts = st.file_uploader(
        "Counts Matrix (CSV)", 
        type=["csv"],
        help="Genlerin satırlarda, örneklerin sütunlarda olduğu, sayısal değerler içeren CSV dosyası."
    )
    
    file_samples = st.file_uploader(
        "Metadata / Samples (CSV)", 
        type=["csv"],
        help="İlk sütunu örnek isimleri olan, içinde 'condition' sütunu barındıran grup dosyası."
    )
    
    file_genes = st.file_uploader(
        "Gen Listesi (TXT - Opsiyonel)", 
        type=["txt"],
        help="Heatmap'te sadece belirli genlere bakmak isterseniz, gen isimlerinin alt alta yazılı olduğu TXT dosyası."
    )
    
    st.divider()
    st.header("2. Parametreler")
    
    padj_cut = st.number_input(
        "P-adj Cutoff (Anlamlılık Değeri)", 
        min_value=0.0, max_value=1.0, value=0.05, step=0.01,
        help="Genellikle 0.05 kullanılır. Daha sıkı bir analiz için 0.01 yapabilirsiniz."
    )
    
    lfc_cut = st.number_input(
        "Log2 Fold Change (Kat Değişimi)", 
        min_value=0.0, max_value=10.0, value=1.0, step=0.5,
        help="1 = 2 kat değişim. 2 = 4 kat değişim. 0 yaparsanız en ufak değişimi bile dahil eder."
    )
    
    min_count = st.number_input(
        "Min Count Filtresi", 
        min_value=0, max_value=100, value=10,
        help="Tüm örneklerdeki toplam okuma sayısı bu değerden düşük olan genler analizden atılır."
    )
    
    btn_run = st.button("Analizi Başlat", type="primary", use_container_width=True)

# --- Fonksiyonlar ---

@st.cache_resource
def run_deseq_fit(counts_df, metadata_df, design_col, min_cnt):
    """ DESeq2 Model Kurulumu """
    # Transpose kontrolü (PyDESeq2 Samples x Genes ister)
    # Eğer Counts sütunları ile Metadata index'i tutuyorsa Transpose alıyoruz.
    if set(counts_df.columns) == set(metadata_df.index):
        counts_df = counts_df.T
    
    # Eksik verileri doldur ve integer yap
    counts_df = counts_df.fillna(0).astype(int)
    
    # Filtreleme
    genes_to_keep = counts_df.columns[counts_df.sum(axis=0) >= min_cnt]
    counts_df = counts_df[genes_to_keep]

    inference = DeseqDataSet(
        counts=counts_df,
        metadata=metadata_df,
        design_factors=design_col,
        quiet=True
    )
    inference.deseq2()
    return inference, counts_df  # counts_df'in filtrelenmiş halini de döndür

def run_deseq_result(dds, contrast):
    """ İstatistiksel Test """
    stat_res = DeseqStats(dds, contrast=contrast, quiet=True)
    stat_res.summary()
    return stat_res.results_df

# --- ANA AKIŞ ---

if btn_run and file_counts and file_samples:
    
    # 1. Veri Okuma
    try:
        counts_data = pd.read_csv(file_counts, index_col=0)
        samples_data = pd.read_csv(file_samples, index_col=0)
        
        # Metadata kontrol
        design_col = "condition"
        if "condition" not in samples_data.columns:
            st.warning("⚠️ 'condition' sütunu bulunamadı! İlk sütun grup bilgisi olarak varsayılıyor.")
            design_col = samples_data.columns[0]
        
        # String'e çevir
        samples_data[design_col] = samples_data[design_col].astype(str)
        
        # Örnek isimleri eşleşiyor mu kontrolü
        common_samples = list(set(counts_data.columns) & set(samples_data.index))
        if len(common_samples) == 0:
            st.error("❌ HATA: Counts dosyasındaki sütun isimleri ile Metadata satır isimleri eşleşmiyor!")
            st.stop()
            
        # Sadece ortak olanları al
        counts_data = counts_data[common_samples]
        samples_data = samples_data.loc[common_samples]
        
        st.success(f"✅ Veriler yüklendi! {len(common_samples)} örnek ve {counts_data.shape[0]} gen analiz ediliyor...")
        
        # 2. DESeq2 Fit
        with st.spinner('⏳ DESeq2 Analizi Çalışıyor... (Lütfen bekleyiniz)'):
            dds, filt_counts = run_deseq_fit(counts_data, samples_data, design_col, min_count)
            # Normalize countları al
            norm_counts = dds.layers['log1norm']
            
        st.info("✅ Model tamamlandı. Aşağıdaki sekmelerden sonuçları inceleyin.")
        
        # 3. Sekmeler
        tab1, tab2, tab3 = st.tabs(["📊 PCA & Genel", "🌋 Volcano & Tablo", "🔥 Heatmaps"])
        
        # --- TAB 1: PCA ---
        with tab1:
            st.subheader("PCA Analizi")
            pca = PCA(n_components=2)
            pca_res = pca.fit_transform(norm_counts)
            var_exp = pca.explained_variance_ratio_ * 100
            
            pca_df = pd.DataFrame(pca_res, columns=["PC1", "PC2"], index=norm_counts.index)
            pca_df['Condition'] = samples_data[design_col]
            
            fig_pca, ax = plt.subplots(figsize=(8, 6))
            sns.scatterplot(data=pca_df, x="PC1", y="PC2", hue="Condition", s=100, ax=ax)
            ax.set_xlabel(f"PC1 ({var_exp[0]:.1f}%)")
            ax.set_ylabel(f"PC2 ({var_exp[1]:.1f}%)")
            ax.set_title("PCA Plot - Örneklerin Ayrışımı")
            st.pyplot(fig_pca)
            
        # --- TAB 2: Karşılaştırma ---
        with tab2:
            st.subheader("Diferansiyel İfade Analizi")
            groups = samples_data[design_col].unique()
            c1, c2 = st.columns(2)
            with c1:
                group_a = st.selectbox("Grup 1 (Test Grubu)", groups)
            with c2:
                group_b = st.selectbox("Grup 2 (Referans/Kontrol)", [g for g in groups if g != group_a])
                
            if st.button("⚔️ Grupları Karşılaştır"):
                with st.spinner("Hesaplanıyor..."):
                    contrast = [design_col, group_a, group_b]
                    res_df = run_deseq_result(dds, contrast)
                    
                    # Renklendirme
                    res_df['Color'] = 'Anlamsız'
                    res_df.loc[(res_df['log2FoldChange'] > lfc_cut) & (res_df['padj'] < padj_cut), 'Color'] = 'UP (Artan)'
                    res_df.loc[(res_df['log2FoldChange'] < -lfc_cut) & (res_df['padj'] < padj_cut), 'Color'] = 'DOWN (Azalan)'
                    
                    # Volcano
                    fig_vol, ax = plt.subplots(figsize=(8, 6))
                    colors = {'UP (Artan)': 'blue', 'DOWN (Azalan)': 'red', 'Anlamsız': 'grey'}
                    
                    plot_df = res_df.dropna(subset=['log2FoldChange', 'padj']).copy()
                    sns.scatterplot(data=plot_df, x='log2FoldChange', y=-np.log10(plot_df['padj']), 
                                    hue='Color', palette=colors, alpha=0.7, ax=ax)
                    
                    ax.axvline(x=lfc_cut, ls="--", c="black", alpha=0.3); ax.axvline(x=-lfc_cut, ls="--", c="black", alpha=0.3)
                    ax.axhline(y=-np.log10(padj_cut), ls="--", c="black", alpha=0.3)
                    st.pyplot(fig_vol)
                    
                    # Tablo
                    st.write("### Anlamlı Genler Listesi")
                    sig_genes = res_df[res_df['Color'] != 'Anlamsız'].sort_values("padj")
                    st.dataframe(sig_genes)
                    
                    # İndir
                    csv = res_df.to_csv().encode('utf-8')
                    st.download_button("📥 Tüm Sonuçları İndir (CSV)", csv, f"Deseq2_{group_a}_vs_{group_b}.csv", "text/csv")

        # --- TAB 3: Heatmap ---
        with tab3:
            st.subheader("Gen İfadesi Isı Haritası")
            heatmap_mode = st.radio("Seçim:", ["Top 50 Değişken Gen", "Dosyadan Gen Listesi Yükle"])
            
            plot_matrix = norm_counts.T # Genes x Samples
            genes_to_plot = []
            
            if heatmap_mode == "Top 50 Değişken Gen":
                variances = plot_matrix.var(axis=1)
                genes_to_plot = variances.sort_values(ascending=False).head(50).index
            elif heatmap_mode == "Dosyadan Gen Listesi Yükle" and file_genes:
                file_genes.seek(0)
                target_genes = [line.decode("utf-8").strip() for line in file_genes]
                genes_to_plot = [g for g in target_genes if g in plot_matrix.index]
                if not genes_to_plot:
                    st.warning("⚠️ Yüklediğiniz listedeki genler veri setinde bulunamadı.")
            
            if len(genes_to_plot) > 1:
                final_mat = plot_matrix.loc[genes_to_plot]
                # Clustermap
                cmap = sns.diverging_palette(240, 10, as_cmap=True)
                fig_heat = sns.clustermap(final_mat, z_score=0, cmap=cmap, center=0, col_cluster=False, figsize=(8, 10))
                st.pyplot(fig_heat)

    except Exception as e:
        st.error(f"❌ Bir hata oluştu! Hata detayı: {e}")
        st.warning("Lütfen 'Nasıl Kullanılır' kısmındaki dosya formatlarına uyduğunuzdan emin olun.")

else:
    st.info("👈 Lütfen sol menüden 'Counts' ve 'Metadata' dosyalarınızı yükleyin.")
