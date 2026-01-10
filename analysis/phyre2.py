import streamlit as st
import requests
import time
from io import StringIO
import re
import pandas as pd
from datetime import datetime
import os
import json
import uuid

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Phyre2 Pro Suite v2", page_icon="🧬", layout="wide")

# --- CSS ---
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 5px; }
    .reportview-container { background: #fdfdfd; }
    div[data-testid="stExpander"] {
        border: 1px solid #ddd;
        border-radius: 8px;
        margin-bottom: 10px;
    }
    </style>
""", unsafe_allow_html=True)

# --- GLOBAL DEĞİŞKENLER ---
HISTORY_FILE = "phyre_sessions.json"
MAX_HISTORY = 10

# --- SESSION STATE BAŞLATMA ---
if 'results_data' not in st.session_state:
    st.session_state.results_data = []
if 'analysis_complete' not in st.session_state:
    st.session_state.analysis_complete = False
if 'current_session_id' not in st.session_state:
    st.session_state.current_session_id = None
if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0
# YENİ: Dosya ismini hafızada tutmak için değişken
if 'active_filename' not in st.session_state:
    st.session_state.active_filename = "results"

# --- GEÇMİŞ YÖNETİMİ ---
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    else:
        return []

def update_session_in_history(session_id, filename, results_list):
    history = load_history()
    
    current_session_data = {
        "id": session_id,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "filename": filename,
        "count": len(results_list),
        "data": results_list
    }
    
    found_index = -1
    for i, item in enumerate(history):
        if item["id"] == session_id:
            found_index = i
            break
    
    if found_index != -1:
        history[found_index] = current_session_data
    else:
        history.insert(0, current_session_data)
    
    if len(history) > MAX_HISTORY:
        history = history[:MAX_HISTORY]
        
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=4)
            f.flush()
            os.fsync(f.fileno())
    except Exception as e:
        st.error(f"History save error: {e}")

def delete_session(session_id):
    history = load_history()
    history = [s for s in history if s["id"] != session_id]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=4)

def clear_all_history():
    if os.path.exists(HISTORY_FILE):
        os.remove(HISTORY_FILE)

# --- SIFIRLAMA ---
def reset_app():
    st.session_state.uploader_key += 1
    st.session_state.results_data = []
    st.session_state.analysis_complete = False
    st.session_state.current_session_id = None
    st.session_state.active_filename = "results" # Dosya ismini de sıfırla
    st.rerun()

# --- BAŞLIK ---
st.title("🧬 Phyre2 Protein Modelling Automation")
st.markdown("Automated tool with **Persistent State**. Data is safe during download.")
st.divider()

# --- SIDEBAR ---
with st.sidebar:
    st.button("🔄 New Analysis / Reset", on_click=reset_app, type="primary")
    st.markdown("---")
    
    st.subheader("📂 Analysis Sessions")
    history_data = load_history()
    
    if history_data:
        if st.button("🗑️ Delete All History", type="secondary"):
            clear_all_history()
            st.rerun()
            
        st.markdown("---")
        for session in history_data:
            expander_title = f"📅 {session['date']} | 📄 {session['filename']} ({session['count']})"
            with st.expander(expander_title):
                df_session = pd.DataFrame(session['data'])
                st.dataframe(df_session, hide_index=True)
                
                csv_session = df_session.to_csv(index=False).encode('utf-8')
                st.download_button("💾 CSV", csv_session, f"{session['filename']}.csv", "text/csv", key=f"dl_{session['id']}")
                
                if st.button("❌ Delete", key=f"del_{session['id']}"):
                    delete_session(session['id'])
                    st.rerun()
    else:
        st.caption("No history available.")

    st.markdown("---")
    st.subheader("Configuration")
    email = st.text_input("E-mail Address", value="", placeholder="Enter email to enable start")
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

if uploaded_file:
    if not email:
        with col2:
            st.warning("⚠️ Lütfen analizi başlatmak için E-mail adresi giriniz.")
    else:
        stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
        content = stringio.read()
        raw_entries = [x for x in content.split('>') if x.strip()]
        
        with col2:
            st.info(f"**Status:** Ready\n\n**Total Sequences:** {len(raw_entries)}")
            
            if not st.session_state.analysis_complete:
                start_btn = st.button("🚀 Start Analysis", type="primary")
            else:
                start_btn = False
                st.success("✅ Analysis Completed!")

        # --- ANALİZ MANTIĞI ---
        if start_btn:
            # DÜZELTME: Dosya ismini hemen hafızaya alıyoruz
            st.session_state.active_filename = uploaded_file.name

            # Önceki verileri temizle
            st.session_state.results_data = []
            st.session_state.analysis_complete = False
            
            st.session_state.current_session_id = str(uuid.uuid4())
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            result_placeholder = st.empty()
            
            for i, entry in enumerate(raw_entries):
                lines = entry.strip().split('\n')
                header = lines[0].strip()
                sequence = "".join(lines[1:]).replace(" ", "") 
                
                status_text.caption(f"Processing ({i+1}/{len(raw_entries)}): {header}...")
                progress_bar.progress((i + 1) / len(raw_entries))
                
                # --- API İSTEĞİ ---
                url = "http://www.sbg.bio.ic.ac.uk/phyre2/webscripts/phyre2_submit.cgi"
                headers_http = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Referer': 'http://www.sbg.bio.ic.ac.uk/phyre2/html/page.cgi?id=index'
                }
                payload = {
                    'usr-email': email, 'seq-desc': header, 'sequence': sequence,      
                    'modelmode': mode, 'private': 'no', 
                    'type': 'academic' if 'Academic' in user_type else 'commercial' 
                }
                
                status_code = "Pending"
                result_link = ""
                current_job_id = "-"
                
                try:
                    response = requests.post(url, data=payload, headers=headers_http, timeout=45)
                    resp_text_lower = response.text.lower()
                    success_keywords = ["submitted", "success", "job id", "queue"]
                    
                    if response.status_code == 200 and any(x in resp_text_lower for x in success_keywords):
                        job_match = re.search(r"jobid=([a-zA-Z0-9]+)", response.text)
                        if job_match:
                            job_id = job_match.group(1)
                            current_job_id = job_id
                            monitor_link = f"http://www.sbg.bio.ic.ac.uk/phyre2/webscripts/jobmonitor-harry.cgi?jobid={job_id}"
                            status_code = "Completed"
                            result_link = monitor_link
                        else:
                            status_code = "Submitted (No Link)"
                    else:
                        status_code = "Failed"
                except Exception as e:
                    status_code = "Connection Error"
                
                st.session_state.results_data.append({
                    "Protein ID": header,
                    "Job ID": current_job_id,
                    "Status": status_code,
                    "Result Link": result_link
                })
                
                # --- AUTOSAVE ---
                update_session_in_history(
                    st.session_state.current_session_id, 
                    st.session_state.active_filename, # Kaydedilen ismi kullan
                    st.session_state.results_data
                )
                
                df_live = pd.DataFrame(st.session_state.results_data)
                with result_placeholder.container():
                    st.dataframe(
                        df_live,
                        column_config={
                            "Result Link": st.column_config.LinkColumn("Access", display_text="View"),
                        },
                        hide_index=True,
                        use_container_width=True
                    )

                time.sleep(bekleme_suresi)
            
            progress_bar.empty()
            status_text.success("Analysis Batch Completed.")
            st.session_state.analysis_complete = True
            st.rerun()

# --- SONUÇLARI GÖSTERME VE İNDİRME ALANI ---
if st.session_state.results_data:
    st.subheader("📊 Analysis Results")
    
    df_final = pd.DataFrame(st.session_state.results_data)
    
    st.dataframe(
        df_final,
        column_config={
            "Result Link": st.column_config.LinkColumn("Access", display_text="View"),
            "Status": st.column_config.TextColumn("Status"),
            "Job ID": st.column_config.TextColumn("Job ID", width="medium"),
        },
        hide_index=True,
        use_container_width=True
    )
    
    col_d1, col_d2 = st.columns([1, 4])
    with col_d1:
        # DÜZELTME: Artık uploaded_file objesine bağımlı değiliz.
        # Session State'teki kayıtlı ismi kullanıyoruz.
        try:
            stored_name = st.session_state.get('active_filename', 'results')
            file_name_clean = stored_name.split('.')[0]
        except:
            file_name_clean = "results"
            
        timestamp = datetime.now().strftime("%H%M")
        final_filename = f'{file_name_clean}_{timestamp}_results.csv'
        
        csv_final = df_final.to_csv(index=False).encode('utf-8')
        
        st.download_button(
            label="📥 Download CSV",
            data=csv_final,
            file_name=final_filename,
            mime='text/csv',
            type="primary"
        )
