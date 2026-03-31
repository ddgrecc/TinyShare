from flask import Flask, request, redirect, render_template_string
import subprocess
import os
import json
import uuid

app = Flask(__name__)

# --- KONFIGURATION ---
# Da du NFS nun zum Laufen gebracht hast, können wir die echten Systempfade nutzen.
DB_FILE = "/etc/tinyshare.json"
SMB_CONF_PATH = "/etc/samba/smb.conf"
NFS_EXPORTS_PATH = "/etc/exports"

# Falls die Pfade nicht existieren (z.B. beim ersten Start in einem frischen LXC),
# stellen wir sicher, dass zumindest das Verzeichnis für die config exisitert.
os.makedirs(os.path.dirname(SMB_CONF_PATH), exist_ok=True)

# --- DATENBANK LOGIK (Source of Truth) ---
def load_db():
    if not os.path.exists(DB_FILE):
        return {"shares": []}
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

# --- CONFIG GENERATOREN ---
def generate_configs():
    db = load_db()
    
    # 1. Samba Config generieren (Basis-Konfiguration)
    smb_out = "[global]\n"
    smb_out += "   workgroup = WORKGROUP\n"
    smb_out += "   security = user\n"
    smb_out += "   map to guest = bad user\n\n"
    
    # 2. NFS Config generieren (Basis-Kommentar)
    nfs_out = "# Generiert von TinyShare\n"
    
    for share in db.get("shares", []):
        # SAMBA Konfiguration für diesen Share
        if share["protocols"].get("smb"):
            smb_out += f"[{share['name']}]\n"
            smb_out += f"   path = {share['path']}\n"
            
            # IP Whitelisting (Dein Feature!)
            if share.get("allowed_ips"):
                smb_out += f"   hosts allow = {share['allowed_ips']} 127.0.0.1\n"
                smb_out += f"   hosts deny = ALL\n"
            
            # Zentrale Rechte auf SMB mappen
            valid_users = []
            if share.get("users_rw"): valid_users.extend([u.strip() for u in share["users_rw"].split(",")])
            if share.get("users_ro"): valid_users.extend([u.strip() for u in share["users_ro"].split(",")])
            
            if valid_users:
                smb_out += f"   valid users = {', '.join(valid_users)}\n"
            if share.get("users_rw"):
                smb_out += f"   write list = {share['users_rw']}\n"
                
            smb_out += "   read only = no\n"
            smb_out += "   guest ok = no\n"
            smb_out += "   browseable = yes\n\n"
            
        # NFS Konfiguration für diesen Share
        if share["protocols"].get("nfs"):
            # Bei NFS ist die IP Pflicht. Fallback auf * nur zur Sicherheit, 
            # aber unser Frontend blockiert leere Eingaben bei NFS.
            ips = share.get("allowed_ips") if share.get("allowed_ips") else "*"
            nfs_out += f"{share['path']} {ips}(rw,sync,no_subtree_check,no_root_squash)\n"

    # In Dateien schreiben
    with open(SMB_CONF_PATH, "w") as f: 
        f.write(smb_out)
    with open(NFS_EXPORTS_PATH, "w") as f: 
        f.write(nfs_out)

    # Dienste neustarten (Da du als root im LXC bist und die Dienste laufen, ist das jetzt aktiv!)
    try:
        subprocess.run(["systemctl", "restart", "smbd", "nmbd"], capture_output=True)
        subprocess.run(["systemctl", "restart", "nfs-kernel-server"], capture_output=True)
        subprocess.run(["exportfs", "-ra"], capture_output=True) # Zwingt NFS die exports neu zu lesen
    except Exception as e:
        print(f"Fehler beim Neustart der Dienste: {e}")

# --- WEB INTERFACE (Tailwind + JS) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <title>TinyShare</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        // JS Logik für dein IP-Feature: NFS macht die IP zum Pflichtfeld!
        function toggleIPRequirement() {
            const nfsCheckbox = document.getElementById('proto_nfs');
            const ipInput = document.getElementById('allowed_ips');
            const ipLabel = document.getElementById('ip_label');
            
            if (nfsCheckbox.checked) {
                ipInput.required = true;
                ipLabel.innerHTML = 'Zugelassene IPs / Subnetze <span class="text-red-500">* (Pflicht für NFS)</span>';
            } else {
                ipInput.required = false;
                ipLabel.innerHTML = 'Zugelassene IPs / Subnetze <span class="text-gray-400">(Optional)</span>';
            }
        }
    </script>
