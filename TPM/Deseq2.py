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
st.set_page_config(page_title="RNA-Seq Analiz Hattı (V2)", layout="wide")
st.title("🧬 RNA-Seq Analiz Hattı V2: HISAT & SALMON")

# --- 0. MANUEL & BİLGİLENDİRME ---
with st.expander("ℹ️ NASIL KULLANILIR? (Dosya İsimleri ve Formatlar)"):
    st.markdown("""
    ### Kullanılması Gereken Dosya Formatları
    
    Bu uygulama, elinizdeki R kodunun mantığıyla birebir çalışır. Aşağıdaki dosyaları ilgili kutucuklara yükleyiniz.

    1.  **HISAT Counts Dosyası:**
        * Örnek Dosya Adı: `HISAT_Raw_Counts_Matrix_Verbose.csv`
        * İçerik: Satırlarda Genler, Sütunlarda Örnekler (Ham Sayılar).

    2.  **SALMON Counts Dosyası:**
        * Örnek Dosya Adı: `SALMON_Raw_Counts_Matrix.csv`
        * İçerik: HISAT ile aynı formatta.

    3.  **Samples (Metadata) Dosyası:**
        * Örnek Dosya Adı: `samples.csv`
        * **Önemli:** İlk sütunda örnek isimleri (SRR...), ikinci sütunda veya `condition` adında bir sütunda gruplar (Control, Treatment vb.) olmalı.

    4.  **Gen Listesi (Opsiyonel):**
        * Örnek Dosya Adı: `gen_listesi.txt`
        * İçerik: Alt alta gen isimleri.
    """)

# --- 1. SIDEBAR: TÜM DOSYALARI YÜKLE ---
with st.sidebar:
    st.header("1. Veri Dosyaları")
    
    st.markdown("### A) HISAT Verisi")
    file_hisat = st.file_uploader("HISAT CSV Yükle", type=["csv"], key="hisat")
    
    st.markdown("### B) SALMON Verisi")
    file_salmon = st.file_uploader("SALMON CSV Yükle", type=["csv"], key="salmon")
    
    st.markdown("---")
    st.markdown("### C) Ortak Dosyalar")
    file_samples = st.file_uploader("Samples.csv (Metadata)", type=["csv"], key="samples")
    file_genes = st.file_uploader("Gen Listesi.txt (Opsiyonel)", type=["txt"], key="genes")
    
    st.markdown("---")
    st.header("2. Parametreler")
    padj_cut = st.number_input("P-adj Cutoff", 0.0, 1.0, 0.05, 0.01)
    lfc_cut = st.number_input("Log2FoldChange Cutoff", 0.0, 10.0, 1.0, 0.5)
    min_count = st.number_input("Min Count (Row Sums)", 0, 100, 10)

# --- FONKSİYONLAR (R MANTIĞI BİREBİR) ---

def add_interpretation(df, lfc_limit, padj_limit):
    """
    R Kodundaki add_interpretation fonksiyonunun aynısı.
    """
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
def run_pipeline_step1(counts_df, samples_df, design_col, min_cnt):
    """
    R: dds oluşturma, filtreleme ve DESeq() fonksiyonu
    """
    # 1. Kesişim Kontrolü (R'daki common = intersect logic)
    common = list(set(counts_df.columns) & set(samples_df.index))
    if not common:
        return None, "Samples ve Counts arasında ortak örnek bulunamadı!"
    
    counts_df = counts_df[common]
    samples_df = samples_df.loc[common]
    
    # 2. Transpose (PyDESeq2 gereksinimi: Samples x Genes)
    # R: Genes x Samples idi, Python kütüphanesi tersini istiyor.
    counts_T = counts_df.T 
    
    # 3. Filtreleme (R: rowSums >= 10)
    # Transpose aldığımız için burada sütun toplamına bakıyoruz (Genler sütun oldu)
    genes_keep = counts_T.columns[counts_T.sum(axis=0) >= min_cnt]
    counts_T = counts_T[genes_keep]
    
    # 4. DESeq Object
    inference = DeseqDataSet(
        counts=counts_T,
        metadata=samples_df,
        design_factors=design_col,
        quiet=True
    )
    inference.deseq2()
    
    return inference, None

def run_contrast(dds, group1, group2, design_col):
    """
    R: results(dds, contrast=...)
    """
    stat_res = DeseqStats(dds, contrast=[design_col, group1, group2], quiet=True)
    stat_res.summary()
    return stat_res.results_df

# --- ANA UYGULAMA MANTIĞI ---

