import streamlit as st
import pandas as pd
import requests
import time
import zipfile
import io
import re
import os
import shutil
import tempfile
import streamlit.components.v1 as components
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Phyre2 Smart Manager", page_icon="🧬", layout="wide")

# --- UTILS & DRIVER SETUP ---
def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1200")
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except:
        driver = webdriver.Chrome(options=chrome_options)
    return driver

def download_file_to_path(url, save_path):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        with requests.get(url, stream=True, timeout=120, headers=headers) as r:
            r.raise_for_status()
            with open(save_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        return True
    except Exception as e:
        print(f"Download error: {e}")
        return False

# --- TEMP KLASÖR KULLANAN İNDİRME FONKSİYONU ---
def fetch_single_protein_data_to_temp(url, protein_id):
    driver = get_driver()
    zip_binary_data = None
    success = False
    
    with tempfile.TemporaryDirectory() as temp_dir:
        job_folder = os.path.join(temp_dir, protein_id)
        os.makedirs(job_folder, exist_ok=True)
        
        try:
            driver.get(url)
            time.sleep(3)
            
            try:
                screenshot_path = os.path.join(job_folder, "status_view.png")
                driver.save_screenshot(screenshot_path)
            except: pass
            
            elements = driver.find_elements(By.TAG_NAME, "a")
            pdb_url, zip_url = None, None
            
            for elem in elements:
                href = elem.get_attribute("href")
                if href and "final.casp.pdb" in href: pdb_url = href; break
            if not pdb_url:
                for elem in elements:
                    href = elem.get_attribute("href")
                    if href and "final_model.pdb" in href: pdb_url = href; break
            
            for elem in elements:
                href = elem.get_attribute("href")
                if href:
                    if href.endswith(".tar.gz") and "phyre" in href: zip_url = href; break
                    elif href.endswith(".zip") and "results" in href and not zip_url: zip_url = href
            
            found_any = False
            
            if pdb_url:
                save_name = os.path.join(job_folder, f"{protein_id}.pdb")
                if download_file_to_path(pdb_url, save_name):
                    found_any = True
            
            if zip_url:
                ext = ".tar.gz" if ".tar.gz" in zip_url else ".zip"
                save_name = os.path.join(job_folder, f"{protein_id}{ext}")
                if download_file_to_path(zip_url, save_name):
                    found_any = True
            
            if found_any:
                success = True
                zip_base_name = os.path.join(temp_dir, f"{protein_id}_archive")
                shutil.make_archive(zip_base_name, 'zip', job_folder)
                
                with open(f"{zip_base_name}.zip", "rb") as f:
                    zip_binary_data = f.read()
                    
        except Exception as e:
            print(f"Fetch Error: {e}")
        finally:
            driver.quit()
            
    return success, zip_binary_data

# --- ANALİZ FONKSİYONU ---
def analyze_page_status(driver, url):
    try:
        driver.get(url)
        time.sleep(1)
        page_source = driver.page_source
        page_text = driver.find_element(By.TAG_NAME, "body").text
        
        time_match = re.search(r"Estimated total processing time.*?:(.*?)(<|\n)", page_source, re.IGNORECASE)
        step_match = re.search(r"(\d+\.\s+[^\n\r]+)", page_text)
        
        status_data = {"status": "Unknown", "details": "-", "est_time": "-", "is_complete": False}

        if "FAILED" in page_text:
            status_data["status"] = "FAILED"; status_data["details"] = "Error"
        elif "Job Status" in page_text or "Queue" in page_text or "Estimated" in page_text:
            if "Download zip of all results" not in page_text:
                status_data["status"] = "RUNNING"
                status_data["est_time"] = time_match.group(1).strip() if time_match else "Calculating..."
                status_data["details"] = step_match.group(1).strip() if step_match else "Init..."
            else:
                status_data["status"] = "COMPLETE"; status_data["details"] = "Ready"; status_data["is_complete"] = True
                status_data["est_time"] = "Done"
        else:
            status_data["status"] = "COMPLETE"; status_data["details"] = "Ready"; status_data["is_complete"] = True
            status_data["est_time"] = "Done"
            
        return status_data
    except Exception as e:
        return {"status": "ERROR", "details": str(e), "est_time": "-", "is_complete": False}

# --- JS SCROLL HELPER (GÜÇLENDİRİLMİŞ RETRY LOGIC) ---
def scroll_to_table():
    js = """
    <script>
        function attemptScroll(count) {
            var element = window.parent.document.getElementById("monitor_anchor");
            if (element) {
                // Element bulundu, hafif yukarı ofset ile kaydır
                element.scrollIntoView({behavior: "smooth", block: "start"});
            } else if (count > 0) {
                // Bulamazsa 100ms bekle tekrar dene (toplam 15 deneme)
                setTimeout(function() { attemptScroll(count - 1); }, 100);
            }
        }
        // Sayfa yüklendikten sonra aramaya başla
        attemptScroll(15);
    </script>
    """
    st.components.v1.html(js, height=0)

# --- SESSION STATE ---
if 'monitor_active' not in st.session_state: st.session_state.monitor_active = False
if 'last_scan_time' not in st.session_state: st.session_state.last_scan_time = None
if 'latest_results_list' not in st.session_state: st.session_state.latest_results_list = []
if 'cycle_count' not in st.session_state: st.session_state.cycle_count = 0
if 'file_manager' not in st.session_state: st.session_state.file_manager = {}
if 'downloader_results' not in st.session_state: st.session_state.downloader_results = []
if 'completed_ids' not in st.session_state: st.session_state.completed_ids = set()

# --- SIDEBAR ---
st.sidebar.title("🎮 Control Panel")
operation_mode = st.sidebar.radio("Select Protocol:", ("🔍 Monitor Mode", "⬇️ Downloader Mode"))
skip_completed = st.sidebar.checkbox("✅ Bitenleri Tekrar Tarama", value=True, help="Complete olanları atlar.")
st.sidebar.markdown("---")

if st.sidebar.button("🗑️ Önbelleği Sıfırla"):
    st.session_state.file_manager = {}
    st.success("Önbellek temizlendi!")
    time.sleep(1)
    st.rerun()

st.title("🧬 Phyre2 Smart Manager")

# ==========================================
# AKILLI TABLO ÇİZİCİ
# ==========================================
def render_results_table(data_list, show_buttons=True):
    h1, h2, h_time, h3, h4, h5 = st.columns([1.8, 1.2, 1.2, 2, 0.8, 2.5])
    h1.markdown("**Protein ID**")
    h2.markdown("**Status**")
    h_time.markdown("**Est. Time**")
    h3.markdown("**Current Stage**")
    h4.markdown("**Link**")
    h5.markdown("**File Manager**") 
    st.markdown("---")

    for item in data_list:
        pid = item["Protein ID"]
        safe_pid = pid.replace(" ", "_")
        status = item["Status"]
        
        c1, c2, c_time, c3, c4, c5 = st.columns([1.8, 1.2, 1.2, 2, 0.8, 2.5])
        
        c1.write(pid)
        color = "orange" if status == "RUNNING" else "green" if status == "COMPLETE" else "red"
        c2.markdown(f":{color}[{status}]")
        
        c_time.write(item.get("Est Time", "-")) 

        c3.write(item["Current Stage"])
        c4.markdown(f"[🔗 Open]({item['Result Link']})")
        
        if status == "COMPLETE":
            file_record = st.session_state.file_manager.get(pid)
            
            if file_record and file_record['status'] == 'saved':
                if show_buttons:
                    btn_col1, btn_col2 = c5.columns([1, 1])
                    btn_col1.download_button(
                        label="💾 İndir",
                        data=file_record['data'],
                        file_name=f"{safe_pid}_result.zip",
                        mime="application/zip",
                        key=f"dl_{safe_pid}"
                    )
                    if btn_col2.button("🗑️ Sil", key=f"del_{safe_pid}"):
                        st.session_state.file_manager[pid]['status'] = 'deleted'
                        st.session_state.file_manager[pid]['data'] = None 
                        st.rerun()
                else:
                    c5.markdown("💾 *Hazır*")
            
            elif file_record and file_record['status'] == 'deleted':
                if show_buttons:
                    c5.write("🗑️ *Silindi*")
                    if c5.button("♻️ Getir", key=f"refetch_{safe_pid}"):
                        st.session_state.last_scan_time = datetime.now()
                        with st.spinner("Temp klasörüne çekiliyor..."):
                            success, data = fetch_single_protein_data_to_temp(item["Result Link"], safe_pid)
                            if success:
                                st.session_state.file_manager[pid] = {'data': data, 'status': 'saved'}
                                st.rerun()
                else:
                    c5.markdown("🗑️ *Silindi*")

            else:
                if show_buttons:
                    if c5.button("📥 Getir", key=f"fetch_{safe_pid}"):
                        st.session_state.last_scan_time = datetime.now()
                        with st.spinner("Geçici (Temp) klasörde hazırlanıyor... Sayaç duraklatıldı."):
                            success, data = fetch_single_protein_data_to_temp(item["Result Link"], safe_pid)
                            if success:
                                st.session_state.file_manager[pid] = {'data': data, 'status': 'saved'}
                                st.rerun()
                            else:
                                st.error("İndirme başarısız.")
                else:
                    c5.caption("⏳ Bekliyor...")
        else:
            c5.write("-")

# ==========================================
# MONITOR MODE
# ==========================================
if operation_mode == "🔍 Monitor Mode":
    uploaded_file = st.file_uploader("Upload CSV", type=["csv"], key="monitor_csv")
    refresh_minutes = st.sidebar.slider("Cycle Wait Time (Minutes)", 1, 120, 15)
    
    info_col1, info_col2 = st.columns([3, 1])
    with info_col1:
        st.info(f"⏱️ **Döngü Süresi:** {refresh_minutes} Dakika")
    
    if uploaded_file:
        df = pd.read_csv(uploaded_file)
        
        col1, col2 = st.columns([1, 4])
        with col1:
            if not st.session_state.monitor_active:
                if st.button("▶️ Başlat", type="primary"):
                    st.session_state.monitor_active = True
                    st.session_state.last_scan_time = None
                    st.rerun()
            else:
                if st.button("⏹️ Durdur", type="secondary"):
                    st.session_state.monitor_active = False
                    st.rerun()

        st.divider()

        # Monitor Logic
        if st.session_state.monitor_active:
            now = datetime.now()
            should_scan = False
            
            if st.session_state.last_scan_time is None:
                should_scan = True
            else:
                time_diff = now - st.session_state.last_scan_time
                target_wait = timedelta(minutes=refresh_minutes)
                
                if time_diff >= target_wait:
                    should_scan = True
                else:
                    # BEKLEME MODU
                    seconds_left = (target_wait - time_diff).total_seconds()
                    
                    # --- ÇAPA NOKTASI ---
                    # Tam olarak sayacin ustune, hafif yukari kaydirarak konumlandiriyoruz.
                    st.markdown('<div id="monitor_anchor" style="position: relative; top: -50px; visibility: hidden;"></div>', unsafe_allow_html=True)
                    
                    t1, t2 = st.columns([3,1])
                    t1.caption(f"⏳ Bir sonraki tarama: {int(seconds_left // 60)}dk {int(seconds_left % 60)}sn")
                    
                    if st.session_state.latest_results_list:
                        render_results_table(st.session_state.latest_results_list, show_buttons=True)
                        # Tablo cizildikten sonra scroll fonksiyonunu cagiriyoruz
                        scroll_to_table()
                    
                    time.sleep(1)
                    st.rerun()

            if should_scan:
                st.session_state.cycle_count += 1
                temp_results_list = [] 
                
                # Tarama baslarken de anchor koyalim ki yukari kaysin
                st.markdown('<div id="monitor_anchor" style="position: relative; top: -50px; visibility: hidden;"></div>', unsafe_allow_html=True)
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                table_container = st.empty() 
                
                driver = get_driver()
                try:
                    total_items = len(df)
                    for index, row in df.iterrows():
                        protein_id = str(row.get("Protein ID", f"Protein_{index}")).strip()
                        url = row["Result Link"]
                        
                        if skip_completed and protein_id in st.session_state.completed_ids:
                            temp_results_list.append({
                                "Protein ID": protein_id,
                                "Status": "COMPLETE",
                                "Est Time": "Done",
                                "Current Stage": "Hazır (Önbellek)",
                                "Result Link": url
                            })
                            status_text.markdown(f"### ⏭️ Atlanıyor: **{protein_id}**")
                            time.sleep(0.05) 
                        else:
                            status_text.markdown(f"### 🔎 Kontrol Ediliyor: **{protein_id}**...")
                            res = analyze_page_status(driver, url)
                            
                            if res["status"] == "COMPLETE":
                                st.session_state.completed_ids.add(protein_id)
                            
                            temp_results_list.append({
                                "Protein ID": protein_id,
                                "Status": res["status"],
                                "Est Time": res["est_time"],
                                "Current Stage": res["details"],
                                "Result Link": url
                            })
                        
                        progress_bar.progress((index + 1) / total_items)
                        with table_container.container():
                            render_results_table(temp_results_list, show_buttons=False)
                            # Her adimda scroll'u tazeleyelim
                            scroll_to_table()
                    
                    status_text.success(f"✅ Döngü {st.session_state.cycle_count} Tamamlandı!")
                    time.sleep(1)
                    status_text.empty()
                    st.session_state.latest_results_list = temp_results_list
                    st.session_state.last_scan_time = datetime.now()
                    
                except Exception as e:
                    st.error(f"Scan Error: {e}")
                finally:
                    driver.quit()
                    st.rerun()

# ==========================================
# DOWNLOADER MODE
# ==========================================
elif operation_mode == "⬇️ Downloader Mode":
    st.markdown("### 📥 Toplu İndirme Modu")
    st.info("Sistem Temp klasörünü kullanarak verileri toplar ve tek bir ZIP paketi yapar.")
    
    uploaded_file_dl = st.file_uploader("Upload CSV", type=["csv"], key="dl_csv")
    
    if uploaded_file_dl:
        df_dl = pd.read_csv(uploaded_file_dl)
        
        if st.button("🚀 Listeyi Tara ve Durumu Gör", type="primary"):
            st.session_state.downloader_results = []
            progress_bar = st.progress(0)
            status_text = st.empty()
            driver = get_driver()
            temp_results = []
            try:
                total = len(df_dl)
                for index, row in df_dl.iterrows():
                    pid = str(row.get("Protein ID", f"Protein_{index}")).strip()
                    url = row["Result Link"]
                    
                    status_text.text(f"Taranıyor ({index+1}/{total}): {pid}")
                    res = analyze_page_status(driver, url)
                    
                    temp_results.append({
                        "Protein ID": pid,
                        "Status": res["status"],
                        "Est Time": res["est_time"],
                        "Result Link": url
                    })
                    progress_bar.progress((index + 1) / total)
                
                st.session_state.downloader_results = temp_results
                status_text.success("Tarama Tamamlandı!")
            except Exception as e:
                st.error(f"Hata: {e}")
            finally:
                driver.quit()
        
        if st.session_state.downloader_results:
            st.markdown("#### 📋 Sonuç Listesi")
            results_df = pd.DataFrame(st.session_state.downloader_results)
            st.dataframe(results_df, use_container_width=True)
            
            completed_jobs = [x for x in st.session_state.downloader_results if x["Status"] == "COMPLETE"]
            count_complete = len(completed_jobs)
            
            if count_complete > 0:
                st.divider()
                st.success(f"🎉 **{count_complete}** adet tamamlanmış iş bulundu.")
                
                if st.button(f"📦 Bitenleri Paketle ve İndir", type="primary"):
                    master_zip_buffer = io.BytesIO()
                    
                    with st.spinner("Dosyalar Temp klasörüne indiriliyor ve paketleniyor..."):
                        with zipfile.ZipFile(master_zip_buffer, "w", zipfile.ZIP_DEFLATED) as master_zip:
                            progress_dl = st.progress(0)
                            for idx, job in enumerate(completed_jobs):
                                pid = job["Protein ID"]
                                url = job["Result Link"]
                                safe_pid = pid.replace(" ", "_")
                                success, zip_data = fetch_single_protein_data_to_temp(url, safe_pid)
                                if success:
                                    master_zip.writestr(f"{safe_pid}_result.zip", zip_data)
                                progress_dl.progress((idx + 1) / count_complete)
                        
                        st.balloons()
                        st.download_button(
                            label="💾 ZIP Dosyasını İndir",
                            data=master_zip_buffer.getvalue(),
                            file_name="Phyre2_Toplu_Temp_Sonuc.zip",
                            mime="application/zip"
                        )
            else:
                st.warning("Henüz tamamlanmış (COMPLETE) bir iş yok.")
