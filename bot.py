import asyncio
import ctypes
import json
import logging
import os
import platform
import re
import socket
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import aiofiles
import psutil
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

# ==============================================================================
# 1. KONFIGURATSIYA VA .ENV YUKLASH
# ==============================================================================

def load_env_file(filepath: str = ".env") -> None:
    if not os.path.exists(filepath):
        return
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("'\"")
            if key not in os.environ:
                os.environ[key] = val

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_env_file(os.path.join(BASE_DIR, ".env"))

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_ID_RAW = os.environ.get("ADMIN_ID", "0").strip()

if not BOT_TOKEN or not ADMIN_ID_RAW or ADMIN_ID_RAW == "0":
    print("XATOLIK: .env faylida BOT_TOKEN yoki ADMIN_ID ko'rsatilmagan!")
    print("Iltimos, .env faylini to'ldiring.")
    sys.exit(1)

try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except ValueError:
    print(f"XATOLIK: ADMIN_ID son bo'lishi kerak, berilgan qiymat: {ADMIN_ID_RAW}")
    sys.exit(1)

TIMEZONE_STR = os.environ.get("TIMEZONE", "Asia/Tashkent")
try:
    import zoneinfo
    UZ_TZ = zoneinfo.ZoneInfo(TIMEZONE_STR)
except Exception:
    UZ_TZ = timezone(timedelta(hours=5))

TRACK_INTERVAL_SECONDS = int(os.environ.get("TRACK_INTERVAL_SECONDS", "60"))
DAILY_REPORT_HOUR = int(os.environ.get("DAILY_REPORT_HOUR", "23"))
DAILY_REPORT_MINUTE = int(os.environ.get("DAILY_REPORT_MINUTE", "55"))
LOW_BATTERY_THRESHOLD = int(os.environ.get("LOW_BATTERY_THRESHOLD", "20"))
STATS_FILE = os.path.join(BASE_DIR, "daily_stats.json")

# ==============================================================================
# 2. LOGGING SOZLAMALARI
# ==============================================================================

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_FILE = os.path.join(BASE_DIR, "remote_bot.log")

logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("remote_win_bot")

# ==============================================================================
# 3. GLOBAL STATISTIKA VA XOTIRA
# ==============================================================================

daily_stats: Dict[str, Any] = {
    "date": datetime.now(UZ_TZ).strftime("%Y-%m-%d"),
    "app_minutes": {},
    "battery_samples": [],
    "report_sent": False,
}

low_battery_notified = False

SYSTEM_IGNORE_CLASSES = {
    "", "unknown", "bosh ekran", "desktop", "explorer", "taskbar",
    "applicationframehost", "shellexperiencehost", "lockapp"
}

def load_daily_stats():
    global daily_stats
    today_str = datetime.now(UZ_TZ).strftime("%Y-%m-%d")
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("date") == today_str:
                    daily_stats = data
                    logger.info(f"Bugungi statistika qayta tiklandi ({today_str}).")
                    return
        except Exception as e:
            logger.error(f"Statistika faylini o'qishda xatolik: {e}")

    daily_stats = {
        "date": today_str,
        "app_minutes": {},
        "battery_samples": [],
        "report_sent": False,
    }
    save_daily_stats()

def save_daily_stats():
    try:
        temp_file = STATS_FILE + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(daily_stats, f, ensure_ascii=False, indent=2)
        os.replace(temp_file, STATS_FILE)
    except Exception as e:
        logger.error(f"Statistikani saqlashda xatolik: {e}")

# ==============================================================================
# 4. TUGMALAR VA MENYULAR
# ==============================================================================

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Holat"), KeyboardButton(text="📸 Kamera")],
        [KeyboardButton(text="🎵 Spotify"), KeyboardButton(text="🔊 Ovoz")],
        [KeyboardButton(text="🔒 Qulflash"), KeyboardButton(text="📋 Clipboard")],
        [KeyboardButton(text="📅 Kunlik hisobot"), KeyboardButton(text="🔔 Xabar yuborish")],
        [KeyboardButton(text="🔄 Qayta yoqish"), KeyboardButton(text="🛑 O'chirish")],
    ],
    resize_keyboard=True,
)

status_inline_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Yangilash", callback_data="status_refresh"),
            InlineKeyboardButton(text="📸 Kamera", callback_data="quick_photo"),
            InlineKeyboardButton(text="🎵 Spotify", callback_data="quick_music"),
        ]
    ]
)

