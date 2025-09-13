# test-shorts.py
# -*- coding: utf-8 -*-
import os, sys, time, json, threading, smtplib, ssl, re, shutil, glob, tempfile, subprocess
from dataclasses import dataclass, asdict, field
from typing import Optional, Dict, Any, List, Tuple
from email.mime.text import MIMEText
from urllib.parse import urlparse, parse_qs

# ====== USER CONFIG ======
DEFAULT_CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
FALLBACK_VERSION_MAIN = 140
PLAY_VIDEOS = False

# Login davranışı
LOGIN_MODE = 'auto'          # 'auto' | 'off' | 'force'
CHALLENGE_MAX_WAIT = 180     # Tek tek challenge bekleme üst limiti (sn)
START_AFTER_LOGIN = 'soft'   # 'require' | 'soft' | 'none'
LOGIN_GATE_WAIT = 90
ABORT_ON_2FA = True
# =========================

def _ensure_deps():
    try:
        import undetected_chromedriver, selenium, requests  # noqa
    except Exception:
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade",
                            "undetected-chromedriver", "selenium", "requests"],
                           check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
try: _ensure_deps()
except Exception: pass

os.environ["QT_OPENGL"] = "software"
os.environ["QT_QUICK_BACKEND"] = "software"

from PySide6.QtCore import Qt, Signal, QObject, QTime
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
    QPushButton, QLabel, QSpinBox, QLineEdit, QListWidgetItem, QToolBar,
    QProgressBar, QMessageBox, QDialog, QDialogButtonBox, QFormLayout,
    QTimeEdit, QComboBox, QTextEdit, QListWidgetItem as QLI, QCheckBox,
    QFrame  # ← eklendi
)

import requests
import undetected_chromedriver as uc
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By

APP_DIR  = os.path.dirname(__file__)
APP_NAME = "URL Rotator (UC + Chrome140 Fix)"
APP_ICON = os.path.join(APP_DIR, "img", "favicon.png")

URLLIST_FILE       = os.path.join(APP_DIR, "shorts-urllist.json")
SCHEDULE_FILE      = os.path.join(APP_DIR, "schedule.json")
SMTP_FILE          = os.path.join(APP_DIR, "smtp.json")
MAIL_ACCOUNTS_FILE = os.path.join(APP_DIR, "mail_accounts.json")

LOG_DIR = os.path.join(APP_DIR, "logs"); os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "short-log.txt")

def _ts(): return time.strftime("%Y-%m-%d %H:%M:%S")
def log_append(widget: Optional[QTextEdit], text: str):
    line = f"[{_ts()}] {text}"
    try:
        if widget:
            if widget.document().blockCount() > 2000:
                cur = widget.textCursor()
                cur.movePosition(cur.Start); cur.movePosition(cur.Down, cur.KeepAnchor, 200)
                cur.removeSelectedText(); cur.deleteChar()
            widget.append(line)
    except Exception: pass
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f: f.write(line + "\n")
    except Exception: pass

def normalize_youtube_url(u: str) -> str:
    try:
        url = (u or "").strip()
        if not url: return url
        pr = urlparse(url); host = (pr.netloc or "").lower(); path = pr.path or ""
        if host.endswith("youtube.com") and "/shorts/" in path: return url
        if host.endswith("youtu.be"):
            vid = path.strip("/").split("/")[0] if path else ""
            t = parse_qs(pr.query).get("t", [""])[0]
            base = f"https://www.youtube.com/watch?v={vid}" if vid else url
            return f"{base}&t={t}" if (vid and t) else base
        return url
    except Exception:
        return u

def get_public_ip(timeout=5) -> str:
    for url in ["https://api.ipify.org","https://ifconfig.me/ip","https://ipinfo.io/ip"]:
        try:
            r=requests.get(url,timeout=timeout)
            if r.ok:
                ip=(r.text or "").strip()
                if ip: return ip
        except Exception: pass
    return "-"

