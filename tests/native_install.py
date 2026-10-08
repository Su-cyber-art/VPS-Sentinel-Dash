"""Runs on disposable Ubuntu CI VMs, exercises the real interactive/systemd installer."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

import httpx
import pexpect

ROOT = Path(__file__).resolve().parents[1]
PREFIX = Path('/opt/vps-sentinel-ci')
AGENT_PREFIX = Path('/opt/vps-sentinel-agent-ci')
URL = 'http://127.0.0.1:19080'
changed_password = 'CI-changed-password-2026'


def install(arguments, interactive=False, password=False):
    child = pexpect.spawn('/bin/bash', [str(ROOT/'install.sh'), *arguments], encoding='utf-8', timeout=900,
                          env=dict(os.environ, NO_COLOR='1'), maxread=65536)
    if interactive:
        child.expect('管理员用户名'); child.sendline('admin')
        child.expect('外部访问地址'); child.sendline('')
    initial = None
    if password:
        child.expect(r'初始密码：([^\r\n]+)')
        initial = child.match.group(1).strip()
    child.expect(pexpect.EOF)
    remaining = child.before
    child.close()
    if child.exitstatus != 0:
        raise AssertionError('Installer failed: ' + remaining[-6000:])
    return initial, remaining


def wait_for(fn, seconds=60):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = fn()
        if result: return result
        time.sleep(0.5)
    raise AssertionError('Timed out waiting for expected service state')


def main():
    assert os.geteuid() == 0 and sys.platform == 'linux'
    initial, _ = install(['--role','panel','--source',str(ROOT),'--prefix',str(PREFIX),
                          '--bind','127.0.0.1','--port','19080','--api-port','19081'], interactive=True, password=True)
    print('PASS: interactive installation printed a generated password after both services became healthy', flush=True)
    with httpx.Client(base_url=URL, trust_env=False, timeout=30) as client:
        def request(method, path, data=None, expected=200):
            response = client.request(method, path, json=data if method != 'GET' else None)
            assert response.status_code == expected, (path,response.status_code,response.text[:500])
            return response.json()
        login = request('POST','/api/auth/login',{'username':'admin','password':initial})
        assert login['must_change_password']
        client.headers['X-CSRF-Token'] = login['csrf']
        assert client.get('/api/overview').status_code == 403
        changed = request('POST','/api/auth/password',{'current_password':initial,'new_password':changed_password})
        client.headers['X-CSRF-Token'] = changed['csrf']
        assert not changed['must_change_password']
        request('GET','/api/overview')
        assert client.post('/api/auth/login',json={'username':'admin','password':initial}).status_code == 401
        print('PASS: initial-password gate enforced; password change unlocked control plane and invalidated initial password', flush=True)
        token = request('POST','/api/enrollments',{'name':'Linux CI sentinel'},201)['token']
        with tempfile.NamedTemporaryFile(mode='w',delete=False) as file:
            file.write(token); token_file=file.name
        try:
            install(['--role','agent','--prefix',str(AGENT_PREFIX),'--master',URL,'--token-file',token_file,'--yes'])
        finally: Path(token_file).unlink(missing_ok=True)
        nodes = wait_for(lambda: [n for n in request('GET','/api/overview')['nodes'] if n['online']])
        node = nodes[0]
        assert set(('snapshot','network','quality','google','trust','patrol','logs','update_data')) <= set(node['capabilities'])
        print('PASS: Agent installed modules, enrolled over remote-capable HTTP, and completed its first heartbeat', flush=True)

        # Run original Sentinel shell modules with deterministic HTTP fixtures. No third-party traffic.
        module_root = AGENT_PREFIX/'state/modules'
        fixtures = AGENT_PREFIX/'state/test-bin'; fixtures.mkdir()
        curl_fixture = fixtures/'curl'
        curl_fixture.write_text('''#!/usr/bin/env python3
import sys
args=sys.argv[1:]
if '-w' in args: print('200',end='')
elif any('youtube.com' in x for x in args): print('{"INNERTUBE_CONTEXT_GL":"US"}')
elif any('http://www.google.com/' in x for x in args): print('Location: https://www.google.com/?gl=US')
''')
        (fixtures/'sleep').write_text('#!/bin/sh\nexit 0\n')
        curl_fixture.chmod(0o755); (fixtures/'sleep').chmod(0o755)
        quality = module_root/'core/ip_probe.sh'
        quality.write_text('#!/bin/bash\n# xykt deterministic CI fixture\nprintf \'{"Head":{"IP":"203.0.113.10"},"Info":{"Region":{"Name":"Test fixture"}},"Score":{"SCAMALYTICS":null}}\\n\'\n')
        quality.chmod(0o755)
        dropin = Path('/etc/systemd/system/vps-sentinel-agent.service.d')
        dropin.mkdir(exist_ok=True)
        (dropin/'ci.conf').write_text(f'''[Service]
Environment="PATH={fixtures}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=
ExecStart=/usr/bin/python3 {AGENT_PREFIX}/current/sentinel_agent.py --config {AGENT_PREFIX}/state/agent.json --interval 0.5
''')
        subprocess.run(['systemctl','daemon-reload'],check=True)
        subprocess.run(['systemctl','restart','vps-sentinel-agent'],check=True)
        policy = node['policy'] | {'google':True,'trust':True}
        request('PATCH','/api/nodes/'+node['id'],{'name':node['name'],'region':'CI fixture','group_name':'CI','policy':policy})
        def run(action):
            task_id=request('POST','/api/nodes/'+node['id']+'/jobs',{'action':action},202)['id']
            result=wait_for(lambda: (value if (value:=request('GET','/api/jobs/'+task_id))['status'] not in ('queued','running') else None))
            assert result['status']=='succeeded',result
            return result
        for action in ('snapshot','google','trust','quality','patrol','logs','update_data'):
            result=run(action)
            if action=='quality': assert result['result']['report']['Head']['IP']=='203.0.113.10'
            print('PASS: browser API -> real Agent -> '+action+' -> persisted result (external HTTP fixture)',flush=True)
        quality.write_text('#!/bin/bash\n# xykt long-running cancellation fixture\npython3 -c "import time; time.sleep(120)"\n')
        task_id=request('POST','/api/nodes/'+node['id']+'/jobs',{'action':'quality'},202)['id']
        wait_for(lambda: request('GET','/api/jobs/'+task_id)['status']=='running')
        request('POST','/api/jobs/'+task_id+'/cancel',{})
        wait_for(lambda: request('GET','/api/jobs/'+task_id)['status']=='cancelled')
        print('PASS: cancellation reached the Agent and terminated a running sentinel subprocess',flush=True)

        # Restore the default service definition before testing upgrade persistence.
        (dropin/'ci.conf').unlink(); dropin.rmdir()
        subprocess.run(['systemctl','daemon-reload'],check=True)
        credential=(AGENT_PREFIX/'state/agent.json').read_bytes()
        _, upgrade_output=install(['--role','panel','--action','upgrade','--source',str(ROOT),'--prefix',str(PREFIX),'--yes'])
        assert '初始密码：' not in upgrade_output
        assert request('GET','/api/overview')['nodes'][0]['id']==node['id']
        session=request('POST','/api/auth/login',{'username':'admin','password':changed_password})
        assert not session['must_change_password']; client.headers['X-CSRF-Token']=session['csrf']
        install(['--role','agent','--action','upgrade','--prefix',str(AGENT_PREFIX),'--yes'])
        assert (AGENT_PREFIX/'state/agent.json').read_bytes()==credential
        print('PASS: panel and Agent upgrades preserved credentials, node identity, and task history',flush=True)
        reset, _=install(['--role','panel','--action','reset-password','--prefix',str(PREFIX),'--yes'],password=True)
        assert client.get('/api/overview').status_code==401
        session=request('POST','/api/auth/login',{'username':'admin','password':reset})
        assert session['must_change_password']
        print('PASS: password recovery generated a new initial password and restored mandatory rotation',flush=True)
    install(['--role','agent','--action','uninstall','--prefix',str(AGENT_PREFIX),'--yes'])
    install(['--role','panel','--action','uninstall','--prefix',str(PREFIX),'--yes'])
    assert (PREFIX/'state/sentinel.sqlite3').exists() and (AGENT_PREFIX/'state/agent.json').exists()
    print('PASS: uninstall stopped services and preserved operator data',flush=True)


if __name__=='__main__':
    main()
