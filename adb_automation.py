"""ADB automation for Android device interaction.

Provides helpers to control an Android device over ADB: wake/unlock, tap by
relative coordinates, type text, and upload videos to TikTok.
"""

from __future__ import annotations

import re
import subprocess
import time

from logging_config import get_logger

logger = get_logger(__name__)

#: Device serial. Leave empty to use the single connected device.
DEVICE_ID = ""
#: TikTok application package name.
TIKTOK_PACKAGE = "com.zhiliaoapp.musically"
#: Telegram package name.
TELEGRAM_PACKAGE = "org.telegram.messenger"


def adb(command: str) -> str:
    """Run a native ADB command.

    Args:
        command: The ADB command (without the ``adb`` prefix).

    Returns:
        The decoded stdout of the command.
    """
    prefix = f"adb -s {DEVICE_ID} " if DEVICE_ID else "adb "
    proc = subprocess.Popen(
        prefix + command, stdout=subprocess.PIPE, shell=True
    )
    out, _ = proc.communicate()
    return out.decode("utf-8")


def get_screen_size() -> tuple[int, int]:
    """Return the device screen size as ``(width, height)``.

    Returns:
        A tuple of screen dimensions, falling back to 1080x2400.
    """
    size_str = adb("shell wm size")
    match = re.search(r"(\d+)x(\d+)", size_str)
    if match:
        return int(match.group(1)), int(match.group(2))
    return 1080, 2400


def touch_relative(x_prop: float, y_prop: float) -> None:
    """Simulate a tap using relative coordinates (0-100 scale).

    Args:
        x_prop: Horizontal position as a percentage (0-100).
        y_prop: Vertical position as a percentage (0-100).
    """
    w, h = get_screen_size()
    x = int(x_prop * w) / 100
    y = int(y_prop * h) / 100
    logger.info("Tap at (%.0f, %.0f) [%s, %s]", x, y, x_prop, y_prop)
    adb(f"shell input tap {x} {y}")


def wake_and_unlock() -> None:
    """Wake the screen and unlock the device."""
    power_state = adb("shell dumpsys power")
    is_asleep = any(
        marker in power_state
        for marker in [
            "mScreenOn=false",
            "mWakefulness=Asleep",
            "Display Power: state=OFF",
        ]
    )

    if is_asleep:
        logger.info("Screen off; sending power key.")
        adb("shell input keyevent 26")
        time.sleep(0.8)
    else:
        logger.info("Screen already on.")

    adb("shell input keyevent 82")  # KEYCODE_MENU
    time.sleep(0.3)

    w, h = get_screen_size()
    x_start = x_end = int(0.5 * w)
    y_start = int(0.8 * h)
    y_end = int(0.2 * h)
    adb(f"shell input swipe {x_start} {y_start} {x_end} {y_end} 700")
    time.sleep(0.5)

    adb("shell input keyevent 3")  # KEYCODE_HOME
    logger.info("Device unlocked.")


def type_text(text: str) -> None:
    """Type text via ADB, escaping spaces.

    Args:
        text: The text to type.
    """
    escaped = text.replace(" ", "%s")
    adb(f"shell input text {escaped}")


def open_telegram() -> None:
    """Open Telegram via the monkey launcher."""
    logger.info("Opening Telegram via Monkey...")
    adb(
        f"shell monkey -p {TELEGRAM_PACKAGE} "
        "-c android.intent.category.LAUNCHER 1"
    )


def pull_file_from_phone(phone_filename: str, local_destination: str = "./") -> None:
    """Pull a file from the phone's Telegram download folder.

    Args:
        phone_filename: Filename on the device.
        local_destination: Local destination directory.
    """
    logger.info("Listing Telegram download folder...")
    print(adb("shell ls -al /storage/emulated/0/Download/Telegram/"))
    phone_path = f"/storage/emulated/0/Download/Telegram/{phone_filename}"
    logger.info("Pulling %s from phone...", phone_filename)
    adb(f"pull {phone_path} {local_destination}")


def upload_tiktok(video_path: str, caption: str) -> bool:
    """Upload a video to TikTok via ADB automation.

    Args:
        video_path: Local path of the video to upload.
        caption: Caption text for the post.

    Returns:
        True on success.
    """
    logger.info("Starting TikTok...")
    adb(
        f"shell am start -n {TIKTOK_PACKAGE}/"
        "com.ss.android.ugc.aweme.splash.SplashActivity"
    )
    time.sleep(10)

    for x, y in [(95, 95), (50, 95), (5, 90), (5, 20), (80, 95), (80, 90)]:
        touch_relative(x, y)
        time.sleep(2)

    touch_relative(42, 25)
    type_text("test titolo")
    time.sleep(2)

    touch_relative(37, 36)
    type_text("test descrizione")
    time.sleep(2)

    logger.info("Upload flow completed.")
    return True
