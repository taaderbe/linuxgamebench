# Linux Game Benchmark (lgb)

Automatisiertes Benchmark-Tool für Steam-Spiele unter Linux.
Misst FPS, Stutter, Frame Pacing und mehr mit MangoHud.

## Features

- Automatische Steam-Spielerkennung
- MangoHud-Integration für Frametimes
- Detaillierte Metriken (AVG FPS, 1% Low, 0.1% Low, Stutter)
- Multi-Auflösungs-Support (FHD, WQHD, UHD)
- Schöne HTML-Reports mit interaktiven Charts
- Multi-System-Vergleich (verschiedene GPUs/CPUs vergleichen)
- Upload zur Community-Datenbank (coming soon)

## Voraussetzungen

- Linux (getestet auf Arch, Fedora, Ubuntu)
- Steam installiert
- MangoHud installiert
- Python 3.10+

Optional:
- Gamescope (für Auflösungstests)
- GameMode (für Performance-Optimierung)

## Installation

### Arch Linux / CachyOS

```bash
# MangoHud und optionale Tools installieren
sudo pacman -S mangohud lib32-mangohud gamemode lib32-gamemode gamescope

# Tool installieren
pip install linux-game-benchmark
```

### Ubuntu/Debian

```bash
sudo apt install mangohud
pip install linux-game-benchmark
```

### Aus Source installieren

```bash
git clone https://github.com/taaderbe/linuxgamebench
cd linuxgamebench
pip install -e .
```

## Schnellstart

### 1. System prüfen

```bash
lgb check
```

### 2. Steam-Spiele auflisten

```bash
lgb list
```

### 3. Benchmark starten

```bash
# Interaktiver Modus (empfohlen)
lgb record_manual
```

**So funktioniert record_manual:**
1. lgb konfiguriert MangoHud und wartet
2. Starte dein Spiel mit `MANGOHUD=1 %command%` in den Steam-Startoptionen
3. Drücke **Shift+F2** im Spiel um die Aufnahme zu starten (60 Sekunden)
4. Zurück zum Terminal: Spielname und Auflösung eingeben
5. Wiederhole für weitere Aufnahmen oder beenden

### 4. Report anschauen

```bash
xdg-open ~/benchmark_results/index.html
```

## Befehle

| Befehl | Beschreibung |
|--------|--------------|
| `lgb check` | Systemanforderungen prüfen |
| `lgb list` | Installierte Steam-Spiele anzeigen |
| `lgb scan` | Steam-Bibliothek scannen |
| `lgb info` | System-Informationen anzeigen |
| `lgb record [game]` | Benchmark für ein Spiel starten |
| `lgb record_manual` | Manueller Modus (Spiel selbst starten) |
| `lgb analyze [log]` | MangoHud-Log analysieren |
| `lgb report` | Reports neu generieren |

## Metriken

| Metrik | Beschreibung |
|--------|--------------|
| **AVG FPS** | Durchschnittliche Bilder pro Sekunde |
| **1% Low** | Niedrigste 1% der Frametimes (zeigt Mikroruckler) |
| **0.1% Low** | Niedrigste 0.1% der Frametimes (extreme Ruckler) |
| **Stutter** | Wie häufig treten Ruckler auf? (excellent/good/moderate/poor) |
| **Consistency** | Wie gleichmäßig ist die Framerate? |

## Ergebnis-Struktur

```
~/benchmark_results/
    index.html                    # Overview aller Spiele
    Baldurs_Gate_3/
        CachyOS_abc123/           # System 1
            FHD/
                run_001.json
            WQHD/
                run_001.json
        EndeavourOS_def456/       # System 2
            UHD/
                run_001.json
        report.html               # Spiel-Report mit Tabs
```

**Wichtig:**
- Daten werden **NIE gelöscht** - alle Benchmarks bleiben erhalten
- Jedes System bekommt seinen eigenen Ordner
- Reports zeigen alle Systeme mit Tabs zum Umschalten

## MangoHud Setup

Füge in den Steam-Startoptionen hinzu:
```
MANGOHUD=1 %command%
```

Oder global aktivieren:
```bash
mkdir -p ~/.config/environment.d
echo "MANGOHUD=1" >> ~/.config/environment.d/mangohud.conf
```

## Ergebnisse hochladen (coming soon)

```bash
# Steam Account verknüpfen
lgb login

# Benchmark wird automatisch hochgeladen
lgb record "Cyberpunk 2077"
# → "Hochladen? [J/n]"
```

## Lizenz

MIT License

## Beitragen

Pull Requests sind willkommen! Bitte erstelle zuerst ein Issue um die Änderung zu besprechen.