music_inline_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="⏮ Oldingi", callback_data="mus_prev"),
            InlineKeyboardButton(text="⏯ Play / Pause", callback_data="mus_play_pause"),
            InlineKeyboardButton(text="⏭ Keyingi", callback_data="mus_next"),
        ],
        [
            InlineKeyboardButton(text="🔄 Yangilash", callback_data="mus_refresh"),
        ]
    ]
)

volume_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="🔉 -10%", callback_data="vol_down"),
            InlineKeyboardButton(text="🔇 Mute / Unmute", callback_data="vol_mute"),
            InlineKeyboardButton(text="🔊 +10%", callback_data="vol_up"),
        ]
    ]
)

clipboard_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="📥 Matnni o'qish", callback_data="clip_get"),
            InlineKeyboardButton(text="📤 Yangi matn yozish", callback_data="clip_set"),
        ]
    ]
)

def confirm_kb(action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ha, tasdiqlayman", callback_data=f"confirm_{action}"),
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel"),
            ]
        ]
    )

class NotifyState(StatesGroup):
    waiting_text = State()

class ClipboardState(StatesGroup):
    waiting_text = State()

# ==============================================================================
# 5. WINDOWS TIZIM FUNKSIYALARI (SYSTEM HELPERS)
# ==============================================================================

def get_device_name() -> str:
    env_name = os.environ.get("DEVICE_NAME", "").strip()
    if env_name:
        return env_name
    try:
        return socket.gethostname()
    except Exception:
        return f"Windows {platform.release()} PC"

def make_progress_bar(percent: int, length: int = 8) -> str:
    filled = int(round(length * (percent / 100)))
    filled = max(0, min(length, filled))
    return "■" * filled + "□" * (length - filled)

def clean_app_name(raw_name: str) -> str:
    if not raw_name:
        return "Bosh ekran"
    raw_lower = raw_name.lower().replace(".exe", "").strip()
    
    app_map = {
        "telegram": "Telegram",
        "chrome": "Google Chrome",
        "msedge": "Microsoft Edge",
        "firefox": "Firefox",
        "spotify": "Spotify",
        "pycharm64": "PyCharm",
        "pycharm": "PyCharm",
        "code": "VS Code",
        "devenv": "Visual Studio",
        "idea64": "IntelliJ IDEA",
        "clion64": "CLion",
        "windowsterminal": "Windows Terminal",
        "cmd": "Buyruqlar satri (CMD)",
        "powershell": "PowerShell",
        "explorer": "Fayl menejeri (Explorer)",
        "vlc": "VLC Media Player",
        "obsidian": "Obsidian",
        "notion": "Notion",
        "discord": "Discord",
    }
    for k, v in app_map.items():
        if k in raw_lower:
            return v
    return raw_name.replace(".exe", "").capitalize()

def _sync_get_active_window_name() -> str:
    try:
        import win32gui
        import win32process
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return "Bosh ekran"
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        proc = psutil.Process(pid)
        app_name = proc.name()
        return clean_app_name(app_name)
    except Exception:
        pass
    return "Bosh ekran"

async def get_active_window_name() -> str:
    return await asyncio.to_thread(_sync_get_active_window_name)

def _sync_get_wifi_name() -> str:
    try:
        out = subprocess.check_output(
            ["netsh", "wlan", "show", "interfaces"],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            timeout=2
        ).decode("utf-8", errors="ignore")
        match = re.search(r"^\s*SSID\s*:\s*(.+)$", out, re.MULTILINE)
        if match:
            ssid = match.group(1).strip()
            if ssid and ssid != "None":
                return ssid
    except Exception:
        pass
    return "Ulanmagan"

async def get_wifi_name() -> str:
    return await asyncio.to_thread(_sync_get_wifi_name)

# --- Ovoz boshqaruvi (pycaw + ctypes fallback) ---
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF

def _sync_get_volume_percent() -> str:
    try:
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        from comtypes import CLSCTX_ALL
        from ctypes import cast, POINTER
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        current_volume = volume.GetMasterVolumeLevelScalar()
        return f"{int(round(current_volume * 100))}%"
    except Exception:
        return "50%"

async def get_current_volume_percent() -> str:
    return await asyncio.to_thread(_sync_get_volume_percent)

def _sync_is_muted() -> bool:
    try:
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        from comtypes import CLSCTX_ALL
        from ctypes import cast, POINTER
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        return bool(volume.GetMute())
    except Exception:
        return False

async def is_muted() -> bool:
    return await asyncio.to_thread(_sync_is_muted)

