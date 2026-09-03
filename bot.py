import asyncio
import base64
import ctypes
from ctypes import wintypes
import json
import logging
import os
import platform
import re
import socket
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

import psutil
from aiogram import BaseMiddleware, Bot, Dispatcher, F, types
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
    TelegramObject,
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
            # Izohlarni tozalash (agar satr oxirida bo'lsa)
            if " #" in val:
                val = val.split(" #")[0].strip().strip("'\"")
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
    print(f"XATOLIK: ADMIN_ID butun son bo'lishi kerak, berilgan: {ADMIN_ID_RAW}")
    sys.exit(1)

DEVICE_NAME = os.environ.get("DEVICE_NAME", "").strip()
TIMEZONE_STR = os.environ.get("TIMEZONE", "Asia/Tashkent")

try:
    import zoneinfo
    UZ_TZ = zoneinfo.ZoneInfo(TIMEZONE_STR)
except Exception:
    UZ_TZ = timezone(timedelta(hours=5))

TRACK_INTERVAL_SECONDS = max(10, int(os.environ.get("TRACK_INTERVAL_SECONDS", "60")))
DAILY_REPORT_HOUR = int(os.environ.get("DAILY_REPORT_HOUR", "23"))
DAILY_REPORT_MINUTE = int(os.environ.get("DAILY_REPORT_MINUTE", "55"))
LOW_BATTERY_THRESHOLD = int(os.environ.get("LOW_BATTERY_THRESHOLD", "20"))
STATS_FILE = os.path.join(BASE_DIR, "daily_stats.json")
HISTORY_DIR = os.path.join(BASE_DIR, "history")
os.makedirs(HISTORY_DIR, exist_ok=True)

# pythonw.exe (silent fon rejimi) da sys.stdout va sys.stderr None bo'ladi
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

# ==============================================================================
# 2. LOGGING SOZLAMALARI (Stdout va bot.log fayliga real vaqtda yozish)
# ==============================================================================

class FlushingFileHandler(logging.FileHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(message)s"
LOG_FILE = os.path.join(BASE_DIR, "bot.log")

file_handler = FlushingFileHandler(LOG_FILE, encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter(LOG_FORMAT))

handlers_list: List[logging.Handler] = [file_handler]
try:
    if sys.stdout and hasattr(sys.stdout, "isatty") and sys.stdout.isatty():
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(logging.INFO)
        stream_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        handlers_list.append(stream_handler)
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    handlers=handlers_list,
    force=True,
)
logger = logging.getLogger("remote_win_bot")
logger.setLevel(logging.INFO)

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

SYSTEM_IGNORE_APPS = {
    "", "unknown", "bosh ekran", "desktop", "explorer", "taskbar",
    "applicationframehost", "shellexperiencehost", "lockapp", "searchapp",
    "startmenuexperiencehost", "systemsettings"
}

def load_daily_stats() -> None:
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
                else:
                    # Kechagi statistikani arxivga saqlash
                    old_date = data.get("date", "previous")
                    archive_path = os.path.join(HISTORY_DIR, f"stats_{old_date}.json")
                    try:
                        with open(archive_path, "w", encoding="utf-8") as af:
                            json.dump(data, af, ensure_ascii=False, indent=2)
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"Statistika faylini o'qishda xatolik: {e}")

    daily_stats = {
        "date": today_str,
        "app_minutes": {},
        "battery_samples": [],
        "report_sent": False,
    }
    save_daily_stats()

def save_daily_stats() -> None:
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
        [KeyboardButton(text="🖥 Ekran (Skrinshot)"), KeyboardButton(text="🎵 Spotify")],
        [KeyboardButton(text="🔊 Ovoz"), KeyboardButton(text="🔒 Qulflash")],
        [KeyboardButton(text="📋 Clipboard"), KeyboardButton(text="🔔 Xabar yuborish")],
        [KeyboardButton(text="📅 Kunlik hisobot"), KeyboardButton(text="⚡️ Quvvat / O'chirish")],
    ],
    resize_keyboard=True,
)

status_inline_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Yangilash", callback_data="status_refresh"),
            InlineKeyboardButton(text="📸 Kamera", callback_data="quick_photo"),
            InlineKeyboardButton(text="🖥 Ekran", callback_data="quick_screenshot"),
        ],
        [
            InlineKeyboardButton(text="🎵 Spotify", callback_data="quick_music"),
            InlineKeyboardButton(text="🔊 Ovoz", callback_data="quick_volume"),
            InlineKeyboardButton(text="🔒 Qulflash", callback_data="quick_lock"),
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
            InlineKeyboardButton(text="🚀 Spotify'ni ochish", callback_data="mus_open"),
        ]
    ]
)

