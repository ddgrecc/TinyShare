from database import SessionLocal, Share, GlobalConfig
from system_ops import restart_samba, restart_nfs
import os
import subprocess

SMB_CONF_PATH = "/etc/samba/smb.conf"
NFS_EXPORTS_PATH = "/etc/exports"
NFS_DEFAULT_PATH = "/etc/default/nfs-kernel-server"

def update_nfs_daemon(threads, v4_only):
    """ Passt die Debian NFS Server Start-Parameter an """
    if not os.path.exists(NFS_DEFAULT_PATH):
        return
    
    opts = ""
    if v4_only == "yes":
        opts = "--no-nfs-version 2 --no-nfs-version 3 "
        
    # Schreibe die Datei per sed um (ersetzt RPCNFSDCOUNT und RPCNFSDOPTS)
    subprocess.run(["sed", "-i", f's/^RPCNFSDCOUNT=.*/RPCNFSDCOUNT={threads}/', NFS_DEFAULT_PATH])
    subprocess.run(["sed", "-i", f's/^RPCNFSDOPTS=.*/RPCNFSDOPTS="{opts}"/', NFS_DEFAULT_PATH])

def generate_and_apply_configs():
    db = SessionLocal()
    try:
        # Globale Konfigurationen laden
        conf = {c.key: c.value for c in db.query(GlobalConfig).all()}
        
        # --- SAMBA GLOBAL ---
        smb_out = "[global]\n"
        smb_out += f"   workgroup = {conf.get('smb_workgroup', 'WORKGROUP')}\n"
        smb_out += f"   server string = {conf.get('smb_server_string', 'TinyShare NAS')}\n"
        smb_out += f"   server min protocol = {conf.get('smb_min_protocol', 'SMB2')}\n"
        smb_out += f"   strict sync = {conf.get('smb_strict_sync', 'yes')}\n"
        smb_out += "   security = user\n"
        smb_out += "   map to guest = bad user\n"
        smb_out += "   deadtime = 15\n"
        
        if conf.get('smb_socket_opts', 'yes') == "yes":
            smb_out += "   socket options = TCP_NODELAY IPTOS_LOWDELAY SO_RCVBUF=65536 SO_SNDBUF=65536\n"
        
        smb_out += "\n"
        
        # --- NFS GLOBAL ---
        update_nfs_daemon(conf.get('nfs_threads', '8'), conf.get('nfs_v4_only', 'no'))
        nfs_out = "# Generiert von TinyShare\n"
        
        # --- SHARES ---
        shares = db.query(Share).all()
        for share in shares:
            if share.status != "Aktiv": continue
                
            if share.smb_enabled and share.smb_template:
                smb_out += f"[{share.name}]\n   path = {share.path}\n"
                if share.allowed_ips:
                    smb_out += f"   hosts allow = {share.allowed_ips} 127.0.0.1\n   hosts deny = ALL\n"
                
                db_link = db.execute("SELECT u.username, l.access_level FROM share_user_link l JOIN users u ON l.user_id = u.id WHERE l.share_id = :id", {"id": share.id}).fetchall()
                rw_users = [row[0] for row in db_link if row[1] == "rw"]
                ro_users = [row[0] for row in db_link if row[1] == "ro"]
                all_valid = rw_users + ro_users
                
                if all_valid: smb_out += f"   valid users = {', '.join(all_valid)}\n"
                if rw_users: smb_out += f"   write list = {', '.join(rw_users)}\n"
                
                for line in share.smb_template.content.split('\n'):
                    if line.strip(): smb_out += f"   {line.strip()}\n"
                smb_out += "\n"
                
            if share.nfs_enabled and share.nfs_template:
                ips = share.allowed_ips if share.allowed_ips else "*"
                nfs_out += f"{share.path} {ips}({share.nfs_template.content.strip()})\n"

        with open(SMB_CONF_PATH, "w") as f: f.write(smb_out)
        with open(NFS_EXPORTS_PATH, "w") as f: f.write(nfs_out)
        
        restart_samba()
        restart_nfs()
    finally:
        db.close()