def _sync_run_volume_action(arg: str) -> str:
    try:
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        from comtypes import CLSCTX_ALL
        from ctypes import cast, POINTER
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        
        if arg == "up":
            cur = volume.GetMasterVolumeLevelScalar()
            volume.SetMasterVolumeLevelScalar(min(1.0, cur + 0.1), None)
        elif arg == "down":
            cur = volume.GetMasterVolumeLevelScalar()
            volume.SetMasterVolumeLevelScalar(max(0.0, cur - 0.1), None)
        elif arg == "mute":
            cur_mute = volume.GetMute()
            volume.SetMute(not cur_mute, None)
    except Exception:
        # Fallback via keybd_event
        if arg == "up":
            ctypes.windll.user32.keybd_event(VK_VOLUME_UP, 0, 0, 0)
        elif arg == "down":
            ctypes.windll.user32.keybd_event(VK_VOLUME_DOWN, 0, 0, 0)
        elif arg == "mute":
            ctypes.windll.user32.keybd_event(VK_VOLUME_MUTE, 0, 0, 0)

    vol = _sync_get_volume_percent()
    muted = _sync_is_muted()
    muted_str = " <i>(O'chirilgan 🔇)</i>" if muted else ""
    return f"🔊 <b>Ovoz Boshqaruvi</b>\n\n🔈 <b>Joriy daraja:</b> <b>{vol}</b>{muted_str}"

async def run_volume_action(arg: str) -> str:
    return await asyncio.to_thread(_sync_run_volume_action, arg)

# --- Veb-kamera (OpenCV) ---
def _sync_take_photo(output_path: str):
    import cv2
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(0)
    
    try:
        # Kameraga fokus va yorug'likni moslash uchun 3 ta kadr tashlab o'tish
        for _ in range(3):
            cap.read()
        ret, frame = cap.read()
        if ret:
            cv2.imwrite(output_path, frame)
        else:
            raise RuntimeError("Kameradan tasvir olib bo'lmadi.")
    finally:
        cap.release()

async def take_photo(output_path: str):
    await asyncio.to_thread(_sync_take_photo, output_path)

# --- Spotify & Media boshqaruv ---
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3

def _sync_open_spotify() -> bool:
    logger.info("Spotify ishga tushirilmoqda...")
    try:
        os.startfile("spotify:")
        return True
    except Exception:
        try:
            subprocess.Popen(["cmd", "/c", "start", "spotify:"], shell=True)
            return True
        except Exception:
            return False

async def open_spotify() -> bool:
    return await asyncio.to_thread(_sync_open_spotify)

def _sync_media_control(action: str) -> str:
    logger.info(f"Media buyruq: {action}")
    if action == "play_pause":
        ctypes.windll.user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, 0, 0)
        return "⏯ Ijro holati o'zgartirildi"
    elif action == "next":
        ctypes.windll.user32.keybd_event(VK_MEDIA_NEXT_TRACK, 0, 0, 0)
        return "⏭ Keyingi trekka o'tkazildi"
    elif action == "prev":
        ctypes.windll.user32.keybd_event(VK_MEDIA_PREV_TRACK, 0, 0, 0)
        return "⏮ Oldingi trekka o'tkazildi"
    return "✅ Bajarildi"

async def run_media_control(action: str) -> str:
    return await asyncio.to_thread(_sync_media_control, action)

def _sync_get_music_info() -> Dict[str, str]:
    info = {"title": "", "artist": "", "album": "", "status": "Faol", "player": "Spotify"}
    try:
        import win32gui
        def enum_windows_callback(hwnd, extra):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title and " - " in title and ("Spotify" in title or "Chrome" in title):
                    extra.append(title)
        windows = []
        win32gui.EnumWindows(enum_windows_callback, windows)
        if windows:
            title_part = windows[0].split(" - ")
            if len(title_part) >= 2:
                info["artist"] = title_part[0].strip()
                info["title"] = title_part[1].replace("Spotify", "").strip()
    except Exception:
        pass
    return info

async def get_music_info() -> Dict[str, str]:
    return await asyncio.to_thread(_sync_get_music_info)

async def build_music_view() -> Tuple[str, InlineKeyboardMarkup]:
    info = await get_music_info()
    title = info.get("title")
    artist = info.get("artist")
    
    if title:
        meta_text = (
            f"🎧 <b>Trek:</b> <b>{title}</b>\n"
            f"👤 <b>Ijrochi:</b> {artist}\n"
            f"📊 <b>Holat:</b> Ijro etilmoqda 🟢\n"
            f"💻 <b>Pleyer:</b> Spotify"
        )
    else:
        meta_text = (
            "🎧 <b>Spotify Boshqaruvi</b>\n\n"
            "Musiqani boshqarish uchun quyidagi tugmalardan foydalaning 👇"
        )

    text = f"🟢 <b>Spotify Boshqaruvi</b>\n\n{meta_text}"
    return text, music_inline_kb

