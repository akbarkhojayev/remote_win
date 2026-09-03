# 💻 Remote Bot (Windows 10 / 11 Edition)

Telegram orqali **Windows** noutbuk yoki kompyuteringizni dunyoning istalgan nuqtasidan masofadan turib to'liq nazorat qilish va monitoring qilish uchun mo'ljallangan bot.

---

## ✨ Imkoniyatlar (Features)

| Bo'lim | Funksiya | Tavsif |
| :--- | :--- | :--- |
| 📊 **Monitoring** | Tizim Holati | CPU, RAM, Disk bo'sh joyi, Batareya foizi va zaryadlash holati, Wi-Fi SSID, Ovoz balandligi |
| 📱 **Faollik** | Active Window Tracker | Foydalanuvchi aynan qaysi dasturda (Chrome, PyCharm, Telegram, VS Code va h.k.) ishlayotganini aniqlash |
| 📸 **Kamera** | Web-camera Capture | Noutbukning veb-kamerasi orqali bir zumda surat olib Telegramga yuborish (`opencv-python`) |
| 🎵 **Spotify** | Spotify Controller | Noutbukda Spotify'ni ochish, treklarni boshqarish (Play/Pause, Keyingi, Oldingi) |
| 🔊 **Ovoz** | Volume Control | Inline tugmalar orqali ovozni boshqarish (+10%, -10%, Mute/Unmute) |
| 🔒 **Qulflash** | Lock Screen | Ekranni masofadan bir zumda qulflash (`LockWorkStation`) |
| 📋 **Clipboard** | Vaqtinchalik Xotira | Kompyuter clipboardidagi matnni o'qish va yangi matn nusxalash (`pyperclip`) |
| 🔔 **Bildirishnoma** | Desktop Notification | Kompyuter ekraniga toza tizim bildirishnomasini chiqarish (`plyer`) |
| 📅 **Hisobot** | Daily Report | Kun davomida qaysi dasturlarda necha soat ishlaganingiz haqida kunlik xulosa (23:55 da) |
| 🛑 **Quvvat** | Shutdown & Reboot | Noutbukni masofadan xavfsiz o'chirish yoki qayta yoqish |

---

## 🛠 O'rnatish va Ishga Tushirish (Installation)

### 1. Python o'rnatilganligini tekshiring
Windows kompyuteringizda **Python 3.10+** o'rnatilgan bo'lishi kerak. O'rnatish paytida **`Add python.exe to PATH`** katakchasini belgilashni unutmang.

### 2. Sozlamalarni kiritish (`.env`):
`remote_win` papkasi ichidagi `.env.example` faylidan nusxa oling va nomini `.env` qilib o'zgartiring:
* `BOT_TOKEN` — [@BotFather](https://t.me/BotFather) orqali olingan bot tokeningiz.
* `ADMIN_ID` — [@userinfobot](https://t.me/userinfobot) orqali olingan shaxsiy Telegram raqamli ID'ingiz.

Namuna (`.env`):
```ini
BOT_TOKEN=1234567890:ABCDefGhIJklMNopQRstUVwxyz
ADMIN_ID=8200157886
TIMEZONE=Asia/Tashkent
TRACK_INTERVAL_SECONDS=60
DAILY_REPORT_HOUR=23
DAILY_REPORT_MINUTE=55
LOW_BATTERY_THRESHOLD=20
```

---

## 🚀 Ishga Tushirish

### Usul 1: Tezkor ishga tushirish (Bir marta bosish orqali)
Papkadagi **`start_bot.bat`** faylini ikki marta bosing. U avtomatik tarzda:
1. Virtual muhitni (`venv`) yaratadi;
2. Barcha kerakli kutubxonalarni o'rnatadi;
3. Botni ishga tushiradi.

---

### Usul 2: Fonda (Qora oynasiz / Silent) ishga tushirish
Agar konsol oynasi ko'rinmasdan, bot fonda jimgina ishlashini xohlasangiz:
* **`start_hidden.vbs`** faylini ikki marta bosing.

---

## ⚙️ Kompyuter yonganda avtomatik ishga tushirish (Autostart)

Windows yonganda bot avtomatik fonda ishlashi uchun:

1. Klaviaturada **`Win + R`** tugmalarini bosing;
2. **`shell:startup`** deb yozib, **Enter** bosing (Avtostart papkasi ochiladi);
3. Ushbu papkaga `remote_win` ichidagi **`start_hidden.vbs`** faylining **Yorlig'ini (Shortcut / Ярлык)** tashlab qo'ying.

Endi kompyuteringiz yonganda bot avtomatik tarzda fonda ishga tushadi va Telegramingizga **"🟢 Noutbuk Ishga Tushdi"** xabarini yuboradi!

---

## 📱 Telegram Buyruqlari va Menyusi

```text
┌─────────────────┬─────────────────┐
│   📊 Holat      │   📸 Kamera     │
├─────────────────┼─────────────────┤
│   🎵 Spotify    │   🔊 Ovoz       │
├─────────────────┼─────────────────┤
│   🔒 Qulflash   │   📋 Clipboard  │
├─────────────────┼─────────────────┤
│ 📅 Kunlik hisob │ 🔔 Xabar yubor  │
├─────────────────┼─────────────────┤
│ 🔄 Qayta yoqish │   🛑 O'chirish  │
└─────────────────┴─────────────────┘
```

* **📊 Holat (`/status`)** — CPU, RAM, Disk, Batareya, Wi-Fi, Ovoz va faol dastur holati.
* **📸 Kamera (`/photo`)** — Veb-kameradan bir zumda foto oladi va yuboradi.
* **🎵 Spotify (`/spotify`)** — Spotify'ni ochadi va musiqani boshqarish pultini chiqaradi.
* **🔊 Ovoz** — Ovozni pasaytirish/ko'tarish yoki Mute qilish.
* **🔒 Qulflash (`/lock`)** — Ekranni qulflaydi.
* **📋 Clipboard** — Kompyuter xotirasidagi matnni olish yoki yangi matn joylash.
* **📅 Kunlik hisobot (`/report`)** — Kunlik dasturlar faolligi va batareya sarfi.
* **🔔 Xabar yuborish** — Kompyuter ekraniga pop-up bildirishnoma chiqaradi.
* **🔄 Qayta yoqish (`/reboot`) & 🛑 O'chirish (`/shutdown`)** — Tasdiqlash orqali tizimni boshqarish.

---

## 🔒 Xavfsizlik
Botga begona foydalanuvchilar kirishini taqiqlash uchun **Middleware & ID Filter** o'rnatilgan. Faqat `.env` dagi `ADMIN_ID` egasigina buyruqlarni boshqara oladi.