volume_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="🔉 -10%", callback_data="vol_down"),
            InlineKeyboardButton(text="🔇 Mute / Unmute", callback_data="vol_mute"),
            InlineKeyboardButton(text="🔊 +10%", callback_data="vol_up"),
        ],
        [
            InlineKeyboardButton(text="🔄 Yangilash", callback_data="vol_refresh"),
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

power_menu_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Qayta yoqish (Reboot)", callback_data="ask_reboot"),
            InlineKeyboardButton(text="🛑 Butunlay o'chirish (Shutdown)", callback_data="ask_shutdown"),
        ],
        [
            InlineKeyboardButton(text="🔒 Ekranni qulflash", callback_data="quick_lock"),
        ]
    ]
)

def confirm_kb(action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Ha, tasdiqlayman", callback_data=f"confirm_{action}"),
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_action"),
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
    if DEVICE_NAME:
        return DEVICE_NAME
    try:
        return socket.gethostname()
    except Exception:
        return f"Windows {platform.release()} PC"

def make_progress_bar(percent: float, length: int = 8) -> str:
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
        "opera": "Opera",
        "brave": "Brave Browser",
        "spotify": "Spotify",
        "pycharm64": "PyCharm",
        "pycharm": "PyCharm",
        "code": "VS Code",
        "devenv": "Visual Studio",
        "idea64": "IntelliJ IDEA",
        "clion64": "CLion",
        "webstorm64": "WebStorm",
        "windowsterminal": "Windows Terminal",
        "cmd": "Buyruqlar satri (CMD)",
        "powershell": "PowerShell",
        "explorer": "Fayl menejeri (Explorer)",
        "vlc": "VLC Media Player",
        "obsidian": "Obsidian",
        "notion": "Notion",
        "discord": "Discord",
        "word": "Microsoft Word",
        "excel": "Microsoft Excel",
        "powerpnt": "Microsoft PowerPoint",
    }
    for k, v in app_map.items():
        if k in raw_lower:
            return v
    return raw_name.replace(".exe", "").capitalize()

# --- Faol Oyna va Jarayon (Ctypes orqali xavfsiz) ---
def _sync_get_active_window_info() -> Tuple[str, str]:
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return "Bosh ekran", ""
        
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        
        title = ""
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value.strip()

        app_name = "Bosh ekran"
        if pid.value > 0:
            try:
                proc = psutil.Process(pid.value)
                app_name = clean_app_name(proc.name())
            except Exception:
                app_name = "Bosh ekran"

        return app_name, title
    except Exception:
        return "Bosh ekran", ""

async def get_active_window_name() -> str:
    app_name, _ = await asyncio.to_thread(_sync_get_active_window_info)
    return app_name

async def get_active_window_full() -> Tuple[str, str]:
    return await asyncio.to_thread(_sync_get_active_window_info)

# --- Tarmoq va Wi-Fi aniqlash ---
def _sync_get_network_info() -> Tuple[str, str]:
    network_name = "Ulanmagan"
    
    # 1. PowerShell Get-NetConnectionProfile (Windows 10/11 da admin huquqisiz ishlaydi)
    try:
        cmd = "Get-NetConnectionProfile | Select-Object Name, InterfaceAlias, IPv4Connectivity | ConvertTo-Json"
        res = subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", cmd],
            capture_output=True,
            text=True,
            timeout=3
        )
        if res.returncode == 0 and res.stdout.strip():
            try:
                data = json.loads(res.stdout)
                if isinstance(data, list) and len(data) > 0:
                    data = data[0]
                if isinstance(data, dict):
                    name = data.get("Name")
                    if name:
                        network_name = name
            except Exception:
                pass
    except Exception:
        pass

    # 2. Agar hali ham topilmasa, netsh fallback
    if network_name == "Ulanmagan":
        try:
            out = subprocess.check_output(
                ["netsh", "wlan", "show", "interfaces"],
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                timeout=2
            ).decode("utf-8", errors="ignore")
            match = re.search(r"^\s*SSID\s*:\s*(.+)$", out, re.MULTILINE)
            if match:
                ssid = match.group(1).strip()
                if ssid and ssid != "None" and "not running" not in ssid:
                    network_name = ssid
        except Exception:
            pass

    # 3. Mahalliy IP manzilni aniqlash
    local_ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    return network_name, local_ip