# --- Ekranni qulflash ---
def _sync_lock_screen():
    ctypes.windll.user32.LockWorkStation()

async def lock_screen():
    await asyncio.to_thread(_sync_lock_screen)

# --- Clipboard ---
def _sync_get_clipboard_text() -> Optional[str]:
    try:
        import pyperclip
        text = pyperclip.paste()
        return text if text else None
    except Exception:
        return None

async def get_clipboard_text() -> Optional[str]:
    return await asyncio.to_thread(_sync_get_clipboard_text)

def _sync_set_clipboard_text(text: str):
    import pyperclip
    pyperclip.copy(text)

async def set_clipboard_text(text: str):
    await asyncio.to_thread(_sync_set_clipboard_text, text)

# --- Bildirishnoma (Notification) ---
def _sync_send_notification(text: str, title: str = "Bildirishnoma"):
    try:
        from plyer import notification
        notification.notify(title=title, message=text, app_name="Remote Control", timeout=5)
    except Exception:
        # Fallback via PowerShell
        ps_cmd = f'[reflection.assembly]::loadwithpartialname("System.Windows.Forms"); [Windows.Forms.MessageBox]::Show("{text}", "{title}")'
        subprocess.Popen(["powershell", "-WindowStyle", "Hidden", "-Command", ps_cmd])

async def send_desktop_notification(text: str, title: str = "Bildirishnoma"):
    await asyncio.to_thread(_sync_send_notification, text, title)

# --- O'chirish va Qayta yoqish ---
def _sync_shutdown():
    logger.info("Noutbuk o'chirilmoqda...")
    os.system("shutdown /s /t 0")

async def execute_shutdown():
    await asyncio.to_thread(_sync_shutdown)

def _sync_reboot():
    logger.info("Noutbuk qayta yoqilmoqda...")
    os.system("shutdown /r /t 0")

async def execute_reboot():
    await asyncio.to_thread(_sync_reboot)

# ==============================================================================
# 6. ASOSIY STATISTIKA VA HISOBOT FORMATLARI
# ==============================================================================

async def build_status_view() -> Tuple[str, InlineKeyboardMarkup]:
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage(os.path.splitdrive(os.path.abspath(__file__))[0] + "\\")
    disk_percent = disk.percent
    free_gb = disk.free / (1024 ** 3)

    battery = psutil.sensors_battery()
    if battery:
        bat_state = "Zaryadlanmoqda ⚡️" if battery.power_plugged else "Batareyada 🔋"
        bat_text = f"<b>{round(battery.percent)}%</b> <i>({bat_state})</i>"
    else:
        bat_text = "Mavjud emas"

    wifi_name, volume, muted, current_app = await asyncio.gather(
        get_wifi_name(),
        get_current_volume_percent(),
        is_muted(),
        get_active_window_name(),
    )

    volume_text = f"<b>{volume}</b>" + (" <i>(O'chirilgan 🔇)</i>" if muted else "")
    device_name = get_device_name()
    now_str = datetime.now(UZ_TZ).strftime("%H:%M:%S")

    cpu_bar = make_progress_bar(cpu)
    ram_bar = make_progress_bar(ram)

    text = (
        f"🖥 <b>Tizim Holati</b> • <code>{device_name}</code>\n\n"
        f"⚡️ <b>CPU:</b> <code>{cpu_bar}</code> {cpu}%\n"
        f"🧠 <b>RAM:</b> <code>{ram_bar}</code> {ram}%\n"
        f"🔋 <b>Batareya:</b> {bat_text}\n"
        f"💽 <b>Disk:</b> {disk_percent}% band <i>({free_gb:.1f} GB bo'sh)</i>\n"
        f"📶 <b>Wi-Fi:</b> <code>{wifi_name}</code>\n"
        f"🔊 <b>Ovoz:</b> {volume_text}\n"
        f"📱 <b>Faol oyna:</b> <b>{current_app}</b>\n\n"
        f"🕒 <i>Yangilandi: {now_str}</i>"
    )
    return text, status_inline_kb

