# -*- coding: utf-8 -*-
import os
import sys
import time
import json
import threading
import smtplib
import ssl
from email.mime.text import MIMEText
from urllib.parse import urlparse, parse_qs

# Qt (GPU'suz ortamlar)
os.environ["QT_OPENGL"] = "software"
os.environ["QT_QUICK_BACKEND"] = "software"

from PySide6.QtCore import Qt, Signal, QObject, QTime
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
    QPushButton, QLabel, QSpinBox, QLineEdit, QListWidgetItem, QToolBar,
    QProgressBar, QMessageBox, QDialog, QDialogButtonBox, QFormLayout,
    QTimeEdit, QComboBox, QTextEdit
)

# HTTP
import requests

# Selenium (Chrome tabanlı)
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

APP_DIR = os.path.dirname(__file__)
APP_NAME = "URL Rotator (Shorts + Zamanlama + SMTP + Log)"
APP_ICON = os.path.join(APP_DIR, "img", "favicon.png")

# İstenilen dosya adları
URLLIST_FILE = os.path.join(APP_DIR, "shorts-urllist.json")
SCHEDULE_FILE = os.path.join(APP_DIR, "schedule.json")
SMTP_FILE = os.path.join(APP_DIR, "smtp.json")

# LOG dosyası
LOG_DIR = os.path.join(APP_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "short-log.txt")

# --------------- Basit log yardımcıları ---------------
def _ts():
    return time.strftime("%Y-%m-%d %H:%M:%S")

def log_append(widget: QTextEdit, text: str):
    """Hem ekrana hem dosyaya yazar."""
    line = f"[{_ts()}] {text}"
    try:
        if widget:
            # metin kutusunu çok şişirmemek için 2000 satır sınırı
            if widget.document().blockCount() > 2000:
                cursor = widget.textCursor()
                cursor.movePosition(cursor.Start)
                cursor.movePosition(cursor.Down, cursor.KeepAnchor, 200)
                cursor.removeSelectedText()
                cursor.deleteChar()
            widget.append(line)
    except Exception:
        pass
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

# ---------------- SMTP ----------------
def load_smtp():
    try:
        with open(SMTP_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "enabled": False,
            "host": "smtp.gmail.com",
            "port": 465,
            "user": "",
            "password": "",
            "to_addr": "",
            "use_tls": False,
            "use_ssl": True
        }

def send_smtp_mail(subject: str, html: str):
    """
    Başarı (True, "") veya Hata (False, "mesaj") döndürür.
    """
    cfg = load_smtp()
    if not cfg.get("enabled"):
        return False, "SMTP disabled (enabled:false)"

    host = cfg.get("host", "smtp.gmail.com")
    port = int(cfg.get("port", 465))
    user = cfg.get("user", "")
    pwd  = cfg.get("password", "")
    to   = cfg.get("to_addr", "")
    use_tls = bool(cfg.get("use_tls", False))
    use_ssl = bool(cfg.get("use_ssl", True))

    if not (user and pwd and to):
        return False, "Missing user/password/to_addr"

    try:
        msg = MIMEText(html, "html", "utf-8")
        msg["Subject"] = subject
        msg["From"] = user
        msg["To"] = to
        if use_ssl:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as s:
                s.login(user, pwd)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as s:
                s.ehlo()
                if use_tls:
                    s.starttls()
                s.login(user, pwd)
                s.send_message(msg)
        return True, ""
    except Exception as e:
        return False, str(e)

# --------------- Helpers ---------------
def normalize_youtube_url(u: str) -> str:
    """
    KURAL:
      - youtube.com/shorts/... (m. alt alan adı dahil) → ASLA dönüştürme (olduğu gibi).
      - youtu.be/... → watch?v=... (t parametresi korunur).
      - diğerleri → olduğu gibi.
    """
    try:
        url = (u or "").strip()
        if not url:
            return url
        pr = urlparse(url)
        host = (pr.netloc or "").lower()
        path = pr.path or ""

        if host.endswith("youtube.com") and "/shorts/" in path:
            return url

        if host.endswith("youtu.be"):
            vid = path.strip("/").split("/")[0] if path else ""
            t = parse_qs(pr.query).get("t", [""])[0]
            base = f"https://www.youtube.com/watch?v={vid}" if vid else url
            return f"{base}&t={t}" if (vid and t) else base

        return url
    except Exception:
        return u

