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
st.info("Bu uygulama dosyaları 'upload' etmez. Bilgisayarınızdaki klasör yolunu okuyarak çalışır.")

# ==============================================================================
# SIDEBAR AYARLARI
# ==============================================================================
st.sidebar.header("📂 Klasör ve Dosya Yolları")

# Varsayılan değerler
default_base_dir = "/home/mutu/Desktop/Musca-rpkm/6-TPM/"
default_gff = os.path.join(default_base_dir, "Musca_veriler_yedek/Musca_domestica.gff3")

# 1. ANA KLASÖR GİRİŞİ (Folder Input)
st.sidebar.markdown("### 1. Ana Çalışma Klasörü")
BASE_DIR = st.sidebar.text_input("Klasör Yolunu Yapıştırın:", value=default_base_dir, help="BAM ve Quant dosyalarının bulunduğu ana klasör.")

# Klasör kontrolü (Validasyon)
if os.path.isdir(BASE_DIR):
    st.sidebar.success("✅ Klasör bulundu.")
else:
    st.sidebar.error("❌ Klasör bulunamadı! Lütfen yolu kontrol edin.")

# 2. GFF DOSYASI GİRİŞİ
st.sidebar.markdown("### 2. GFF Dosyası")
GFF_FILE = st.sidebar.text_input("GFF Dosya Yolu:", value=default_gff)

if os.path.exists(GFF_FILE):
    st.sidebar.success("✅ GFF dosyası bulundu.")
else:
    st.sidebar.error("❌ GFF dosyası bulunamadı!")

st.sidebar.markdown("---")
st.sidebar.subheader("🔍 Arama Ayarları")
# Kullanıcı buraya klasör değil, klasör içindeki desen şablonunu giriyor
SEARCH_PATTERN_BAM = st.sidebar.text_input("BAM Arama Deseni (Glob)", value="**/bam_files_final/*.bam")
SEARCH_PATTERN_QUANT = st.sidebar.text_input("Salmon Arama Deseni (Glob)", value="**/*_quant/quant.sf")

st.sidebar.subheader("⚙️ Analiz Modu")
mode_selection = st.sidebar.radio("Hangi analiz yapılsın?", ("Her İkisi (3)", "Sadece HISAT/BAM (1)", "Sadece SALMON (2)"))

MODE = 3
if "Sadece HISAT" in mode_selection: MODE = 1
elif "Sadece SALMON" in mode_selection: MODE = 2

st.sidebar.subheader("🎚️ BAM Hassasiyeti")
MIN_MAPQ = st.sidebar.number_input("Min MapQ", value=1, min_value=0)

# Çıktı Klasörleri
OUT_DIR_HISAT = os.path.join(BASE_DIR, "DESeq2_Input_HISAT_Verbose")
OUT_DIR_SALMON = os.path.join(BASE_DIR, "DESeq2_Input_SALMON_Verbose")

# ==============================================================================
# BUTONLAR
# ==============================================================================
if st.sidebar.button("🧹 Önbelleği Temizle / Sıfırla", type="primary"):
    st.cache_data.clear()
    st.cache_resource.clear()
    st.rerun()

# ==============================================================================
# FONKSİYONLAR
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

@st.cache_data(show_spinner=False)
def parse_gff_cached(gff_path):
    # Bu fonksiyon sadece dosya yolu doğruysa çalışır
    genes = {} 
    tx2gene = {}
    rna_parent_map = {}
    unique_chroms = set()

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
        
        return genes, tx2gene, f"✅ GFF Okundu. Toplam Gen: {len(genes)}."
    except Exception as e:
        return None, None, str(e)

# BAM Process
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
            if not os.path.exists(bam_path + ".bai"):
                pysam.index(bam_path)
            
            samfile = pysam.AlignmentFile(bam_path, "rb")
            bam_refs = set(samfile.references)
            
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

            file_progress = st.progress(0)
            total_chroms_to_scan = len(chrom_map)
            chrom_processed_count = 0

            for g_chrom, target_chrom in chrom_map.items():
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
            
            file_progress.empty()
            logs.append(f"✅ {base_name}: {total_assigned_reads} okuma atandı.")
            md_hisat[base_name.replace(".bam", "")] = counts
            samfile.close()

        except Exception as e:
            logs.append(f"🛑 HATA {base_name}: {e}")
            md_hisat[base_name.replace(".bam", "")] = {}

    overall_progress.progress(1.0)
    status_text.text("BAM analizi tamamlandı.")
    
    df_h = pd.DataFrame(index=sorted(list(all_genes_h)))
    for s, c in md_hisat.items():
        df_h[s] = pd.Series(c).reindex(df_h.index, fill_value=0)
    
    return df_h.fillna(0).astype(int), logs

