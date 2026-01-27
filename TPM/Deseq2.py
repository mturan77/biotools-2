import streamlit as st
import os
import glob
import pandas as pd
import pysam
import sys
from collections import defaultdict

# ==============================================================================
# SAYFA YAPILANDIRMASI
# ==============================================================================
st.set_page_config(page_title="RNA-Seq Count Matrix Generator", layout="wide")

st.title("🧬 RNA-Seq Count Matrix Oluşturucu")
st.markdown("BAM ve Salmon çıktılarından ham sayım (Raw Counts) matrislerini oluşturur.")

# ==============================================================================
# SIDEBAR AYARLARI
# ==============================================================================
st.sidebar.header("📂 Ayarlar ve Yollar")

# Varsayılan değerler (Senin kodundaki pathler)
default_base_dir = "/home/mutu/Desktop/Musca-rpkm/6-TPM/"
default_gff = os.path.join(default_base_dir, "Musca_veriler_yedek/Musca_domestica.gff3")

BASE_DIR = st.sidebar.text_input("Ana Dizin (Base Dir)", value=default_base_dir)
GFF_FILE = st.sidebar.text_input("GFF3 Dosya Yolu", value=default_gff)

st.sidebar.subheader("🔍 Arama Desenleri")
SEARCH_PATTERN_BAM = st.sidebar.text_input("BAM Arama Deseni", value="**/bam_files_final/*.bam")
SEARCH_PATTERN_QUANT = st.sidebar.text_input("Salmon Arama Deseni", value="**/*_quant/quant.sf")

st.sidebar.subheader("⚙️ Analiz Modu")
mode_selection = st.sidebar.radio("Hangi analiz yapılsın?", ("Her İkisi (3)", "Sadece HISAT/BAM (1)", "Sadece SALMON (2)"))

# Modu sayıya çevir
MODE = 3
if "Sadece HISAT" in mode_selection: MODE = 1
elif "Sadece SALMON" in mode_selection: MODE = 2

st.sidebar.subheader("🎚️ BAM Hassasiyeti")
MIN_MAPQ = st.sidebar.number_input("Min MapQ", value=1, min_value=0)

# Çıktı Klasörleri
OUT_DIR_HISAT = os.path.join(BASE_DIR, "DESeq2_Input_HISAT_Verbose")
OUT_DIR_SALMON = os.path.join(BASE_DIR, "DESeq2_Input_SALMON_Verbose")

# ==============================================================================
# YENİ ANALİZ / CACHE TEMİZLEME BUTONU
# ==============================================================================
if st.sidebar.button("🧹 Önbelleği Temizle / Yeni Analiz", type="primary"):
    st.cache_data.clear()
    st.cache_resource.clear()
    st.success("Önbellek temizlendi! Sayfa yenileniyor...")
    st.rerun()

# ==============================================================================
# YARDIMCI SINIF VE FONKSİYONLAR
# ==============================================================================

def normalize_id(s):
    if not s: return None
    s = str(s).strip()
    for prefix in ['gene-', 'rna-', 'transcript-', 'id-', 'mps-']:
        if s.startswith(prefix): return s[len(prefix):].split('.')[0]
    return s.split('.')[0]

class GeneInterval:
    def __init__(self, gene_id, chrom):
        self.gene_id = gene_id
        self.chrom = chrom
        self.exons = []
        self.start = float('inf')
        self.end = float('-inf')

    def add_exon(self, start, end):
        self.exons.append((start, end))
        self.start = min(self.start, start)
        self.end = max(self.end, end)

# GFF Okuma işlemini Cache'liyoruz (Hız için)
@st.cache_data(show_spinner=False)
def parse_gff_cached(gff_path):
    if not os.path.exists(gff_path):
        return None, None, f"GFF dosyası bulunamadı: {gff_path}"

    genes = {} 
    tx2gene = {}
    rna_parent_map = {}
    unique_chroms = set()
    log_messages = []

    try:
        with open(gff_path, "r") as f:
            for line in f:
                if line.startswith("#"): continue
                parts = line.strip().split("\t")
                if len(parts) < 9: continue
                
                chrom, _, feat, start, end, _, _, _, attribs = parts
                start, end = int(start)-1, int(end)
                unique_chroms.add(chrom)
                
                attr = {x.split('=')[0]: x.split('=')[1] for x in attribs.split(';') if '=' in x}
                
                if feat == "gene":
                    gid = normalize_id(attr.get("ID"))
                    if gid: genes[gid] = GeneInterval(gid, chrom)
                elif feat in ["mRNA", "transcript", "lincRNA"]:
                    tid = normalize_id(attr.get("ID"))
                    gid = normalize_id(attr.get("Parent"))
                    if tid and gid: 
                        rna_parent_map[tid] = gid
                        tx2gene[tid] = gid
                elif feat == "exon":
                    parent = normalize_id(attr.get("Parent"))
                    gid = rna_parent_map.get(parent, parent)
                    if gid:
                        if gid not in genes: genes[gid] = GeneInterval(gid, chrom)
                        genes[gid].add_exon(start, end)
        
        return genes, tx2gene, f"✅ GFF Okundu. Toplam Gen: {len(genes)}. Kromozomlar: {list(unique_chroms)[:5]}..."
    except Exception as e:
        return None, None, str(e)

