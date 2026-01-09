import streamlit as st
import pandas as pd
import streamlit.components.v1 as components
import io

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="Gen Arama Otomasyonu Pro",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- JAVASCRIPT BİLEŞENİ (Client-Side İşlemler İçin) ---
# Streamlit sunucuda çalıştığı için tarayıcıda kopyalama ve yeni sekme açma
# işlemini bu özel HTML/JS bloğu ile yapıyoruz.
def copy_and_open_button(text_to_copy, url_to_open, button_text="📋 Kopyala & Aç"):
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        .btn {{
            background-color: #4CAF50; /* Green */
            border: none;
            color: white;
            padding: 15px 32px;
            text-align: center;
            text-decoration: none;
            display: inline-block;
            font-size: 16px;
            margin: 4px 2px;
            cursor: pointer;
            border-radius: 8px;
            width: 100%;
            font-family: sans-serif;
            font-weight: bold;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            transition: background-color 0.3s;
        }}
        .btn:hover {{ background-color: #45a049; }}
        .btn:active {{ background-color: #3e8e41; transform: translateY(2px); }}
    </style>
    </head>
    <body>
        <button class="btn" onclick="handleClick()">
            {button_text}
        </button>

        <script>
        function handleClick() {{
            const text = `{text_to_copy}`;
            const url = `{url_to_open}`;
            
            // 1. Panoya Kopyala
            const textArea = document.createElement("textarea");
            textArea.value = text;
            document.body.appendChild(textArea);
            textArea.select();
            try {{
                document.execCommand('copy');
            }} catch (err) {{
                console.error('Kopyalama hatası', err);
            }}
            document.body.removeChild(textArea);
            
            // 2. Yeni Sekmede Aç
            window.open(url, '_blank');
        }}
        </script>
    </body>
    </html>
    """
    # Yüksekliği butona göre ayarlıyoruz
    return components.html(html_code, height=70)

# --- ANA FONKSİYONLAR ---

def load_data(file):
    try:
        if file.name.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
        return df
    except Exception as e:
        st.error(f"Dosya okunamadı: {e}")
        return None

# --- ARAYÜZ ---

st.title("🧬 Insect Genome Çalışma İstasyonu")
st.markdown("""
Bu araç, Excel listenizdeki genleri **sırasıyla** taramanızı sağlar. 
Odak modu sayesinde listede kaybolmadan tek tuşla veriyi kopyalar ve siteyi açar.
""")

# --- SIDEBAR (AYARLAR) ---
with st.sidebar:
    st.header("1. Veri Yükle")
    uploaded_file = st.file_uploader("Excel veya CSV Seç", type=['xlsx', 'xls', 'csv'])
    
    st.header("2. Ayarlar")
    url_template = st.text_input(
        "Hedef URL Şablonu", 
        value="https://www.insect-genome.com/search?q={ID}",
        help="Gen ID'nin geleceği yere {ID} yazın."
    )
    
    st.info("İpucu: URL içinde {ID} yazan yer, otomatik olarak tablodaki gen koduyla değiştirilir.")

# --- ANA AKIŞ ---

if uploaded_file is not None:
    # Veriyi Yükle
    if 'df' not in st.session_state or st.session_state.get('file_name') != uploaded_file.name:
        df = load_data(uploaded_file)
        if df is not None:
            st.session_state.df = df
            st.session_state.file_name = uploaded_file.name
            # Otomatik sütun tahmini
            cols = df.columns.tolist()
            default_col_idx = 0
            for i, col in enumerate(cols):
                if "seq" in col.lower() or "id" in col.lower() or "gen" in col.lower():
                    default_col_idx = i
                    break
            st.session_state.selected_col_idx = default_col_idx
            st.session_state.current_index = 0
            st.session_state.processed_indices = set()

    df = st.session_state.df
    
    # Sütun Seçimi
    col1, col2 = st.columns([1, 3])
    with col1:
        target_col = st.selectbox(
            "Hangi Sütun Gen ID İçeriyor?", 
            df.columns, 
            index=st.session_state.get('selected_col_idx', 0)
        )
    
    # --- ÇALIŞMA MODLARI ---
    tab1, tab2 = st.tabs(["🎯 Odak Modu (Sıralı)", "📊 Tüm Liste"])

    # TAB 1: ODAK MODU (FOCUS MODE)
    with tab1:
        if df is not None and target_col:
            total_rows = len(df)
            current_idx = st.session_state.current_index
            
            # İlerleme Çubuğu
            progress = (len(st.session_state.processed_indices) / total_rows)
            st.progress(progress, text=f"İlerleme: {len(st.session_state.processed_indices)} / {total_rows}")

            # Navigasyon Kontrolleri
            col_prev, col_stat, col_next = st.columns([1, 2, 1])
            
            with col_prev:
                if st.button("⬅️ Önceki", use_container_width=True):
                    if st.session_state.current_index > 0:
                        st.session_state.current_index -= 1
                        st.rerun()
            
            with col_next:
                if st.button("Sonraki ➡️", use_container_width=True):
                    if st.session_state.current_index < total_rows - 1:
                        st.session_state.current_index += 1
                        st.session_state.processed_indices.add(current_idx) # Şuankini yapıldı say
                        st.rerun()

            with col_stat:
                st.markdown(f"<div style='text-align:center; font-weight:bold; padding-top:10px;'>Kayıt {current_idx + 1} / {total_rows}</div>", unsafe_allow_html=True)

            # --- KART GÖRÜNÜMÜ ---
            st.markdown("---")
            row = df.iloc[current_idx]
            gene_id = str(row[target_col])
            
            # URL Oluşturma
            final_url = url_template.replace("{ID}", gene_id.strip())

            c1, c2 = st.columns([2, 1])
            
            with c1:
                st.subheader("🧬 Mevcut Gen ID")
                st.code(gene_id, language="text")
                
                # Diğer bilgileri göster (Expandable)
                with st.expander("Bu satırdaki diğer veriler"):
                    st.json(row.to_dict())

            with c2:
                st.markdown("### ⚡ Aksiyon")
                st.caption("Butona basınca kopyalar ve siteyi açar.")
                
                # Custom JS Buton
                copy_and_open_button(gene_id, final_url)
                
                # Manuel İşaretleme
                if current_idx in st.session_state.processed_indices:
                    st.success("✅ Bu kayıt incelendi.")
                else:
                    if st.button("İncelendi İşaretle", key="mark_done"):
                        st.session_state.processed_indices.add(current_idx)
                        st.rerun()

    # TAB 2: TÜM LİSTE
    with tab2:
        st.dataframe(df, use_container_width=True)
        
        # Rapor İndirme
        if st.button("Raporu İndir (.csv)"):
            # Orijinal veriye 'Durum' sütunu ekle
            export_df = df.copy()
            export_df['Durum'] = ['İncelendi' if i in st.session_state.processed_indices else 'Bekliyor' for i in range(len(df))]
            
            csv = export_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 CSV Olarak İndir",
                data=csv,
                file_name='gen_calisma_raporu.csv',
                mime='text/csv',
            )

else:
    st.info("Lütfen sol menüden bir Excel dosyası yükleyin.")