def build_daily_report_text(stats_dict: Optional[Dict[str, Any]] = None) -> str:
    stats = stats_dict or daily_stats
    date_str = stats.get("date", datetime.now(UZ_TZ).strftime("%Y-%m-%d"))
    battery_samples = stats.get("battery_samples", [])

    if battery_samples:
        start_percent = battery_samples[0]["percent"]
        current_percent = battery_samples[-1]["percent"]
        min_percent = min(s["percent"] for s in battery_samples)
        max_percent = max(s["percent"] for s in battery_samples)
    else:
        battery = psutil.sensors_battery()
        cur = round(battery.percent) if battery else 0
        start_percent = current_percent = min_percent = max_percent = cur

    total_minutes = sum(stats.get("app_minutes", {}).values())
    hours = total_minutes // 60
    minutes = total_minutes % 60

    merged_apps = Counter()
    for raw_k, count in stats.get("app_minutes", {}).items():
        cleaned_k = clean_app_name(raw_k)
        if cleaned_k and cleaned_k not in SYSTEM_IGNORE_CLASSES:
            merged_apps[cleaned_k] += count

    top_apps = merged_apps.most_common(8)
    apps_lines = []
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"]
    rank = 0
    for name, count in top_apps:
        h = count // 60
        m = count % 60
        time_str = f"{h} soat {m} daqiqa" if h > 0 else f"{m} daqiqa"
        medal = medals[rank] if rank < len(medals) else f"🔹 {rank + 1}."
        apps_lines.append(f"{medal} <b>{name}</b> — {time_str}")
        rank += 1

    apps_text = "\n".join(apps_lines) if apps_lines else "<i>Ilovalar faolligi qayd etilmadi</i>"
    device_name = get_device_name()

    return (
        f"📊 <b>Kunlik Foydalanish Hisoboti</b>\n"
        f"🗓 <i>{date_str}</i> • <code>{device_name}</code>\n\n"
        f"⏱ <b>Umumiy faol vaqt:</b> <b>{hours} soat {minutes} daqiqa</b>\n"
        f"🔋 <b>Batareya dinamikasi:</b> {start_percent}% ➔ {current_percent}% "
        f"<i>(min: {min_percent}%, max: {max_percent}%)</i>\n\n"
        f"📱 <b>Eng ko'p ishlatilgan ilovalar:</b>\n"
        f"{apps_text}"
    )

# ==============================================================================
# 7. TELEGRAM BOT INIT VA MIDDLEWARE
# ==============================================================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

@dp.message(F.from_user.id != ADMIN_ID)
async def unauthorized_message(message: types.Message):
    user = message.from_user
    logger.warning(f"Ruxsatsiz xabar! ID: {user.id}, Username: @{user.username}")
    await message.reply("⛔️ Kechirasiz, siz ushbu noutbuk boshqaruvchisi emassiz!")

@dp.callback_query(F.from_user.id != ADMIN_ID)
async def unauthorized_callback(callback: CallbackQuery):
    await callback.answer("⛔️ Ruxsat berilmagan!", show_alert=True)

# ==============================================================================
# 8. HANDLERS VA BUYRUQLAR
# ==============================================================================

@dp.message(Command("start", "help"))
async def cmd_start(message: types.Message):
    device_name = get_device_name()
    logger.info("Admin /start buyrug'ini yubordi.")
    await message.answer(
        "🤖 <b>Masofaviy Boshqaruv Markazi (Windows)</b>\n"
        f"💻 <b>Qurilma:</b> <code>{device_name}</code>\n\n"
        "Noutbukingizni nazorat qilish va boshqarish uchun menyudan foydalaning 👇",
        parse_mode="HTML",
        reply_markup=main_menu,
    )

@dp.message(Command("status"))
@dp.message(F.text == "📊 Holat")
async def cmd_status(message: types.Message):
    status_text, kb = await build_status_view()
    await message.answer(status_text, parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "status_refresh")
async def callback_status_refresh(callback: CallbackQuery):
    try:
        status_text, kb = await build_status_view()
        await callback.message.edit_text(status_text, parse_mode="HTML", reply_markup=kb)
        await callback.answer("✅ Yangilandi")
    except Exception:
        await callback.answer("Ma'lumotlar yangilandi")

@dp.message(Command("report"))
@dp.message(F.text == "📅 Kunlik hisobot")
async def cmd_report(message: types.Message):
    report_text = build_daily_report_text()
    await message.answer(report_text, parse_mode="HTML")

