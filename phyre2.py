import streamlit as st
import requests
import time
from io import StringIO
import re
import pandas as pd
from datetime import datetime
import os

# Sayfa Ayarları (Wide mode)
st.set_page_config(page_title="Phyre2 Analysis Tool", page_icon="🧬", layout="wide")

# --- CSS İLE PROFESYONEL GÖRÜNÜM ---
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 5px; }
    .reportview-container { background: #fdfdfd; }
    header { visibility: hidden; }
    </style>
""", unsafe_allow_html=True)

# --- AYARLAR ---
HISTORY_FILE = "phyre_history.csv"
MAX_HISTORY = 50

# --- GEÇMİŞ YÖNETİMİ ---
def load_history():
    if os.path.exists(HISTORY_FILE):
        return pd.read_csv(HISTORY_FILE)
    else:
        return pd.DataFrame(columns=["Tarih", "Protein", "Job_ID", "Link"])

def save_to_history(protein_name, job_id, link):
    df = load_history()
    tarih = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_row = pd.DataFrame([{
        "Tarih": tarih,
        "Protein": protein_name,
        "Job_ID": job_id,
        "Link": link
    }])
    df = pd.concat([new_row, df], ignore_index=True)
    if len(df) > MAX_HISTORY:
        df = df.head(MAX_HISTORY)
    df.to_csv(HISTORY_FILE, index=False)

# --- SIFIRLAMA ---
if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

def reset_app():
    st.session_state.uploader_key += 1

# --- BAŞLIK ---
st.title("🧬 Phyre2 Protein Modelling Automation")
st.markdown("Automated submission tool for high-throughput protein structure prediction.")
st.divider()

# --- SIDEBAR (Geçmiş) ---
with st.sidebar:
    st.button("🔄 New Analysis / Reset", on_click=reset_app, type="primary")
    st.markdown("---")
    
    st.subheader("📜 Analysis History")
    history_placeholder = st.empty()

    def render_sidebar_history():
        history_df = load_history()
        with history_placeholder.container():
            if not history_df.empty:
                # Profesyonel Tablo Görünümü
                st.dataframe(
                    history_df,
                    column_config={
                        "Link": st.column_config.LinkColumn(
                            "Result", display_text="Open Link"
                        ),
                        "Tarih": st.column_config.TextColumn("Date", width="small"),
                        "Protein": st.column_config.TextColumn("Protein ID"),
                        # --- GÜNCELLEME: Job ID artık görünür ---
                        "Job_ID": st.column_config.TextColumn("Job ID", width="medium"),
                    },
                    hide_index=True,
                    use_container_width=True
                )
                csv_history = history_df.to_csv(index=False).encode('utf-8')
                st.download_button("💾 Download History (CSV)", csv_history, "analysis_history.csv", "text/csv")
            else:
                st.caption("No history available.")

    render_sidebar_history()

    st.markdown("---")
    st.subheader("Configuration")
    email = st.text_input("E-mail Address", value="muratturan077@gmail.com")
    mode = st.selectbox("Modelling Mode", ["normal", "intensive"])
    user_type = st.radio("User Type", ["Academic", "Commercial"], index=0)
    bekleme_suresi = st.number_input("Delay (sec)", 0.5, 30.0, 2.0, 0.1)

# --- ANA EKRAN ---
col1, col2 = st.columns([2, 1])

with col1:
    uploaded_file = st.file_uploader(
        "Upload Protein FASTA File", 
        type=["fa", "fasta", "txt"],
        key=f"uploader_{st.session_state.uploader_key}" 
    )

if uploaded_file and email:
    stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
    content = stringio.read()
    raw_entries = [x for x in content.split('>') if x.strip()]
    
    with col2:
        st.info(f"**Status:** Ready\n\n**Total Sequences:** {len(raw_entries)}")
        start_btn = st.button("🚀 Start Analysis", type="primary")
    
    if start_btn:
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        st.subheader("Analysis Log")
        result_placeholder = st.empty()
        current_results = [] 

        for i, entry in enumerate(raw_entries):
            lines = entry.strip().split('\n')
            header = lines[0].strip()
            sequence = "".join(lines[1:]).replace(" ", "") 
            
            status_text.caption(f"Processing ({i+1}/{len(raw_entries)}): {header}...")
            progress_bar.progress((i + 1) / len(raw_entries))
            
            url = "http://www.sbg.bio.ic.ac.uk/phyre2/webscripts/phyre2_submit.cgi"
            
            headers_http = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'http://www.sbg.bio.ic.ac.uk/phyre2/html/page.cgi?id=index'
            }

            payload = {
                'usr-email': email,      
                'seq-desc': header,      
                'sequence': sequence,    
                'modelmode': mode,
                'private': 'no', 
                'type': 'academic' if 'Academic' in user_type else 'commercial' 
            }
            
            status_code = "Pending"
            result_link = ""
            current_job_id = "-" # Varsayılan boş ID
            
            try:
                response = requests.post(url, data=payload, headers=headers_http, timeout=45)
                resp_text_lower = response.text.lower()
                success_keywords = ["submitted", "success", "job id", "queue"]
                
                if response.status_code == 200 and any(x in resp_text_lower for x in success_keywords):
                    job_match = re.search(r"jobid=([a-zA-Z0-9]+)", response.text)
                    if job_match:
                        job_id = job_match.group(1)
                        current_job_id = job_id # ID'yi yakaladık
                        monitor_link = f"http://www.sbg.bio.ic.ac.uk/phyre2/webscripts/jobmonitor-harry.cgi?jobid={job_id}"
                        
                        save_to_history(header, job_id, monitor_link)
                        render_sidebar_history() 
                        
                        status_code = "Completed"
                        result_link = monitor_link
                    else:
                        status_code = "Submitted (No Link)"
                else:
                    status_code = "Failed"
                    
            except Exception as e:
                status_code = "Connection Error"
            
            # --- TABLO VERİSİNE JOB ID EKLENDİ ---
            current_results.append({
                "Index": i+1,
                "Protein ID": header,
                "Job ID": current_job_id, # Yeni Sütun
                "Status": status_code,
                "Result Link": result_link
            })
            
            # CANLI TABLOYU GÜNCELLE
            df_live = pd.DataFrame(current_results)
            with result_placeholder.container():
                st.dataframe(
                    df_live,
                    column_config={
                        "Result Link": st.column_config.LinkColumn(
                            "Access", display_text="View Result"
                        ),
                        "Status": st.column_config.TextColumn("Status"),
                        "Job ID": st.column_config.TextColumn("Phyre2 Job ID", width="medium"),
                    },
                    hide_index=True,
                    use_container_width=True
                )

            time.sleep(bekleme_suresi)
            
        progress_bar.empty()
        status_text.success("All sequences processed successfully.")
        
        if current_results:
            df_final = pd.DataFrame(current_results)
            csv_final = df_final.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Report (CSV)", csv_final, 'session_report.csv', 'text/csv', type="primary")

elif not email and uploaded_file:
    st.warning("Please enter your e-mail address to proceed.")
