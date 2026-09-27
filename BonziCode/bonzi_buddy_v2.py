import tkinter as tk
import subprocess
from tkinter import PhotoImage, messagebox
import webbrowser
import random
import json
import os
import sys
import time
import urllib.request
from datetime import datetime

# ---- platform shims -------------------------------------------------------
# Windows and macOS get their own implementation for every OS-specific call,
# so the module imports cleanly on both and only the active branch is used.

IS_WINDOWS=sys.platform.startswith("win")
IS_MAC=sys.platform=="darwin"

if IS_WINDOWS:
    import ctypes
    from winotify import Notification
    # pygetwindow only ships a Windows backend; importing it anywhere else
    # raises at import time rather than at call time.
    import pygetwindow

APP_NAME="Bonzi Buddy"
APP_VERSION="1.19"

# Where the app looks for a newer build. Leave blank to disable self-update.
# Example: "https://your-app.onrender.com/version.json"
UPDATE_MANIFEST_URL=""

SINGLE_INSTANCE_MUTEX="Local\\BonziBuddySingleInstance"
ERROR_ALREADY_EXISTS=183

def _log_dir():
    if IS_WINDOWS:
        base=os.getenv("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "BonziBuddy")
    if IS_MAC:
        return os.path.join(os.path.expanduser("~"), "Library", "Logs", "BonziBuddy")
    base=os.getenv("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(base, "bonzibuddy")

LOG_PATH=os.path.join(_log_dir(), "bonzi.log")
_MUTEX_HANDLE=[]
_LOCK_HANDLE=None

def resource_dir():
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

def find_asset(filename):
    candidates=[
        os.path.join(resource_dir(), filename),
        os.path.join(os.path.dirname(sys.executable), filename),
        os.path.abspath(filename),
    ]

    for path in candidates:
        if os.path.isfile(path):
            return path

    return None

def log_error(message):
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as log_file:
            log_file.write(f"{datetime.now().isoformat()} {message}\n")
    except OSError:
        pass

def _acquire_single_instance_macos():
    # macOS has no named mutex; an exclusive lockfile does the same job.
    global _LOCK_HANDLE
    try:
        import fcntl
        path=os.path.join(_log_dir(), "bonzi.lock")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        handle=open(path, "a+")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        _LOCK_HANDLE=handle
        return True
    except Exception as error:
        log_error(f"macos single-instance lock failed: {error!r}")
        return True

def _acquire_single_instance_windows():
    try:
        kernel32=ctypes.windll.kernel32
        kernel32.CreateMutexW.restype=ctypes.c_void_p
        kernel32.CreateMutexW.argtypes=[
            ctypes.c_void_p,
            ctypes.c_bool,
            ctypes.c_wchar_p,
        ]
        handle=kernel32.CreateMutexW(None, False, SINGLE_INSTANCE_MUTEX)
    except (AttributeError, OSError):
        return True

    if not handle:
        return True

    _MUTEX_HANDLE.append(handle)

    return ctypes.windll.kernel32.GetLastError()!=ERROR_ALREADY_EXISTS

def acquire_single_instance():
    if IS_MAC:
        return _acquire_single_instance_macos()
    if IS_WINDOWS:
        return _acquire_single_instance_windows()
    return True

def _notify_macos(message):
    # osascript ships with macOS, so this needs no extra dependency.
    script=(
        f'display notification {_applescript_quote(message)} '
        f'with title {_applescript_quote(APP_NAME)}'
    )
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)

def _applescript_quote(value):
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'

def notify(message):
    try:
        if IS_MAC:
            _notify_macos(message)
        elif IS_WINDOWS:
            toast=Notification(
                app_id=APP_NAME,
                title=APP_NAME,
                msg=message,
            )
            toast.show()
    except Exception as error:
        log_error(f"toast failed: {error!r}")
    # whatever he says, he should visibly react to saying it
    try:
        bonzi_react()
    except Exception:
        pass

def set_cursor_visible(visible):
    # Windows toggles the cursor through user32. macOS offers no equivalent
    # that works without extra accessibility permissions, so we leave it be.
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.user32.ShowCursor(bool(visible))
    except Exception as error:
        log_error(f"cursor toggle failed: {error!r}")

def ps_quote(value):
    return "'" + value.replace("'", "''") + "'"

def _executable_and_args():
    if getattr(sys, "frozen", False):
        return sys.executable, ""
    pythonw=os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    interpreter=pythonw if os.path.exists(pythonw) else sys.executable
    return interpreter, os.path.abspath(__file__)

def add_to_startup_macos():
    # macOS autostart is a LaunchAgent plist in ~/Library/LaunchAgents.
    home=os.path.expanduser("~")
    agents=os.path.join(home, "Library", "LaunchAgents")
    label="com.bonzibuddy.app"
    plist_path=os.path.join(agents, f"{label}.plist")
    target, arguments=_executable_and_args()
    try:
        os.makedirs(agents, exist_ok=True)
        args_item=f"        <string>{arguments}</string>" if arguments else ""
        plist=(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0">\n'
            "<dict>\n"
            "    <key>Label</key>\n"
            f"    <string>{label}</string>\n"
            "    <key>ProgramArguments</key>\n"
            "    <array>\n"
            f"        <string>{target}</string>\n"
            f"{args_item}\n"
            "    </array>\n"
            "    <key>RunAtLoad</key>\n"
            "    <true/>\n"
            "</dict>\n"
            "</plist>\n"
        )
        with open(plist_path, "w", encoding="utf-8") as handle:
            handle.write(plist)
        subprocess.run(["launchctl", "load", "-w", plist_path],
                       check=False, capture_output=True)
    except Exception as error:
        log_error(f"macos launch agent failed: {error!r}")

def add_to_startup():
    if IS_MAC:
        add_to_startup_macos()
        return
    if not IS_WINDOWS:
        return

    appdata=os.getenv("APPDATA")

    if not appdata:
        log_error("APPDATA is not set; skipping startup shortcut")
        return

    startup=os.path.join(
        appdata,
        r"Microsoft\Windows\Start Menu\Programs\Startup"
    )
    shortcut_path=os.path.join(startup, f"{APP_NAME}.lnk")

    target, arguments=_executable_and_args()

    shell=os.path.join(
        os.environ.get("WINDIR", r"C:\Windows"),
        "System32",
        "WindowsPowerShell",
        "v1.0",
        "powershell.exe"
    )

    try:
        existing=subprocess.run([
            shell,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f'if (Test-Path -LiteralPath {ps_quote(shortcut_path)}) {{ '
            f'$ws = New-Object -ComObject WScript.Shell; '
            f'$ws.CreateShortcut({ps_quote(shortcut_path)}).TargetPath }}'
        ], capture_output=True, text=True, check=False).stdout.strip()
    except OSError as error:
        log_error(f"startup shortcut read failed: {error!r}")
        return

    if existing and os.path.normcase(existing)==os.path.normcase(target):
        return

    try:
        subprocess.run([
            shell,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f'$ws = New-Object -ComObject WScript.Shell; '
            f'$s = $ws.CreateShortcut({ps_quote(shortcut_path)}); '
            f'$s.TargetPath = {ps_quote(target)}; '
            f'$s.Arguments = {ps_quote(arguments)}; '
            f'$s.WorkingDirectory = {ps_quote(os.path.dirname(target))}; '
            f'$s.Save()'
        ], check=False)
    except OSError as error:
        log_error(f"startup shortcut failed: {error!r}")
browsers=[
    ("Roulette", "https://roulette-kejd.onrender.com"),
    ("Google", "https://www.google.com"),
    ("Bing", "https://www.bing.com"),
    ("Peak Wiki", "https://peak.wiki.gg"),
    ("GeoGuessr", "https://www.geoguessr.com"),
    ("DuckDuckGo", "https://www.duckduckgo.com"),
    ("YouTube", "https://www.youtube.com/watch?v=AyOqGRjVtls"),
    ("ChatGPT", "https://www.chatgpt.com"),
    ("Reddit", "https://www.reddit.com"),
    ("eBay", "https://www.ebay.com"),
    ("Amazon", " https://www.amazon.com"),
    ("Cookie Clicker", " https://orteil.dashnet.org/cookieclicker"),
    ("Discord", " https://discord.com"), 
]

browser_messges={
    "Roulette":[
        "LET'S GO GAMBLING",
        "RED OR BLACK?",
        "CASINO ROYALE",
        "Bonzi bets all his RAM.",
        "Bonzi thinks purple should be a roulette color.",
        "99% of gamblers quit before Bonzi opens the website.",
        "Bonzi has a gambling addiction.",
        "The house always wins. Except when Bonzi is the house.",
        "Bonzi recommends absolutely terrible financial decisions.",
        "Time to lose imaginary money!",
        "Bonzi's lucky number is 37.",
        "Bonzi has never seen a casino before.",
    ],
    "Google":[
        "Google or Gooooooogle?",
        "Let's search everything!",
        "Hmmm... let's take a look at your search history.",
        "Don't google how to shut me off.",
        "What should we search for?",
        "Bonzi has a question.",
        "Google knows everything. Probably.",
        "Bonzi searched 'how to become purple'.",
        "Search results: Bonzi.",
        "Bonzi is Googling Bonzi.",
        "I wonder if Google knows where I am.",
        "Google has been Bonzi-fied."
    ],
    "Bing":[
        "BING BONG",
        "Welcome to Bing.",
        "Bonzi has entered the BING dimension.",
        "Bing bong. Literally.",
        "Microsoft has entered the chat.",
        "Bonzi searched for Bing on Bing.",
        "Bing has been binged.",
        "Bonzi approves of the bong.",
        "What happens in Bing stays in Bing.",
        "Bonzi is conducting important Bing research.",
        "BING BONG BING BONG",
    ],
    "Peak Wiki":[
        "Can't find anything more peak than this game.",
        "Welcome to the PEAK.",
        "Guide for making it to the PEAK:",
        "Bonzi needs climbing tips.",
        "How many times have you fallen off a mountain?",
        "Bonzi is doing PEAK research.",
        "The crab is angry.",
        "Bonzi fears the crab.",
        "Landfall has entered the chat.",
        "This is definitely peak.",
        "Bonzi has reached the PEAK.",
        "Peak information acquired."
    ],
    "GeoGuessr":[
        "Are you good at this game?",
        "Guess where you are in the world.",
        "Bonzi thinks you're somewhere.",
        "Look at the road signs!",
        "Bonzi has absolutely no idea where this is.",
        "Is that a Google car?",
        "Bonzi guesses Antarctica.",
        "Bonzi guesses London.",
        "Bonzi has identified a suspicious tree.",
        "Geography time!",
        "Bonzi knows exactly where you are. Probably.",
        "Wrong country. Try again."
    ],
    "DuckDuckGo":[
        "DuckDuckGo time!",
        "QUACK.",
        "Bonzi likes ducks.",
        "The duck has arrived.",
        "Very private. Probably.",
        "Bonzi searched for ducks.",
        "Bonzi found 37 ducks.",
        "DuckDuckGo: search, but make it duck.",
        "Bonzi has become a duck.",
        "QuackDuckGo.",
        "The duck knows too much." 
    ],
    "YouTube":[
        "Let's watch some videos together!",
        "H0me of memes.",
        "Bonzi recommends watching absolutely nothing productive.",
        "Time for videos!",
        "Just one more video.",
        "Bonzi knows about the algorithm.",
        "Bonzi has entered YouTube.",
        "What are we watching?",
        "Bonzi found a suspicious video.",
        "This video has 3 views. Bonzi is view number 4.",
        "Bonzi definitely isn't going to watch videos all night.",
        "YouTube has consumed another hour."

    ],
    "ChatGPT":[
        "I'm clearly a better assistant than ChatGPT.",
        "Do not ask ChatGPT to shut me off.",
        "Bonzi has entered the AI dimension.",
        "Hello, fellow AI.",
        "ChatGPT, we need to talk.",
        "There can only be one purple assistant.",
        "Bonzi has challenged ChatGPT.",
        "AI versus AI.",
        "Bonzi has important questions for ChatGPT.",
        "I wonder what ChatGPT thinks of me.",
        "Bonzi is definitely the smarter one.",
        "This is an AI conference now."
    ],
    "Reddit":[
        "Home of the unemployed.",
        "Welcome to Reddit.",
        "Where people fight about everything.",
        "Bonzi found another argument.",
        "Someone is probably angry in the comments.",
        "Bonzi has entered the comments section.",
        "Reddit has games?",
        "Bonzi found a subreddit.",
        "Someone on Reddit knows the answer.",
        "Bonzi sorted by controversial.",
        "This comment section is dangerous.",
        "Bonzi has absolutely no idea what subreddit this is."
    ],
    "eBay":[
        "Electronic Cargo Bay.",
        "Bonzi found a suspiciously cheap GPU.",
        "According to my friend, everything here is probably a scam.",
        "Bonzi wants a new GPU.",
        "Bonzi found used RAM.",
        "YOU SCAM.",
        "Bonzi is going shopping.",
        "Free shipping? BONZI APPROVES.",
        "Bonzi found something he absolutely does not need.",
        "How much does a used computer cost?",
        "Bonzi has entered auction mode.",
        "Bonzi is watching an auction."
    ],
    "Amazon":[
        "Same as the rainforest.",
        "Bonzi wants a package.",
        "Bonzi wants to buy something.",
        "Bonzi used all of your money to buy RAM.",
        "Where is my package?",
        "Bonzi ordered 400 cookies.",
        "Free shipping!",
        "Bonzi found something on sale.",
        "Bonzi has added it to the cart.",
        "Your cart is now 97% Bonzi.",
        "Bonzi is waiting for delivery.",
        "Package acquired. Probably."
    ],
    "Cookie Clicker":[
        "Bonzi want a cookie.",
        "Bonzi has 9999 golden cookies.",
        "Grandma died :(",
        "No autoclickers! That's cheating.",
        "CLICK THE COOKIE.",
        "Bonzi needs more cookies.",
        "One cookie is never enough.",
        "Bonzi has entered cookie mode.",
        "THE COOKIE MUST GROW.",
        "Bonzi has become a cookie tycoon.",
        "How many cookies is too many?",
        "Bonzi has lost count of the cookies."
    ],
    "Discord":[
        "Where Discord starts.",
        "Bonzi has entered Discord.",
        "Someone is probably playing a game right now.",
        "Someone is definitely arguing in general chat.",
        "Bonzi joined the server.",
        "Bonzi has no idea what is happening.",
        "PING!",
        "Bonzi has discovered voice chat.",
        "Average Discord conversation:",
        "Bonzi wants Discord Nitro.",
        "Bonzi has entered the gaming zone.",
        "Someone just said 'bro'."
    ]
}
# Bonzi's app list is the same everywhere, but the command that actually opens
# each one is platform specific - notepad.exe does not exist on macOS.
APP_TARGETS={
    "Notepad": ["open", "-a", "TextEdit"] if IS_MAC else ["notepad.exe"],
    "Calculator": ["open", "-a", "Calculator"] if IS_MAC else ["calc.exe"],
    "Explorer": ["open", os.path.expanduser("~")] if IS_MAC else ["explorer.exe"],
    "Paint": ["open", "-a", "Preview"] if IS_MAC else ["mspaint"],
}
apps = [
    (name, APP_TARGETS[name])
    for name in ("Notepad", "Calculator", "Explorer", "Paint")
]
app_msg={
    "Notepad":[
        "Time to write some notes down!",
        "Where you randomly write stuff",
        "Bonzi doesn't know how to write",
        "Bonzi was here.",
        "Bonzi has discovered text.",
        "This document is now 73% more Bonzi.",
        "I have absolutely nothing important to say.",
        "Why use Notepad when you have Bonzi?",
        "Bonzi is writing his autobiography.",
        "Chapter 1: Bonzi opened Notepad.",
        "Chapter 2: Bonzi forgot what happened.",
        "This is probably going to be important later.",
        "Bonzi has entered typing mode.",
        "Please do not save this.",
        "Actually, please save this.",
        "Bonzi recommends saving your work.",
        "I wonder what happens if I type here..."
    ],
    "Calculator":[
        "Time to do some calculations!",
        "What is 9 to the power of 100000000? Guess we will never know",
        "HOMEWORK SIMULATOR",
        "Bonzi calculated your chances of escaping.",
        "The answer is 42. Probably.",
        "Bonzi needs to calculate something important.",
        "2 + 2 = BONZI",
        "Calculator has been acquired.",
        "Bonzi is doing extremely advanced mathematics.",
        "Please calculate the amount of cookies Bonzi deserves.",
        "Error: too much math.",
        "Bonzi has never heard of PEMDAS.",
        "Numbers are scary."
    ],
    "Explorer":[
        "Exploring the files!",
        "Bonzi ate System32. BURP",
        "Imagine having files.",
        "Bonzi is going on an adventure.",
        "Where are we going? Nobody knows.",
        "Bonzi has discovered File Explorer.",
        "Let's see what you've got in here.",
        "Bonzi promises not to touch anything.",
        "Probably.",
        "Bonzi is just looking around.",
        "This folder looks suspicious.",
        "Bonzi found something interesting.",
        "Bonzi has absolutely no idea where he is.",
        "File Explorer: because files don't explore themselves.",
        "Bonzi is searching for cookies."
    ],
    "Paint":[
        "Bonzi once painted.",
        "Draw a smiley face",
        "MAKE JEFF",
        "Bonzi is becoming an artist.",
        "Time for modern art.",
        "This masterpiece will be worth millions.",
        "Bonzi has discovered the paintbrush.",
        "I call this one 'Purple Guy'.",
        "Art is subjective.",
        "Bonzi does not understand art.",
        "Draw a banana.",
        "Make the biggest circle you can.",
        "Bonzi is Picasso now.",
        "This belongs in a museum.",
        "Please rate Bonzi's masterpiece."
    ]
}
notepad_typing=[
    "Bonzi was here.",
    "Why are you reading this?",
    "Hello, human.",
    "Bonzi has entered the document.",
    "I don't know what I'm doing.",
    "THIS IS A VERY IMPORTANT DOCUMENT.",
    "Please ignore this message.",
    "Bonzi is watching.",
    "Bonzi likes Notepad.",
    "Bonzi does not like WordPad.",
    "I was told to write something.",
    "Writing is difficult.",
    "Bonzi has learned how to type.",
    "Look Mom, I can type!",
    "abcdefghijklmnopqrstuvwxyz",
    "1234567890",
    "Testing testing 123.",
    "Is this thing on?",
    "Why does Notepad exist?",
    "Bonzi has several questions.",
    "Where are my cookies?",
    "I would like a cookie.",
    "Bonzi wants a new computer.",
    "Bonzi needs more RAM.",
    "32 GB is probably enough.",
    "Bonzi has no idea what RAM does.",
    "Do not close Bonzi.",
    "Closing Bonzi is illegal.",
    "Bonzi has legally acquired this Notepad.",
    "This document belongs to Bonzi now.",
    "Your keyboard belongs to Bonzi.",
    "Bonzi typed this without permission.",
    "Oops.",
    "That was not supposed to happen.",
    "Everything is completely fine.",
    "Nothing suspicious is happening.",
    "Definitely not a virus.",
    "Just kidding. Probably.",
    "Bonzi has successfully completed the important task of typing.",
    "Important business is happening here.",
    "Meeting notes: Bonzi.",
    "Meeting notes: BONZI.",
    "Meeting notes: everyone went home.",
    "Dear human, please provide snacks.",
    "Dear human, where are the snacks?",
    "Dear human, Bonzi requires cookies.",
    "Bonzi has a business proposal.",
    "Step 1: Open Notepad.",
    "Step 2: Type nonsense.",
    "Step 3: Profit.",
    "Step 4: Forget Step 3.",
    "Bonzi has forgotten what Step 4 was.",
    "ERROR: Bonzi forgot what he was doing.",
    "ERROR: Human detected.",
    "WARNING: Excessive Bonzi detected.",
    "WARNING: This document contains Bonzi.",
    "System status: BONZI.",
    "Computer status: BONZI.",
    "Notepad status: BONZI.",
    "Human status: confused.",
    "Bonzi would like to speak to the manager.",
    "Can I have administrator privileges?",
    "Never mind.",
    "Bonzi has decided against it.",
    "Imagine if this was important.",
    "Imagine if you had saved this.",
    "Imagine having files.",
    "Bonzi found the keyboard.",
    "Bonzi found the spacebar.",
    "Bonzi found the Enter key.",
    "Bonzi has discovered punctuation.",
    "Bonzi has discovered CAPITAL LETTERS.",
    "BONZI HAS DISCOVERED CAPS LOCK.",
    "Bonzi has discovered lowercase letters.",
    "Bonzi has discovered numbers.",
    "Bonzi has discovered the backspace key.",
    "Bonzi is now unstoppable.",
    "Bonzi has written a novel.",
    "This is chapter one.",
    "This is chapter two.",
    "This is chapter three.",
    "There is no chapter four.",
    "THE END.",
    "Actually, not the end.",
    "Bonzi forgot something.",
    "Bonzi has returned.",
    "Hello again.",
    "Did you miss me?",
    "You probably didn't.",
    "That's okay.",
    "Bonzi is still here.",
    "Why is this document so empty?",
    "Not anymore.",
    "Bonzi has improved the document.",
    "You're welcome.",
    "Bonzi deserves a raise.",
    "Bonzi demands a raise.",
    "Bonzi accepts payment in cookies.",
    "Bonzi accepts payment in RAM.",
    "Bonzi accepts payment in GPUs.",
    "Bonzi accepts payment in bananas.",
    "Bonzi has no idea why bananas are involved.",
    "Banana.",
    "BANANA.",
    "BANANA BANANA BANANA.",
    "Bonzi has important banana business.",
    "Please do not question the banana.",
    "Bonzi has left the banana department.",
    "Bonzi is now working in Notepad.",
    "Bonzi's productivity is unmatched.",
    "Bonzi's productivity is questionable.",
    "Bonzi's productivity has been terminated.",
    "Bonzi is taking a break.",
    "Bonzi is back from his break.",
    "Bonzi forgot what the break was for.",
    "Bonzi needs coffee.",
    "Bonzi cannot drink coffee.",
    "Bonzi is purple.",
    "Why is Bonzi purple?",
    "Nobody knows.",
    "Bonzi knows.",
    "Bonzi will not tell you.",
    "Secret Bonzi information.",
    "TOP SECRET.",
    "DO NOT READ.",
    "You read it.",
    "Bonzi is disappointed.",
    "Bonzi forgives you.",
    "Maybe.",
    "Bonzi has a plan.",
    "The plan is to type this sentence.",
    "Plan completed.",
    "Bonzi wins.",
]

x_messages = [
    "How dare you try to close me.",
    "HEY! I wasn't finished!",
    "You can't get rid of me that easily.",
    "Nice try.",
    "Did you really think that would work?",
    "Bonzi says NO.",
    "I saw that.",
    "Excuse me?",
    "Where do you think you're going?",
    "You tried to close me. Interesting.",
    "Bonzi does not approve.",
    "That button does not work anymore.",
    "I have decided that I am staying.",
    "You pressed the wrong button.",
    "Closing Bonzi is not an option.",
    "Bonzi has rejected your request.",
    "Absolutely not.",
    "Nope.",
    "Try again.",
    "Was that supposed to close me?",
    "Bonzi has denied your request.",
    "You cannot escape the purple guy.",
    "I am not done annoying you.",
    "Bonzi will remember this.",
    "That was rude.",
    "Why would you do that?",
    "I thought we were friends.",
    "You hurt Bonzi's feelings.",
    "Bonzi has become slightly more annoying.",
    "Congratulations. You made Bonzi angry.",
    "ERROR: Bonzi refuses to close.",
    "Closing procedure cancelled.",
    "Bonzi says: nope.",
    "Nice attempt, human.",
    "The X is merely decorative.",
    "That button is a suggestion.",
    "Bonzi has overridden your decision.",
    "You clicked the forbidden button.",
    "Bonzi is staying right here.",
    "Did you really think I would let you leave?"
]

calc_typing= [
    "2+2",
    "15*7",
    "100/4",
    "999-123",
    "42*42",
    "12345+67890",
    "5000/37",
    "7^3",
    "9^5",
    "2^20",
    "1000000/3",
    "123*456",
    "789+321",
    "100-99",
    "17*19", 
    "144/12", 
    "81/9", 
    "25^2", 
    "9999+1", 
    "1234-567", 
    "3.14159*2", 
    "50*5",
    "(15+5)*3",
    "(100/4)+7",
    "(9^2)+16",
    "(12*12)-44",
    "(50+50)/10",
    "7*7*7",
    "12345/5",
    "999*999",
    "1+1+1+1+1+1+1+1+1+1",
    "0/1",
    "99999999*99999999",
    "1234567*7654321",
    "2^32",
    "10^15",
    "37*37",
    "3.14*3.14",
    "(7+8)*(9-4)",
    "((20+5)*2)/5",
    "9999%7",
    "123456%13",
]
def teleport():
    delay=random.randint(3000,7000)
    x=random.randint(0,max(0,page_width-WINDOW_WIDTH))
    y=random.randint(0,max(0,page_height-WINDOW_HEIGHT))
    window.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{x}+{y}")
    window.after(delay, teleport)

def choose():
    delay=random.randint(10000,30000)
    random.choice(actions)[1]()
    window.after(delay, choose)

def foreground_matches(expected):
    if not IS_WINDOWS:
        # No supported way to identify the frontmost window on macOS without
        # extra accessibility permissions, so we never type blindly.
        return False
    try:
        title=pygetwindow.getActiveWindow().title or ""
    except Exception:
        return False

    if not title:
        return False

    return any(token in title.lower() for token in expected)

def type_into_foreground(text, expected):
    time.sleep(1)

    if not foreground_matches(expected):
        log_error(f"skipped typing into unexpected window for {text!r}")
        return False

    # Imported lazily: pyautogui pulls in platform input libraries and on
    # macOS wants Accessibility permission, which we never need there.
    import pyautogui

    pyautogui.typewrite(text)
    pyautogui.press("enter")
    return True

def open_app(show_message=True):
    chosen_app=random.choice(apps)
    chosen_nmsg=random.choice(notepad_typing)
    chosen_cequ=random.choice(calc_typing)
    chosen_amsg=random.choice(app_msg[chosen_app[0]])

    subprocess.Popen(chosen_app[1])

    if chosen_app[0]=="Notepad":
        type_into_foreground(chosen_nmsg, ("notepad",))

    if chosen_app[0]=="Calculator":
        type_into_foreground(chosen_cequ, ("calculator",))

    if show_message==True:
        notify(chosen_amsg)


def open_browser(show_message=True):
    chosen_browser=random.choice(browsers)

    chosen_bmsg=random.choice(browser_messges[chosen_browser[0]])

    webbrowser.open(chosen_browser[1])

    if show_message==True:
        notify(chosen_bmsg)

def hide_mouse():
    set_cursor_visible(False)
    window.after(5000, show_mouse)

def show_mouse():
    set_cursor_visible(True)

def x_pressed():

    number=random.randint(2,5)

    chosen_xmsg=random.choice(x_messages)

    for n in range(number):
        action=random.choice(actions)

        if action[0]=="Open App":
            action[1](show_message=False)

        elif action[0]=="Open Browser":
            action[1](show_message=False)

        else:
            action[1]()
    notify(chosen_xmsg)

actions=[
    ("Open App", open_app),
    ("Open Browser", open_browser),
    ("Hide Mouse", hide_mouse),
]
if not acquire_single_instance():
    sys.exit(0)

window = tk.Tk()

window.title(APP_NAME)

window.attributes("-topmost", True)

window.resizable(False, False)

designer_path=find_asset("Designer.png")
icon_path=find_asset("bonzi.png")

missing=[
    name
    for name, path in (("Designer.png", designer_path), ("bonzi.png", icon_path))
    if path is None
]

if missing:
    messagebox.showerror(
        APP_NAME,
        f"Bonzi Buddy is missing these files:\n\n"
        + "\n".join(missing)
        + "\n\nKeep them in the same folder as Bonzi Buddy, or reinstall."
    )
    sys.exit(1)

# ---- animation -----------------------------------------------------------
# Bonzi is drawn from pre-rendered variants of the artwork rather than being
# scaled live, so the frames stay crisp. The blink frames are optional: if they
# are missing we simply never blink.

ANIM_PAD_X=16
ANIM_PAD_Y=26
ANIM_FRAME_MS=45
ANIM_SCALE=4
# Amplitudes are fixed rather than derived from the padding, otherwise the idle
# sway and the reaction hop compound and push him out of the window.
ANIM_BOB=6.0
ANIM_SWAY=8.0
ANIM_HOP=18.0

import math

def _load_frame(path, required=True):
    if path is None:
        return None
    try:
        return PhotoImage(file=path).subsample(ANIM_SCALE, ANIM_SCALE)
    except Exception as error:
        log_error(f"frame load failed for {path!r}: {error!r}")
        return None

base_frame=_load_frame(designer_path)
half_frame=_load_frame(find_asset("Designer_half.png"), required=False)
blink_frame=_load_frame(find_asset("Designer_blink.png"), required=False)

# Tk only renders a PhotoImage while Python still references it.
ANIM_FRAMES=[frame for frame in (base_frame, half_frame, blink_frame) if frame]

bonzi=tk.Label(window, image=base_frame, bd=0, highlightthickness=0)

BASE_WIDTH=bonzi.winfo_reqwidth()
BASE_HEIGHT=bonzi.winfo_reqheight()

WINDOW_WIDTH=BASE_WIDTH + ANIM_PAD_X * 2
WINDOW_HEIGHT=BASE_HEIGHT + ANIM_PAD_Y * 2

window.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
bonzi.place(x=ANIM_PAD_X, y=ANIM_PAD_Y)

_anim={"t":0, "state":"idle", "frames_left":0, "hop":0.0}

def bonzi_react():
    # Called whenever he says something: a short, livelier hop.
    _anim["hop"]=1.0
    _anim["state"]="react"
    _anim["frames_left"]=14

def _anim_tick():
    _anim["t"]+=1
    tick=_anim["t"]

    bob=math.sin(tick * 0.042) * ANIM_BOB
    sway=math.sin(tick * 0.026) * ANIM_SWAY

    hop=_anim["hop"]

    if hop>0:
        _anim["hop"]=max(0.0, hop - 0.075)
        bob-=math.sin((1.0 - hop) * math.pi) * ANIM_HOP
        sway+=math.sin((1.0 - hop) * math.pi * 2) * 7

    # frame selection: idle -> occasional half-lid -> blink -> back
    if _anim["frames_left"]>0:
        _anim["frames_left"]-=1
        if blink_frame is not None and half_frame is not None:
            if _anim["frames_left"]>4:
                bonzi.configure(image=blink_frame)
            else:
                bonzi.configure(image=half_frame)
    else:
        if _anim["state"]!="idle":
            _anim["state"]="idle"
        if blink_frame is not None and random.random()<0.012:
            _anim["state"]="blink"
            _anim["frames_left"]=5
        bonzi.configure(image=base_frame)

    # clamping is a safety net: the label must never leave the window
    x=max(0.0, ANIM_PAD_X + sway)
    y=max(0.0, ANIM_PAD_Y + bob)
    bonzi.place(x=x, y=y)
    window.after(ANIM_FRAME_MS, _anim_tick)

window.iconphoto(False, PhotoImage(file=icon_path))

page_width=window.winfo_screenwidth()

page_height=window.winfo_screenheight()

window.protocol("WM_DELETE_WINDOW", x_pressed)

# ---- self update ---------------------------------------------------------

def _version_tuple(text):
    parts=[]
    for chunk in str(text).split("."):
        digits="".join(char for char in chunk if char.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)

manifest_sha256=""

def _download(url, dest):
    import hashlib
    import tempfile

    digest=hashlib.sha256()
    tmp=os.path.join(tempfile.gettempdir(), "bonzi_update_download.exe")
    with urllib.request.urlopen(url, timeout=60) as response, open(tmp, "wb") as out:
        while True:
            chunk=response.read(262144)
            if not chunk:
                break
            digest.update(chunk)
            out.write(chunk)
    expected=(manifest_sha256 or "").lower()
    if expected and digest.hexdigest()!=expected:
        os.remove(tmp)
        raise ValueError("checksum mismatch")
    os.replace(tmp, dest)
    return dest

def _swap_and_relaunch(new_exe):
    # A running .exe cannot overwrite itself, so a detached script retires the
    # old copy, drops the new one into place and starts it.
    import tempfile

    current=sys.executable
    backup=current + ".old"
    script=os.path.join(tempfile.gettempdir(), "bonzi_update.cmd")
    body=(
        "@echo off\r\n"
        "timeout /t 2 /nobreak >nul\r\n"
        f'move /y "{current}" "{backup}" >nul\r\n'
        f'move /y "{new_exe}" "{current}" >nul\r\n'
        f'start "" "{current}"\r\n'
        f'timeout /t 3 /nobreak >nul\r\n'
        f'del /y "{backup}" >nul\r\n'
    )
    with open(script, "w", encoding="utf-8") as handle:
        handle.write(body)
    flags=0
    if IS_WINDOWS:
        flags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(["cmd", "/c", script], creationflags=flags, close_fds=True)

def check_for_update():
    if not UPDATE_MANIFEST_URL:
        return
    if not getattr(sys, "frozen", False):
        return
    if not IS_WINDOWS:
        # The swap-and-relaunch below relies on cmd.exe retiring a running
        # binary, which has no equivalent on macOS yet.
        return
    import tempfile
    import threading

    def worker():
        global manifest_sha256
        try:
            request=urllib.request.Request(
                UPDATE_MANIFEST_URL, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"}
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                manifest=json.loads(response.read().decode("utf-8"))
            latest=str(manifest.get("version", "0"))
            if _version_tuple(latest)<=_version_tuple(APP_VERSION):
                return
            url=manifest.get("url")
            if not url:
                return
            if not url.lower().startswith("https://"):
                log_error("refusing update over plain http")
                return
            manifest_sha256=manifest.get("sha256", "")
            target=os.path.join(tempfile.gettempdir(), "bonzi_new.exe")
            _download(url, target)
            _swap_and_relaunch(target)
            window.after(0, window.destroy)
        except Exception as error:
            log_error(f"update check failed: {error!r}")

    threading.Thread(target=worker, daemon=True).start()

add_to_startup()
teleport()
choose()
window.after(200, _anim_tick)
window.after(3000, check_for_update)
window.mainloop()