import subprocess
import os
import pwd, grp

def restart_samba():
    try:
        subprocess.run(["systemctl", "restart", "smbd", "nmbd"], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Fehler bei Samba Neustart: {e.stderr}")
        return False

def restart_nfs():
    try:
        subprocess.run(["systemctl", "restart", "nfs-kernel-server"], check=True, capture_output=True)
        subprocess.run(["exportfs", "-ra"], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Fehler bei NFS Neustart: {e.stderr}")
        return False

def check_service_status(service_name):
    result = subprocess.run(["systemctl", "is-active", service_name], capture_output=True, text=True)
    return "Aktiv" if result.stdout.strip() == "active" else "Inaktiv"

def create_or_update_system_user(username, password=None, groups="", is_active=True):
    try:
        user_check = subprocess.run(["id", username], capture_output=True)
        exists = user_check.returncode == 0
        
        # User anlegen
        if not exists:
            subprocess.run(["useradd", "-M", "-s", "/usr/sbin/nologin", username], check=True, capture_output=True)
            
        # Gruppen zuweisen
        group_cmd = ["usermod", "-G", f"{username},{groups}" if groups else username, username]
        subprocess.run(group_cmd, check=True, capture_output=True)
        
        # Samba Passwort setzen
        if password:
            smb_process = subprocess.Popen(["smbpasswd", "-s", "-a", username], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            smb_process.communicate(input=f"{password}\n{password}\n")
            
        # Aktiv/Inaktiv setzen
        if is_active:
            subprocess.run(["smbpasswd", "-e", username], capture_output=True)
        else:
            subprocess.run(["smbpasswd", "-d", username], capture_output=True)
            
        return True, "User erfolgreich aktualisiert."
    except subprocess.CalledProcessError as e:
        return False, f"Fehler: {e.stderr.decode()}"

def delete_system_user(username):
    try:
        subprocess.run(["smbpasswd", "-x", username], capture_output=True)
        subprocess.run(["userdel", username], capture_output=True)
        return True
    except Exception:
        return False

def check_practical_access(username, path):
    """ Testet per sudo, ob der User reale Rechte auf dem Dateisystem hat und analysiert Probleme. """
    
    # Fehler 1: Pfad existiert nicht
    if not os.path.exists(path):
        return {
            "read": False, "write": False, 
            "error_type": "not_found",
            "system_msg": f"No such file or directory: '{path}'",
            "description": f"Der angegebene Pfad '{path}' existiert nicht im Dateisystem des LXC-Containers.",
            "solution": "1. Prüfe, ob du dich beim Pfad vertippt hast.\n2. Falls der Pfad auf dem Proxmox-Host existiert, stelle sicher, dass du den Bind-Mount (mp0, mp1) in der LXC-Konfiguration korrekt eingerichtet und den LXC neu gestartet hast."
        }
    
    # Fehler 2: Pfad ist kein Verzeichnis (z.B. eine Datei)
    if not os.path.isdir(path):
        return {
            "read": False, "write": False, 
            "error_type": "not_a_directory",
            "system_msg": f"Not a directory: '{path}'",
            "description": f"Der Pfad '{path}' verweist auf eine Datei, nicht auf einen Ordner.",
            "solution": "Ein Share muss immer auf einen Ordner (Verzeichnis) verweisen. Bitte wähle einen gültigen Ordner-Pfad."
        }

    try:
        r_test = subprocess.run(["sudo", "-u", username, "test", "-r", path])
        w_test = subprocess.run(["sudo", "-u", username, "test", "-w", path])
        
        can_read = (r_test.returncode == 0)
        can_write = (w_test.returncode == 0)
        
        # Alles OK
        if can_read and can_write:
            return {"read": True, "write": True, "error_type": None}
            
        # Fehler 3: Berechtigungsproblem
        # Wenn wir hier sind, existiert der Pfad, aber der User darf nicht lesen/schreiben.
        stat = os.stat(path)
        owner = pwd.getpwuid(stat.st_uid).pw_name
        group = grp.getgrgid(stat.st_gid).gr_name
        perms = oct(stat.st_mode)[-3:]
        
        missing = []
        if not can_read: missing.append("Lese-Rechte (Read)")
        if not can_write: missing.append("Schreib-Rechte (Write)")
        
        return {
            "read": can_read, "write": can_write, 
            "error_type": "permission_denied",
            "system_msg": f"Permission denied for user '{username}' on '{path}'.",
            "description": f"Der Linux-Benutzer '{username}' hat keine {', '.join(missing)} für dieses Verzeichnis. Der Ordner gehört aktuell dem Benutzer '{owner}' und der Gruppe '{group}' (Rechte: {perms}).",
            "solution": f"1. Weise den Benutzer '{username}' der Gruppe '{group}' zu (in der User-Verwaltung).\n2. Oder passe die Rechte auf dem Host an:\n   chown -R {owner}:{group} {path}\n   chmod -R 775 {path}"
        }
        
    except Exception as e:
        # Fallback für unerwartete Fehler (z.B. sudo nicht installiert)
        return {
            "read": False, "write": False, 
            "error_type": "unknown",
            "system_msg": str(e),
            "description": "Ein unerwarteter Systemfehler ist bei der Rechte-Prüfung aufgetreten.",
            "solution": "Überprüfe die Konsolen-Logs des LXC-Containers auf weitere Details."
        }