</head>
<body class="bg-gray-100 text-gray-800 font-sans p-8">
    <div class="max-w-5xl mx-auto bg-white rounded-xl shadow-lg overflow-hidden">
        
        <div class="bg-indigo-600 p-6 text-white flex justify-between items-center">
            <h1 class="text-2xl font-bold">📂 TinyShare (Share-Centric Edition)</h1>
            <span class="bg-indigo-800 px-3 py-1 rounded text-sm">Privileged LXC Ready</span>
        </div>

        <div class="p-6">
            <!-- Share Liste -->
            <h2 class="text-xl font-semibold border-b pb-2 mb-4">Aktive Freigaben</h2>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
                {% for share in db.shares %}
                <div class="bg-gray-50 border border-gray-200 rounded p-4 relative">
                    <form action="/delete/{{ share.id }}" method="POST" class="absolute top-4 right-4">
                        <button type="submit" class="text-red-500 hover:text-red-700 text-sm font-bold">X</button>
                    </form>
                    <h3 class="font-bold text-lg text-indigo-600">{{ share.name }}</h3>
                    <p class="text-sm font-mono text-gray-600 mb-2">{{ share.path }}</p>
                    
                    <div class="flex gap-2 mb-2">
                        {% if share.protocols.smb %}<span class="bg-blue-100 text-blue-800 text-xs px-2 py-1 rounded font-bold">SMB</span>{% endif %}
                        {% if share.protocols.nfs %}<span class="bg-orange-100 text-orange-800 text-xs px-2 py-1 rounded font-bold">NFS</span>{% endif %}
                    </div>
                    
                    <p class="text-xs text-gray-500">
                        <strong>IPs:</strong> {{ share.allowed_ips or 'Alle (Kein Filter)' }}<br>
                        <strong>RW User:</strong> {{ share.users_rw or '-' }} | 
                        <strong>RO User:</strong> {{ share.users_ro or '-' }}
                    </p>
                </div>
                {% else %}
                <p class="text-gray-500 italic">Noch keine Freigaben definiert.</p>
                {% endfor %}
            </div>

            <!-- Neue Freigabe anlegen -->
            <h2 class="text-xl font-semibold border-b pb-2 mb-4">Neue Freigabe erstellen</h2>
            <form action="/add" method="POST" class="bg-gray-50 p-6 rounded border border-gray-200">
                
                <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Share Name</label>
                        <input type="text" name="name" placeholder="z.B. Filme" required class="w-full border-gray-300 rounded p-2 border focus:ring-indigo-500 focus:border-indigo-500">
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Host-Pfad</label>
                        <input type="text" name="path" placeholder="z.B. /mnt/filme" required class="w-full border-gray-300 rounded p-2 border focus:ring-indigo-500 focus:border-indigo-500">
                    </div>
                </div>

                <div class="mb-6 p-4 bg-white border rounded">
                    <label class="block text-sm font-bold text-gray-700 mb-2">Aktive Protokolle</label>
                    <div class="flex gap-6">
                        <label class="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" name="proto_smb" value="1" checked class="w-5 h-5 text-indigo-600 rounded"> SMB (Samba)
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" name="proto_nfs" id="proto_nfs" value="1" onchange="toggleIPRequirement()" class="w-5 h-5 text-indigo-600 rounded"> NFS
                        </label>
                    </div>
                </div>

                <div class="mb-6">
                    <label id="ip_label" class="block text-sm font-medium text-gray-700 mb-1">
                        Zugelassene IPs / Subnetze <span class="text-gray-400">(Optional)</span>
                    </label>
                    <input type="text" name="allowed_ips" id="allowed_ips" placeholder="z.B. 192.168.1.0/24 oder 10.0.0.5" 
                           class="w-full border-gray-300 rounded p-2 border focus:ring-indigo-500 focus:border-indigo-500">
                    <p class="text-xs text-gray-500 mt-1">Gilt protokollübergreifend! Bei NFS ist diese Angabe Pflicht.</p>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Lese- & Schreib-Benutzer (RW)</label>
                        <input type="text" name="users_rw" placeholder="z.B. pm, admin" class="w-full border-gray-300 rounded p-2 border focus:ring-indigo-500 focus:border-indigo-500">
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Nur-Lese-Benutzer (RO)</label>
                        <input type="text" name="users_ro" placeholder="z.B. gast" class="w-full border-gray-300 rounded p-2 border focus:ring-indigo-500 focus:border-indigo-500">
                    </div>
                </div>

                <button type="submit" class="bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-3 px-6 rounded shadow-lg w-full md:w-auto">
                    💾 Share anlegen & Configs generieren
                </button>
            </form>
        </div>
    </div>
</body>
</html>
"""

@app.route("/")
def index():
    db = load_db()
    return render_template_string(HTML_TEMPLATE, db=db)

@app.route("/add", methods=["POST"])
def add_share():
    db = load_db()
    
    new_share = {
        "id": str(uuid.uuid4())[:8],
        "name": request.form.get("name"),
        "path": request.form.get("path"),
        "allowed_ips": request.form.get("allowed_ips", "").strip(),
        "protocols": {
            "smb": request.form.get("proto_smb") == "1",
            "nfs": request.form.get("proto_nfs") == "1"
        },
        "users_rw": request.form.get("users_rw", "").strip(),
        "users_ro": request.form.get("users_ro", "").strip()
    }
    
    db["shares"].append(new_share)
    save_db(db)
    
    # Nach jedem Speichern generieren wir die Configs neu und starten die Dienste!
    generate_configs()
    
    return redirect("/")

@app.route("/delete/<share_id>", methods=["POST"])
def delete_share(share_id):
    db = load_db()
    db["shares"] = [s for s in db["shares"] if s["id"] != share_id]
    save_db(db)
    
    # Configs neu generieren und Dienste neustarten
    generate_configs()
    
    return redirect("/")

if __name__ == "__main__":
    # Bei Start direkt einmal die Configs schreiben, um sicherzustellen, dass die Systemdienste synchron mit der DB sind.
    generate_configs()
    print(f"TinyShare läuft! Configs werden generiert in: {SMB_CONF_PATH} und {NFS_EXPORTS_PATH}")
    # Host 0.0.0.0 macht den Server im Netzwerk erreichbar
    app.run(host="0.0.0.0", port=8000, debug=True)