async def handle_photo_capture(target_chat_id: int):
    now_str = datetime.now(UZ_TZ).strftime("%H:%M:%S")
    cam_file = os.path.join(BASE_DIR, f"cam_shot_{int(datetime.now().timestamp())}.jpg")
    try:
        await take_photo(cam_file)
        photo = FSInputFile(cam_file)
        await bot.send_photo(chat_id=target_chat_id, photo=photo, caption=f"📸 <b>Veb-kamera surati</b> • <i>{now_str}</i>", parse_mode="HTML")
        logger.info("Kamera surati yuborildi.")
    except Exception as e:
        logger.error(f"Kamera xatosi: {e}")
        await bot.send_message(chat_id=target_chat_id, text=f"❌ Kamera xatoligi: {e}")
    finally:
        if os.path.exists(cam_file):
            try:
                os.remove(cam_file)
            except Exception:
                pass

@dp.message(Command("photo"))
@dp.message(F.text == "📸 Kamera")
async def cmd_photo(message: types.Message):
    msg = await message.answer("📸 Surat olinmoqda, kuting...")
    await handle_photo_capture(message.chat.id)
    try:
        await msg.delete()
    except Exception:
        pass

@dp.callback_query(F.data == "quick_photo")
async def callback_quick_photo(callback: CallbackQuery):
    await callback.answer("📸 Surat olinmoqda...")
    await handle_photo_capture(callback.message.chat.id)