async def get_network_info() -> Tuple[str, str]:
    return await asyncio.to_thread(_sync_get_network_info)

# --- Ovoz boshqaruvi (PyCAW Modern + COM Thread Safety + Fallback) ---
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF

def _get_pycaw_volume_endpoint():
    import comtypes
    comtypes.CoInitialize()
    from pycaw.pycaw import AudioUtilities
    speakers = AudioUtilities.GetSpeakers()
    if not speakers:
        return None
    if hasattr(speakers, "EndpointVolume"):
        return speakers.EndpointVolume
    try:
        from pycaw.pycaw import IAudioEndpointVolume
        from comtypes import CLSCTX_ALL
        from ctypes import cast, POINTER
        interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(interface, POINTER(IAudioEndpointVolume))
    except Exception:
        return None

def _sync_get_volume_percent() -> str:
    try:
        endpoint = _get_pycaw_volume_endpoint()
        if endpoint:
            vol = endpoint.GetMasterVolumeLevelScalar()
            return f"{int(round(vol * 100))}%"
    except Exception as e:
        logger.debug(f"Volume percent error: {e}")
    return "Aniqlanmadi"

async def get_current_volume_percent() -> str:
    return await asyncio.to_thread(_sync_get_volume_percent)

def _sync_is_muted() -> bool:
    try:
        endpoint = _get_pycaw_volume_endpoint()
        if endpoint:
            return bool(endpoint.GetMute())
    except Exception as e:
        logger.debug(f"Mute check error: {e}")
    return False

async def is_muted() -> bool:
    return await asyncio.to_thread(_sync_is_muted)

def _sync_run_volume_action(arg: str) -> str:
    try:
        endpoint = _get_pycaw_volume_endpoint()
        if endpoint:
            if arg == "up":
                cur = endpoint.GetMasterVolumeLevelScalar()
                new_vol = min(1.0, cur + 0.1)
                endpoint.SetMasterVolumeLevelScalar(new_vol, None)
                if endpoint.GetMute():
                    endpoint.SetMute(0, None)
            elif arg == "down":
                cur = endpoint.GetMasterVolumeLevelScalar()
                new_vol = max(0.0, cur - 0.1)
                endpoint.SetMasterVolumeLevelScalar(new_vol, None)
            elif arg == "mute":
                cur_mute = endpoint.GetMute()
                endpoint.SetMute(0 if cur_mute else 1, None)
        else:
            # Fallback via keybd_event
            if arg == "up":
                ctypes.windll.user32.keybd_event(VK_VOLUME_UP, 0, 0, 0)
            elif arg == "down":
                ctypes.windll.user32.keybd_event(VK_VOLUME_DOWN, 0, 0, 0)
            elif arg == "mute":
                ctypes.windll.user32.keybd_event(VK_VOLUME_MUTE, 0, 0, 0)
    except Exception as e:
        logger.error(f"Volume action error: {e}")
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
    
    if not cap.isOpened():
        raise RuntimeError("Veb-kamerani ochib bo'lmadi (kamera ulanmagan yoki boshqa dasturda band).")

    try:
        # Yorug'lik va avtofokus uchun bir nechta kadr o'tkazib yuborish
        for _ in range(5):
            cap.read()
        ret, frame = cap.read()
        if ret and frame is not None:
            cv2.imwrite(output_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        else:
            raise RuntimeError("Kameradan kadr olib bo'lmadi.")
    finally:
        cap.release()

async def take_photo(output_path: str):
    await asyncio.to_thread(_sync_take_photo, output_path)

# --- Ekran Skrinshoti (Pillow / Win32 GDI) ---
def _sync_take_screenshot(output_path: str):
    # 1. Pillow ImageGrab
    try:
        from PIL import ImageGrab
        im = ImageGrab.grab(all_screens=True)
        if im:
            im.save(output_path, "JPEG", quality=85)
            return
    except Exception:
        pass

    # 2. Win32 GDI BitBlt
    try:
        import win32gui
        import win32ui
        import win32con
        import win32api
        from PIL import Image

        hwin = win32gui.GetDesktopWindow()
        width = win32api.GetSystemMetrics(win32con.SM_CXVIRTUALSCREEN)
        height = win32api.GetSystemMetrics(win32con.SM_CYVIRTUALSCREEN)
        left = win32api.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN)
        top = win32api.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN)

        hwindc = win32gui.GetWindowDC(hwin)
        srcdc = win32ui.CreateDCFromHandle(hwindc)
        memdc = srcdc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(srcdc, width, height)
        memdc.SelectObject(bmp)
        memdc.BitBlt((0, 0), (width, height), srcdc, (left, top), win32con.SRCCOPY)

        bmpinfo = bmp.GetInfo()
        bmpstr = bmp.GetBitmapBits(True)
        im = Image.frombuffer('RGB', (bmpinfo['bmWidth'], bmpinfo['bmHeight']), bmpstr, 'raw', 'BGRX', 0, 1)
        im.save(output_path, 'JPEG', quality=85)

        win32gui.DeleteObject(bmp.GetHandle())
        memdc.DeleteDC()
        srcdc.DeleteDC()
        win32gui.ReleaseDC(hwin, hwindc)
        return
    except Exception as e:
        raise RuntimeError(f"Skrinshot olib bo'lmadi: {e}")

