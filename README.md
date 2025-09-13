# URL Rotator (UC + Chrome140 Fix)

YouTube Shorts (ve diğer URL’ler) için basit bir **izleme/rotasyon** aracı.  
PySide6 ile masaüstü arayüzü, undetected-chromedriver + Selenium ile Chrome kontrolü, **zamanlama**, **grup bazlı oynatma**, **genel ilerleme (süre & adet)** ve **SMTP e-posta bildirimi** içerir.

> ⚠️ Yalnızca eğitim/test amaçlıdır. Kendi hesabınız ve içerikleriniz dışında kullanım, ilgili platformların hizmet koşullarını ihlâl edebilir.

---

## ✨ Özellikler

- **URL listesi**: süre (dk) ve **grup** alanıyla birlikte kaydet/yükle.
- **İlerleme**:
  - Aktif URL için yüzde ve zaman sayacı.
  - **Genel süre** (zaman ağırlıklı) ve **Genel URL** (tamamlanan adet) metrikleri.
- **Google oturumu**:
  - Profil tabanlı oturum; gerekirse **ayrı sekmede** giriş dener.
  - **2FA algılanırsa** (isteğe bağlı) işlemi güvenli şekilde iptal eder.
- **Zamanlama**: Belirli saat + gün aralığında bir **grubu** otomatik çalıştır.
- **SMTP**: Çalışma bitince özet tabloyu e-posta ile gönderir.
- **Kayıt**: `logs/short-log.txt`
- **Profiller**: Her e-posta için ayrı Chrome kullanıcı profili (`profiles/…`).

---

## 📸 Ekran görünümü

- Üstte durum + ilerleme ve sağda **Grup** alanı  
- Altında, desenli bir panelde **Genel süre** ve **Genel URL** (dikey çizgi ile ayrılmış)  
- Liste, alt giriş çubuğu ve log alanı

> Projeye görselleri `img/` klasörüne ekleyebilirsiniz (örn. `img/screenshot.png`) ve README’ye referans verebilirsiniz:
>
> ```md
> ![Ekran Görüntüsü](img/screenshot.png)
> ```

---

## 🧰 Gereksinimler

- **Windows 10/11**
- **Google Chrome** (sisteminizde kurulu olmalı)
- **Python 3.9+** (öneri: 3.10/3.11)
- Pip ile Python paketleri:
  - `PySide6`
  - `undetected-chromedriver`
  - `selenium`
  - `requests`

> Kod, eksikse `undetected-chromedriver / selenium / requests`’ı otomatik kurmayı dener.  
> **PySide6** için manuel kurulum yapmanız gerekir.

### Hızlı kurulum

```bash
# (opsiyonel) sanal ortam
python -m venv .venv
.venv\Scripts\activate

pip install PySide6 undetected-chromedriver selenium requests
```

> İsterseniz projeye bir `requirements.txt` ekleyin:
> ```txt
> PySide6
> undetected-chromedriver
> selenium
> requests
> ```

---

## 🚀 Çalıştırma

```bash
python test-shorts.py
```

> **Chrome sürümü**: Uygulama yüklü Chrome’u otomatik bulur; bulamazsa `FALLBACK_VERSION_MAIN = 140` ile eşleştirme dener.  
> Chrome’un sistemde bulunması önerilir. Gerekirse `DEFAULT_CHROME_EXE` yolunu değiştirin.

---

## 🗂️ Dosya Yapısı

```
project/
├─ test-shorts.py
├─ img/
│  └─ favicon.png                # (opsiyonel) pencere ikonu
├─ logs/
│  └─ short-log.txt              # çalışma günlükleri
├─ profiles/                     # her e-posta için Chrome profili (otomatik)
├─ shorts-urllist.json           # URL listesi
├─ schedule.json                 # zamanlama
├─ smtp.json                     # SMTP ayarları
└─ mail_accounts.json            # mail hesapları
```

---

## 🔧 Yapılandırma (kod başındaki sabitler)

Dosya başında:

```python
DEFAULT_CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
FALLBACK_VERSION_MAIN = 140
PLAY_VIDEOS = False

LOGIN_MODE = 'auto'     # 'auto' | 'off' | 'force'
CHALLENGE_MAX_WAIT = 180
START_AFTER_LOGIN = 'soft'  # 'require' | 'soft' | 'none'
LOGIN_GATE_WAIT = 90
ABORT_ON_2FA = True
```

- **PLAY_VIDEOS**: `True` olursa <video> bulunursa sessizce `play()` edilir.
- **LOGIN_MODE**: `off` → giriş denenmez; `auto` → gerekirse dener; `force` → zorunlu.
- **START_AFTER_LOGIN**: `require` → giriş olmadan başlamaz; `soft` → süre dolunca başlar; `none` → hemen başlat.
- **ABORT_ON_2FA**: 2FA tespitinde run’ı iptal eder ve raporlar.

---