def make_item(url: str, mins: int, group: str) -> QListWidgetItem:
    label = f"{url}  [{mins} dk]  {{{group or '—'}}}"
    it = QListWidgetItem(label)
    it.setData(Qt.UserRole, (url, int(mins)))
    it.setData(Qt.UserRole + 1, group or "")
    return it

def save_url_list(listw: QListWidget):
    data = []
    for i in range(listw.count()):
        it = listw.item(i)
        (url, mins) = it.data(Qt.UserRole) or (it.text(), 1)
        group = it.data(Qt.UserRole + 1) or ""
        data.append({"url": url, "minutes": int(mins), "group": group})
    try:
        with open(URLLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def load_url_list(listw: QListWidget) -> int:
    try:
        if not os.path.exists(URLLIST_FILE):
            return 0
        with open(URLLIST_FILE, "r", encoding="utf-8") as f:
            arr = json.load(f)
        listw.clear()
        for obj in arr or []:
            listw.addItem(make_item(obj.get("url",""), int(obj.get("minutes",1)), obj.get("group","")))
        return len(arr or [])
    except Exception:
        return 0

def find_chrome_binary() -> str:
    override = os.environ.get("CHROME_BINARY", "").strip()
    if override and os.path.exists(override):
        return override
    for p in [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
    ]:
        if p and os.path.exists(p):
            return p
    return ""

def find_chromedriver() -> str:
    # Aynı klasöre veya drivers/ altına koy
    candidates = [
        os.path.join(APP_DIR, "drivers", "chromedriver.exe"),
        os.path.join(APP_DIR, "chromedriver.exe"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return ""

# --- Public IP alma (VPN varsa onun IP'sini görürüz) ---
def get_public_ip(timeout=5) -> str:
    endpoints = [
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://ipinfo.io/ip",
    ]
    for url in endpoints:
        try:
            r = requests.get(url, timeout=timeout)
            if r.ok:
                ip = (r.text or "").strip()
                if ip:
                    return ip
        except Exception:
            continue
    return "-"

# --------------- Chrome Controller ---------------
class ChromeController:
    def __init__(self, log_cb=None):
        self.chrome = None
        self.log_cb = log_cb or (lambda s: None)

    def _log(self, msg: str):
        try:
            self.log_cb(msg)
        except Exception:
            pass

    def start(self):
        chrome_bin = find_chrome_binary()
        driver_path = find_chromedriver()

        opts = ChromeOptions()
        opts.add_argument("--no-first-run")
        opts.add_argument("--no-default-browser-check")
        opts.add_argument("--disable-extensions")
        opts.add_argument("--autoplay-policy=no-user-gesture-required")
        opts.add_argument("--remote-allow-origins=*")
        # Gürültüyü azaltalım:
        opts.add_argument("--disable-logging")
        opts.add_argument("--log-level=3")
        opts.add_argument("--disable-notifications")
        opts.add_argument("--disable-gcm-driver")
        opts.add_argument("--disable-features=LiveCaption,OnDeviceSpeechRecognition")
        opts.add_argument("--disable-background-networking")
        opts.add_argument("--disable-renderer-backgrounding")
        opts.add_argument("--disable-background-timer-throttling")
        if chrome_bin:
            opts.binary_location = chrome_bin

        if not driver_path:
            self._log("ERROR: chromedriver.exe bulunamadı.")
            QMessageBox.critical(None, "ChromeDriver Gerekli",
                                 "chromedriver.exe bulunamadı.\n"
                                 "Lütfen projeye chromedriver.exe ekleyin (aynı klasör veya drivers/).")
            raise RuntimeError("chromedriver yok")

        try:
            service = ChromeService(executable_path=driver_path, log_output=open(os.devnull, "w"))
        except TypeError:
            service = ChromeService(executable_path=driver_path)
        self.chrome = webdriver.Chrome(service=service, options=opts)
        self._log("Chrome başlatıldı.")
        self.chrome.get("about:blank")

    def stop(self):
        if self.chrome:
            try:
                self.chrome.quit()
                self._log("Chrome kapatıldı.")
            except Exception as e:
                self._log(f"Chrome kapatma hatası: {e}")
            self.chrome = None

    def _wait_ready(self, drv, timeout=25):
        try:
            WebDriverWait(drv, timeout).until(
                lambda d: d.execute_script("return document.readyState") in ("interactive", "complete")
            )
            return True
        except Exception:
            return False

    def _dismiss_overlays(self):
        try:
            sels = [
                'button[aria-label*="Kabul"]',
                'button[aria-label*="Accept"]',
                'button[aria-label*="I agree"]',
                'button[aria-label*="Tümünü kabul et"]',
            ]
            for css in sels:
                for el in self.chrome.find_elements(By.CSS_SELECTOR, css):
                    try:
                        el.click()
                        time.sleep(0.2)
                        self._log(f"Overlay kapatıldı: {css}")
                    except Exception:
                        pass
        except Exception:
            pass

    def _try_play(self, retries=6, wait_between=1.0):
        for i in range(retries):
            self._dismiss_overlays()
            # 1) video.play()
            try:
                vids = self.chrome.find_elements(By.TAG_NAME, "video")
                if vids:
                    try:
                        vids[0].click(); time.sleep(0.2)
                    except Exception:
                        pass
                    self.chrome.execute_script(
                        "arguments[0].muted = true; arguments[0].play && arguments[0].play();", vids[0]
                    )
                    ok = self.chrome.execute_script(
                        "return arguments[0] && arguments[0].paused===false", vids[0]
                    )
                    if ok:
                        self._log("Oynatma: video.play() ile başladı (muted).")
                        return True
            except Exception as e:
                self._log(f"Oynatma JS hatası: {e}")

            # 2) play butonu
            try:
                clicked = False
                for b in self.chrome.find_elements(By.CSS_SELECTOR, "button.ytp-play-button"):
                    try:
                        b.click(); time.sleep(0.4); clicked = True
                    except Exception:
                        pass
                if clicked:
                    vids = self.chrome.find_elements(By.TAG_NAME, "video")
                    if vids:
                        ok = self.chrome.execute_script(
                            "return arguments[0] && arguments[0].paused===false", vids[0]
                        )
                        if ok:
                            self._log("Oynatma: ytp-play-button ile başladı.")
                            return True
            except Exception:
                pass

            # 3) sayfaya tık + space / k
            try:
                ActionChains(self.chrome).move_by_offset(1,1).click().perform()
            except Exception:
                pass
            for key in (Keys.SPACE, "k"):
                try:
                    ActionChains(self.chrome).send_keys(key).perform(); time.sleep(0.5)
                    vids = self.chrome.find_elements(By.TAG_NAME, "video")
                    if vids:
                        ok = self.chrome.execute_script(
                            "return arguments[0] && arguments[0].paused===false", vids[0]
                        )
                        if ok:
                            self._log(f"Oynatma: klavye ({'SPACE' if key==Keys.SPACE else 'k'}) ile başladı.")
                            return True
                except Exception:
                    pass

            time.sleep(wait_between)
            self._log(f"Oynatma denemesi #{i+1} başarısız, tekrar denenecek.")
        self._log("Oynatma başlatılamadı.")
        return False

    def open_and_play(self, url: str):
        if not self.chrome:
            return
        nav_url = normalize_youtube_url(url)
        try:
            self._log(f"URL açılıyor: {nav_url}")
            self.chrome.get(nav_url)
            self._wait_ready(self.chrome, timeout=25)
            time.sleep(2)
            ok = self._try_play()
            if ok:
                self._log("Durum: OK (video oynuyor)")
            else:
                self._log("Durum: FAIL (oynatma başlamadı)")
        except Exception as e:
            self._log(f"URL hata: {e}")

# ---------------- Worker ----------------
class WorkerSignals(QObject):
    finished = Signal()
    status   = Signal(str)
    progress = Signal(int, int, str)   # elapsed, total, url
    logline  = Signal(str)             # doğrudan loga yaz

class RotatorWorker(threading.Thread):
    def __init__(self, urls_with_minutes, signals: WorkerSignals):
        super().__init__(daemon=True)
        self.urls = list(urls_with_minutes)
        self.signals = signals
        self._stop = threading.Event()
        self.results = []  # [{url, minutes, status, ip}]
        self.controller = ChromeController(log_cb=lambda s: self.signals.logline.emit(s))

    def stop(self):
        self._stop.set()

    def run(self):
        try:
            self.controller.start()
            for url, mins in self.urls:
                if self._stop.is_set():
                    break

                # Public IP'yi URL başlamadan al (VPN aktifse onun IP'si gelir)
                ip = get_public_ip(timeout=5)
                self.signals.logline.emit(f"Çıkış IP: {ip or '-'}")

                total = max(1, int(mins)) * 60
                self.signals.status.emit(f"Açılıyor: {url} — {mins} dk")
                self.signals.logline.emit(f"Çalıştırılıyor: {url} ({mins} dk)")

                ok_flag = True
                try:
                    self.controller.open_and_play(url)
                except Exception as e:
                    ok_flag = False
                    self.signals.logline.emit(f"ERROR open_and_play: {e}")

                start = time.time()
                while not self._stop.is_set():
                    elapsed = int(time.time() - start)
                    if elapsed >= total:
                        break
                    if elapsed % 5 == 0:
                        self.signals.progress.emit(elapsed, total, url)
                    time.sleep(1)

                self.results.append({
                    "url": url,
                    "minutes": int(mins),
                    "status": "OK" if ok_flag else "FAIL",
                    "ip": ip or "-"
                })
                self.signals.logline.emit(f"Tamamlandı (URL): {url} — Durum: {'OK' if ok_flag else 'FAIL'} — IP: {ip or '-'}")

            self.signals.status.emit("Tamamlandı.")
        except Exception as e:
            self.signals.logline.emit(f"WORKER ERROR: {e}")
        finally:
            try:
                self.controller.stop()
            except Exception as e:
                self.signals.logline.emit(f"Controller stop hatası: {e}")
            self.signals.finished.emit()

# ---------------- Zamanlama ----------------
def load_schedule():
    try:
        with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
            arr = json.load(f)
        if isinstance(arr, list):
            return arr
    except Exception:
        pass
    return []

def save_schedule(arr):
    try:
        with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
            json.dump(arr, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

class ScheduleDialog(QDialog):
    """
    Basit zamanlayıcı:
      - Saat (HH:MM)
      - Grup adı
      - Gün: Her Gün | Hafta İçi | Hafta Sonu
    """
    def __init__(self, parent: 'MainWindow'):
        super().__init__(parent)
        self.setWindowTitle("Zamanlama")

        self._time = QTimeEdit(); self._time.setDisplayFormat("HH:mm"); self._time.setTime(QTime.currentTime())
        self._group = QLineEdit(); self._group.setPlaceholderText("Örn. Gece")
        self._days  = QComboBox(); self._days.addItems(["Her Gün","Hafta İçi","Hafta Sonu"])

        form = QFormLayout()
        form.addRow("Saat:", self._time)
        form.addRow("Grup:", self._group)
        form.addRow("Günler:", self._days)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._add); btns.rejected.connect(self.reject)

        layout = QVBoxLayout(); layout.addLayout(form); layout.addWidget(btns)
        self.setLayout(layout)

    def _add(self):
        hhmm = self._time.time().toString("HH:mm")
        grp  = self._group.text().strip()
        days = self._days.currentText()
        if not grp:
            QMessageBox.warning(self, "Eksik", "Grup adı boş olamaz.")
            return
        items = load_schedule()
        items.append({"time": hhmm, "group": grp, "days": days, "enabled": True})
        save_schedule(items)
        QMessageBox.information(self, "Tamam", "Zamanlama eklendi.")
        self.accept()

class SchedulerThread(threading.Thread):
    def __init__(self, main_ref: 'MainWindow'):
        super().__init__(daemon=True)
        self.main = main_ref
        self._stop = threading.Event()
        self._last_min = None

    def stop(self): self._stop.set()

    def run(self):
        while not self._stop.is_set():
            try:
                now = time.localtime()
                key = (now.tm_year, now.tm_mon, now.tm_mday, now.tm_hour, now.tm_min)
                if key != self._last_min:
                    hhmm = f"{now.tm_hour:02d}:{now.tm_min:02d}"
                    wday = now.tm_wday  # 0=Mon .. 6=Sun
                    for it in load_schedule():
                        if not it.get("enabled", True):
                            continue
                        if it.get("time") != hhmm:
                            continue
                        days = it.get("days", "Her Gün")
                        if days == "Hafta İçi" and wday >= 5:
                            continue
                        if days == "Hafta Sonu" and wday < 5:
                            continue
                        grp = it.get("group","")
                        self.main.start_group_now(grp, via_scheduler=True)
                    self._last_min = key
                time.sleep(5)
            except Exception:
                time.sleep(5)

# ---------------- UI ----------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        if os.path.exists(APP_ICON):
            self.setWindowIcon(QIcon(APP_ICON))
        self.resize(1200, 800)

        self.worker = None
        self.scheduler = SchedulerThread(self); self.scheduler.start()

        tb = QToolBar()
        self.btn_start = QPushButton("Başlat (Grup)")
        self.btn_stop  = QPushButton("Durdur")
        self.btn_save  = QPushButton("Kaydet")
        self.btn_load  = QPushButton("Yükle")
        self.btn_sched = QPushButton("Zamanlama…")
        self.btn_smtp_test = QPushButton("SMTP Test")
        for b in (self.btn_start, self.btn_stop, self.btn_save, self.btn_load, self.btn_sched, self.btn_smtp_test):
            tb.addWidget(b)
        self.addToolBar(tb)

        central = QWidget(); root = QVBoxLayout(central)
        top = QHBoxLayout()
        self.lbl_status = QLabel("Hazır.")
        self.progress = QProgressBar(); self.progress.setRange(0, 100); self.progress.setValue(0)
        top.addWidget(self.lbl_status, 3); top.addWidget(self.progress, 2)
        top.addWidget(QLabel("Grup:"))
        self.in_active_group = QLineEdit(); self.in_active_group.setPlaceholderText("örn. Gece")
        top.addWidget(self.in_active_group)
        root.addLayout(top)

        # Liste
        self.listw = QListWidget(); root.addWidget(self.listw, 3)

        # URL ekleme alanı
        bar = QHBoxLayout()
        self.in_url = QLineEdit(); self.in_url.setPlaceholderText("URL (örn: https://www.youtube.com/shorts/...)")
        self.in_min = QSpinBox(); self.in_min.setRange(1, 180); self.in_min.setValue(1)
        self.in_group = QLineEdit(); self.in_group.setPlaceholderText("Grup (örn. Gece)")
        lbl = QLabel("dk")
        btn_add = QPushButton("Ekle"); btn_del = QPushButton("Sil")
        bar.addWidget(self.in_url, 5); bar.addWidget(self.in_min, 0); bar.addWidget(lbl, 0); bar.addWidget(self.in_group, 2); bar.addWidget(btn_add, 0); bar.addWidget(btn_del, 0)
        root.addLayout(bar)

        # LOG ekranı
        self.log = QTextEdit(); self.log.setReadOnly(True); self.log.setMinimumHeight(200)
        root.addWidget(self.log, 2)

        self.setCentralWidget(central)

        # events
        btn_add.clicked.connect(self.add_url)
        btn_del.clicked.connect(self.delete_selected)
        self.in_url.returnPressed.connect(self.add_url)
        self.btn_save.clicked.connect(lambda: (save_url_list(self.listw), self.set_status("Liste kaydedildi."), log_append(self.log, "Liste kaydedildi.")))
        self.btn_load.clicked.connect(self.load_list)
        self.btn_start.clicked.connect(lambda: self.start_group_now(self.in_active_group.text().strip()))
        self.btn_stop.clicked.connect(self.stop_run)
        self.btn_sched.clicked.connect(self.open_scheduler)
        self.btn_smtp_test.clicked.connect(self.smtp_test_now)

        # initial load
        cnt = load_url_list(self.listw)
        log_append(self.log, f"Uygulama açıldı. {cnt} URL yüklendi.")

    # --- UI helpers ---
    def set_status(self, s: str):
        self.lbl_status.setText(s)

    def add_url(self):
        url = (self.in_url.text() or "").strip()
        mins = int(self.in_min.value())
        grp  = (self.in_group.text() or "").strip()
        if not url:
            return
        self.listw.addItem(make_item(url, mins, grp))
        self.in_url.clear()
        save_url_list(self.listw)
        log_append(self.log, f"URL eklendi: {url} [{mins} dk] {{{grp or '—'}}}")

    def delete_selected(self):
        for it in self.listw.selectedItems():
            log_append(self.log, f"URL silindi: {(it.data(Qt.UserRole) or ('',0))[0]}")
            self.listw.takeItem(self.listw.row(it))
        save_url_list(self.listw)

    def load_list(self):
        cnt = load_url_list(self.listw)
        self.set_status(f"Yüklendi: {cnt} kayıt")
        log_append(self.log, f"Liste yeniden yüklendi: {cnt} kayıt")

    def _collect_group(self, group: str):
        out = []
        for i in range(self.listw.count()):
            it = self.listw.item(i)
            url, mins = it.data(Qt.UserRole) or (it.text(), 1)
            grp = (it.data(Qt.UserRole + 1) or "").strip()
            if (not group) or (grp == group):
                out.append((url, int(mins)))
        return out

    # --- Mail şablonu (IP sütunu eklendi) ---
    def _build_mail_html(self, results):
        rows = []
        for r in results:
            color = "green" if r["status"] == "OK" else "red"
            ip = r.get("ip", "-") or "-"
            rows.append(
                f"<tr>"
                f"<td>{r['url']}</td>"
                f"<td align='right'>{int(r['minutes'])}</td>"
                f"<td>{ip}</td>"
                f"<td style='color:{color}; font-weight:bold;'>{r['status']}</td>"
                f"</tr>"
            )
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        html = f"""
        <h3>Shorts Video Görevi Tamamlandı</h3>
        <p>URL Rotator işlemi tamamlandı. Aşağıda çalıştırılan URL'lerin özeti yer alıyor:</p>
        <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse; font-family:Arial, sans-serif; font-size:14px; width:100%;">
          <tr style="background:#f2f2f2; text-align:left;">
            <th>URL</th><th>Süre (dk)</th><th>Çıkış IP</th><th>Durum</th>
          </tr>
          {''.join(rows) if rows else '<tr><td colspan="4">Kayıt yok</td></tr>'}
        </table>
        <p style="margin-top:12px; font-size:12px; color:#555;">
          📌 Bu mail otomatik olarak oluşturulmuştur.<br>
          ⏰ Tamamlanma Zamanı: {ts}
        </p>
        """
        return html

    # --- Run ---
    def start_group_now(self, group: str, via_scheduler: bool=False):
        if self.worker is not None:
            if not via_scheduler:
                QMessageBox.warning(self, "Uyarı", "Zaten çalışıyor.")
            return
        urls = self._collect_group(group)
        if not urls:
            if not via_scheduler:
                QMessageBox.information(self, "Bilgi", f"Bu grupta URL yok: {group or 'Tümü'}")
            return

        self.signals = WorkerSignals()
        self.signals.finished.connect(self.on_finished)
        self.signals.status.connect(self.on_status)
        self.signals.progress.connect(self.on_progress)
        self.signals.logline.connect(lambda line: log_append(self.log, line))

        self.worker = RotatorWorker(urls, self.signals)
        self.worker.start()
        self.set_status(f"Çalışıyor… (Grup: {group or 'Tümü'})")
        self.progress.setValue(0)
        log_append(self.log, f"Görev başladı. Grup: {group or 'Tümü'} | {len(urls)} URL")

    def stop_run(self):
        if self.worker:
            self.worker.stop()
            self.set_status("Durduruluyor…")
            log_append(self.log, "Durdurma talebi gönderildi.")

    # --- Callbacks ---
    def on_finished(self):
        results = getattr(self.worker, "results", [])
        self.worker = None
        self.set_status("Tamamlandı veya durduruldu.")
        self.progress.setValue(0)
        log_append(self.log, "Görev tamamlandı; mail hazırlanıyor…")

        subject = "[URL Rotator] Shorts Video Görevi Tamamlandı"
        body_html = self._build_mail_html(results)
        ok, err = send_smtp_mail(subject, body_html)

        if ok:
            log_append(self.log, "SMTP: Bildirim maili gönderildi.")
            QMessageBox.information(self, "SMTP", "Bildirim maili gönderildi.")
        else:
            log_append(self.log, f"SMTP HATA: {err}")
            QMessageBox.warning(self, "SMTP",
                                "Mail gönderilemedi.\n\n"
                                f"- smtp.json okundu mu? (enabled:true)\n"
                                f"- host/port doğru mu?\n"
                                f"- Gmail App Password kullanılıyor mu?\n\n"
                                f"Hata: {err}")

    def on_status(self, msg: str):
        self.set_status(msg)
        log_append(self.log, msg)

    def on_progress(self, elapsed: int, total: int, url: str):
        pct = int(max(0, min(100, (elapsed/total)*100)))
        self.progress.setValue(pct)
        mm_e, ss_e = divmod(elapsed, 60)
        mm_t, ss_t = divmod(total, 60)
        status_line = f"{normalize_youtube_url(url)} — {mm_e:02d}:{ss_e:02d} / {mm_t:02d}:{ss_t:02d}  ({pct}%)"
        self.set_status(status_line)
        # çok sık yazmasın diye ~%20 aralıklarında logla
        if elapsed in (int(total*0.2), int(total*0.4), int(total*0.6), int(total*0.8)):
            log_append(self.log, f"İlerleme: {status_line}")

    def open_scheduler(self):
        dlg = ScheduleDialog(self)
        dlg.exec()

    def smtp_test_now(self):
        log_append(self.log, "SMTP Testi başlatıldı…")
        ok, err = send_smtp_mail(
            "[URL Rotator] SMTP Test",
            "<h3>Test</h3><p>Bu bir deneme mailidir.</p>"
        )
        if ok:
            log_append(self.log, "SMTP Test: Başarılı (mail gönderildi).")
            QMessageBox.information(self, "SMTP", "Test maili gönderildi.")
        else:
            log_append(self.log, f"SMTP Test: HATA — {err}")
            QMessageBox.warning(self, "SMTP", f"Test maili gönderilemedi.\n\nHata: {err}")

    def closeEvent(self, e):
        try:
            if self.scheduler: self.scheduler.stop()
        except Exception:
            pass
        log_append(self.log, "Uygulama kapanıyor.")
        super().closeEvent(e)

# ---------------- Main ----------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    if os.path.exists(APP_ICON):
        app.setWindowIcon(QIcon(APP_ICON))
    w = MainWindow()
    if os.path.exists(APP_ICON):
        w.setWindowIcon(QIcon(APP_ICON))
    w.show()
    sys.exit(app.exec())
