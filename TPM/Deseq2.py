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
st.set_page_config(page_title="RNA-Seq Final Fixed", layout="wide")
st.title("🧬 RNA-Seq Analiz Hattı (Final UI & Variance Fix)")

# --- CSS (UI DÜZELTME) ---
# Butonların ve grafiklerin taşmasını engellemek için
st.markdown("""
<style>
    .stButton>button { width: 100%; }
    .reportview-container .main .block-container { max-width: 1000px; }
</style>
""", unsafe_allow_html=True)

# --- OTURUM YÖNETİMİ ---
if 'hisat_dds' not in st.session_state: st.session_state.hisat_dds = None
if 'salmon_dds' not in st.session_state: st.session_state.salmon_dds = None
if 'processed' not in st.session_state: st.session_state.processed = False
if 'design_col' not in st.session_state: st.session_state.design_col = None

# --- İNDİRME FONKSİYONLARI ---
def save_plot_hq(fig, format="png"):
    buf = io.BytesIO()
    fig.savefig(buf, format=format, bbox_inches="tight", dpi=300)
    buf.seek(0)
    return buf

# --- ANALİZ FONKSİYONLARI ---
def run_deseq_fit(counts_df, samples_df, design_col, ref_level, min_cnt):
    # Kesişim
    common = list(set(counts_df.columns) & set(samples_df.index))
    if not common: return None, "Samples ve Counts uyuşmuyor!"
    
    counts_df = counts_df[common]
    samples_df = samples_df.loc[common]
    
    # Filtreleme
    counts_df = counts_df[counts_df.sum(axis=1) >= min_cnt]
    
    try:
        inference = DeseqDataSet(
            counts=counts_df.T, 
            metadata=samples_df, 
            design_factors=design_col,
            ref_level=[design_col, ref_level],
            quiet=True
        )
        inference.deseq2()
        
        # --- VST ZORLAMA BLOĞU ---
        # Versiyon farklarını tolere eden yapı
        try:
            # Önce argümansız dene (Yeni versiyonlar)
            inference.vst()
        except:
            try:
                # Olmazsa blind=False dene (Eski versiyonlar)
                inference.vst(blind=False)
            except:
                st.warning("VST başarısız oldu, varyanslar düşük çıkabilir (Log kullanılıyor).")
        
        return inference, None
    except Exception as e:
        return None, str(e)

def get_norm_data(dds):
    # VST varsa onu al (R ile eşleşmek için şart)
    if hasattr(dds, 'layers') and 'vst_counts' in dds.layers:
        return pd.DataFrame(dds.layers['vst_counts'], index=dds.obs_names, columns=dds.var_names)
    # Yoksa log1p al (Yedek)
    elif hasattr(dds, 'layers') and 'log1norm' in dds.layers:
        return dds.layers['log1norm']
    else:
        return np.log2(dds.X + 1) # Manuel log dönüşümü

def run_contrast(dds, g1, g2, design_col):
    res = DeseqStats(dds, contrast=[design_col, g1, g2], quiet=True)
    res.summary()
    return res.results_df

def add_interp(df, lfc, p):
    c = [
        (df['log2FoldChange'] > lfc) & (df['padj'] < p),
        (df['log2FoldChange'] < -lfc) & (df['padj'] < p)
    ]
    df['Yorum'] = np.select(c, ["UP", "DOWN"], default="NS")
    return df

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Veri Yükleme")
    f_hisat = st.file_uploader("HISAT CSV", type=["csv"], key="hisat")
    f_salmon = st.file_uploader("SALMON CSV", type=["csv"], key="salmon")
    st.markdown("---")
    f_samples = st.file_uploader("Samples CSV", type=["csv"], key="samples")
    f_genes = st.file_uploader("Gen Listesi (TXT)", type=["txt"], key="genes")
    
    st.markdown("---")
    st.header("2. Ayarlar")
    ref_grp = st.text_input("Referans Grup", "Control")
    
    if st.button("Analizi Başlat", type="primary"):
        st.session_state.processed = False
        st.session_state.run_trigger = True
    else:
        st.session_state.run_trigger = False

# --- ANA İŞLEM ---
if st.session_state.run_trigger:
    if not f_samples:
        st.error("Samples dosyası yok!"); st.stop()
        
    samp = pd.read_csv(f_samples, index_col=0)
    d_col = "condition" 
    if "condition" not in samp.columns: d_col = samp.columns[0]
    samp[d_col] = samp[d_col].astype(str)
    st.session_state.design_col = d_col
    
    with st.status("Hesaplanıyor..."):
        if f_hisat:
            d = pd.read_csv(f_hisat, index_col=0)
            dds, err = run_deseq_fit(d, samp, d_col, ref_grp, 10)
            st.session_state.hisat_dds = dds
        if f_salmon:
            d = pd.read_csv(f_salmon, index_col=0)
            dds, err = run_deseq_fit(d, samp, d_col, ref_grp, 10)
            st.session_state.salmon_dds = dds
        st.session_state.processed = True

