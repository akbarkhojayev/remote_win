# 💻 Remote Bot (Windows 10 / 11 Masofaviy Boshqaruv)

Telegram orqali **Windows 10 / 11** noutbuk yoki shaxsiy kompyuteringizni masofadan turib to'liq nazorat qilish, monitoring qilish va boshqarish uchun yaratilgan Telegram bot.

---

## ✨ Imkoniyatlar (Features)

| Bo'lim | Funksiya | Tavsif |
| :--- | :--- | :--- |
| 📊 **Monitoring** | Tizim Holati | CPU, RAM, Disk bandligi, Batareya foizi va zaryadlash holati, Wi-Fi/Tarmoq nomi (SSID), Mahalliy IP, Ovoz balandligi |
| 📱 **Faollik** | Active Window Tracker | Noutbukda ayni vaqtda qaysi dastur va oyna ochiqligini (Chrome, VS Code, PyCharm, Telegram va h.k.) xavfsiz aniqlash |
| 📸 **Kamera** | Web-camera Capture | Noutbukning veb-kamerasi orqali bir zumda surat olib Telegramga yuborish (`opencv-python`) |
| 🖥 **Ekran** | Screen Screenshot | Noutbuk ekranining to'liq va tiniq skrinshotini olib yuborish (`pillow`) |
| 🎵 **Spotify** | Spotify & Media Pult | Spotify'ni ochish, treklarni boshqarish (Play/Pause, Keyingi, Oldingi) hamda joriy ijrochi va trek nomini ko'rish |
| 🔊 **Ovoz** | Volume Control | Real vaqtda ovoz balandligini boshqarish (+10%, -10%, Mute/Unmute) va aniq foizini ko'rsatish (`pycaw`) |
| 🔒 **Qulflash** | Lock Screen | Noutbuk ekranini masofadan bir zumda qulflash (`LockWorkStation`) |
| 📋 **Clipboard** | Vaqtinchalik Xotira | Kompyuter clipboardidagi matnni Telegramda o'qish va kompyuter xotirasiga yangi matn nusxalash (`pyperclip`) |
| 🔔 **Bildirishnoma** | Native Windows Toast | Noutbuk ekranining burchagida zamonaviy Windows Toast bildirishnomasini chiqarish |
| 📅 **Hisobot** | Daily Report | Kun davomida qaysi dasturlarda qancha vaqt ishlaganingiz va batareya dinamikasi haqida xulosa (23:55 da) |
| ⚡️ **Quvvat** | Shutdown & Reboot | Noutbukni xavfsiz qayta yoqish yoki butunlay o'chirish (tasdiqlash orqali) |

---

## 🛠 O'rnatish va Sozlash

### 1. Python o'rnatilganligini tekshiring
Kompyuteringizda **Python 3.10 yoki undan yuqori** versiya o'rnatilgan bo'lishi kerak. O'rnatish paytida **`Add python.exe to PATH`** katakchasini belgilash tavsiya etiladi.

### 2. Sozlamalar (`.env` fayli):
Loyiha papkasidagi `.env` faylini oching va ma'lumotlaringizni kiriting:

```ini
# Telegram Bot Token (@BotFather dan olingan)
BOT_TOKEN=1234567890:ABCDefGhIJklMNopQRstUVwxyz

# Sizning shaxsiy Telegram ID raqamingiz (@userinfobot orqali olingan)
ADMIN_ID=8200157886

# Qurilma nomi (ixtiyoriy)
DEVICE_NAME=Windows 11 Laptop

# Sozlamalar
TIMEZONE=Asia/Tashkent
TRACK_INTERVAL_SECONDS=60
DAILY_REPORT_HOUR=23
DAILY_REPORT_MINUTE=55
LOW_BATTERY_THRESHOLD=20
```

---

## 🚀 Ishga Tushirish Usullari

### 1-usul: Oddiy ishga tushirish (Konsol oynasi bilan)
Papkadagi **`start_bot.bat`** faylini ikki marta bosing.
U avtomatik ravishda virtual muhitni (`venv`) yaratadi, paketlarni o'rnatadi va botni ishga tushiradi.

---

### 2-usul: Fonda (Qora oynasiz / Silent) ishga tushirish
Agar konsol oynasi ko'rinmasdan, bot fonda jimgina ishlashini xohlasangiz:
* **`start_hidden.vbs`** faylini ikki marta bosing.

---

### 3-usul: Kompyuter yoqilganda avtomatik ishga tushirish (Autostart)
Windows yoqilganda bot avtomatik fonda ishlashi uchun:

1. Klaviaturada **`Win + R`** tugmalarini bosing;
2. **`shell:startup`** deb yozib, **Enter** bosing (Windows Avtostart papkasi ochiladi);
3. Ushbu papka ichiga loyihangizdagi **`start_hidden.vbs`** faylining **Yorlig'ini (Shortcut / Ярлык)** tashlab qo'ying.

> 💡 *Endi kompyuteringiz yoqilishi bilan bot avtomatik fonda ishga tushadi, internetga ulanishni kutadi va Telegramingizga **"🟢 Noutbuk Ishga Tushdi"** xabarini yuboradi!*

---

## 📱 Telegram Menyusi va Buyruqlar

```text
┌─────────────────────────┬─────────────────────────┐
│   📊 Holat              │   📸 Kamera             │
├─────────────────────────┼─────────────────────────┤
│   🖥 Ekran (Skrinshot)  │   🎵 Spotify            │
├─────────────────────────┼─────────────────────────┤
│   🔊 Ovoz               │   🔒 Qulflash           │
├─────────────────────────┼─────────────────────────┤
│   📋 Clipboard          │   🔔 Xabar yuborish     │
├─────────────────────────┼─────────────────────────┤
│   📅 Kunlik hisobot     │   ⚡️ Quvvat / O'chirish │
└─────────────────────────┴─────────────────────────┘
```

| Buyruq | Tavsif |
| :--- | :--- |
| `/start` | Botni ishga tushirish va asosiy menyuni ochish |
| `/status` yoki **📊 Holat** | CPU, RAM, Disk, Batareya, Tarmoq (SSID + IP), Ovoz va faol dasturni ko'rsatish |
| `/photo` yoki **📸 Kamera** | Noutbuk veb-kamerasidan tezkor surat olish |
| `/screenshot` yoki **🖥 Ekran** | Noutbuk ekranining to'liq skrinshotini olish |
| `/spotify`, `/music` yoki **🎵 Spotify** | Spotify'ni ochish va musiqani boshqarish pulti |
| **🔊 Ovoz** | Ovozni boshqarish (+10%, -10%, Mute/Unmute) |
| `/lock` yoki **🔒 Qulflash** | Noutbuk ekranini qulflash |
| **📋 Clipboard** | Kompyuter clipboardidagi matnni o'qish yoki yangi matn yozish |
| **🔔 Xabar yuborish** | Kompyuter ekraniga Windows Toast bildirishnomasi chiqarish |
| `/report` yoki **📅 Kunlik hisobot** | Kunlik dasturlar faolligi va batareya sarfi hisoboti |
| `/power` yoki **⚡️ Quvvat / O'chirish** | Noutbukni qayta yoqish (Reboot) yoki o'chirish (Shutdown) |

---

## 🔒 Xavfsizlik
Botga begona shaxslar kirishining oldini olish maqsadida **AdminAuthMiddleware** o'rnatilgan. Faqat `.env` faylida ko'rsatilgan `ADMIN_ID` egasigina buyruqlardan foydalana oladi.
