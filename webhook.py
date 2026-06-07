from flask import Flask, request, abort
import subprocess, os, hmac, hashlib, json, time

app = Flask(__name__)

SECRET = os.environ.get('WEBHOOK_SECRET', '')
BUILD_SCRIPT = os.path.expanduser('~/build-godot.sh')
STATUS_FILE = '/tmp/godot-build-status.json'

def write_status(branch, state, line=''):
    with open(STATUS_FILE, 'w') as f:
        json.dump({'branch': branch, 'state': state, 'line': line, 'ts': time.time(), 'time': time.strftime('%H:%M:%S')}, f)

def run_build(branch):
    write_status(branch, 'building', f'Starting build for {branch}...')
    proc = subprocess.Popen(
        ['bash', BUILD_SCRIPT, branch],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
    )
    for line in proc.stdout:
        write_status(branch, 'building', line.rstrip())
    proc.wait()
    if proc.returncode == 0:
        write_status(branch, 'success', '=== Build successful! ===')
    else:
        write_status(branch, 'failed', '=== Build FAILED ===')

@app.route('/webhook', methods=['POST'])
def webhook():
    sig = request.headers.get('X-Hub-Signature-256', '')
    body = request.get_data()

    if SECRET:
        expected = 'sha256=' + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            abort(403)

    data = request.json
    if not data:
        abort(400)

    ref = data.get('ref', '')
    branch = ref.replace('refs/heads/', '')

    if not branch:
        return 'ok', 200

    import threading
    threading.Thread(target=run_build, args=(branch,), daemon=True).start()
    return f'Building {branch}', 200

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=7778)
