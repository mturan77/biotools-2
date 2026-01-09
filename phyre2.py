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

# Sayfa Ayarları (Wide mode)
st.set_page_config(page_title="Phyre2 Pro Suite", page_icon="🧬", layout="wide")

# --- CSS DÜZELTMESİ ---
# BURASI DEĞİŞTİ: 'header { visibility: hidden; }' satırını sildik.
# Artık üst menü ve STOP butonu görünecek.
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 5px; }
    .reportview-container { background: #fdfdfd; }
    
    /* Delete butonu için özel stil */
    div[data-testid="stExpander"] {
        border: 1px solid #ddd;
        border-radius: 8px;
        margin-bottom: 10px;
    }
    </style>
""", unsafe_allow_html=True)

# --- AYARLAR ---
HISTORY_FILE = "phyre_sessions.json" 
MAX_HISTORY = 10 

# --- GEÇMİŞ YÖNETİMİ (JSON) ---
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    else:
        return []

def save_session(filename, results_list):
    history = load_history()
    new_session = {
        "id": str(uuid.uuid4()),
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "filename": filename,
        "count": len(results_list),
        "data": results_list
    }
    history.insert(0, new_session)
    if len(history) > MAX_HISTORY:
        history = history[:MAX_HISTORY]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=4)

def delete_session(session_id):
    history = load_history()
    history = [s for s in history if s["id"] != session_id]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=4)

def clear_all_history():
    if os.path.exists(HISTORY_FILE):
        os.remove(HISTORY_FILE)

# --- SIFIRLAMA ---
if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

def reset_app():
    st.session_state.uploader_key += 1

# --- BAŞLIK ---
st.title("🧬 Phyre2 Protein Modelling Automation")
st.markdown("Automated submission tool with **Grouped History** management.")
st.divider()

# --- SIDEBAR (Geçmiş) ---
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
                st.dataframe(
                    df_session,
                    column_config={
                        "Result Link": st.column_config.LinkColumn("Result", display_text="Open"),
                        "Job ID": st.column_config.TextColumn("ID", width="small"),
                        "Status": st.column_config.TextColumn("Stat", width="small"),
                    },
                    hide_index=True,
                    use_container_width=True
                )
                
                csv_session = df_session.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "💾 Download CSV", 
                    csv_session, 
                    f"{session['filename']}_results.csv", 
                    "text/csv",
                    key=f"dl_{session['id']}"
                )
                
                if st.button("❌ Delete This Session", key=f"del_{session['id']}"):
                    delete_session(session['id'])
                    st.rerun()

    else:
        st.caption("No history available.")

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
        
        st.subheader("Current Analysis Log")
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
            
            current_results.append({
                "Protein ID": header,
                "Job ID": current_job_id,
                "Status": status_code,
                "Result Link": result_link
            })
            
            df_live = pd.DataFrame(current_results)
            with result_placeholder.container():
                st.dataframe(
                    df_live,
                    column_config={
                        "Result Link": st.column_config.LinkColumn("Access", display_text="View"),
                        "Status": st.column_config.TextColumn("Status"),
                        "Job ID": st.column_config.TextColumn("Job ID", width="medium"),
                    },
                    hide_index=True,
                    use_container_width=True
                )

            time.sleep(bekleme_suresi)
            
        progress_bar.empty()
        status_text.success("Analysis Batch Completed.")
        
        save_session(uploaded_file.name, current_results)
        
        st.toast("Analysis saved to history!", icon="💾")
        
        if current_results:
            df_final = pd.DataFrame(current_results)
            csv_final = df_final.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Batch Report (CSV)", csv_final, 'batch_report.csv', 'text/csv', type="primary")

elif not email and uploaded_file:
    st.warning("Please enter your e-mail address to proceed.")