async def take_screenshot(output_path: str):
    await asyncio.to_thread(_sync_take_screenshot, output_path)

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
    info = {"title": "", "artist": "", "status": "To'xtatilgan", "player": "Aniqlanmadi"}
    
    # 1. Spotify oynasini qidirish (ctypes orqali xavfsiz)
    try:
        user32 = ctypes.windll.user32
        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        spotify_titles = []

        def enum_proc(hwnd, lparam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value.strip()

                    cls_buff = ctypes.create_unicode_buffer(256)
                    user32.GetClassNameW(hwnd, cls_buff, 256)
                    cls_name = cls_buff.value.strip()

                    if "Spotify" in cls_name or cls_name == "Chrome_WidgetWin_0" and " - " in title:
                        spotify_titles.append(title)
            return True

        user32.EnumWindows(WNDENUMPROC(enum_proc), 0)

        for title in spotify_titles:
            if title and " - " in title and title not in ("Spotify", "Spotify Free", "Spotify Premium"):
                parts = title.split(" - ", 1)
                info["artist"] = parts[0].strip()
                info["title"] = parts[1].strip()
                info["status"] = "Ijro etilmoqda 🟢"
                info["player"] = "Spotify"
                return info
            elif title in ("Spotify", "Spotify Free", "Spotify Premium"):
                info["player"] = "Spotify"
                info["status"] = "Pauzada ⏸"
    except Exception as e:
        logger.debug(f"Spotify enum error: {e}")

    # 2. WinRT Universal Media Session (Windows 10/11)
    try:
        ps_script = """
[Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media, ContentType = WindowsRuntime] | Out-Null
$manager = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync().GetAwaiter().GetResult()
$session = $manager.GetCurrentSession()
if ($session) {
    $media = $session.TryGetMediaPropertiesAsync().GetAwaiter().GetResult()
    $status = $session.GetPlaybackInfo().PlaybackStatus
    Write-Output ($session.SourceAppUserModelId + "|||" + $media.Artist + "|||" + $media.Title + "|||" + $status)
}
"""
        res = subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=2
        )
        if res.returncode == 0 and "|||" in res.stdout:
            parts = res.stdout.strip().split("|||")
            if len(parts) >= 3:
                app_id = parts[0]
                artist = parts[1]
                title = parts[2]
                status_raw = parts[3] if len(parts) > 3 else "Playing"
                
                if title or artist:
                    info["title"] = title
                    info["artist"] = artist or "Noma'lum ijrochi"
                    info["status"] = "Ijro etilmoqda 🟢" if "Playing" in status_raw or "4" in status_raw else "Pauzada ⏸"
                    info["player"] = "Spotify" if "Spotify" in app_id else "Media Player"
                    return info
    except Exception:
        pass

    return info

async def get_music_info() -> Dict[str, str]:
    return await asyncio.to_thread(_sync_get_music_info)