# ==============================================================================
# BAM ANALİZİ (STREAMLIT UYUMLU)
# ==============================================================================
def process_bam_files(bam_files, genes_db):
    md_hisat = {}
    all_genes_h = set(genes_db.keys())
    
    overall_progress = st.progress(0)
    status_text = st.empty()
    logs = []

    for idx, bam_path in enumerate(bam_files):
        base_name = os.path.basename(bam_path)
        status_text.text(f"İşleniyor ({idx+1}/{len(bam_files)}): {base_name}")
        overall_progress.progress((idx) / len(bam_files))
        
        counts = defaultdict(int)
        total_assigned_reads = 0
        
        try:
            # Index kontrolü
            if not os.path.exists(bam_path + ".bai"):
                pysam.index(bam_path)
            
            samfile = pysam.AlignmentFile(bam_path, "rb")
            bam_refs = set(samfile.references)
            
            # Kromozom Eşleme Mantığı
            genes_by_chrom = defaultdict(list)
            for g in genes_db.values():
                genes_by_chrom[g.chrom].append(g)
            
            matched_chroms = 0
            chrom_map = {}
            for g_chrom in genes_by_chrom.keys():
                target = None
                if g_chrom in bam_refs: target = g_chrom
                else:
                    cands = [g_chrom.replace("Scaffold", ""), f"Scaffold{g_chrom}", f"chr{g_chrom}", g_chrom.replace("chr","")]
                    target = next((c for c in cands if c in bam_refs), None)
                
                if target:
                    chrom_map[g_chrom] = target
                    matched_chroms += 1
            
            if matched_chroms == 0:
                logs.append(f"❌ {base_name}: Hiçbir kromozom eşleşmedi!")
                md_hisat[base_name.replace(".bam", "")] = {}
                samfile.close()
                continue

            # --- Sayım Döngüsü (Görselleştirilmiş) ---
            # Tek bir dosya için inner progress bar
            file_progress = st.progress(0)
            total_chroms_to_scan = len(chrom_map)
            chrom_processed_count = 0

            for g_chrom, target_chrom in chrom_map.items():
                # Performans için: Her kromozomda bar güncelleme
                chrom_processed_count += 1
                if chrom_processed_count % 10 == 0:
                    file_progress.progress(chrom_processed_count / total_chroms_to_scan)

                for gene in genes_by_chrom[g_chrom]:
                    if gene.start >= gene.end: continue
                    try:
                        read_names = set()
                        iter_reads = samfile.fetch(target_chrom, gene.start, gene.end)
                        for read in iter_reads:
                            if read.is_secondary or read.is_supplementary or read.is_unmapped: continue
                            if read.mapping_quality < MIN_MAPQ: continue
                            
                            is_exonic = False
                            r_s, r_e = read.reference_start, read.reference_end
                            for es, ee in gene.exons:
                                if r_s < ee and r_e > es:
                                    is_exonic = True
                                    break
                            
                            if is_exonic:
                                read_names.add(read.query_name)
                        
                        if read_names:
                            cnt = len(read_names)
                            counts[gene.gene_id] = cnt
                            total_assigned_reads += cnt
                    except ValueError: continue
            
            file_progress.empty() # Dosya bitince barı temizle
            logs.append(f"✅ {base_name}: {total_assigned_reads} okuma atandı.")
            md_hisat[base_name.replace(".bam", "")] = counts
            samfile.close()

        except Exception as e:
            logs.append(f"🛑 HATA {base_name}: {e}")
            md_hisat[base_name.replace(".bam", "")] = {}

    overall_progress.progress(1.0)
    status_text.text("BAM analizi tamamlandı.")
    
    # DataFrame oluşturma
    df_h = pd.DataFrame(index=sorted(list(all_genes_h)))
    for s, c in md_hisat.items():
        df_h[s] = pd.Series(c).reindex(df_h.index, fill_value=0)
    
    return df_h.fillna(0).astype(int), logs

