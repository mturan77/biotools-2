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
st.set_page_config(page_title="RNA-Seq Full Analiz", layout="wide")
st.title("🧬 RNA-Seq Analiz Hattı: HISAT & SALMON (Full Çıktı)")

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






# --- 1. SIDEBAR ---
with st.sidebar:
    st.header("1. Veri Dosyaları")
    st.info("HISAT ve SALMON dosyalarını yükleyin. İkisi de varsa ayrı sekmelerde analiz edilir.")
    
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
    """ Grafikleri belleğe kaydeder (İndirmek için) """
    buf = io.BytesIO()
    fig.savefig(buf, format=format, bbox_inches="tight", dpi=300)
    buf.seek(0)
    return buf

def download_buttons_for_plot(fig, filename_prefix):
    """ Her grafik için 3'lü indirme butonu oluşturur (PNG, SVG, PDF) """
    col1, col2, col3 = st.columns([1, 1, 1])
    
    # PNG
    with col1:
        st.download_button(
            label="📷 PNG İndir",
            data=save_plot_to_memory(fig, "png"),
            file_name=f"{filename_prefix}.png",
            mime="image/png",
            use_container_width=True
        )
    # SVG
    with col2:
        st.download_button(
            label="✒️ SVG İndir",
            data=save_plot_to_memory(fig, "svg"),
            file_name=f"{filename_prefix}.svg",
            mime="image/svg+xml",
            use_container_width=True
        )
    # PDF
    with col3:
        st.download_button(
            label="📄 PDF İndir",
            data=save_plot_to_memory(fig, "pdf"),
            file_name=f"{filename_prefix}.pdf",
            mime="application/pdf",
            use_container_width=True
        )

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

@st.cache_resource
def run_deseq_fit(counts_df, samples_df, design_col, min_cnt):
    # Kesişim
    common = list(set(counts_df.columns) & set(samples_df.index))
    if not common: return None, "Samples ve Counts arasında ortak örnek yok!"
    
    counts_df = counts_df[common]
    samples_df = samples_df.loc[common]
    
    # Transpose & Filtre
    counts_T = counts_df.T 
    genes_keep = counts_T.columns[counts_T.sum(axis=0) >= min_cnt]
    counts_T = counts_T[genes_keep]
    
    # Fit
    inference = DeseqDataSet(counts=counts_T, metadata=samples_df, design_factors=design_col, quiet=True)
    inference.deseq2()
    return inference, None

def run_contrast_analysis(dds, g1, g2, design_col):
    stat_res = DeseqStats(dds, contrast=[design_col, g1, g2], quiet=True)
    stat_res.summary()
    return stat_res.results_df

def render_analysis_section(dds, samples_df, design_col, method_name, gene_list_file):
    """ Tek bir yöntemin (HISAT veya SALMON) tüm çıktılarını basar """
    
    st.success(f"✅ {method_name} Analizi Hazır")
    norm_counts = dds.layers['log1norm']
    
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
        
        # İNDİRME BUTONLARI
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
            
            # --- A) VOLCANO PLOT ---
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
            
            # İNDİRME BUTONLARI (VOLCANO)
            st.caption("Volcano Grafiğini İndir:")
            download_buttons_for_plot(fig_vol, f"Volcano_{method_name}_{g1}_{g2}")
            
            st.divider()
            
            # --- B) CSV DOSYALARI (TABLO) ---
            st.markdown("### 📥 Sonuç Tablolarını İndir")
            col_d1, col_d2 = st.columns(2)
            
            # 1. TÜM SONUÇLAR (Yorumlu)
            csv_full = res_df.to_csv().encode('utf-8')
            col_d1.download_button(
                label=f"📄 TÜM LİSTE İndir ({g1}vs{g2})",
                data=csv_full,
                file_name=f"Sonuc_TUMU_{method_name}_{g1}_{g2}.csv",
                mime="text/csv",
                help="Tüm genlerin P-value, FoldChange ve Yorum sütunlarını içerir."
            )
            
            # 2. ÖZEL LİSTE (Varsa)
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
                        mime="text/csv",
                        help="Sadece yüklediğiniz gen listesindeki genlerin sonuçları."
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
            st.info("ℹ️ Top 50 Değişken Gen Gösteriliyor (Özel liste yok).")

        mat_subset = norm_counts[target_genes].T 
        
        if not mat_subset.empty:
            # A) BİREYSEL HEATMAP
            st.markdown("#### A) Bireysel Heatmap")
            fig_ind = sns.clustermap(mat_subset, z_score=0, cmap="vlag", col_cluster=False, figsize=(6, 8))
            st.pyplot(fig_ind)
            st.caption("Bireysel Heatmap İndir:")
            download_buttons_for_plot(fig_ind, f"Heatmap_Bireysel_{method_name}")
            
            st.divider()
            
            # B) ORTALAMA HEATMAP
            st.markdown("#### B) Ortalama Heatmap (Gruplar)")
            norm_counts_subset = norm_counts[target_genes]
            norm_counts_subset['condition'] = samples_df[design_col]
            grouped_mean = norm_counts_subset.groupby('condition').mean().T 
            
            # Heatmap Verisini İndir (Senin R kodundaki özellik)
            csv_heatmap = grouped_mean.to_csv().encode('utf-8')
            st.download_button(
                label="📊 Ortalama Verisini İndir (CSV)",
                data=csv_heatmap,
                file_name=f"Heatmap_ORTALAMA_VERISI_{method_name}.csv",
                mime="text/csv"
            )
            
            fig_avg, ax = plt.subplots(figsize=(6, 6))
            sns.heatmap(grouped_mean, cmap="vlag", z_score=0, ax=ax)
            st.pyplot(fig_avg)
            st.caption("Ortalama Heatmap İndir:")
            download_buttons_for_plot(fig_avg, f"Heatmap_Ortalama_{method_name}")

# --- ANA AKIŞ ---
if btn_run:
    if not file_samples:
        st.error("Samples dosyası eksik!")
    elif not (file_hisat or file_salmon):
        st.error("En az bir Counts dosyası yükleyin.")
    else:
        try:
            samples_data = pd.read_csv(file_samples, index_col=0)
            design_col = "condition"
            if "condition" not in samples_data.columns: design_col = samples_data.columns[0]
            samples_data[design_col] = samples_data[design_col].astype(str)
        except Exception as e:
            st.error(f"Samples hatası: {e}")
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
