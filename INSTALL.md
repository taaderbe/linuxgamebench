# Installation Guide

## Schnellinstallation

### Methode 1: pipx (empfohlen)

```bash
# Arch / CachyOS
sudo pacman -S python-pipx
pipx install git+https://github.com/taaderbe/linuxgamebench.git

# Ubuntu / Debian
sudo apt install pipx
pipx install git+https://github.com/taaderbe/linuxgamebench.git
```

### Update auf neueste Version

```bash
pipx uninstall linux-game-benchmark
pipx install git+https://github.com/taaderbe/linuxgamebench.git
```

### Methode 2: Aus Source (Development)

```bash
git clone https://github.com/taaderbe/linuxgamebench
cd linuxgamebench
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

---

## MangoHud installieren

MangoHud ist **zwingend erforderlich** für die Frametime-Aufnahme.

### Arch Linux / CachyOS / EndeavourOS

```bash
sudo pacman -S mangohud lib32-mangohud
```

### Ubuntu / Debian / Pop!_OS

```bash
sudo apt install mangohud
```

### Fedora

```bash
sudo dnf install mangohud
```

### Flatpak (falls Spiele als Flatpak installiert)

```bash
flatpak install flathub org.freedesktop.Platform.VulkanLayer.MangoHud
```

---

## Optionale Abhängigkeiten

### GameMode (Performance-Boost)

```bash
# Arch
sudo pacman -S gamemode lib32-gamemode

# Ubuntu
sudo apt install gamemode

# Fedora
sudo dnf install gamemode
```

### Gamescope (Auflösungs-Testing)

```bash
# Arch
sudo pacman -S gamescope

# Ubuntu (22.04+)
sudo apt install gamescope

# Fedora
sudo dnf install gamescope
```

---

## Prüfen ob alles funktioniert

```bash
lgb check
```

**Erwartete Ausgabe:**

```
Checking system requirements...

MangoHud: v0.7.2 ✓
Steam: /usr/bin/steam ✓
Gamescope: /usr/bin/gamescope (optional)
GameMode: /usr/bin/gamemoderun (optional)

All required components are installed!
```

---

## Steam konfigurieren

### Option 1: Per-Spiel (empfohlen)

1. Rechtsklick auf Spiel in Steam → Eigenschaften
2. Startoptionen:
   ```
   MANGOHUD=1 %command%
   ```

### Option 2: Global (für alle Spiele)

```bash
mkdir -p ~/.config/environment.d
echo "MANGOHUD=1" >> ~/.config/environment.d/mangohud.conf
```

Neu einloggen oder neustarten.

---

## Troubleshooting

### "MangoHud not found"

```bash
# Prüfe Installation
mangohud --version

# Falls nicht installiert
sudo pacman -S mangohud  # Arch
sudo apt install mangohud  # Ubuntu
```

### "Steam not found"

lgb sucht Steam in:
- `/usr/bin/steam`
- `/usr/games/steam`
- `~/.local/share/Steam/steam.sh`

Falls Steam woanders installiert ist, erstelle einen Symlink:
```bash
sudo ln -s /pfad/zu/steam /usr/bin/steam
```

### 32-bit Spiele funktionieren nicht

```bash
# Arch
sudo pacman -S lib32-mangohud

# Ubuntu
sudo apt install mangohud:i386
```

### Flatpak-Spiele

```bash
# MangoHud für Flatpak
flatpak install flathub org.freedesktop.Platform.VulkanLayer.MangoHud

# Startoptionen in Steam (Flatpak)
MANGOHUD=1 %command%
```

---

## Development Setup

Für Entwickler:

```bash
git clone https://github.com/taaderbe/linuxgamebench
cd linuxgamebench

# Virtual Environment
python3 -m venv .venv
source .venv/bin/activate

# Dev-Dependencies installieren
pip install -e ".[dev]"

# Tests ausführen
pytest

# Mit Playwright-Browser
playwright install chromium
pytest tests/e2e/
```
