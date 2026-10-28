# 🖥️ PyOS — Hybrid Operating System Simulation

**PyOS** is an educational desktop-environment simulation built with **Python** and **PyQt6**. It mixes the look and feel of macOS, Windows 11 and Linux, and demonstrates core operating-system concepts — process scheduling, memory allocation, I/O devices, users & permissions — inside a fully working GUI.

> ⚠️ Educational project — **not** a real operating system.

---

## ✨ Features

### 🪟 Desktop Environment
- Login / registration screen with glassmorphism card over an animated background
- MDI-based window manager with a top bar and notification toasts
- Animated futuristic **Dock** (spring-based spacing, glow, tooltips, active indicators)
- Desktop icons and a notification center

### 🎨 Appearance & Themes
- Dark / Light themes with a custom accent color (presets + color picker)
- Animated wallpapers: **Aurora, Matrix, Waves, Particles, Cosmos, Solid**
- Custom wallpaper image support
- Adjustable font size and dock position (top / bottom)
- All settings persist instantly to `~/.pyos/settings.json`

### ⚙️ OS Concepts
| Module | What it does |
|---|---|
| **Process Manager** | Simulated processes with **Round Robin** scheduling (states: Running / Ready / Waiting / Terminated), plus real system processes via `psutil` |
| **Memory Manager** | Fixed-partition allocation (1024 MB total, 32 MB blocks) with a visual block map |
| **I/O Manager** | Tracks keyboard, mouse, display, CPU, battery, disk and network interfaces |
| **System Monitor** | Real-time CPU (per core), memory, swap, disk and network stats on a background thread |
| **User Manager** | Users, groups, passwords (SHA-256), admin / sudo roles, persisted to `~/.pyos/users.json` |

### 💻 Built-in Terminal
A pure-Python Linux-style shell that works on **Windows, Linux and macOS** without WSL:
- 100+ native commands: `ls`, `cat`, `grep`, `find`, `cp`, `mv`, `rm`, `tar`, `zip`, `curl`, `ping`, `ps`, `top`, `awk`, `sed`, ...
- Full built-in **nano**-style text editor with syntax highlighting
- User commands linked to the OS user manager: `useradd`, `userdel`, `usermod`, `passwd`, `groupadd`, `groupdel`, `su`, `id`, `groups`
- Multi-tab terminals, command history, ANSI colors
- Unknown commands fall through to the real system shell

### 🌐 Networking
- **Embedded browser** (QtWebEngine): tabs, bookmarks, private mode, privacy settings, zoom, keyboard shortcuts (`Ctrl+T/W/L/R/H`)
- **LAN scanner**: gateway detection, ARP table, parallel TCP probing, MAC vendor lookup, latency checks — works even when ICMP is blocked
- **Wi-Fi manager**: scan, connect and disconnect using native tools (`nmcli` on Linux, `netsh wlan` on Windows, `airport` on macOS)

### 📁 File Manager
- Browse the real host filesystem (tree + icon view)
- Create / rename / delete files and folders
- Built-in text editor dialog

---

## 📸 Screenshots

_Add your screenshots here (e.g. `docs/login.png`, `docs/desktop.png`)._

---

## 🚀 Getting Started

### Requirements
- Python **3.10+**
- PyQt6 ≥ 6.6.0
- PyQt6-WebEngine ≥ 6.6.0
- psutil ≥ 5.9.0

### Installation

```bash
git clone https://github.com/<your-username>/pyos.git
cd pyos
pip install -r requirements.txt
python main.py
```

Or on Linux / macOS:

```bash
chmod +x run.sh
./run.sh
```

### Default Login

| Username | Password |
|---|---|
| `root` | `root` |

> 🔐 Change the default password after the first login (`passwd root` in the terminal).

---

## 🗂️ Project Structure

```
pyos/
├── main.py                 # Entry point (login → desktop)
├── main_gui.py             # Desktop environment, windows, top bar
├── login.py                # Login / register screen
├── dock.py                 # Animated dock
├── themes.py               # Dark / light QSS theme engine
├── animated_background.py  # Animated wallpapers
├── settings.py             # Settings panel UI
├── settings_manager.py     # Persistent settings (~/.pyos/settings.json)
├── user_manager.py         # Users, groups, auth (~/.pyos/users.json)
├── process_manager.py      # Process simulation + Round Robin scheduler
├── memory_manager.py       # Fixed-partition memory simulation
├── io_manager.py           # I/O device tracking
├── system_monitor.py       # Real-time system stats
├── terminal.py             # Pure-Python shell + nano editor
├── file_system.py          # File manager
├── browser.py              # Embedded web browser
├── network.py              # LAN scanner
├── wifi_manager.py         # Wi-Fi manager
├── requirements.txt
└── run.sh
```

---

## ⚙️ Configuration

Config files are stored in `~/.pyos/`:

| File | Purpose |
|---|---|
| `settings.json` | Theme, accent, wallpaper, font size, dock position, polling intervals |
| `users.json` | Users and groups |

---

## 🛠️ Troubleshooting

- **Browser doesn't load:** make sure `PyQt6-WebEngine` is installed. PyOS shows a fallback if it's unavailable.
- **Wi-Fi scan returns nothing:** check that the OS tool is available (`nmcli` / `netsh` / `airport`).
- **Black screen / GPU issues:** PyOS already launches with `--disable-gpu` for WebEngine.

---

## 🤝 Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you'd like to change.

## 📄 License

Add a license of your choice (e.g. [MIT](https://choosealicense.com/licenses/mit/)) and update this section.
