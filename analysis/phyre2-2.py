import streamlit as st
import pandas as pd
import requests
import time
import zipfile
import io
import re
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

def download_content(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, stream=True, timeout=60, headers=headers)
        if r.status_code == 200:
            return r.content
    except:
        return None
    return None

# --- TEKİL İNDİRME FONKSİYONU ---
def fetch_single_protein_data(url, protein_id):
    driver = get_driver()
    zip_buffer = io.BytesIO()
    success = False
    
    try:
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as single_zip:
            folder = f"{protein_id}/"
            driver.get(url)
            time.sleep(2)
            
            # Screenshot
            try:
                png_data = driver.get_screenshot_as_png()
                single_zip.writestr(f"{folder}status_view.png", png_data)
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
                c = download_content(pdb_url)
                if c: 
                    single_zip.writestr(f"{folder}{protein_id}.pdb", c)
                    found_any = True
            
            if zip_url:
                c = download_content(zip_url)
                if c: 
                    ext = ".tar.gz" if ".tar.gz" in zip_url else ".zip"
                    single_zip.writestr(f"{folder}{protein_id}{ext}", c)
                    found_any = True
            
            if found_any:
                success = True
            
    except Exception as e:
        print(e)
    finally:
        driver.quit()
        
    return success, zip_buffer.getvalue()

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
        else:
            status_data["status"] = "COMPLETE"; status_data["details"] = "Ready"; status_data["is_complete"] = True
            
        return status_data
    except Exception as e:
        return {"status": "ERROR", "details": str(e), "est_time": "-", "is_complete": False}

# --- SESSION STATE (AKILLI HAFIZA) ---
if 'monitor_active' not in st.session_state: st.session_state.monitor_active = False
if 'last_scan_time' not in st.session_state: st.session_state.last_scan_time = None
if 'latest_results_list' not in st.session_state: st.session_state.latest_results_list = []
if 'cycle_count' not in st.session_state: st.session_state.cycle_count = 0

# Dosya Yöneticisi: { 'ProteinID': {'data': binary, 'status': 'saved'/'deleted'} }
if 'file_manager' not in st.session_state: st.session_state.file_manager = {}

# Tamamlanan Görevler Listesi (Tekrar taramamak için)
if 'completed_ids' not in st.session_state: st.session_state.completed_ids = set()

# --- SIDEBAR ---
st.sidebar.title("🎮 Control Panel")
operation_mode = st.sidebar.radio("Select Protocol:", ("🔍 Monitor Mode", "⬇️ Downloader Mode"))

# YENİ ÖZELLİK: Tamamlananları Atla
skip_completed = st.sidebar.checkbox("✅ Bitenleri Tekrar Tarama", value=True, help="İşaretliyse, daha önce bitmiş olan genleri tekrar kontrol etmez.")

st.title("
