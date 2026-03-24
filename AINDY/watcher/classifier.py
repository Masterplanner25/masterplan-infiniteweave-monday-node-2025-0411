"""
classifier.py — Activity classification from window/process information.

Maps (app_name, window_title) → ActivityType.

Rules are evaluated in priority order: IDLE → DISTRACTION → WORK → COMMUNICATION → UNKNOWN.
Pattern matching is case-insensitive and uses substring matching on app_name and window_title.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from watcher.window_detector import WindowInfo


class ActivityType(str, Enum):
    WORK = "work"
    COMMUNICATION = "communication"
    DISTRACTION = "distraction"
    IDLE = "idle"
    UNKNOWN = "unknown"


@dataclass
class ClassificationResult:
    activity_type: ActivityType
    confidence: float  # 0.0 – 1.0
    matched_rule: str  # human-readable label for the rule that matched
    app_name: str
    window_title: str


# ---------------------------------------------------------------------------
# Classification rule sets
# (process_patterns, title_patterns) — all lowercase, substring or regex)
# ---------------------------------------------------------------------------

_IDLE_PROCESSES: frozenset[str] = frozenset(
    [
        "screensaver",
        "loginwindow",
        "lockapp",          # Windows lock screen
        "logonui",          # Windows logon UI
        "systemuiserver",   # macOS menu bar daemon (no foreground app)
    ]
)

_WORK_PROCESSES: frozenset[str] = frozenset(
    [
        # Editors / IDEs
        "cursor",
        "code",             # VS Code
        "code - insiders",
        "pycharm",
        "pycharm64",
        "idea",
        "idea64",
        "webstorm",
        "webstorm64",
        "phpstorm",
        "goland",
        "clion",
        "rider",
        "rubymine",
        "datagrip",
        "vim",
        "nvim",
        "neovim",
        "sublime_text",
        "atom",
        "emacs",
        "notepad++",
        "zed",
        # Terminals
        "terminal",
        "iterm",
        "iterm2",
        "warp",
        "windows terminal",
        "windowsterminal",
        "cmd",
        "powershell",
        "pwsh",
        "bash",
        "zsh",
        "alacritty",
        "kitty",
        "hyper",
        "wezterm",
        "konsole",
        "gnome-terminal",
        "xterm",
        # Runtime / build tools
        "python",
        "python3",
        "node",
        "npm",
        "cargo",
        "rustc",
        "go",
        "java",
        "javac",
        "gradle",
        "mvn",
        "make",
        "cmake",
        # Version control
        "git",
        "sourcetree",
        "gitkraken",
        "fork",
        # Design / docs
        "figma",
        "sketch",
        "affinity",
        "notion",
        # Productivity
        "obsidian",
        "logseq",
        "roamresearch",
    ]
)

_COMMUNICATION_PROCESSES: frozenset[str] = frozenset(
    [
        "slack",
        "teams",
        "discord",
        "zoom",
        "meet",
        "webex",
        "skype",
        "outlook",
        "thunderbird",
        "mail",
        "airmail",
        "mimestream",
        "spark",
        "superhuman",
        "telegram",
        "signal",
        "whatsapp",
        "messenger",
        "imessage",
        "messages",
        "facetime",
    ]
)

_DISTRACTION_PROCESSES: frozenset[str] = frozenset(
    [
        "youtube",
        "netflix",
        "twitch",
        "hulu",
        "disneyplus",
        "primevideo",
        "spotify",
        "music",           # macOS Music.app
        "vlc",
        "mpv",
        "steam",
        "epicgameslauncher",
        "roblox",
        "minecraft",
        "origin",
        "battlenet",
        "gog galaxy",
    ]
)

# Title patterns indicating distraction even when in a browser
_DISTRACTION_TITLE_PATTERNS: list[re.Pattern] = [
    re.compile(r"youtube", re.IGNORECASE),
    re.compile(r"netflix", re.IGNORECASE),
    re.compile(r"twitch", re.IGNORECASE),
    re.compile(r"\breddit\b", re.IGNORECASE),
    re.compile(r"twitter|x\.com", re.IGNORECASE),
    re.compile(r"tiktok", re.IGNORECASE),
    re.compile(r"instagram", re.IGNORECASE),
    re.compile(r"facebook", re.IGNORECASE),
    re.compile(r"\bsteam\b.*store", re.IGNORECASE),
    re.compile(r"hacker news", re.IGNORECASE),
]

_BROWSER_PROCESSES: frozenset[str] = frozenset(
    [
        "chrome",
        "chromium",
        "firefox",
        "safari",
        "edge",
        "msedge",
        "opera",
        "brave browser",
        "brave",
        "vivaldi",
        "arc",
    ]
)


def classify(window: Optional[WindowInfo]) -> ClassificationResult:
    """
    Classify the current activity from a WindowInfo snapshot.

    Returns ClassificationResult with IDLE when window is None.
    """
    if window is None:
        return ClassificationResult(
            activity_type=ActivityType.IDLE,
            confidence=1.0,
            matched_rule="no_active_window",
            app_name="",
            window_title="",
        )

    app = window.app_name.lower().strip()
    title = window.window_title.lower().strip()

    # Remove file extension for matching (.exe, .app)
    app_base = re.sub(r"\.(exe|app|bin)$", "", app)

    # --- IDLE ---
    for pat in _IDLE_PROCESSES:
        if pat in app_base or pat in app:
            return ClassificationResult(
                activity_type=ActivityType.IDLE,
                confidence=0.95,
                matched_rule=f"idle_process:{pat}",
                app_name=app,
                window_title=window.window_title,
            )

    # --- DISTRACTION (process name) ---
    for pat in _DISTRACTION_PROCESSES:
        if pat in app_base or pat in app:
            return ClassificationResult(
                activity_type=ActivityType.DISTRACTION,
                confidence=0.9,
                matched_rule=f"distraction_process:{pat}",
                app_name=app,
                window_title=window.window_title,
            )

    # --- DISTRACTION (browser + title) ---
    is_browser = any(b in app_base or b in app for b in _BROWSER_PROCESSES)
    if is_browser:
        for pattern in _DISTRACTION_TITLE_PATTERNS:
            if pattern.search(title) or pattern.search(window.window_title):
                return ClassificationResult(
                    activity_type=ActivityType.DISTRACTION,
                    confidence=0.85,
                    matched_rule=f"distraction_title:{pattern.pattern}",
                    app_name=app,
                    window_title=window.window_title,
                )

    # --- WORK ---
    for pat in _WORK_PROCESSES:
        if pat in app_base or pat in app:
            return ClassificationResult(
                activity_type=ActivityType.WORK,
                confidence=0.9,
                matched_rule=f"work_process:{pat}",
                app_name=app,
                window_title=window.window_title,
            )

    # --- COMMUNICATION ---
    for pat in _COMMUNICATION_PROCESSES:
        if pat in app_base or pat in app:
            return ClassificationResult(
                activity_type=ActivityType.COMMUNICATION,
                confidence=0.9,
                matched_rule=f"communication_process:{pat}",
                app_name=app,
                window_title=window.window_title,
            )

    # --- UNKNOWN ---
    return ClassificationResult(
        activity_type=ActivityType.UNKNOWN,
        confidence=0.5,
        matched_rule="no_match",
        app_name=app,
        window_title=window.window_title,
    )