# --- SONUÇ EKRANI ---
if st.session_state.processed:
    tabs = st.tabs(["📊 HISAT2", "📊 SALMON"])
    datasets = []
    if st.session_state.hisat_dds: datasets.append(("HISAT2", st.session_state.hisat_dds, tabs[0]))
    if st.session_state.salmon_dds: datasets.append(("SALMON", st.session_state.salmon_dds, tabs[1]))
    
    for name, dds, tab in datasets:
        with tab:
            # Veriyi çek (VST veya Log)
            norm_df = pd.DataFrame(get_norm_data(dds), index=dds.obs_names, columns=dds.var_names)
            meta = dds.obs
            d_col = st.session_state.design_col
            
            # --- PCA BÖLÜMÜ ---
            st.subheader(f"PCA Analizi - {name}")
            
            # Kontroller
            c1, c2, c3 = st.columns(3)
            use_custom = c1.checkbox(f"Gen Listesi Kullan ({name})", key=f"uc_{name}")
            inv_x = c2.checkbox("X Ekseni Ters", key=f"ix_{name}")
            inv_y = c3.checkbox("Y Ekseni Ters", key=f"iy_{name}")
            
            # Gen Seçimi Mantığı (R Uyumlu Varyans)
            pca_genes = []
            title_suffix = ""
            
            if use_custom and f_genes:
                f_genes.seek(0)
                targets = [line.decode("utf-8").strip() for line in f_genes]
                pca_genes = [t for t in targets if t in norm_df.columns]
                title_suffix = f"(User List: {len(pca_genes)})"
                if not pca_genes: st.error("Listedeki genler veride bulunamadı!")
            else:
                # R GİBİ VARYANS HESABI (ddof=1 ÇOK ÖNEMLİ)
                vars = norm_df.var(axis=0, ddof=1)
                pca_genes = vars.sort_values(ascending=False).head(500).index
                title_suffix = "(Top 500 Genes)"

            if len(pca_genes) > 0:
                pca_input = norm_df[pca_genes]
                
                # PCA Hesapla
                pca = PCA(n_components=2)
                coords = pca.fit_transform(pca_input)
                var_exp = pca.explained_variance_ratio_ * 100
                
                # Yön Çevirme
                if inv_x: coords[:,0] *= -1
                if inv_y: coords[:,1] *= -1
                
                plot_df = pd.DataFrame(coords, columns=["PC1", "PC2"], index=norm_df.index)
                plot_df['group'] = meta[d_col]
                
                # Çizim (Küçük Boyut)
                fig, ax = plt.subplots(figsize=(5, 4))
                sns.scatterplot(data=plot_df, x="PC1", y="PC2", hue="group", s=100, ax=ax)
                ax.set_xlabel(f"PC1: {int(var_exp[0])}% variance")
                ax.set_ylabel(f"PC2: {int(var_exp[1])}% variance")
                ax.set_title(f"PCA {title_suffix}")
                ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
                ax.grid(True, linestyle='--', alpha=0.3)
                
                # UI Düzeni: Grafik üstte, butonlar altta
                st.pyplot(fig, use_container_width=False)
                
                # Butonlar
                bc1, bc2, bc3 = st.columns(3)
                bc1.download_button("PNG İndir", save_plot_hq(fig, "png"), f"PCA_{name}.png")
                bc2.download_button("SVG İndir", save_plot_hq(fig, "svg"), f"PCA_{name}.svg")
                bc3.download_button("PDF İndir", save_plot_hq(fig, "pdf"), f"PCA_{name}.pdf")
                plt.close(fig)

            st.divider()

            # --- VOLCANO BÖLÜMÜ ---
            st.subheader("Volcano Plot")
            vc1, vc2 = st.columns(2)
            grps = meta[d_col].unique()
            opts = [g for g in grps if g != ref_grp]
            
            if opts:
                g_test = vc1.selectbox(f"Test ({name})", opts)
                
                if st.button(f"Karşılaştır: {g_test} vs {ref_grp}", key=f"btn_{name}"):
                    res = run_contrast(dds, g_test, ref_grp, d_col)
                    res = add_interp(res, 1.0, 0.05)
                    
                    # Filtreleme (Gen Listesi varsa)
                    plot_res = res
                    if use_custom and len(pca_genes) > 0:
                        plot_res = res[res.index.isin(pca_genes)]
                    
                    # Çizim
                    fig_v, ax_v = plt.subplots(figsize=(5, 4))
                    colors = {"UP": "red", "DOWN": "blue", "NS": "grey"}
                    sns.scatterplot(data=plot_res, x='log2FoldChange', y=-np.log10(plot_res['padj']), 
                                    hue='Yorum', palette=colors, ax=ax_v, legend=False)
                    ax_v.set_title(f"{g_test} vs {ref_grp}")
                    ax_v.grid(True, linestyle='--', alpha=0.3)
                    
                    st.pyplot(fig_v, use_container_width=False)
                    
                    vb1, vb2, vb3 = st.columns(3)
                    vb1.download_button("PNG İndir", save_plot_hq(fig_v, "png"), f"Vol_{name}.png")
                    vb2.download_button("SVG İndir", save_plot_hq(fig_v, "svg"), f"Vol_{name}.svg")
                    st.download_button("CSV İndir", res.to_csv().encode(), f"Res_{name}.csv")
                    plt.close(fig_v)
            
            st.divider()
            
            # --- HEATMAP BÖLÜMÜ ---
            st.subheader("Heatmap")
            
            # Heatmap için gen seçimi
            hm_genes = pca_genes if len(pca_genes) > 0 else norm_df.var(axis=0, ddof=1).sort_values(ascending=False).head(50).index
            
            if len(hm_genes) > 0:
                mat = norm_df[hm_genes].T
                
                # Bireysel
                fig_hm = sns.clustermap(mat, z_score=0, cmap="vlag", col_cluster=False, figsize=(5, 6))
                st.pyplot(fig_hm)
                hb1, hb2 = st.columns(2)
                hb1.download_button("Heatmap PNG", save_plot_hq(fig_hm.fig, "png"), f"HM_{name}.png")
                plt.close(fig_hm.fig)