# ==============================================================================
# SALMON ANALİZİ (STREAMLIT UYUMLU)
# ==============================================================================
def process_salmon_files(quant_pattern, tx2gene):
    full_pattern = os.path.join(BASE_DIR, quant_pattern)
    quant_files = glob.glob(full_pattern, recursive=True)
    
    if not quant_files:
        return None, ["Salmon dosyası bulunamadı."]

    master_data = {}
    all_genes = set(tx2gene.values())
    logs = []
    
    progress_bar = st.progress(0)
    
    for i, q_path in enumerate(quant_files):
        progress_bar.progress((i+1) / len(quant_files))
        s_name = os.path.dirname(q_path).split(os.sep)[-1].replace("_quant", "")
        
        try:
            df = pd.read_csv(q_path, sep="\t")
            df['CleanName'] = df['Name'].apply(normalize_id)
            df['GeneID'] = df['CleanName'].map(tx2gene).fillna(df['CleanName'])
            grouped = df.groupby('GeneID')['NumReads'].sum()
            
            master_data[s_name] = grouped.to_dict()
            all_genes.update(grouped.index)
            logs.append(f"🔹 {s_name}: {int(grouped.sum())} okuma işlendi.")
        except Exception as e:
            logs.append(f"🛑 HATA {s_name}: {e}")

    df_f = pd.DataFrame(index=sorted(list(all_genes)))
    for s, c in master_data.items():
        df_f[s] = pd.Series(c).reindex(df_f.index, fill_value=0)
    
    return df_f.fillna(0).round().astype(int), logs

# ==============================================================================
# MAIN UYGULAMA AKIŞI
# ==============================================================================

# Başlat Butonu
if st.button("🚀 Analizi Başlat", type="primary"):
    
    if not os.path.exists(BASE_DIR):
        st.error(f"Ana dizin bulunamadı: {BASE_DIR}")
        st.stop()

    # 1. GFF Okuma
    with st.spinner('GFF dosyası okunuyor...'):
        gene_db, tx2gene, msg = parse_gff_cached(GFF_FILE)
    
    if gene_db is None:
        st.error(msg)
        st.stop()
    else:
        st.info(msg)

    # 2. HISAT/BAM Analizi
    if MODE == 1 or MODE == 3:
        st.subheader("📊 HISAT/BAM Analiz Sonuçları")
        full_bam_pattern = os.path.join(BASE_DIR, SEARCH_PATTERN_BAM)
        bam_files = glob.glob(full_bam_pattern, recursive=True)
        
        if bam_files:
            st.write(f"Bulunan BAM Dosyası Sayısı: {len(bam_files)}")
            
            with st.spinner("BAM dosyaları taranıyor (Bu işlem uzun sürebilir)..."):
                df_hisat, logs_hisat = process_bam_files(bam_files, gene_db)
            
            # Logları Göster
            with st.expander("BAM İşlem Logları (Tıkla Gör)", expanded=False):
                for l in logs_hisat: st.write(l)
            
            # Önizleme ve İndirme
            st.dataframe(df_hisat.head())
            
            os.makedirs(OUT_DIR_HISAT, exist_ok=True)
            out_file_h = os.path.join(OUT_DIR_HISAT, "HISAT_Raw_Counts_Matrix_Verbose.csv")
            df_hisat.to_csv(out_file_h)
            
            st.success(f"HISAT Matrisi Kaydedildi: {out_file_h}")
            st.download_button(
                label="📥 HISAT CSV İndir",
                data=df_hisat.to_csv().encode('utf-8'),
                file_name="HISAT_Raw_Counts.csv",
                mime='text/csv'
            )
        else:
            st.warning("⚠️ Belirtilen yolda BAM dosyası bulunamadı!")

    st.markdown("---")

    # 3. SALMON Analizi
    if MODE == 2 or MODE == 3:
        st.subheader("🐟 SALMON Analiz Sonuçları")
        with st.spinner("Salmon dosyaları işleniyor..."):
            df_salmon, logs_salmon = process_salmon_files(SEARCH_PATTERN_QUANT, tx2gene)
        
        if df_salmon is not None:
             # Logları Göster
            with st.expander("Salmon İşlem Logları (Tıkla Gör)", expanded=False):
                for l in logs_salmon: st.write(l)
            
            st.dataframe(df_salmon.head())
            
            os.makedirs(OUT_DIR_SALMON, exist_ok=True)
            out_file_s = os.path.join(OUT_DIR_SALMON, "SALMON_Raw_Counts_Matrix.csv")
            df_salmon.to_csv(out_file_s)
            
            st.success(f"SALMON Matrisi Kaydedildi: {out_file_s}")
            st.download_button(
                label="📥 SALMON CSV İndir",
                data=df_salmon.to_csv().encode('utf-8'),
                file_name="SALMON_Raw_Counts.csv",
                mime='text/csv'
            )
        else:
            st.warning(logs_salmon[0])

    st.balloons()
    st.success("Tüm işlemler başarıyla tamamlandı.")
