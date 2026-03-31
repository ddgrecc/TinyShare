# 📁 TinyShare

TinyShare ist ein ultra-leichtgewichtiges Web-Interface zur Verwaltung von Samba (SMB) und NFS Freigaben. 
Es wurde speziell für den Einsatz in **Proxmox LXC-Containern (Debian/Ubuntu)** entwickelt und bietet eine moderne Alternative zu schweren NAS-Betriebssystemen (wie TrueNAS oder OMV), wenn man eigentlich "nur ein paar Ordner freigeben" möchte.

## ✨ Features

- **🚀 Minimalistisch & Schnell:** Basiert auf Python (FastAPI), SQLAlchemy und Vanilla JS/CSS.
- **👥 Benutzerverwaltung:** SMB-Benutzer direkt im Web-Interface anlegen, Passwörter setzen und Berechtigungen verwalten (ohne Linux Login-Shell für mehr Sicherheit).
- **📂 Share-Verwaltung:** SMB und NFS Freigaben per Klick erstellen und Routings festlegen.
- **🔍 Live Diagnose-Engine:** Prüft automatisch, ob die Samba-Rechte in TinyShare mit den echten Linux-Host-Rechten (`chown`/`chmod`) übereinstimmen und spuckt genaue Fehlermeldungen + Lösungsvorschläge aus.
- **⚙️ Advanced Templates:** Fortgeschrittene Parameter (z.B. VFS Fruit für macOS, Recycle Bin, NFS Async) über ein sauberes Template-System konfigurierbar.

## 🛠️ Installation (Debian / Ubuntu LXC)

**1. System-Voraussetzungen installieren:**
```bash
apt-get update
apt-get install python3 python3-pip samba nfs-kernel-server -y
```

**2. Projekt klonen & Abhängigkeiten installieren:**
```bash
cd /opt
git clone https://github.com/ddgrecc/TinyShare.git
cd TinyShare
pip install fastapi uvicorn sqlalchemy jinja2 python-multipart
```

**3. Server starten:**
```bash
python3 main.py
```
Das Web-Interface ist nun unter `http://<LXC-IP>:8000` erreichbar.

*(Hinweis: Für den produktiven Einsatz empfiehlt es sich, TinyShare als systemd-Service laufen zu lassen.)*

## 💡 Wie es funktioniert

TinyShare greift nicht tief ins Betriebssystem ein. Es liest und schreibt in eine lokale SQLite-Datenbank (`tinyshare.db`). Beim Speichern generiert es die Dateien `/etc/samba/smb.conf` und `/etc/exports` neu und startet die jeweiligen Dienste im Hintergrund per `systemctl` neu.

## 📝 Lizenz

Dieses Projekt steht unter der [MIT License](LICENSE).
