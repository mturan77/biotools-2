import streamlit as st
import pandas as pd
import streamlit.components.v1 as components
import urllib.parse # URL'deki boşlukları %20 yapmak için gerekli

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="Insect Genome Pro",
    page_icon="🦟",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS / STİL ---
st.markdown("""
<style>
    .big-font { font-size:24px !important; font-weight: bold; color: #2c3e50; }
    .status-ok { color: #27ae60; font-weight: bold; }
    .status-wait { color: #f39c12; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- JAVASCRIPT BİLEŞENİ (Kopyala ve Aç) ---
def copy_and_open_button(text_to_copy, url_to_open, button_text="🚀 Kopyala ve Git"):
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        .btn {{
            background-color: #2980b9; 
            border: none; color: white; padding: 16px 24px;
            text-align: center; text-decoration: none;
            display: block; font-size: 18px; margin: 0px;
            cursor: pointer; border-radius: 8px; width: 100%;
            font-family: 'Segoe UI', sans-serif; font-weight: 600;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            transition: all 0.2s;
        }}
        .btn:hover {{ background-color: #3498db; transform: translateY(-2px); }}
        .btn:active {{ transform: translateY(0px); }}
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
            
            // Panoya Kopyala
            const textArea = document.createElement("textarea");
            textArea.value = text;
            document.body.appendChild(textArea);
            textArea.select();
            try {{ document.execCommand('copy'); }} catch (err) {{}}
            document.body.removeChild(textArea);
            
            // Yeni Sekmede Aç
            window.open(url, '_blank');
        }}
        </script>
    </body>
    </html>
    """
    return components.html(html_code, height=80)

# --- ANA UYGULAMA ---

st.title("🦟 Insect Genome Çalışma Aracı")

# --- SIDEBAR (AYARLAR) ---
with st.sidebar:
    st.header("📂 1. Dosya Yükle")
    uploaded_file = st.file_uploader("Excel Listesi", type=['xlsx', 'xls', 'csv'])
    
    st.divider()
    
    st.header("⚙️ 2. URL Ayarları")
    # Kullanıcının tür ismini girmesini istiyoruz
    species_input = st.text_input("Tür Adı (Species)", value="musca domestica")
    st.caption("Örn: `musca domestica`. Boşluklar otomatik olarak linke uygun hale getirilir.")

    st.divider()
    st.info("Bu araç; yazdığınız tür adını ve Excel'deki ID'yi birleştirerek doğrudan gen sayfasına yönlendirir.")

# --- MANTIK ---

if uploaded_file is not None:
    # State Yönetimi (Sayfa yenilenince veriler kaybolmasın)
    if 'df' not in st.session_state or st.session_state.get('file_name') != uploaded_file.name:
        try:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            
            st.session_state.df = df
            st.session_state.file_name = uploaded_file.name
            st.session_state.current_index = 0
            st.session_state.processed_indices = set()
            
            # Sütun tahmini
            cols = df.columns.tolist()
            default_col = cols[0]
            for col in cols:
                if any(x in col.lower() for x in ['seq', 'id', 'gen', 'accession']):
                    default_col = col
                    break
            st.session_state.target_col = default_col
            
        except Exception as e:
            st.error(f"Dosya hatası: {e}")

    df = st.session_state.df
    
    # Ana Ekran Düzeni
    col_sel, col_info = st.columns([1, 2])
    with col_sel:
        target_col = st.selectbox("Hangi sütun Gen ID?", df.columns, index=df.columns.get_loc(st.session_state.target_col))
    
    # URL Parçalarını Hazırla
    # Tür ismindeki boşlukları %20 yapar (musca domestica -> musca%20domestica)
    encoded_species = urllib.parse.quote(species_input.strip())
    
    # --- SEKME YAPISI ---
    tab_focus, tab_list = st.tabs(["🔍 Odak Modu (Sıralı)", "📋 Tüm Liste"])

    # 1. ODAK MODU
    with tab_focus:
        total = len(df)
        curr = st.session_state.current_index
        
        # Navigasyon
        c_prev, c_prog, c_next = st.columns([1, 4, 1])
        with c_prev:
            if st.button("⬅️ Geri", use_container_width=True):
                if curr > 0: st.session_state.current_index -= 1; st.rerun()
        with c_next:
            if st.button("İleri ➡️", use_container_width=True):
                if curr < total - 1: st.session_state.current_index += 1; st.rerun()
        with c_prog:
            st.progress((curr + 1) / total, text=f"Sıra: {curr + 1} / {total}")

        # Kart Gösterimi
        st.markdown("---")
        row = df.iloc[curr]
        gene_id = str(row[target_col]).strip()
        
        # URL OLUŞTURMA (KRİTİK KISIM)
        # Yapı: https://www.insect-genome.com/gene/musca%20domestica/Mdom002507.1
        final_url = f"https://www.insect-genome.com/gene/{encoded_species}/{gene_id}"

        col_card_L, col_card_R = st.columns([1, 1])
        
        with col_card_L:
            st.caption("Mevcut Gen ID:")
            st.markdown(f"<div class='big-font'>{gene_id}</div>", unsafe_allow_html=True)
            st.text(f"Tür: {species_input}")
            
            with st.expander("Satır Detayları"):
                st.write(row.to_dict())

        with col_card_R:
            st.caption("İşlem:")
            # JS Butonu
            copy_and_open_button(gene_id, final_url)
            
            # İncelendi Butonu
            is_done = curr in st.session_state.processed_indices
            if is_done:
                st.success("✅ Bu gen incelendi.")
            else:
                if st.button("Tamamlandı İşaretle", key=f"btn_{curr}"):
                    st.session_state.processed_indices.add(curr)
                    st.rerun()

    # 2. LİSTE GÖRÜNÜMÜ
    with tab_list:
        # İndirilebilir Rapor
        st.write("Verilerinizi kontrol edin ve raporu indirin.")
        
        preview_df = df.copy()
        preview_df['Durum'] = ['✅ İncelendi' if i in st.session_state.processed_indices else '⏳ Bekliyor' for i in range(len(df))]
        
        st.dataframe(preview_df, use_container_width=True)
        
        csv_data = preview_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Raporu İndir (.csv)", csv_data, "gen_calisma_raporu.csv", "text/csv")

else:
    st.info("👈 Başlamak için soldan Excel dosyasını yükleyin.")
