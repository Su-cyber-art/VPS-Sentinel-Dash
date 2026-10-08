"""Isolated browser-test backend and a real local Agent; never used by production."""
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend')); sys.path.insert(0,str(ROOT))
import uvicorn
from sentinel_api.config import Config
from sentinel_api.cli import provision
from sentinel_api.database import Database
from sentinel_api.security import set_password
from sentinel_api.main import create_app
from sentinel_api.service import ControlPlane
from agent.sentinel_agent import Agent, atomic_json

with tempfile.TemporaryDirectory(prefix='sentinel-e2e-') as temp:
    directory=Path(temp)
    provision(directory/'master')
    config=Config(data_dir=directory/'master',maintenance=False)
    control=ControlPlane(config)
    with control.database.connect(write=True) as db:
        set_password(db,'Initial-e2e-password-2026',must_change=True)
    issued=control.enrollment('Browser test node')
    node=control.register_agent(issued['token'])
    atomic_json(directory/'agent.json',dict(node,master='http://127.0.0.1:19091',root=str(directory/'modules')))
    def run_agent():
        agent=Agent(directory/'agent.json')
        while True:
            try: agent.tick()
            except Exception: pass
            time.sleep(0.5)
    threading.Thread(target=run_agent,daemon=True).start()
    uvicorn.run(create_app(config),host='127.0.0.1',port=19091,log_level='warning',proxy_headers=False)
