"""
User Manager Module
Handles users, groups, passwords, and permissions for PyOS.
Persists data to ~/.pyos/users.json
Thread-safe singleton.
"""

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

CONFIG_DIR  = os.path.expanduser("~/.pyos")
USERS_FILE  = os.path.join(CONFIG_DIR, "users.json")

ROOT_UID    = 0
START_UID   = 1000
START_GID   = 1000


def _hash_pw(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


@dataclass
class PyUser:
    uid:           int
    username:      str
    password_hash: str
    groups:        List[str]   = field(default_factory=list)
    home_dir:      str         = ""
    shell:         str         = "/bin/bash"
    is_admin:      bool        = False
    created_at:    float       = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PyUser":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class PyGroup:
    gid:      int
    groupname: str
    members:  List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PyGroup":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class UserManager:
    """Thread-safe user and group store for PyOS."""

    def __init__(self):
        self._lock   = threading.Lock()
        self._users: Dict[str, PyUser]   = {}
        self._groups: Dict[str, PyGroup] = {}
        self._load()
        self._seed_defaults()

    # ── Persistence ───────────────────────────────────────────────

    def _load(self):
        try:
            if os.path.isfile(USERS_FILE):
                with open(USERS_FILE, "r") as f:
                    data = json.load(f)
                for u in data.get("users", []):
                    obj = PyUser.from_dict(u)
                    self._users[obj.username] = obj
                for g in data.get("groups", []):
                    obj = PyGroup.from_dict(g)
                    self._groups[obj.groupname] = obj
        except Exception:
            pass

    def save(self):
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with self._lock:
                data = {
                    "users":  [u.to_dict() for u in self._users.values()],
                    "groups": [g.to_dict() for g in self._groups.values()],
                }
            with open(USERS_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _seed_defaults(self):
        changed = False
        if "root" not in self._users:
            root = PyUser(uid=0, username="root", password_hash=_hash_pw("root"),
                          groups=["root", "sudo"], home_dir="/root",
                          shell="/bin/bash", is_admin=True)
            self._users["root"] = root
            changed = True
        if "root" not in self._groups:
            self._groups["root"]  = PyGroup(gid=0,    groupname="root",  members=["root"])
            changed = True
        if "sudo" not in self._groups:
            self._groups["sudo"]  = PyGroup(gid=27,   groupname="sudo",  members=["root"])
            changed = True
        if "users" not in self._groups:
            self._groups["users"] = PyGroup(gid=100,  groupname="users", members=[])
            changed = True
        if changed:
            self.save()

    # ── Auth ──────────────────────────────────────────────────────

    def authenticate(self, username: str, password: str) -> Optional[PyUser]:
        with self._lock:
            user = self._users.get(username)
        if user and user.password_hash == _hash_pw(password):
            return user
        return None

    # ── User CRUD ─────────────────────────────────────────────────

    def create_user(self, username: str, password: str,
                    groups: Optional[List[str]] = None,
                    shell: str = "/bin/bash",
                    is_admin: bool = False) -> tuple[bool, str]:
        with self._lock:
            if username in self._users:
                return False, f"useradd: user '{username}' already exists"
            if not username or not username.replace("-", "").replace("_", "").isalnum():
                return False, "useradd: invalid username"
            uid = max((u.uid for u in self._users.values()), default=START_UID - 1) + 1
            home = f"/home/{username}"
            grps = list(groups or [])
            if "users" not in grps:
                grps.append("users")
            user = PyUser(uid=uid, username=username,
                          password_hash=_hash_pw(password),
                          groups=grps, home_dir=home,
                          shell=shell, is_admin=is_admin)
            self._users[username] = user
            # add to each group
            for gname in grps:
                if gname in self._groups:
                    if username not in self._groups[gname].members:
                        self._groups[gname].members.append(username)
                else:
                    gid = max((g.gid for g in self._groups.values()), default=START_GID - 1) + 1
                    self._groups[gname] = PyGroup(gid=gid, groupname=gname, members=[username])
        self.save()
        return True, f"User '{username}' created (uid={uid})"

    def delete_user(self, username: str, actor: str = "") -> tuple[bool, str]:
        if username == "root":
            return False, "userdel: cannot delete root"
        with self._lock:
            if username not in self._users:
                return False, f"userdel: user '{username}' does not exist"
            del self._users[username]
            for g in self._groups.values():
                if username in g.members:
                    g.members.remove(username)
        self.save()
        return True, f"User '{username}' deleted"

    def change_password(self, username: str, new_password: str,
                        actor: str = "") -> tuple[bool, str]:
        with self._lock:
            if username not in self._users:
                return False, f"passwd: user '{username}' not found"
            self._users[username].password_hash = _hash_pw(new_password)
        self.save()
        return True, f"Password for '{username}' updated"

    def modify_user(self, username: str,
                    add_groups: Optional[List[str]] = None,
                    remove_groups: Optional[List[str]] = None,
                    new_shell: Optional[str] = None,
                    new_admin: Optional[bool] = None) -> tuple[bool, str]:
        with self._lock:
            if username not in self._users:
                return False, f"usermod: user '{username}' not found"
            user = self._users[username]
            if new_shell:
                user.shell = new_shell
            if new_admin is not None:
                user.is_admin = new_admin
            if add_groups:
                for g in add_groups:
                    if g not in user.groups:
                        user.groups.append(g)
                    if g in self._groups and username not in self._groups[g].members:
                        self._groups[g].members.append(username)
                    elif g not in self._groups:
                        gid = max((gr.gid for gr in self._groups.values()), default=START_GID - 1) + 1
                        self._groups[g] = PyGroup(gid=gid, groupname=g, members=[username])
            if remove_groups:
                for g in remove_groups:
                    if g in user.groups:
                        user.groups.remove(g)
                    if g in self._groups and username in self._groups[g].members:
                        self._groups[g].members.remove(username)
        self.save()
        return True, f"User '{username}' modified"

    # ── Group CRUD ────────────────────────────────────────────────

    def create_group(self, groupname: str) -> tuple[bool, str]:
        with self._lock:
            if groupname in self._groups:
                return False, f"groupadd: group '{groupname}' already exists"
            if not groupname or not groupname.replace("-", "").replace("_", "").isalnum():
                return False, "groupadd: invalid group name"
            gid = max((g.gid for g in self._groups.values()), default=START_GID - 1) + 1
            self._groups[groupname] = PyGroup(gid=gid, groupname=groupname, members=[])
        self.save()
        return True, f"Group '{groupname}' created (gid={gid})"

    def delete_group(self, groupname: str) -> tuple[bool, str]:
        if groupname in ("root", "sudo", "users"):
            return False, f"groupdel: cannot delete system group '{groupname}'"
        with self._lock:
            if groupname not in self._groups:
                return False, f"groupdel: group '{groupname}' does not exist"
            del self._groups[groupname]
            for u in self._users.values():
                if groupname in u.groups:
                    u.groups.remove(groupname)
        self.save()
        return True, f"Group '{groupname}' deleted"

    # ── Queries ───────────────────────────────────────────────────

    def get_user(self, username: str) -> Optional[PyUser]:
        with self._lock:
            return self._users.get(username)

    def get_group(self, groupname: str) -> Optional[PyGroup]:
        with self._lock:
            return self._groups.get(groupname)

    def list_users(self) -> List[PyUser]:
        with self._lock:
            return list(self._users.values())

    def list_groups(self) -> List[PyGroup]:
        with self._lock:
            return list(self._groups.values())

    def user_groups(self, username: str) -> List[str]:
        with self._lock:
            user = self._users.get(username)
            return list(user.groups) if user else []

    def is_admin(self, username: str) -> bool:
        with self._lock:
            user = self._users.get(username)
            if not user:
                return False
            return user.is_admin or "sudo" in user.groups or username == "root"


# ── Singleton ─────────────────────────────────────────────────────────────

_instance: Optional[UserManager] = None


def get_user_manager() -> UserManager:
    global _instance
    if _instance is None:
        _instance = UserManager()
    return _instance
