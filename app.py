from flask import Flask, Response, render_template_string, request, stream_with_context, jsonify
import subprocess, os, json, time

app = Flask(__name__)

REPO = os.path.expanduser("~/industrial-flow")
BUILD_SCRIPT = os.path.expanduser("~/godot-builder/build-godot.sh")
STATUS_FILE = '/tmp/godot-build-status.json'

def write_status(branch, state, line=''):
    with open(STATUS_FILE, 'w') as f:
        json.dump({'branch': branch, 'state': state, 'line': line, 'ts': time.time(), 'time': time.strftime('%H:%M:%S')}, f)

LOCK_FILE = '/tmp/godot-build.lock'

def read_status():
    try:
        with open(STATUS_FILE) as f:
            return json.load(f)
    except Exception as e:
        if not isinstance(e, FileNotFoundError):
            print(f'[warn] read_status failed: {e}')
        return None

HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Godot Builder</title>
    <style>
        body { font-family: monospace; background: #1e1e1e; color: #d4d4d4; padding: 30px; }
        h1 { color: #569cd6; }
        select, button, a.btn { padding: 10px 20px; font-size: 16px; border-radius: 6px; border: none; cursor: pointer; }
        select { background: #2d2d2d; color: #d4d4d4; margin-right: 10px; min-width: 420px; }
        #build-btn { background: #569cd6; color: white; }
        #build-btn:disabled { background: #555; cursor: not-allowed; }
        #refresh-btn { background: #3a3a3a; color: #d4d4d4; margin-right: 10px; }
        #refresh-btn:disabled { background: #555; cursor: not-allowed; }
        a.btn { text-decoration: none; display: inline-block; margin-left: 10px; }
        #open-btn { background: #4ec94e; color: white; }
        #open-btn.disabled { background: #2a5a2a; color: #888; pointer-events: none; cursor: not-allowed; }
        #log { margin-top: 20px; background: #0e0e0e; padding: 20px; border-radius: 8px; height: 400px; overflow-y: auto; white-space: pre-wrap; font-size: 13px; }
        .ok { color: #4ec94e; }
        .err { color: #f44747; }
        .hint { color: #888; font-size: 12px; margin-top: 8px; }
        #webhook-status { margin-top:15px; padding:10px; background:#0e0e0e; border-radius:6px; display:none; }
    </style>
</head>
<body>
    <h1>🎮 Godot Builder</h1>
    <div>
        <button id="refresh-btn" onclick="refreshBranches()">↻ Update</button>
        <select id="branch"></select>
        <button id="build-btn" onclick="startBuild()">▶ Build</button>
        <a id="open-btn" class="btn disabled" href="https://godot.home.local" target="_blank">🌐 Open Game</a>
    </div>
    <div class="hint" id="hint"></div>
    <div id="webhook-status">
        <span style="color:#888">Webhook билд: </span>
        <span id="ws-branch" style="color:#569cd6"></span>
        <span id="ws-state"></span>
        <div id="ws-line" style="color:#888; font-size:12px; margin-top:4px;"></div>
        <div id="ws-time" style="color:#569cd6; font-size:12px; margin-top:2px;"></div>
    </div>
    <div id="log"></div>

    <script>
        function setOpenBtn(enabled) {
            const btn = document.getElementById('open-btn');
            if (enabled) btn.classList.remove('disabled');
            else btn.classList.add('disabled');
        }

        function loadBranches() {
            return fetch('/branches').then(r => r.json()).then(data => {
                const select = document.getElementById('branch');
                const current = select.value;
                select.innerHTML = '';
                data.forEach(b => {
                    const opt = document.createElement('option');
                    opt.value = b.name;
                    opt.textContent = b.name + '  —  ' + b.date;
                    if (b.name === current) opt.selected = true;
                    select.appendChild(opt);
                });
            });
        }

        function refreshBranches() {
            const btn = document.getElementById('refresh-btn');
            const hint = document.getElementById('hint');
            btn.disabled = true;
            btn.textContent = '↻ Updating...';
            fetch('/branches?fetch=1').then(r => r.json()).then(data => {
                const select = document.getElementById('branch');
                const current = select.value;
                select.innerHTML = '';
                data.forEach(b => {
                    const opt = document.createElement('option');
                    opt.value = b.name;
                    opt.textContent = b.name + '  —  ' + b.date;
                    if (b.name === current) opt.selected = true;
                    select.appendChild(opt);
                });
                hint.textContent = 'Updated: ' + new Date().toLocaleTimeString();
                btn.disabled = false;
                btn.textContent = '↻ Update';
            });
        }

        function startBuild() {
            const branch = document.getElementById('branch').value;
            const btn = document.getElementById('build-btn');
            const log = document.getElementById('log');

            btn.disabled = true;
            setOpenBtn(false);
            log.innerHTML = '';

            const es = new EventSource('/build?branch=' + encodeURIComponent(branch));
            es.onmessage = function(e) {
                const data = JSON.parse(e.data);
                const line = document.createElement('div');
                line.textContent = data.line;
                if (data.line.includes('Done') || data.line.includes('===')) line.className = 'ok';
                if (data.line.includes('error') || data.line.includes('Error')) line.className = 'err';
                log.appendChild(line);
                log.scrollTop = log.scrollHeight;

                if (data.done) {
                    es.close();
                    btn.disabled = false;
                    if (data.success) setOpenBtn(true);
                }
            };
        }

        // Webhook status stream
        const statusEs = new EventSource('/status');
        statusEs.onmessage = function(e) {
            const d = JSON.parse(e.data);
            const box = document.getElementById('webhook-status');
            box.style.display = 'block';
            document.getElementById('ws-branch').textContent = d.branch + ' ';
            const stateEl = document.getElementById('ws-state');
            const buildBtn = document.getElementById('build-btn');
            const currentBranch = document.getElementById('branch').value;
            if (d.state === 'building') {
                stateEl.style.color = '#d4d4d4';
                buildBtn.disabled = true;
            } else if (d.state === 'success') {
                stateEl.style.color = '#4ec94e';
                if (d.branch === currentBranch) setOpenBtn(true);
                buildBtn.disabled = false;
            } else {
                stateEl.style.color = '#f44747';
                buildBtn.disabled = false;
            }
            stateEl.textContent = '[' + d.state + ']';
            document.getElementById('ws-line').textContent = d.line;
            document.getElementById('ws-time').textContent = d.time ? '🕐 ' + d.time : '';
        };

        // On load: check last build status and load branches
        fetch('/last-status').then(r => r.json()).then(d => {
            if (d && d.state === 'success') setOpenBtn(true);
            if (d && d.state === 'building') document.getElementById('build-btn').disabled = true;
        });
        loadBranches();
    </script>
</body>
</html>
"""

def get_branches(do_fetch=False):
    if do_fetch:
        subprocess.run(
            ['git', '-C', REPO, 'fetch', '--prune', 'origin'],
            capture_output=True,
            env={**os.environ, 'GIT_SSH_COMMAND': 'ssh -i /home/hpserver/.ssh/github_deploy -o StrictHostKeyChecking=no'}
        )
    result = subprocess.run(
        ['git', '-C', REPO, 'for-each-ref', '--sort=-committerdate',
         '--format=%(refname:short) %(committerdate:format:%Y-%m-%d %H:%M)',
         'refs/remotes/origin/'],
        capture_output=True, text=True
    )
    branches = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(' ', 1)
        if len(parts) == 2:
            name = parts[0].replace('origin/', '')
            date = parts[1]
            if '->' not in name:
                branches.append({'name': name, 'date': date})
    return branches

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/branches')
def branches():
    do_fetch = request.args.get('fetch') == '1'
    return jsonify(get_branches(do_fetch))

@app.route('/last-status')
def last_status():
    return jsonify(read_status())

@app.route('/status')
def status_stream():
    def generate():
        last_ts = 0
        try:
            while True:
                try:
                    data = read_status()
                    if data and data['ts'] != last_ts:
                        last_ts = data['ts']
                        yield f"data: {json.dumps(data)}\n\n"
                except Exception as e:
                    print(f'[warn] status_stream error: {e}')
                time.sleep(0.5)
        except GeneratorExit:
            pass
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/build')
def build():
    branch = request.args.get('branch', 'main')

    def generate():
        if os.path.exists(LOCK_FILE):
            yield f"data: {json.dumps({'line': '=== Build already in progress, try again later ===', 'done': True, 'success': False})}\n\n"
            return
        write_status(branch, 'building', f'Starting build for {branch}...')
        proc = subprocess.Popen(
            ['bash', BUILD_SCRIPT, branch],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1
        )
        for line in proc.stdout:
            line = line.rstrip()
            write_status(branch, 'building', line)
            yield f"data: {json.dumps({'line': line, 'done': False})}\n\n"
        proc.wait()
        success = proc.returncode == 0
        state = 'success' if success else 'failed'
        msg = '=== Build successful! ===' if success else '=== Build FAILED ==='
        write_status(branch, state, msg)
        yield f"data: {json.dumps({'line': msg, 'done': True, 'success': success})}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=7777)