def load_smtp():
    try:
        with open(SMTP_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except Exception: return {"enabled": False, "host": "smtp.gmail.com", "port": 465, "user": "", "password": "", "to_addr": "", "use_tls": False, "use_ssl": True}

def send_smtp_mail(subject: str, html: str):
    cfg = load_smtp()
    if not cfg.get("enabled"): return False, "SMTP disabled"
    try:
        msg = MIMEText(html, "html", "utf-8"); msg["Subject"]=subject; msg["From"]=cfg["user"]; msg["To"]=cfg["to_addr"]
        if cfg.get("use_ssl", True):
            with smtplib.SMTP_SSL(cfg.get("host","smtp.gmail.com"), int(cfg.get("port",465)), context=ssl.create_default_context(), timeout=30) as s:
                s.login(cfg["user"], cfg["password"]); s.send_message(msg)
        else:
            with smtplib.SMTP(cfg.get("host","smtp.gmail.com"), int(cfg.get("port",587)), timeout=30) as s:
                s.ehlo()
                if cfg.get("use_tls", True): s.starttls()
                s.login(cfg["user"], cfg["password"]); s.send_message(msg)
        return True, ""
    except Exception as e:
        return False, str(e)

def detect_chrome_path_and_major() -> Tuple[Optional[str], Optional[int]]:
    candidates = [
        DEFAULT_CHROME_EXE,
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                out = subprocess.check_output([p, "--version"], stderr=subprocess.STDOUT, text=True, timeout=5)
                m = re.search(r"(\d+)\.(\d+)\.(\d+)\.(\d+)", out or "")
                if m:
                    major = int(m.group(1)); return p, major
            except Exception:
                pass
    return None, None

def clean_uc_cache():
    try:
        uc_cache = os.path.join(os.getenv("LOCALAPPDATA", tempfile.gettempdir()), "undetected_chromedriver")
        if os.path.isdir(uc_cache):
            for item in os.listdir(uc_cache):
                try: shutil.rmtree(os.path.join(uc_cache, item), ignore_errors=True)
                except Exception: pass
    except Exception: pass

class ChromeController:
    def __init__(self, log_cb=None, profile_dir: str = None):
        self.chrome=None; self.log_cb=log_cb or (lambda s:None); self.profile_dir=profile_dir
    def _log(self,msg):
        try:self.log_cb(msg)
        except Exception: pass
    def _kill_stray_chrome(self):
        try: subprocess.run(["taskkill","/F","/IM","chrome.exe","/T"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception: pass
        try: subprocess.run(["taskkill","/F","/IM","chromedriver.exe","/T"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception: pass
    def _cleanup_profile_locks(self, pdir: str):
        try:
            for pat in ["Singleton*", "SSLErrorInfo.pb", "DevToolsActivePort"]:
                for f in glob.glob(os.path.join(pdir, pat)):
                    try: os.remove(f)
                    except Exception: pass
        except Exception: pass
    def start(self):
        self._kill_stray_chrome(); clean_uc_cache()
        chrome_path, major = detect_chrome_path_and_major()
        if not chrome_path: chrome_path = DEFAULT_CHROME_EXE if os.path.exists(DEFAULT_CHROME_EXE) else None
        if not major: major = FALLBACK_VERSION_MAIN
        ua=(f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36")
        base_opts=["--no-first-run","--no-default-browser-check","--disable-extensions","--disable-logging","--log-level=3",
                   "--disable-notifications","--disable-gcm-driver","--disable-background-networking","--disable-renderer-backgrounding",
                   "--disable-background-timer-throttling","--mute-audio","--window-size=1280,800", f"--user-agent={ua}"]
        attempts=0; last_err=None; profiles_to_try=[]
        if self.profile_dir:
            os.makedirs(self.profile_dir, exist_ok=True); self._cleanup_profile_locks(self.profile_dir); profiles_to_try.append(self.profile_dir)
        temp_prof = os.path.join(tempfile.gettempdir(), f"uc_profile_{int(time.time())}"); profiles_to_try.append(temp_prof)
        for pdir in profiles_to_try:
            attempts+=1
            try:
                opts = uc.ChromeOptions()
                for a in base_opts: opts.add_argument(a)
                opts.add_argument(f"--user-data-dir={pdir}"); opts.add_argument("--profile-directory=Default")
                self._log(f"Chrome başlatılıyor (deneme {attempts}) profil: {pdir}")
                kwargs = dict(options=opts, headless=False, use_subprocess=True)
                if major: kwargs["version_main"] = int(major)
                if chrome_path: kwargs["browser_executable_path"] = chrome_path
                self.chrome = uc.Chrome(**kwargs)
                caps = getattr(self.chrome, "capabilities", {}) or {}; ver = caps.get("browserVersion") or caps.get("version")
                self._log(f"Driver: UC | BrowserVersion: {ver}"); self.chrome.get("about:blank")
                return
            except Exception as e:
                last_err = e; self._log(f"UC start hata (profil {pdir}): {e}")
                try:
                    if self.chrome: self.chrome.quit()
                except Exception: pass
                self.chrome=None; continue
        raise RuntimeError(f"Chrome açılamadı: {last_err}")
    def stop(self):
        if self.chrome:
            try: self.chrome.quit(); self._log("Chrome kapatıldı.")
            except Exception as e: self._log(f"Chrome kapatma hatası: {e}")
            self.chrome=None
    def _wait_ready(self, drv, timeout=25):
        try:
            WebDriverWait(drv, timeout).until(lambda d: d.execute_script("return document.readyState") in ("interactive","complete"))
            return True
        except Exception: return False
    def _dismiss_overlays(self):
        try:
            sels=['button[aria-label*="Kabul"]','button[aria-label*="Accept"]','button[aria-label*="I agree"]','button[aria-label*="Tümünü kabul et"]']
        except Exception: return
        for css in sels:
            try:
                for el in self.chrome.find_elements(By.CSS_SELECTOR, css):
                    try: el.click(); time.sleep(0.2); self._log(f"Overlay kapatıldı: {css}")
                    except Exception: pass
            except Exception: pass
    def _try_play(self, retries=4, wait_between=1.0):
        if not PLAY_VIDEOS:
            self._log("PLAY_VIDEOS=False: Sadece URL açılacak, oynatma zorlanmayacak."); return False
        for _ in range(retries):
            self._dismiss_overlays()
            try:
                vids=self.chrome.find_elements(By.TAG_NAME,"video")
                if vids:
                    try: vids[0].click(); time.sleep(0.2)
                    except Exception: pass
                    self.chrome.execute_script("arguments[0].muted=true;arguments[0].play && arguments[0].play();", vids[0])
                    ok=self.chrome.execute_script("return arguments[0] && arguments[0].paused===false", vids[0])
                    if ok: self._log("Oynatma: video.play() (muted)."); return True
            except Exception as e:
                self._log(f"Oynatma JS hatası: {e}")
            time.sleep(wait_between)
        self._log("Oynatma başlatılamadı."); return False
    def open_and_play(self, url: str):
        if not self.chrome: return
        nav_url = normalize_youtube_url(url)
        try:
            self._log(f"URL açılıyor: {nav_url}")
            self.chrome.get(nav_url); self._wait_ready(self.chrome, 25); time.sleep(2); self._try_play()
        except Exception as e:
            self._log(f"URL hata: {e}")

class WorkerSignals(QObject):
    # progress: elapsed, total, url, idx, completed_secs_before, grand_total_secs
    finished=Signal()
    status=Signal(str)
    progress=Signal(int, int, str, int, int, int)
    logline=Signal(str)

class RotatorWorker(threading.Thread):
    def __init__(self, urls_with_minutes, signals: WorkerSignals, login_email="", login_password=""):
        super().__init__(daemon=True)
        self.urls = list(urls_with_minutes)
        self.signals = signals
        self._stop = threading.Event()
        self.results = []
        # abort bilgileri
        self.abort_reason = None
        self.abort_details = ""
        # hesap
        self.login_email = login_email
        self.login_password = login_password
        prof = re.sub(r"[^a-zA-Z0-9_.-]+", "_", self.login_email or "default")
        self.controller = ChromeController(log_cb=lambda s: self.signals.logline.emit(s),
                                           profile_dir=os.path.join(APP_DIR, "profiles", prof))

    def stop(self): self._stop.set()

    # ----- Login Helpers -----
    def _is_signed_in_on_youtube(self) -> bool:
        d=self.controller.chrome
        try:
            orig = d.current_window_handle
            d.switch_to.new_window('tab')
            d.get("https://www.youtube.com/"); WebDriverWait(d,15).until(lambda x:x.execute_script("return document.readyState") in ("interactive","complete"))
            btns = d.find_elements(By.CSS_SELECTOR,'button#avatar-btn')
            d.close(); d.switch_to.window(orig)
            return len(btns)>0
        except Exception:
            try:
                for h in d.window_handles:
                    try: d.switch_to.window(h); break
                    except Exception: pass
            except Exception: pass
            return False

    def _page_has_2fa_markers(self, drv) -> bool:
        try:
            url = ""
            try: url = drv.current_url or ""
            except Exception: pass
            if "signin/challenge" in url or "/challenge/" in url: return True
            txt = drv.execute_script('return document.body ? document.body.innerText : ""') or ""
            t = txt.lower()
            markers = [
                '2-step','two-step','two factor','2fa','iki adımlı','iki adimli',
                'doğrulama kodu','dogrulama kodu','kimliğinizi doğrulayın','kimliginizi dogrulayin',
                'google authenticator','security key','güvenlik anahtarı','guvenlik anahtari',
                'telefonunuza gönderilen','prompt on your phone'
            ]
            return any(m in t for m in markers)
        except Exception:
            return False

    def _google_sign_in_blocking(self) -> bool:
        d=self.controller.chrome
        if not d:
            self.signals.logline.emit("Google login atlandı: driver yok.")
            return False

        if self._is_signed_in_on_youtube():
            self.signals.logline.emit("Google zaten girişli (YouTube tespit).")
            return True

        self.signals.logline.emit(f"Google giriş başlıyor: {self.login_email} (ayrı sekme)")
        main = d.current_window_handle
        d.switch_to.new_window('tab')
        try:
            d.get("https://accounts.google.com/signin/v2/identifier")
        except Exception as e:
            self.signals.logline.emit(f"Giriş sayfası yüklenemedi: {e}")
            try: d.close()
            except Exception: pass
            try: d.switch_to.window(main)
            except Exception: pass
            return False

        # Mail adımı
        for _ in range(30):
            if self._stop.is_set():
                self.signals.logline.emit("Login kullanıcı tarafından durduruldu (mail adımı).")
                try: d.close()
                except Exception: pass
                try: d.switch_to.window(main)
                except Exception: pass
                return False
            try:
                el = d.find_element(By.ID,"identifierId")
                el.clear(); el.send_keys(self.login_email)
                d.find_element(By.ID,"identifierNext").click()
                break
            except Exception:
                time.sleep(1)

        # Şifre adımı
        for _ in range(60):
            if self._stop.is_set():
                self.signals.logline.emit("Login kullanıcı tarafından durduruldu (şifre adımı).")
                try: d.close()
                except Exception: pass
                try: d.switch_to.window(main)
                except Exception: pass
                return False
            try:
                pwd = d.find_element(By.NAME,"Passwd")
                pwd.clear(); pwd.send_keys(self.login_password)
                d.find_element(By.ID,"passwordNext").click()
                break
            except Exception:
                time.sleep(1)

        # Challenge / 2FA bekleme
        start=time.time(); last_note=0; success=False
        while time.time()-start < CHALLENGE_MAX_WAIT:
            if self._stop.is_set():
                self.signals.logline.emit("Login kullanıcı tarafından durduruldu (challenge beklerken).")
                break
            now=int(time.time()-start)
            if now-last_note>=5:
                self.signals.logline.emit(f"Giriş doğrulaması bekleniyor… ({now}s)")
                last_note=now
            time.sleep(2)
            try:
                if self._page_has_2fa_markers(d):
                    self.signals.logline.emit("2FA ekranı algılandı.")
                    if ABORT_ON_2FA:
                        self.abort_reason='2FA_DETECTED'; self.abort_details='Hesapta 2 Adımlı Doğrulama aktif.'
                        break
            except Exception: pass
            try:
                d.get("https://www.youtube.com/")
                WebDriverWait(d,10).until(lambda x:x.execute_script("return document.readyState") in ("interactive","complete"))
                if len(d.find_elements(By.CSS_SELECTOR,'button#avatar-btn'))>0:
                    self.signals.logline.emit("Google giriş başarılı (YouTube avatar bulundu).")
                    success=True
                    break
            except Exception: pass

        try: d.close()
        except Exception: pass
        try: d.switch_to.window(main)
        except Exception: pass
        return success

    def run(self):
        try:
            self.controller.start()

            # --------- LOGIN GATE ---------
            login_needed = (LOGIN_MODE != 'off')
            login_ok = False
            if login_needed:
                self.signals.logline.emit(f"Login kapısı: START_AFTER_LOGIN={START_AFTER_LOGIN}, bekleme={LOGIN_GATE_WAIT}s")
                t0=time.time()
                while time.time()-t0 < LOGIN_GATE_WAIT:
                    if self._stop.is_set():
                        self.signals.logline.emit("Login kapısı iptal edildi (kullanıcı durdurdu).")
                        break
                    login_ok = self._is_signed_in_on_youtube()
                    if login_ok:
                        self.signals.logline.emit("Profil zaten girişli görünüyor (gate ok).")
                        break
                    if LOGIN_MODE in ('auto','force') and self.login_email and self.login_password:
                        login_ok = self._google_sign_in_blocking()
                        if self.abort_reason == '2FA_DETECTED':
                            self.signals.logline.emit("2FA algılandı → işlem sonlandırılıyor.")
                            break
                        if login_ok: break
                    time.sleep(1)

                if self.abort_reason == '2FA_DETECTED':
                    self.signals.status.emit("2FA algılandı, işlem iptal.")
                    return
                if START_AFTER_LOGIN == 'require' and not login_ok:
                    self.signals.logline.emit("Login başarısız → START_AFTER_LOGIN='require' nedeniyle işlem iptal.")
                    self.signals.status.emit("Login başarısız (require).")
                    return
                if START_AFTER_LOGIN == 'soft' and not login_ok:
                    self.signals.logline.emit("Login tamamlanamadı → START_AFTER_LOGIN='soft' → URL'lere devam ediliyor.")
            else:
                self.signals.logline.emit("LOGIN_MODE=off → login denenmeyecek.")

            # --------- URL LOOP ---------
            self.plan_urls = list(self.urls)
            grand_total_secs = sum(max(1, int(m)) * 60 for _, m in self.plan_urls)

            for idx, (url, mins) in enumerate(self.urls):
                if self._stop.is_set(): break
                ip=get_public_ip(timeout=5); self.signals.logline.emit(f"Çıkış IP: {ip or '-'}")
                total=max(1,int(mins))*60
                completed_before_secs = sum(max(1,int(m)) * 60 for _, m in self.urls[:idx])

                self.signals.status.emit(f"Açılıyor: {url} — {mins} dk")
                try: self.controller.open_and_play(url)
                except Exception as e: self.signals.logline.emit(f"URL açma hatası (devam ediliyor): {e}")

                start=time.time()
                while not self._stop.is_set():
                    elapsed=int(time.time()-start)
                    if elapsed>=total:
                        self.signals.progress.emit(total, total, url, idx, completed_before_secs, grand_total_secs)
                        break
                    self.signals.progress.emit(elapsed, total, url, idx, completed_before_secs, grand_total_secs)
                    time.sleep(1)

                self.results.append({"url":url,"minutes":int(mins),"status":"OK","ip":ip or "-"})
                self.signals.logline.emit(f"Tamamlandı (URL): {url} — OK — IP: {ip or '-'}")

            self.signals.status.emit("Tamamlandı.")
        except Exception as e:
            self.signals.logline.emit(f"WORKER ERROR (top-level): {e}")
        finally:
            try:self.controller.stop()
            except Exception as e:self.signals.logline.emit(f"Controller stop hatası: {e}")
            self.signals.finished.emit()

# ------- SCHEDULE / UI -------
def load_schedule():
    try:
        with open(SCHEDULE_FILE,"r",encoding="utf-8") as f: arr=json.load(f)
        if isinstance(arr,list): return arr
    except Exception: pass
    return []

def save_schedule(arr):
    try:
        with open(SCHEDULE_FILE,"w",encoding="utf-8") as f: json.dump(arr,f,ensure_ascii=False,indent=2)
    except Exception: pass

class ScheduleDialog(QDialog):
    def __init__(self,parent:'MainWindow'):
        super().__init__(parent); self.setWindowTitle("Zamanlama")
        self._time=QTimeEdit(); self._time.setDisplayFormat("HH:mm"); self._time.setTime(QTime.currentTime())
        self._group=QLineEdit(); self._group.setPlaceholderText("Örn. Gece")
        self._days=QComboBox(); self._days.addItems(["Her Gün","Hafta İçi","Hafta Sonu"])
        form=QFormLayout(); form.addRow("Saat:",self._time); form.addRow("Grup:",self._group); form.addRow("Günler:",self._days)
        btns=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel); btns.accepted.connect(self._add); btns.rejected.connect(self.reject)
        lay=QVBoxLayout(); lay.addLayout(form); lay.addWidget(btns); self.setLayout(lay)
    def _add(self):
        hhmm=self._time.time().toString("HH:mm"); grp=self._group.text().strip(); days=self._days.currentText()
        if not grp: QMessageBox.warning(self,"Eksik","Grup adı boş olamaz."); return
        items=load_schedule(); items.append({"time":hhmm,"group":grp,"days":days,"enabled":True}); save_schedule(items)
        QMessageBox.information(self,"Tamam","Zamanlama eklendi."); self.accept()

class SchedulerThread(threading.Thread):
    def __init__(self,main_ref:'MainWindow'):
        super().__init__(daemon=True); self.main=main_ref; self._stop=threading.Event(); self._last_min=None
    def stop(self): self._stop.set()
    def run(self):
        while not self._stop.is_set():
            try:
                now=time.localtime(); key=(now.tm_year,now.tm_mon,now.tm_mday,now.tm_hour,now.tm_min)
                if key!=self._last_min:
                    hhmm=f"{now.tm_hour:02d}:{now.tm_min:02d}"; wday=now.tm_wday
                    for it in load_schedule():
                        if not it.get("enabled",True): continue
                        if it.get("time")!=hhmm: continue
                        days=it.get("days","Her Gün")
                        if days=="Hafta İçi" and wday>=5: continue
                        if days=="Hafta Sonu" and wday<5: continue
                        grp=it.get("group",""); self.main.start_group_now(grp, via_scheduler=True)
                    self._last_min=key
                time.sleep(5)
            except Exception: time.sleep(5)

@dataclass
class MailAccount:
    label:str; email:str; password:str; provider:str="google"; enabled:bool=True; auth_overrides:Dict[str,Any]=field(default_factory=dict)

class MailAccountStore:
    def __init__(self,path:str): self.path=path; self.accounts:List[MailAccount]=[]; self.load()
    def load(self):
        if not os.path.exists(self.path): self.accounts=[]; self.save(); return
        with open(self.path,"r",encoding="utf-8") as f: raw=json.load(f) or []
        out=[]
        for item in raw:
            d=dict(item)
            if "provider" not in d: d["provider"]="google"
            out.append(MailAccount(**d))
        self.accounts=out
    def save(self):
        with open(self.path,"w",encoding="utf-8") as f: json.dump([asdict(a) for a in self.accounts], f, ensure_ascii=False, indent=2)
    def add(self,acc:MailAccount): self.accounts.append(acc); self.save()
    def enabled_accounts(self)->List[MailAccount]: return [a for a in self.accounts if a.enabled]

class MailPickerDialog(QDialog):
    def __init__(self,store:MailAccountStore,parent=None):
        super().__init__(parent); self.setWindowTitle("Hangi mail hesabıyla çalışılsın?"); self.store=store; self.selected:Optional[MailAccount]=None
        v=QVBoxLayout(self); v.addWidget(QLabel("Başlamadan önce bir hesap seçin:"))
        self.listw=QListWidget()
        for acc in self.store.enabled_accounts():
            it=QLI(f"{acc.label}  —  {acc.email}"); it.setData(Qt.UserRole,acc); self.listw.addItem(it)
        v.addWidget(self.listw)
        v.addWidget(QLabel("Yeni hesap ekle (opsiyonel):"))
        form=QFormLayout()
        self.inp_label=QLineEdit(); self.inp_email=QLineEdit(); self.inp_pass=QLineEdit(); self.inp_pass.setEchoMode(QLineEdit.Password)
        self.chk_enable=QCheckBox("Etkin"); self.chk_enable.setChecked(True)
        self.inp_label.setPlaceholderText("Örn: Gmail - Hesap 2"); self.inp_email.setPlaceholderText("mail@ornek.com"); self.inp_pass.setPlaceholderText("şifre")
        form.addRow("Etiket",self.inp_label); form.addRow("E-posta",self.inp_email); form.addRow("Şifre",self.inp_pass); form.addRow("",self.chk_enable)
        v.addLayout(form)
        h=QHBoxLayout(); self.btn_add=QPushButton("Ekle"); self.btn_cancel=QPushButton("İptal"); self.btn_ok=QPushButton("Seç ve Başla")
        h.addWidget(self.btn_add); h.addStretch(1); h.addWidget(self.btn_cancel); h.addWidget(self.btn_ok); v.addLayout(h)
        self.btn_add.clicked.connect(self.add_account); self.btn_ok.clicked.connect(self.accept_selection); self.btn_cancel.clicked.connect(self.reject)
        self.resize(560,460)
    def add_account(self):
        label=self.inp_label.text().strip(); email=self.inp_email.text().strip(); pwd=self.inp_pass.text()
        if not label or not email or not pwd: QMessageBox.warning(self,"Eksik bilgi","Etiket, e-posta ve şifre zorunludur."); return
        acc=MailAccount(label=label,email=email,password=pwd,enabled=self.chk_enable.isChecked()); self.store.add(acc)
        it=QLI(f"{acc.label}  —  {acc.email}"); it.setData(Qt.UserRole,acc); self.listw.addItem(it)
        self.inp_label.clear(); self.inp_email.clear(); self.inp_pass.clear(); self.chk_enable.setChecked(True)
    def accept_selection(self):
        it=self.listw.currentItem()
        if not it: QMessageBox.warning(self,"Seçilmedi","Lütfen listeden bir hesap seçin."); return
        self.selected=it.data(Qt.UserRole); self.accept()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle(APP_NAME)
        if os.path.exists(APP_ICON): self.setWindowIcon(QIcon(APP_ICON))
        self.resize(1200,800)
        self.selected_email:Optional[str]=None; self.selected_password:Optional[str]=None
        self.worker=None; self.scheduler=SchedulerThread(self); self.scheduler.start()

        # Toolbar
        tb=QToolBar()
        self.btn_start=QPushButton("Başlat (Grup)"); self.btn_stop=QPushButton("Durdur")
        self.btn_save=QPushButton("Kaydet"); self.btn_load=QPushButton("Yükle")
        self.btn_sched=QPushButton("Zamanlama…"); self.btn_smtp_test=QPushButton("SMTP Test")
        for b in (self.btn_start,self.btn_stop,self.btn_save,self.btn_load,self.btn_sched,self.btn_smtp_test): tb.addWidget(b)
        self.addToolBar(tb)

        central=QWidget(); root=QVBoxLayout(central)

        # Üst satır: durum + progress + sağda Grup alanı (kompakt)
        top = QHBoxLayout(); top.setContentsMargins(4, 0, 4, 0); top.setSpacing(8)
        self.lbl_status = QLabel("Hazır.")
        self.progress = QProgressBar(); self.progress.setRange(0,100); self.progress.setValue(0)
        grp_lbl = QLabel("Grup:")
        self.in_active_group = QLineEdit(); self.in_active_group.setPlaceholderText("örn. Gece")
        self.in_active_group.setFixedWidth(180); self.in_active_group.setClearButtonEnabled(True)
        top.addWidget(self.lbl_status, 4)
        top.addWidget(self.progress, 3)
        top.addStretch(1)
        top.addWidget(grp_lbl, 0)
        top.addWidget(self.in_active_group, 0)
        root.addLayout(top)

        # --- Ayrım çizgisi (toolbar/top ile panel arasında) ---
        hr1 = QFrame()
        hr1.setFrameShape(QFrame.HLine)
        hr1.setFrameShadow(QFrame.Sunken)
        root.addWidget(hr1)

        # --- Panel: Genel süre + Genel URL (tablo hissi + dikey çizgi) ---
        metricsPanel = QFrame()
        metricsPanel.setObjectName("metricsPanel")
        metricsPanel.setFrameShape(QFrame.StyledPanel)
        metricsPanel.setFrameShadow(QFrame.Raised)
        metricsPanel.setStyleSheet("""
        QFrame#metricsPanel {
            border: 1px solid #555;
            border-radius: 6px;
            padding: 6px 10px;
        }
        """)
        metrics = QHBoxLayout(metricsPanel)
        metrics.setContentsMargins(10, 6, 10, 6)
        metrics.setSpacing(12)

        self.lbl_overall = QLabel("Genel süre: 0/0 dk — %0")
        self.lbl_overall_count = QLabel("Genel URL: 0/0 — %0")

        vline = QFrame()
        vline.setFrameShape(QFrame.VLine)
        vline.setFrameShadow(QFrame.Sunken)

        metrics.addWidget(self.lbl_overall, 1)
        metrics.addWidget(vline, 0)
        metrics.addWidget(self.lbl_overall_count, 1)
        root.addWidget(metricsPanel)

        # --- Panel altına da ince bir çizgi (opsiyonel) ---
        hr2 = QFrame()
        hr2.setFrameShape(QFrame.HLine)
        hr2.setFrameShadow(QFrame.Plain)
        root.addWidget(hr2)

        self.listw=QListWidget(); root.addWidget(self.listw,3)

        # Alt giriş barı
        bar=QHBoxLayout(); self.in_url=QLineEdit(); self.in_url.setPlaceholderText("URL (örn: https://www.youtube.com/shorts/...)")
        self.in_min=QSpinBox(); self.in_min.setRange(1,180); self.in_min.setValue(1)
        self.in_group=QLineEdit(); self.in_group.setPlaceholderText("Grup (örn. Gece)")
        lbl=QLabel("dk"); btn_add=QPushButton("Ekle"); btn_del=QPushButton("Sil")
        bar.addWidget(self.in_url,5); bar.addWidget(self.in_min,0); bar.addWidget(lbl,0); bar.addWidget(self.in_group,2); bar.addWidget(btn_add,0); bar.addWidget(btn_del,0)
        root.addLayout(bar)

        self.log=QTextEdit(); self.log.setReadOnly(True); self.log.setMinimumHeight(220); root.addWidget(self.log,2)
        self.setCentralWidget(central)

        # Bağlantılar
        btn_add.clicked.connect(self.add_url); btn_del.clicked.connect(self.delete_selected); self.in_url.returnPressed.connect(self.add_url)
        self.btn_save.clicked.connect(self._save_click); self.btn_load.clicked.connect(self.load_list)
        self.btn_start.clicked.connect(lambda: self.start_group_now(self.in_active_group.text().strip()))
        self.btn_stop.clicked.connect(self.stop_run); self.btn_sched.clicked.connect(self.open_scheduler); self.btn_smtp_test.clicked.connect(self.smtp_test_now)

        self.load_list(); log_append(self.log, f"Uygulama açıldı. {self.listw.count()} URL yüklendi.")

    def _save_click(self):
        data=[]
        for i in range(self.listw.count()):
            it=self.listw.item(i); (url,mins)=it.data(Qt.UserRole) or (it.text(),1); grp=it.data(Qt.UserRole+1) or ""
            data.append({"url":url,"minutes":int(mins),"group":grp})
        with open(URLLIST_FILE,"w",encoding="utf-8") as f: json.dump(data,f,ensure_ascii=False,indent=2)
        self.set_status("Liste kaydedildi."); log_append(self.log,"Liste kaydedildi.")

    def set_status(self,s:str): self.lbl_status.setText(s)

    def add_url(self):
        url=(self.in_url.text() or "").strip(); mins=int(self.in_min.value()); grp=(self.in_group.text() or "").strip()
        if not url: return
        it=QListWidgetItem(f"{url}  [{mins} dk]  {{{grp or '—'}}}"); it.setData(Qt.UserRole,(url,mins)); it.setData(Qt.UserRole+1, grp or "")
        self.listw.addItem(it); self.in_url.clear(); self._save_click(); log_append(self.log,f"URL eklendi: {url} [{mins} dk] {{{grp or '—'}}}")

    def delete_selected(self):
        for it in self.listw.selectedItems():
            log_append(self.log,f"URL silindi: {(it.data(Qt.UserRole) or ('',0))[0]}")
            self.listw.takeItem(self.listw.row(it))
        self._save_click()

    def load_list(self):
        try:
            if not os.path.exists(URLLIST_FILE): return
            with open(URLLIST_FILE,"r",encoding="utf-8") as f: arr=json.load(f)
            self.listw.clear()
            for o in arr or []:
                it=QListWidgetItem(f"{o.get('url','')}  [{int(o.get('minutes',1))} dk]  {{{o.get('group','') or '—'}}}")
                it.setData(Qt.UserRole,(o.get('url',''), int(o.get('minutes',1)))); it.setData(Qt.UserRole+1, o.get('group',''))
                self.listw.addItem(it)
        except Exception as e:
            log_append(self.log, f"Yükleme hatası: {e}")

    def _collect_group(self, group: str):
        out=[]
        for i in range(self.listw.count()):
            it=self.listw.item(i); url,mins=it.data(Qt.UserRole) or (it.text(),1); grp=(it.data(Qt.UserRole+1) or "").strip()
            if (not group) or (grp==group): out.append((url, int(mins)))
        return out

    def _pick_account_and_login(self) -> bool:
        store=MailAccountStore(MAIL_ACCOUNTS_FILE); dlg=MailPickerDialog(store,self)
        if dlg.exec()!=QDialog.Accepted or not dlg.selected: log_append(self.log,"Hesap seçimi iptal edildi."); return False
        acc=dlg.selected; self.selected_email=acc.email; self.selected_password=acc.password
        log_append(self.log,f"Hesap seçildi: {acc.email}"); return True

    def _build_mail_html(self, results):
        rows=[]
        for r in results:
            rows.append(f"<tr><td>{r['url']}</td><td align='right'>{int(r['minutes'])}</td><td>{r.get('ip','-')}</td><td><b>{r['status']}</b></td></tr>")
        ts=time.strftime("%Y-%m-%d %H:%M:%S")
        return f"<h3>Görev Tamamlandı</h3><p><b>Kullanılan mail:</b> {self.selected_email or '-'}</p><table border='1' cellspacing='0' cellpadding='6' style='border-collapse:collapse;width:100%'><tr><th>URL</th><th>Süre</th><th>IP</th><th>Durum</th></tr>{''.join(rows)}</table><p style='color:#666'>Zaman: {ts}</p>"

    def start_group_now(self, group: str, via_scheduler: bool=False):
        if self.worker is not None:
            if not via_scheduler: QMessageBox.warning(self,"Uyarı","Zaten çalışıyor.")
            return
        urls=self._collect_group(group)
        if not urls:
            if not via_scheduler: QMessageBox.information(self,"Bilgi",f"Bu grupta URL yok: {group or 'Tümü'}")
            return
        if not self._pick_account_and_login(): return

        # Genel ilerleme planı ve etiket sıfırlama
        self.plan_urls = list(urls)
        self.plan_total_secs = sum(max(1, int(m)) * 60 for _, m in self.plan_urls)
        self.plan_total_urls = len(self.plan_urls)
        self.lbl_overall.setText("Genel süre: 0/{0} dk — %0".format(int(self.plan_total_secs/60)))
        self.lbl_overall_count.setText("Genel URL: 0/{0} — %0".format(self.plan_total_urls))

        self.signals=WorkerSignals()
        self.signals.finished.connect(self.on_finished); self.signals.status.connect(self.on_status)
        self.signals.progress.connect(self.on_progress); self.signals.logline.connect(lambda l: log_append(self.log,l))

        self.worker=RotatorWorker(urls,self.signals,login_email=(self.selected_email or ""),login_password=(self.selected_password or ""))
        self.worker.start(); self.set_status(f"Çalışıyor… (Grup: {group or 'Tümü'})"); self.progress.setValue(0)
        log_append(self.log, f"Görev başladı. Grup: {group or 'Tümü'} | {len(urls)} URL | Kullanılan mail: {self.selected_email}")

    def stop_run(self):
        if self.worker:
            self.worker.stop(); self.set_status("Durduruluyor…"); log_append(self.log,"Durdurma talebi gönderildi.")

    def on_finished(self):
        results=getattr(self.worker,"results",[])
        abort_reason=getattr(self.worker,"abort_reason",None)
        abort_details=getattr(self.worker,"abort_details","")
        self.worker=None; self.set_status("Tamamlandı veya durduruldu."); self.progress.setValue(0)
        log_append(self.log,"Görev tamamlandı; mail hazırlanıyor…")

        # Etiketleri finalize et
        if hasattr(self, "plan_total_urls"):
            self.lbl_overall_count.setText("Genel URL: {0}/{0} — %100".format(self.plan_total_urls))
        if hasattr(self, "plan_total_secs"):
            self.lbl_overall.setText("Genel süre: {0}/{0} dk — %100".format(int(self.plan_total_secs/60)))

        if abort_reason == '2FA_DETECTED':
            subject = "[URL Rotator] İşlem Başarısız — 2FA aktif"
            html = f"<h3>İşlem Başarısız</h3><p><b>Kullanılan mail:</b> {self.selected_email or '-'}</p><p>2 Adımlı Doğrulama (2FA) tespit edildiği için giriş tamamlanamadı. Bu hesapla otomatik giriş mümkün değil.</p><p>Detay: {abort_details}</p>"
        else:
            subject = "[URL Rotator] Görev Tamamlandı"
            html = self._build_mail_html(results)
        ok,err=send_smtp_mail(subject, html)
        if ok: log_append(self.log,"SMTP: Bildirim maili gönderildi."); QMessageBox.information(self,"SMTP","Bildirim maili gönderildi.")
        else: log_append(self.log,f"SMTP HATA: {err}"); QMessageBox.warning(self,"SMTP",f"Mail gönderilemedi.\nHata: {err}")
        self.selected_email=None; self.selected_password=None

    def on_status(self,msg:str): self.set_status(msg); log_append(self.log,msg)

    def on_progress(self, elapsed:int, total:int, url:str, idx:int, completed_before_secs:int, grand_total_secs:int):
        # Aktif URL yüzdesi (üst çubuk)
        pct=int(max(0,min(100,(elapsed/total)*100)))
        self.progress.setValue(pct)
        mm_e,ss_e=divmod(elapsed,60); mm_t,ss_t=divmod(total,60)
        cur_url = normalize_youtube_url(url)
        self.set_status(f"{cur_url} — {mm_e:02d}:{ss_e:02d} / {mm_t:02d}:{ss_t:02d}  ({pct}%)")

        # Genel süre (zaman-ağırlıklı)
        overall_elapsed = completed_before_secs + min(elapsed, total)
        overall_pct = int(max(0, min(100, (overall_elapsed / max(1, grand_total_secs)) * 100)))
        self.lbl_overall.setText(
            "Genel süre: {done}/{tot} dk — %{p}".format(
                done=int(overall_elapsed/60),
                tot=int(grand_total_secs/60),
                p=overall_pct
            )
        )

        # Genel URL (adet bazlı)
        total_urls = getattr(self, "plan_total_urls", 0)
        done_urls = min(idx, total_urls)  # aktif tamamlanmadıysa idx kadar URL bitmiştir
        url_pct = int(max(0, min(100, (done_urls / max(1, total_urls)) * 100)))
        self.lbl_overall_count.setText(
            "Genel URL: {done}/{tot} — %{p}".format(
                done=done_urls, tot=total_urls, p=url_pct
            )
        )

    def open_scheduler(self): ScheduleDialog(self).exec()
    def smtp_test_now(self):
        ok,err=send_smtp_mail("[URL Rotator] SMTP Test","<h3>Test</h3>")
        if ok: QMessageBox.information(self,"SMTP","Test maili gönderildi."); log_append(self.log,"SMTP Test: OK")
        else: QMessageBox.warning(self,"SMTP",f"Test maili gönderilemedi.\nHata: {err}"); log_append(self.log,f"SMTP Test: HATA — {err}")
    def closeEvent(self,e):
        log_append(self.log,"Uygulama kapanıyor."); super().closeEvent(e)

if __name__=="__main__":
    app=QApplication(sys.argv); app.setApplicationName(APP_NAME)
    if os.path.exists(APP_ICON): app.setWindowIcon(QIcon(APP_ICON))
    w=MainWindow()
    if os.path.exists(APP_ICON): w.setWindowIcon(QIcon(APP_ICON))
    w.show(); sys.exit(app.exec())