async def build_music_view() -> Tuple[str, InlineKeyboardMarkup]:
    info = await get_music_info()
    title = info.get("title")
    artist = info.get("artist")
    status = info.get("status")
    player = info.get("player")
    
    if title:
        meta_text = (
            f"🎧 <b>Trek:</b> <b>{title}</b>\n"
            f"👤 <b>Ijrochi:</b> {artist}\n"
            f"📊 <b>Holat:</b> {status}\n"
            f"💻 <b>Pleyer:</b> {player}"
        )
    else:
        meta_text = (
            "🎧 <b>Musiqa Boshqaruvi</b>\n\n"
            "Hozirda hech qanday musiqa ijro etilmayapti.\n"
            "Musiqani ochish yoki boshqarish uchun quyidagi tugmalardan foydalaning 👇"
        )

    text = f"🟢 <b>Spotify & Musiqa Markazi</b>\n\n{meta_text}"
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

# --- Bildirishnoma (Native Windows 10/11 Toast) ---
def _sync_send_notification(text: str, title: str = "Bildirishnoma"):
    # Xavfsiz Base64 Encoded PowerShell Toast
    safe_title = title.replace('"', '`"').replace("'", "`'")
    safe_text = text.replace('"', '`"').replace("'", "`'")
    
    ps_code = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

$template = @"
<toast>
    <visual>
        <binding template="ToastGeneric">
            <text>{safe_title}</text>
            <text>{safe_text}</text>
        </binding>
    </visual>
</toast>
"@