@dp.message(Command("music", "spotify"))
@dp.message(F.text.in_({"🎵 Spotify", "Spotify", "🎵 Musiqa", "Musiqa", "/music", "/spotify"}))
async def cmd_music(message: types.Message):
    logger.info(f"Admin Spotify bo'limiga kirdi. (Xabar: '{message.text}')")
    asyncio.create_task(open_spotify())
    await asyncio.sleep(0.3)
    try:
        text, kb = await build_music_view()
        await message.answer(text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.error(f"cmd_music xatosi: {e}")
        await message.answer("🟢 <b>Spotify Boshqaruvi</b>\n\nSpotify noutbukda ochilmoqda...", parse_mode="HTML", reply_markup=music_inline_kb)

@dp.callback_query(F.data == "quick_music")
async def callback_quick_music(callback: CallbackQuery):
    asyncio.create_task(open_spotify())
    await asyncio.sleep(0.3)
    text, kb = await build_music_view()
    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer("🟢 Spotify ochilmoqda...")

@dp.callback_query(F.data == "mus_refresh")
async def callback_mus_refresh(callback: CallbackQuery):
    try:
        text, kb = await build_music_view()
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await callback.answer("✅ Yangilandi")
    except Exception:
        await callback.answer("Ma'lumotlar yangilandi")

@dp.callback_query(F.data.in_({"mus_play_pause", "mus_next", "mus_prev"}))
async def callback_mus_controls(callback: CallbackQuery):
    action_map = {"mus_play_pause": "play_pause", "mus_next": "next", "mus_prev": "prev"}
    action = action_map[callback.data]
    msg = await run_media_control(action)
    await callback.answer(msg)
    await asyncio.sleep(0.5)
    try:
        text, kb = await build_music_view()
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass

@dp.message(Command("lock"))
@dp.message(F.text == "🔒 Qulflash")
async def cmd_lock(message: types.Message):
    try:
        await lock_screen()
        await message.answer("🔒 <b>Ekran muvaffaqiyatli qulflandi!</b>", parse_mode="HTML")
        logger.info("Ekran masofadan qulflandi.")
    except Exception as e:
        logger.error(f"Qulflashda xato: {e}")
        await message.answer(f"❌ Qulflashda xatolik yuz berdi: {e}")

@dp.message(F.text == "🔔 Xabar yuborish")
async def notify_button(message: types.Message, state: FSMContext):
    await state.set_state(NotifyState.waiting_text)
    await message.answer("✍️ Noutbuk ekranida ko'rsatiladigan xabarni yozing:")

@dp.message(NotifyState.waiting_text)
async def notify_receive_text(message: types.Message, state: FSMContext):
    text = message.text
    await state.clear()
    try:
        await send_desktop_notification(text)
        await message.answer("🔔 <b>Xabar noutbuk ekranida ko'rsatildi!</b>", parse_mode="HTML", reply_markup=main_menu)
        logger.info(f"Ekranga xabar chiqarildi: {text[:40]}")
    except Exception as e:
        logger.error(f"Ekranga xabar chiqarishda xato: {e}")
        await message.answer(f"❌ Xatolik: {e}", reply_markup=main_menu)

@dp.message(F.text == "🔊 Ovoz")
async def volume_button(message: types.Message):
    vol = await get_current_volume_percent()
    muted = await is_muted()
    muted_str = " <i>(O'chirilgan 🔇)</i>" if muted else ""
    text = f"🔊 <b>Ovoz Boshqaruvi</b>\n\n🔈 <b>Joriy daraja:</b> <b>{vol}</b>{muted_str}"
    await message.answer(text, parse_mode="HTML", reply_markup=volume_kb)

@dp.callback_query(F.data.in_({"vol_up", "vol_down", "vol_mute"}))
async def volume_callback(callback: CallbackQuery):
    action_map = {"vol_up": "up", "vol_down": "down", "vol_mute": "mute"}
    arg = action_map[callback.data]
    try:
        result_text = await run_volume_action(arg)
        await callback.message.edit_text(result_text, parse_mode="HTML", reply_markup=volume_kb)
    except Exception as e:
        logger.error(f"Ovoz callback xatosi: {e}")
        await callback.message.edit_text(f"❌ Xatolik: {e}", reply_markup=volume_kb)
    await callback.answer()

@dp.message(F.text == "📋 Clipboard")
async def clipboard_button(message: types.Message):
    await message.answer(
        "📋 <b>Vaqtinchalik Xotira (Clipboard)</b>\n\nQuyidagi amallardan birini tanlang:",
        parse_mode="HTML",
        reply_markup=clipboard_kb,
    )

@dp.callback_query(F.data == "clip_get")
async def clipboard_get_callback(callback: CallbackQuery):
    await callback.answer()
    text = await get_clipboard_text()
    if text:
        if len(text) > 3800:
            text = text[:3800] + "\n... (qolgan qismi qisqartirildi)"
        await callback.message.answer(f"📥 <b>Nusxalangan matn:</b>\n\n<code>{text}</code>", parse_mode="HTML")
    else:
        await callback.message.answer("📋 Clipboard bo'sh yoki matn topilmadi.")

@dp.callback_query(F.data == "clip_set")
async def clipboard_set_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(ClipboardState.waiting_text)
    await callback.message.answer("✍️ Noutbuk xotirasiga (clipboard) yoziladigan matnni yuboring:")

@dp.message(ClipboardState.waiting_text)
async def clipboard_receive_text(message: types.Message, state: FSMContext):
    text = message.text
    await state.clear()
    try:
        await set_clipboard_text(text)
        await message.answer("✅ <b>Matn noutbuk xotirasiga (clipboard) nusxalandi!</b>", parse_mode="HTML", reply_markup=main_menu)
        logger.info("Clipboardga yangi matn yozildi.")
    except Exception as e:
        logger.error(f"Clipboard yozish xatosi: {e}")
        await message.answer(f"❌ Xatolik: {e}", reply_markup=main_menu)

@dp.message(Command("reboot"))
@dp.message(F.text == "🔄 Qayta yoqish")
async def cmd_reboot(message: types.Message):
    await message.answer("⚠️ Noutbukni <b>qayta ishga tushirishni</b> tasdiqlaysizmi?", parse_mode="HTML", reply_markup=confirm_kb("reboot"))

@dp.message(Command("shutdown"))
@dp.message(F.text == "🛑 O'chirish")
async def cmd_shutdown(message: types.Message):
    await message.answer("⚠️ Noutbukni <b>butunlay o'chirishni</b> tasdiqlaysizmi?", parse_mode="HTML", reply_markup=confirm_kb("shutdown"))

@dp.callback_query(F.data == "confirm_reboot")
async def confirm_reboot(callback: CallbackQuery):
    await callback.message.edit_text("🔄 <b>Noutbuk qayta ishga tushirilmoqda...</b>", parse_mode="HTML")
    await callback.answer("🔄 Qayta yoqilmoqda...")
    logger.info("Masofadan reboot buyrug'i berildi.")
    save_daily_stats()
    await asyncio.sleep(0.5)
    asyncio.create_task(execute_reboot())

@dp.callback_query(F.data == "confirm_shutdown")
async def confirm_shutdown(callback: CallbackQuery):
    await callback.message.edit_text("🛑 <b>Noutbuk o'chirilmoqda... Xayr!</b>", parse_mode="HTML")
    await callback.answer("🛑 O'chirilmoqda...")
    logger.info("Masofadan shutdown buyrug'i berildi.")
    save_daily_stats()
    await asyncio.sleep(0.5)
    asyncio.create_task(execute_shutdown())

@dp.callback_query(F.data == "cancel")
async def cancel_action(callback: CallbackQuery):
    await callback.message.edit_text("❌ Amal bekor qilindi.")
    await callback.answer()

@dp.message()
async def fallback_unknown_message(message: types.Message):
    logger.info(f"Admin noma'lum xabar yubordi: '{message.text}'")
    await message.answer("🤖 Quyidagi menyudan buyruqni tanlang:", reply_markup=main_menu)

# ==============================================================================
# 9. FONDA KUZATUV VA HISOBOTLARNI BOSHQARISH
# ==============================================================================

async def app_tracker_loop():
    global low_battery_notified
    logger.info("Application tracker fon jarayoni ishga tushdi.")
    while True:
        try:
            today_str = datetime.now(UZ_TZ).strftime("%Y-%m-%d")
            if today_str != daily_stats.get("date"):
                daily_stats["date"] = today_str
                daily_stats["app_minutes"] = {}
                daily_stats["battery_samples"] = []
                daily_stats["report_sent"] = False
                low_battery_notified = False

            battery = psutil.sensors_battery()
            if battery:
                pct = round(battery.percent)
                daily_stats["battery_samples"].append({
                    "time": datetime.now(UZ_TZ).strftime("%H:%M"),
                    "percent": pct,
                    "plugged": battery.power_plugged,
                })

                if pct <= LOW_BATTERY_THRESHOLD and not battery.power_plugged:
                    if not low_battery_notified:
                        try:
                            await bot.send_message(
                                chat_id=ADMIN_ID,
                                text=f"⚠️ <b>Batareya Quvvati Kam!</b>\n\n🔋 Joriy quvvat: <b>{pct}%</b>\nIltimos, zaryadlashga ulang.",
                                parse_mode="HTML",
                            )
                            low_battery_notified = True
                        except Exception as e:
                            logger.error(f"Batareya xabarida xatolik: {e}")
                elif battery.power_plugged:
                    low_battery_notified = False

            current_app = await get_active_window_name()
            if current_app and current_app not in SYSTEM_IGNORE_CLASSES:
                daily_stats["app_minutes"][current_app] = daily_stats["app_minutes"].get(current_app, 0) + 1

            save_daily_stats()
        except Exception as e:
            logger.error(f"Tracker xatoligi: {e}")

        await asyncio.sleep(TRACK_INTERVAL_SECONDS)

async def daily_report_scheduler():
    logger.info("Daily report scheduler ishga tushdi.")
    while True:
        try:
            now = datetime.now(UZ_TZ)
            is_report_time = (now.hour == DAILY_REPORT_HOUR and now.minute >= DAILY_REPORT_MINUTE)
            if is_report_time and not daily_stats.get("report_sent", False):
                report_text = build_daily_report_text()
                await bot.send_message(chat_id=ADMIN_ID, text=report_text, parse_mode="HTML")
                daily_stats["report_sent"] = True
                save_daily_stats()
                logger.info("Kunlik hisobot yuborildi.")
        except Exception as e:
            logger.error(f"Scheduler xatosi: {e}")

        await asyncio.sleep(30)

async def on_startup_notify():
    boot_time = datetime.now(UZ_TZ).strftime("%Y-%m-%d %H:%M:%S")
    battery = psutil.sensors_battery()
    bat_text = f"{round(battery.percent)}%" if battery else "Aniqlanmadi"
    wifi_name = await get_wifi_name()
    device_name = get_device_name()

    text = (
        "🟢 <b>Noutbuk Ishga Tushdi (Windows)</b>\n"
        f"💻 <code>{device_name}</code>\n\n"
        f"🔋 <b>Batareya:</b> {bat_text}\n"
        f"📶 <b>Wi-Fi:</b> <code>{wifi_name}</code>\n"
        f"🕒 <b>Vaqt:</b> {boot_time}\n\n"
        "<i>Bot boshqaruvga tayyor 👇</i>"
    )
    try:
        await bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode="HTML", reply_markup=main_menu)
        logger.info("Startup notification yuborildi.")
    except Exception as e:
        logger.error(f"Startup xatoligi: {e}")

async def main():
    device_name = get_device_name()
    logger.info(f"Remote Bot Windows ishga tushmoqda... Qurilma: {device_name}")
    logger.info(f"ADMIN_ID: {ADMIN_ID}, TIMEZONE: {TIMEZONE_STR}")

    load_daily_stats()
    await on_startup_notify()

    asyncio.create_task(app_tracker_loop())
    asyncio.create_task(daily_report_scheduler())

    try:
        await dp.start_polling(bot, drop_pending_updates=True)
    finally:
        save_daily_stats()
        await bot.session.close()
        logger.info("Bot faoliyati to'xtatildi.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot qo'lda to'xtatildi.")