## 🧾 JSON Dosyaları

### 1) `shorts-urllist.json`
URL listesi ve süre (dk) + grup.

```json
[
  {"url": "https://www.youtube.com/shorts/RSV_UBy0Ii4", "minutes": 1, "group": "Gece"},
  {"url": "https://www.youtube.com/shorts/fM0k_jyH2O", "minutes": 2, "group": "Gece"}
]
```

> Listeyi UI’den **Ekle/Sil/Kaydet** ile yönetebilirsiniz.

### 2) `schedule.json`
Zamanlama kayıtları.

```json
[
  {"time": "23:30", "group": "Gece", "days": "Her Gün", "enabled": true},
  {"time": "10:00", "group": "Gündüz", "days": "Hafta İçi", "enabled": true}
]
```

`days`: `Her Gün` | `Hafta İçi` | `Hafta Sonu`

### 3) `smtp.json`
E-posta bildirimi ayarları.

```json
{
  "enabled": false,
  "host": "smtp.gmail.com",
  "port": 465,
  "user": "",
  "password": "",
  "to_addr": "",
  "use_tls": false,
  "use_ssl": true
}
```

> Güvenlik için Gmail’de **Uygulama Şifresi** kullanmanız tavsiye edilir.

### 4) `mail_accounts.json`
Girişte kullanılacak hesaplar. UI’den de eklenebilir.

```json
[
  {
    "label": "Gmail - Hesap 1",
    "email": "ornek@gmail.com",
    "password": "sifre",
    "provider": "google",
    "enabled": true,
    "auth_overrides": {}
  }
]
```

> **Not:** Şifreler düz metin olarak saklanır. Özel/kurumsal ortamlarda farklı bir kimlik doğrulama stratejisi önerilir.

---

## 🗓️ Zamanlama ve Çalıştırma

1. URL’leri ekleyip **grup** atayın (örn. `Gece`).
2. Toolbar → **Zamanlama…** → saat/gün ve grup seçin → kaydedin.
3. Uygulama, dakikada bir kontrol eder; eşleşince **o grubu** başlatır.
4. Bitişte eğer `smtp.json` **enabled: true** ise **özet mail** gönderilir.

---

## 📊 İlerleme Mantığı

- **Aktif URL**: mm:ss / toplam ve **%** (üst progress bar).
- **Genel süre**: tüm planın **dakika bazında ilerlemesi**.
- **Genel URL**: tamamlanan URL sayısı / toplam.

> Genel metriklerde URL adresi **gösterilmez**; sade özet verilir.

---

## 🧪 Geliştirici Notları

- **YouTube URL normalizasyonu**: `youtu.be` → `watch?v=…` formatına çevrilir; `t=` parametresi korunur.
- **IP raporu**: Her URL başlangıcında çıkış IP’si log’a düşer.
- **Kill stray Chrome**: Başlangıçta muhtemel “yetim” Chrome/Driver süreçleri kapatılır.
- **Profil kilidi/port** dosyaları temizlenir (`Singleton*`, `DevToolsActivePort`).

---

## ❓ SSS

**➤ “Chrome bulunamadı”**  
`DEFAULT_CHROME_EXE` yolunu güncelleyin. 64-bit/32-bit kurulumları farklı klasörlerde olabilir.

**➤ “Giriş başarısız / 2FA ekranı”**  
`ABORT_ON_2FA = True` ise işlem iptal edilir. `START_AFTER_LOGIN='soft'` ise login başarılamasa bile süre dolunca run başlar.

**➤ “Play başlamıyor”**  
`PLAY_VIDEOS = True` yapın. Bazı sayfalarda otomatik oynatmayı tarayıcı engelleyebilir.

**➤ “Arayüz açılmıyor”**  
`PySide6` kurulu olduğundan emin olun; sanal ortamınız aktif mi?

---

## 🔐 Güvenlik

- E-posta şifreleri düz metin JSON’dadır. Kişisel depolamada tutmayın, yetkisiz erişime karşı koruyun.
- Gmail için **App Password** / işletme hesapları için kurumsal SMTP önerilir.

---

## 📦 Derleme (opsiyonel)

PyInstaller ile tek dosya exe üretmek isterseniz:

```bash
pip install pyinstaller
pyinstaller --noconsole --name "URL Rotator" --icon img/favicon.ico test-shorts.py
```

Gerekirse `img/` klasörünü `--add-data` ile ekleyin:
```bash
pyinstaller --noconsole --name "URL Rotator" --icon img/favicon.ico   --add-data "img;img" test-shorts.py
```

---

## 📝 Lisans

Bu depo **MIT** lisansı ile yayınlanmıştır. Ayrıntılar için `LICENSE` dosyasına bakın.

---

## 🤝 Katkı

- Hata/öneri için **Issues** oluşturabilirsiniz.
- Küçük PR’ler memnuniyetle kabul edilir (lint & black uyumlu).
