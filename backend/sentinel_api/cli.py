"""Bootstrap and recovery commands for the local administrator."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import time

from .database import Database
from .security import set_password


def provision(directory, username="admin", password_file=None, reset=False):
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", username):
        raise ValueError("用户名只允许字母、数字、下划线、点和连字符")
    database = Database(Path(directory))
    with database.connect(write=True) as db:
        if Database.get(db, "password") and not reset:
            return {"created": False, "username": Database.get(db, "username", "admin")}
        password = secrets.token_urlsafe(20)
        if password_file:
            path = Path(password_file)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as file:
                file.write(password)
        set_password(db, password, must_change=True)
        Database.set(db, "username", username)
        db.execute("DELETE FROM sessions")
        db.execute("INSERT INTO events(created,kind,message) VALUES (?,?,?)", (time.time(), "admin.reset" if reset else "admin.created", "管理员初始凭证已生成，首次登录需修改密码"))
    return {"created": True, "username": username, **({} if password_file else {"initial_password": password})}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["bootstrap", "reset-password"])
    parser.add_argument("--data", default=os.getenv("SENTINEL_DATA", "./runtime/master"))
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password-file")
    args = parser.parse_args()
    print(json.dumps(provision(args.data, args.username, args.password_file, args.command == "reset-password"), ensure_ascii=False))


if __name__ == "__main__":
    main()