$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($template)
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Remote Control").Show($toast)
"""
    try:
        encoded_ps = base64.b64encode(ps_code.encode("utf-16le")).decode("utf-8")
        subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-EncodedCommand", encoded_ps],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
    except Exception as e:
        logger.error(f"Toast notification xatosi: {e}")

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
    
    # Disk holati
    try:
        drive = os.path.splitdrive(os.path.abspath(__file__))[0] + "\\"
        disk = psutil.disk_usage(drive)
        disk_percent = disk.percent
        free_gb = disk.free / (1024 ** 3)
    except Exception:
        disk_percent = 0
        free_gb = 0

    # Batareya holati
    battery = psutil.sensors_battery()
    if battery:
        bat_state = "Zaryadlanmoqda ⚡️" if battery.power_plugged else "Batareyada 🔋"
        bat_text = f"<b>{round(battery.percent)}%</b> <i>({bat_state})</i>"
    else:
        bat_text = "Mavjud emas"

    # Tarmoq, Ovoz, Faol dastur
    (network_name, local_ip), volume, muted, (current_app, win_title) = await asyncio.gather(
        get_network_info(),
        get_current_volume_percent(),
        is_muted(),
        get_active_window_full(),
    )

    volume_text = f"<b>{volume}</b>" + (" <i>(O'chirilgan 🔇)</i>" if muted else "")
    device_name = get_device_name()
    now_str = datetime.now(UZ_TZ).strftime("%H:%M:%S")

    cpu_bar = make_progress_bar(cpu)
    ram_bar = make_progress_bar(ram)

    app_display = f"<b>{current_app}</b>"
    if win_title and win_title != current_app and len(win_title) < 50:
        app_display += f" — <i>{win_title}</i>"

    text = (
        f"🖥 <b>Tizim Holati</b> • <code>{device_name}</code>\n\n"
        f"⚡️ <b>CPU:</b> <code>{cpu_bar}</code> {cpu}%\n"
        f"🧠 <b>RAM:</b> <code>{ram_bar}</code> {ram}%\n"
        f"🔋 <b>Batareya:</b> {bat_text}\n"
        f"💽 <b>Disk:</b> {disk_percent}% band <i>({free_gb:.1f} GB bo'sh)</i>\n"
        f"📶 <b>Tarmoq:</b> <code>{network_name}</code> <i>({local_ip})</i>\n"
        f"🔊 <b>Ovoz:</b> {volume_text}\n"
        f"📱 <b>Faol oyna:</b> {app_display}\n\n"
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
        if cleaned_k and cleaned_k.lower() not in SYSTEM_IGNORE_APPS:
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
# 7. XAVFSIZLIK VA MIDDLEWARE (ADMIN AUTH)
# ==============================================================================

class AdminAuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Any],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if not user:
            return

        if user.id != ADMIN_ID:
            logger.warning(f"Ruxsatsiz urinish! ID: {user.id}, Username: @{user.username}, Ism: {user.full_name}")
            if isinstance(event, types.Message):
                await event.reply("⛔️ Kechirasiz, siz ushbu noutbuk boshqaruvchisi emassiz!")
            elif isinstance(event, types.CallbackQuery):
                await event.answer("⛔️ Ruxsat berilmagan!", show_alert=True)
            return

        return await handler(event, data)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
dp.message.outer_middleware(AdminAuthMiddleware())
dp.callback_query.outer_middleware(AdminAuthMiddleware())

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
        "Noutbukingizni nazorat qilish va masofadan boshqarish uchun quyidagi menyudan foydalaning 👇",
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

# --- Kamera fotosi ---
async def handle_photo_capture(target_chat_id: int):
    now_str = datetime.now(UZ_TZ).strftime("%H:%M:%S")
    cam_file = os.path.join(tempfile.gettempdir(), f"cam_shot_{int(datetime.now().timestamp())}.jpg")
    try:
        await take_photo(cam_file)
        photo = FSInputFile(cam_file)
        await bot.send_photo(
            chat_id=target_chat_id,
            photo=photo,
            caption=f"📸 <b>Veb-kamera surati</b> • <i>{now_str}</i>",
            parse_mode="HTML"
        )
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

# --- Ekran Skrinshoti ---
async def handle_screenshot_capture(target_chat_id: int):
    now_str = datetime.now(UZ_TZ).strftime("%H:%M:%S")
    scr_file = os.path.join(tempfile.gettempdir(), f"scr_shot_{int(datetime.now().timestamp())}.jpg")
    try:
        await take_screenshot(scr_file)
        photo = FSInputFile(scr_file)
        await bot.send_photo(
            chat_id=target_chat_id,
            photo=photo,
            caption=f"🖥 <b>Ekran Skrinshoti</b> • <i>{now_str}</i>",
            parse_mode="HTML"
        )
        logger.info("Ekran skrinshoti yuborildi.")
    except Exception as e:
        logger.error(f"Skrinshot xatosi: {e}")
        await bot.send_message(chat_id=target_chat_id, text=f"❌ Skrinshot xatoligi: {e}")
    finally:
        if os.path.exists(scr_file):
            try:
                os.remove(scr_file)
            except Exception:
                pass

@dp.message(Command("screenshot", "screen"))
@dp.message(F.text.in_({"🖥 Ekran (Skrinshot)", "🖥 Ekran", "Skrinshot", "/screenshot", "/screen"}))
async def cmd_screenshot(message: types.Message):
    msg = await message.answer("🖥 Ekran surati olinmoqda, kuting...")
    await handle_screenshot_capture(message.chat.id)
    try:
        await msg.delete()
    except Exception:
        pass

@dp.callback_query(F.data == "quick_screenshot")
async def callback_quick_screenshot(callback: CallbackQuery):
    await callback.answer("🖥 Skrinshot olinmoqda...")
    await handle_screenshot_capture(callback.message.chat.id)

# --- Spotify & Musiqa ---
@dp.message(Command("music", "spotify"))
@dp.message(F.text.in_({"🎵 Spotify", "Spotify", "🎵 Musiqa", "Musiqa", "/music", "/spotify"}))
async def cmd_music(message: types.Message):
    logger.info("Spotify bo'limi ochildi.")
    try:
        text, kb = await build_music_view()
        await message.answer(text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.error(f"cmd_music xatosi: {e}")
        await message.answer("🟢 <b>Spotify Boshqaruvi</b>", parse_mode="HTML", reply_markup=music_inline_kb)

@dp.callback_query(F.data == "quick_music")
async def callback_quick_music(callback: CallbackQuery):
    text, kb = await build_music_view()
    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data == "mus_open")
async def callback_mus_open(callback: CallbackQuery):
    await open_spotify()
    await callback.answer("🚀 Spotify ochilmoqda...")
    await asyncio.sleep(1.0)
    try:
        text, kb = await build_music_view()
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass

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

# --- Ovoz boshqaruvi ---
@dp.message(F.text == "🔊 Ovoz")
async def volume_button(message: types.Message):
    vol = await get_current_volume_percent()
    muted = await is_muted()
    muted_str = " <i>(O'chirilgan 🔇)</i>" if muted else ""
    text = f"🔊 <b>Ovoz Boshqaruvi</b>\n\n🔈 <b>Joriy daraja:</b> <b>{vol}</b>{muted_str}"
    await message.answer(text, parse_mode="HTML", reply_markup=volume_kb)

@dp.callback_query(F.data == "quick_volume")
async def callback_quick_volume(callback: CallbackQuery):
    vol = await get_current_volume_percent()
    muted = await is_muted()
    muted_str = " <i>(O'chirilgan 🔇)</i>" if muted else ""
    text = f"🔊 <b>Ovoz Boshqaruvi</b>\n\n🔈 <b>Joriy daraja:</b> <b>{vol}</b>{muted_str}"
    await callback.message.answer(text, parse_mode="HTML", reply_markup=volume_kb)
    await callback.answer()

@dp.callback_query(F.data == "vol_refresh")
async def callback_vol_refresh(callback: CallbackQuery):
    vol = await get_current_volume_percent()
    muted = await is_muted()
    muted_str = " <i>(O'chirilgan 🔇)</i>" if muted else ""
    text = f"🔊 <b>Ovoz Boshqaruvi</b>\n\n🔈 <b>Joriy daraja:</b> <b>{vol}</b>{muted_str}"
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=volume_kb)
        await callback.answer("✅ Yangilandi")
    except Exception:
        await callback.answer()

@dp.callback_query(F.data.in_({"vol_up", "vol_down", "vol_mute"}))
async def volume_callback(callback: CallbackQuery):
    action_map = {"vol_up": "up", "vol_down": "down", "vol_mute": "mute"}
    arg = action_map[callback.data]
    try:
        result_text = await run_volume_action(arg)
        await callback.message.edit_text(result_text, parse_mode="HTML", reply_markup=volume_kb)
    except Exception as e:
        logger.error(f"Ovoz callback xatosi: {e}")
    await callback.answer()

# --- Ekranni qulflash ---
@dp.message(Command("lock"))
@dp.message(F.text == "🔒 Qulflash")
async def cmd_lock(message: types.Message):
    try:
        await message.answer("🔒 <b>Ekran muvaffaqiyatli qulflandi!</b>", parse_mode="HTML")
        logger.info("Ekran masofadan qulflandi.")
    except Exception as e:
        logger.warning(f"Xabar yuborishda ogohlantirish: {e}")
    await asyncio.sleep(0.3)
    try:
        await lock_screen()
    except Exception as e:
        logger.error(f"Qulflashda xato: {e}")

@dp.callback_query(F.data == "quick_lock")
async def callback_quick_lock(callback: CallbackQuery):
    try:
        await callback.answer("🔒 Ekran qulflandi!", show_alert=True)
    except Exception as e:
        logger.warning(f"Callback javobida ogohlantirish: {e}")
    await asyncio.sleep(0.3)
    try:
        await lock_screen()
    except Exception as e:
        logger.error(f"Qulflashda xato: {e}")

# --- Clipboard ---
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

# --- Bildirishnoma (Notification) ---
@dp.message(F.text == "🔔 Xabar yuborish")
async def notify_button(message: types.Message, state: FSMContext):
    await state.set_state(NotifyState.waiting_text)
    await message.answer("✍️ Noutbuk ekranida ko'rsatiladigan xabarni yozing:")

@dp.message(NotifyState.waiting_text)
async def notify_receive_text(message: types.Message, state: FSMContext):
    text = message.text
    await state.clear()
    try:
        await send_desktop_notification(text, title="Telegramdan Bildirishnoma")
        await message.answer("🔔 <b>Xabar noutbuk ekraniga yuborildi!</b>", parse_mode="HTML", reply_markup=main_menu)
        logger.info(f"Ekranga bildirishnoma chiqarildi: {text[:40]}")
    except Exception as e:
        logger.error(f"Ekranga xabar chiqarishda xato: {e}")
        await message.answer(f"❌ Xatolik: {e}", reply_markup=main_menu)

# --- Quvvat va O'chirish Menyusi ---
@dp.message(Command("power"))
@dp.message(F.text.in_({"⚡️ Quvvat / O'chirish", "🔄 Qayta yoqish", "🛑 O'chirish"}))
async def cmd_power(message: types.Message):
    await message.answer("⚡️ <b>Quvvat va Tizim Boshqaruvi</b>\n\nKerakli amalni tanlang:", parse_mode="HTML", reply_markup=power_menu_kb)

@dp.callback_query(F.data == "ask_reboot")
async def ask_reboot(callback: CallbackQuery):
    await callback.message.edit_text("⚠️ Noutbukni <b>qayta ishga tushirishni (Reboot)</b> tasdiqlaysizmi?", parse_mode="HTML", reply_markup=confirm_kb("reboot"))
    await callback.answer()

@dp.callback_query(F.data == "ask_shutdown")
async def ask_shutdown(callback: CallbackQuery):
    await callback.message.edit_text("⚠️ Noutbukni <b>butunlay o'chirishni (Shutdown)</b> tasdiqlaysizmi?", parse_mode="HTML", reply_markup=confirm_kb("shutdown"))
    await callback.answer()

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

@dp.callback_query(F.data == "cancel_action")
async def cancel_action(callback: CallbackQuery):
    await callback.message.edit_text("❌ Amal bekor qilindi.")
    await callback.answer()

@dp.message()
async def fallback_unknown_message(message: types.Message):
    logger.info(f"Admin xabar yubordi: '{message.text}'")
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
                # Kun almashganda kechagini arxivlash
                old_date = daily_stats.get("date", "previous")
                archive_path = os.path.join(HISTORY_DIR, f"stats_{old_date}.json")
                try:
                    with open(archive_path, "w", encoding="utf-8") as af:
                        json.dump(daily_stats, af, ensure_ascii=False, indent=2)
                except Exception:
                    pass

                daily_stats["date"] = today_str
                daily_stats["app_minutes"] = {}
                daily_stats["battery_samples"] = []
                daily_stats["report_sent"] = False
                low_battery_notified = False

            # Batareya monitoringi
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

            # Faol dastur kuzatuvi
            current_app = await get_active_window_name()
            if current_app and current_app.lower() not in SYSTEM_IGNORE_APPS:
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

async def wait_for_internet_connection(max_attempts: int = 60, delay: float = 4.0) -> bool:
    logger.info("Internet aloqasi tekshirilmoqda...")
    for attempt in range(1, max_attempts + 1):
        try:
            await bot.get_me()
            logger.info("Telegram API bilan aloqa o'rnatildi.")
            return True
        except Exception as e:
            if attempt % 5 == 1 or attempt == max_attempts:
                logger.warning(f"Internetga ulanish kutilmoqda ({attempt}/{max_attempts}): {e}")
            await asyncio.sleep(delay)
    return False

async def on_startup_notify():
    boot_time = datetime.now(UZ_TZ).strftime("%Y-%m-%d %H:%M:%S")
    battery = psutil.sensors_battery()
    bat_text = f"{round(battery.percent)}%" if battery else "Aniqlanmadi"
    network_name, local_ip = await get_network_info()
    device_name = get_device_name()

    text = (
        "🟢 <b>Noutbuk Ishga Tushdi (Windows)</b>\n"
        f"💻 <code>{device_name}</code>\n\n"
        f"🔋 <b>Batareya:</b> {bat_text}\n"
        f"📶 <b>Tarmoq:</b> <code>{network_name}</code> <i>({local_ip})</i>\n"
        f"🕒 <b>Vaqt:</b> {boot_time}\n\n"
        "<i>Bot boshqaruvga to'liq tayyor 👇</i>"
    )
    try:
        await bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode="HTML", reply_markup=main_menu)
        logger.info("Startup bildirishnomasi Telegramga muvaffaqiyatli yuborildi.")
    except Exception as e:
        logger.error(f"Startup xatoligi: {e}")

async def main():
    device_name = get_device_name()
    logger.info(f"Remote Bot Windows ishga tushmoqda... Qurilma: {device_name}")
    logger.info(f"ADMIN_ID: {ADMIN_ID}, TIMEZONE: {TIMEZONE_STR}")

    load_daily_stats()

    asyncio.create_task(app_tracker_loop())
    asyncio.create_task(daily_report_scheduler())

    # Internet ulanishini kutish va Startup xabarini jo'natish
    startup_sent = False
    while not startup_sent:
        is_connected = await wait_for_internet_connection(max_attempts=30, delay=4.0)
        if is_connected:
            await on_startup_notify()
            startup_sent = True
        else:
            logger.warning("Internet hali ulanmadi, 10 soniyadan keyin qayta tekshiriladi...")
            await asyncio.sleep(10)

    # Polling tsikli: aloqa uzilsa ham bot yopilib ketmasdan avtomatik qayta ulanadi
    try:
        while True:
            try:
                logger.info("Telegram bot polling boshlandi...")
                await dp.start_polling(bot, drop_pending_updates=True)
                break
            except Exception as e:
                logger.error(f"Polling xatoligi: {e}. 10 soniyadan so'ng qayta ulanishga uriniladi...")
                await asyncio.sleep(10)
    finally:
        save_daily_stats()
        await bot.session.close()
        logger.info("Bot faoliyati to'xtatildi.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot qo'lda to'xtatildi.")