if file_samples:
    # Metadata'yı bir kere oku
    try:
        samples_data = pd.read_csv(file_samples, index_col=0)
        # Condition sütununu bul
        design_col = "condition"
        if "condition" not in samples_data.columns:
            st.warning("⚠️ 'condition' sütunu bulunamadı, ilk sütun kullanılıyor.")
            design_col = samples_data.columns[0]
        samples_data[design_col] = samples_data[design_col].astype(str)
        
    except Exception as e:
        st.error(f"Samples dosyası okunurken hata: {e}")
        st.stop()
    
    # --- YÖNTEM SEÇİMİ (HISAT vs SALMON) ---
    st.divider()
    st.subheader("🛠️ Analiz Yöntemini Seçin")
    
    method_choice = st.radio("Hangi veri setini analiz etmek istiyorsunuz?", 
                             ["Seçiniz...", "HISAT2", "SALMON"], horizontal=True)
    
    selected_file = None
    if method_choice == "HISAT2":
        selected_file = file_hisat
    elif method_choice == "SALMON":
        selected_file = file_salmon
        
    # --- ANALİZ MOTORU ---
    if method_choice != "Seçiniz..." and selected_file is not None:
        
        st.info(f"🚀 {method_choice} analizi başlatılıyor...")
        
        # Dosyayı Oku
        counts_data = pd.read_csv(selected_file, index_col=0)
        
        # Pipeline Adım 1: DESeq2 Fit
        with st.spinner(f"{method_choice} için DESeq2 modeli kuruluyor..."):
            dds, error = run_pipeline_step1(counts_data, samples_data, design_col, min_count)
            
            if error:
                st.error(error)
                st.stop()
                
            # Normalize Countlar (PCA ve Heatmap için)
            norm_counts = dds.layers['log1norm'] # VST benzeri log transform
            
        st.success("✅ Model Hazır! Sonuçlar aşağıdadır.")
        
        # --- SEKMELER (PCA, VOLCANO, HEATMAP) ---
        tab1, tab2, tab3 = st.tabs(["01_PCA", "Sonuclar & Volcano", "Heatmaps"])
        
        # 1. PCA (R: plotPCA)
        with tab1:
            st.markdown(f"### PCA - {method_choice}")
            pca = PCA(n_components=2)
            pca_res = pca.fit_transform(norm_counts)
            var_exp = pca.explained_variance_ratio_ * 100
            
            pca_df = pd.DataFrame(pca_res, columns=["PC1", "PC2"], index=norm_counts.index)
            pca_df['condition'] = samples_data[design_col]
            
            fig_pca, ax = plt.subplots(figsize=(8,6))
            sns.scatterplot(data=pca_df, x="PC1", y="PC2", hue="condition", s=100, ax=ax)
            ax.set_xlabel(f"PC1: {int(var_exp[0])}%")
            ax.set_ylabel(f"PC2: {int(var_exp[1])}%")
            st.pyplot(fig_pca)
            
        # 2. KARŞILAŞTIRMALAR (R Döngüsü Yerine Seçim)
        with tab2:
            st.markdown("### Karşılaştırma Seçimi (Results)")
            gruplar = samples_data[design_col].unique()
            
            c1, c2 = st.columns(2)
            g1 = c1.selectbox("Grup 1", gruplar, key="g1")
            g2 = c2.selectbox("Grup 2", [x for x in gruplar if x != g1], key="g2")
            
            if st.button("Karşılaştır (Run Contrast)"):
                with st.spinner("İstatistikler hesaplanıyor..."):
                    res_df = run_contrast(dds, g1, g2, design_col)
                    
                    # R'daki Interpretation Fonksiyonunu Uygula
                    res_df = add_interpretation(res_df, lfc_cut, padj_cut)
                    
                    # Volcano Hazırlığı
                    res_df['VolcanoColor'] = "Degisim Yok / Anlamsiz"
                    # R Kodundaki renklendirme mantığı:
                    # Blue -> UP (Burada R kodunda color manual kısmında sırayla vermişsin, ben mantığı uyguluyorum)
                    # UP ve DOWN olanları ayır
                    
                    # Grafik
                    fig_vol, ax = plt.subplots(figsize=(8,8))
                    
                    # Renkler: UP=Blue, DOWN=Red, Hafifler=Açık renk, Anlamsız=Gri
                    # Basitlik için senin kodundaki 3 renk mantığını (Blue, Grey, Red) uygulayalım
                    # Ama senin interpretation fonksiyonunda 4 çıktı var. 
                    # Görseli senin R çıktına benzetmek için;
                    # Strong UP -> Mavi, Strong Down -> Kırmızı, Diğerleri -> Gri yapalım
                    
                    colors_map = {
                        "GUCLU ARTIS (UP)": "blue",
                        "GUCLU AZALIS (DOWN)": "red",
                        "Hafif Artis": "lightblue",
                        "Hafif Azalis": "salmon",
                        "Degisim Yok / Anlamsiz": "grey"
                    }
                    
                    sns.scatterplot(data=res_df, x='log2FoldChange', y=-np.log10(res_df['padj']),
                                    hue='Yorum', palette=colors_map, alpha=0.7, ax=ax)
                    
                    ax.axvline(lfc_cut, ls="--", c="black"); ax.axvline(-lfc_cut, ls="--", c="black")
                    ax.axhline(-np.log10(padj_cut), ls="--", c="black")
                    ax.set_title(f"Volcano: {g1} vs {g2}")
                    st.pyplot(fig_vol)
                    
                    # Tablo Gösterimi (Önce anlamlılar)
                    st.write("### Sonuç Tablosu")
                    st.dataframe(res_df.sort_values("padj").head(100))
                    
                    # İndirme
                    csv = res_df.to_csv().encode('utf-8')
                    st.download_button(f"Sonuçları İndir ({g1}vs{g2})", csv, f"Sonuc_{method_choice}_{g1}_vs_{g2}.csv")
                    
                    # Özel Liste İndirme
                    if file_genes:
                        file_genes.seek(0)
                        target_list = [line.decode("utf-8").strip() for line in file_genes]
                        subset_df = res_df[res_df.index.isin(target_list)]
                        if not subset_df.empty:
                            csv_sub = subset_df.to_csv().encode('utf-8')
                            st.download_button(f"Özel Liste Sonucu İndir", csv_sub, f"Sonuc_OZEL_{method_choice}.csv")

        # 3. HEATMAPS (R: Bireysel ve Ortalama)
        with tab3:
            st.markdown("### Heatmap Analizi")
            
            # Gen listesi var mı?
            target_genes = []
            if file_genes:
                file_genes.seek(0)
                target_genes = [line.decode("utf-8").strip() for line in file_genes]
            
            if not target_genes:
                st.warning("⚠️ Heatmap çizmek için 'Gen Listesi' yüklemeniz (veya en çok değişenleri seçmeniz) gerekir. Şu an Top 50 gösteriliyor.")
                # Top 50 varyans
                target_genes = norm_counts.var(axis=0).sort_values(ascending=False).head(50).index.tolist()
            
            # Veriyi filtrele (Samples x Genes -> Transpose -> Genes x Samples)
            # Ama heatmap için Genes satırda olsun istiyoruz.
            mat_subset = norm_counts[target_genes].T 
            
            if mat_subset.empty:
                st.error("Seçilen genler veride bulunamadı!")
            else:
                # A) BİREYSEL HEATMAP
                st.subheader("A) Bireysel Heatmap")
                # Metadata annotation lazım
                # Seaborn clustermap ile yapıyoruz
                
                # Sütun renkleri (Grup bilgisi)
                lut = dict(zip(samples_data[design_col].unique(), "rbg"))
                row_colors = samples_data[design_col].map(lut)
                
                g = sns.clustermap(mat_subset, z_score=0, cmap="vlag", col_cluster=False, figsize=(8, 10))
                st.pyplot(g)
                
                # B) ORTALAMA HEATMAP (Senin kodunda elle hesaplanan kısım)
                st.subheader("B) Ortalama Heatmap (Gruplar)")
                
                # Gruplara göre ortalama al (Samples satırda, onlara göre groupby yapıyoruz)
                # norm_counts: Index=Samples, Columns=Genes
                norm_counts_subset = norm_counts[target_genes]
                norm_counts_subset['condition'] = samples_data[design_col]
                
                # Ortalama al
                grouped_mean = norm_counts_subset.groupby('condition').mean().T # Genes x Groups
                
                # Çiz
                fig_avg, ax = plt.subplots(figsize=(6, 8))
                sns.heatmap(grouped_mean, cmap="vlag", z_score=0, ax=ax) # z_score=0 satır bazlı
                st.pyplot(fig_avg)

    elif method_choice != "Seçiniz..." and selected_file is None:
        st.warning(f"Lütfen sol menüden {method_choice} dosyasını yükleyin.")

else:
    st.info("👈 Lütfen önce sol menüden 'Samples.csv' dosyasını yükleyin (Her iki yöntem için ortaktır).")