# Salmon Process
def process_salmon_files(full_pattern, tx2gene):
    quant_files = glob.glob(full_pattern, recursive=True)
    
    if not quant_files:
        return None, [f"Dosya bulunamadı. Aranan yol: {full_pattern}"]

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
            logs.append(f"🔹 {s_name}: {int(grouped.sum())} okuma.")
        except Exception as e:
            logs.append(f"🛑 HATA {s_name}: {e}")

    df_f = pd.DataFrame(index=sorted(list(all_genes)))
    for s, c in master_data.items():
        df_f[s] = pd.Series(c).reindex(df_f.index, fill_value=0)
    
    return df_f.fillna(0).round().astype(int), logs

# ==============================================================================
# ANA AKIŞ
# ==============================================================================

if st.button("🚀 Analizi Başlat", type="primary"):
    
    # 1. Klasör Kontrolü
    if not os.path.isdir(BASE_DIR):
        st.error(f"🛑 HATA: Ana klasör yolu yanlış veya erişilemiyor:\n{BASE_DIR}")
        st.stop()
    
    # 2. GFF Kontrolü
    if not os.path.exists(GFF_FILE):
        st.error(f"🛑 HATA: GFF dosyası bulunamadı:\n{GFF_FILE}")
        st.stop()

    # 3. GFF İşleme
    with st.spinner('GFF dosyası işleniyor...'):
        gene_db, tx2gene, msg = parse_gff_cached(GFF_FILE)
    
    if gene_db is None:
        st.error(msg)
        st.stop()
    else:
        st.info(msg)

    # 4. BAM Analizi
    if MODE == 1 or MODE == 3:
        st.subheader("📊 HISAT/BAM Analizi")
        # Klasör + Desen birleştirme
        full_bam_pattern = os.path.join(BASE_DIR, SEARCH_PATTERN_BAM)
        bam_files = glob.glob(full_bam_pattern, recursive=True)
        
        st.write(f"📂 Aranan Yol: `{full_bam_pattern}`")
        
        if bam_files:
            st.success(f"📄 {len(bam_files)} adet BAM dosyası bulundu.")
            with st.spinner("BAM dosyaları sayılıyor..."):
                df_hisat, logs_hisat = process_bam_files(bam_files, gene_db)
            
            with st.expander("Detaylı Loglar", expanded=False):
                for l in logs_hisat: st.write(l)
            
            st.dataframe(df_hisat.head())
            
            os.makedirs(OUT_DIR_HISAT, exist_ok=True)
            out_file_h = os.path.join(OUT_DIR_HISAT, "HISAT_Raw_Counts_Matrix_Verbose.csv")
            df_hisat.to_csv(out_file_h)
            st.success(f"Kaydedildi: {out_file_h}")
            
            st.download_button("📥 BAM Sonuçlarını İndir (CSV)", df_hisat.to_csv().encode('utf-8'), "HISAT_Counts.csv", "text/csv")
        else:
            st.error("⚠️ Hiç BAM dosyası bulunamadı! Arama desenini veya klasör yolunu kontrol edin.")

    st.markdown("---")

    # 5. SALMON Analizi
    if MODE == 2 or MODE == 3:
        st.subheader("🐟 SALMON Analizi")
        full_quant_pattern = os.path.join(BASE_DIR, SEARCH_PATTERN_QUANT)
        st.write(f"📂 Aranan Yol: `{full_quant_pattern}`")
        
        with st.spinner("Salmon dosyaları işleniyor..."):
            df_salmon, logs_salmon = process_salmon_files(full_quant_pattern, tx2gene)
        
        if df_salmon is not None:
            with st.expander("Detaylı Loglar", expanded=False):
                for l in logs_salmon: st.write(l)
            
            st.dataframe(df_salmon.head())
            
            os.makedirs(OUT_DIR_SALMON, exist_ok=True)
            out_file_s = os.path.join(OUT_DIR_SALMON, "SALMON_Raw_Counts_Matrix.csv")
            df_salmon.to_csv(out_file_s)
            st.success(f"Kaydedildi: {out_file_s}")
            
            st.download_button("📥 SALMON Sonuçlarını İndir (CSV)", df_salmon.to_csv().encode('utf-8'), "SALMON_Counts.csv", "text/csv")
        else:
            st.error("⚠️ Salmon dosyası bulunamadı!")

    st.balloons()
