from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, Table, Text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
import os

DATABASE_URL = "sqlite:////opt/tinyshare/tinyshare.db"
os.makedirs("/opt/tinyshare", exist_ok=True)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

share_user_link = Table(
    'share_user_link', Base.metadata,
    Column('share_id', Integer, ForeignKey('shares.id', ondelete="CASCADE"), primary_key=True),
    Column('user_id', Integer, ForeignKey('users.id', ondelete="CASCADE"), primary_key=True),
    Column('access_level', String)
)

# NEU: Die Vorlagen-Tabelle
class ConfigTemplate(Base):
    __tablename__ = "config_templates"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    protocol = Column(String) # "smb" oder "nfs"
    content = Column(Text) # Die tatsächlichen Raw-Konfigurationen
    is_system_default = Column(Boolean, default=False) # Verhindert Löschung

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    is_active = Column(Boolean, default=True)
    groups = Column(String, default="")

class Share(Base):
    __tablename__ = "shares"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    path = Column(String)
    allowed_ips = Column(String, default="")
    status = Column(String, default="Aktiv")
    
    # SMB Setup
    smb_enabled = Column(Boolean, default=True)
    smb_template_id = Column(Integer, ForeignKey("config_templates.id", ondelete="SET NULL"), nullable=True)
    
    # NFS Setup
    nfs_enabled = Column(Boolean, default=False)
    nfs_template_id = Column(Integer, ForeignKey("config_templates.id", ondelete="SET NULL"), nullable=True)
    
    users = relationship("User", secondary=share_user_link, backref="shares")
    smb_template = relationship("ConfigTemplate", foreign_keys=[smb_template_id])
    nfs_template = relationship("ConfigTemplate", foreign_keys=[nfs_template_id])

class GlobalConfig(Base):
    __tablename__ = "global_config"
    key = Column(String, primary_key=True, index=True)
    value = Column(String)

# Update die init_db() Funktion:
def init_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    
    # Templates (wie bisher)
    if db.query(ConfigTemplate).count() == 0:
        db.add_all([
            ConfigTemplate(name="Samba Default", protocol="smb", is_system_default=True, content="read only = no\nguest ok = no\nbrowseable = yes"),
            ConfigTemplate(name="NFS Default", protocol="nfs", is_system_default=True, content="rw,sync,no_subtree_check,no_root_squash")
        ])
        
    # Global Config Defaults
    if db.query(GlobalConfig).count() == 0:
        db.add_all([
            GlobalConfig(key="smb_workgroup", value="WORKGROUP"),
            GlobalConfig(key="smb_server_string", value="TinyShare NAS"),
            GlobalConfig(key="smb_min_protocol", value="SMB2"),
            GlobalConfig(key="smb_strict_sync", value="yes"),
            GlobalConfig(key="smb_socket_opts", value="yes"),
            GlobalConfig(key="nfs_v4_only", value="no"),
            GlobalConfig(key="nfs_threads", value="8")
        ])
        
    db.commit()
    db.close()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
