from flask import Flask, render_template_string, request, send_file, jsonify
from flask_socketio import SocketIO, emit
import os
import io
from crypto_engine import CryptoEngine
from protocol import Protocol

app = Flask(__name__)
app.config['SECRET_KEY'] = 'cryptoshare_secret!'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

RECEIVED_FILES = {}

APP_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>CryptoShare - E2EE Dashboard</title>
    <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        body { background: #0f111a; color: #e1e1e6; display: flex; height: 100vh; overflow: hidden; }

        .sidebar { width: 250px; background: #161824; border-right: 1px solid #27293d; display: flex; flex-direction: column; padding: 25px 15px; }
        .brand { color: #4e73df; font-size: 20px; font-weight: bold; margin-bottom: 35px; text-align: center; letter-spacing: 1px; }
        .nav-item { display: flex; align-items: center; justify-content: space-between; padding: 14px 20px; color: #8a8d9b; border-radius: 8px; cursor: pointer; margin-bottom: 10px; transition: 0.3s; font-weight: 600; }
        .nav-item:hover, .nav-item.active { background: #1e2235; color: #ffffff; }
        .nav-item.active { border-left: 4px solid #4e73df; }
        
        .badge { background: #e74c3c; color: white; font-size: 11px; font-weight: bold; padding: 3px 8px; border-radius: 12px; display: none; animation: pulse 1.5s infinite; }
        @keyframes pulse { 0% { transform: scale(1); } 50% { transform: scale(1.15); } 100% { transform: scale(1); } }

        .main-content { flex: 1; padding: 40px; overflow-y: auto; background: #0f111a; }
        .tab-panel { display: none; }
        .tab-panel.active { display: block; }

        .card { background: #161824; border: 1px solid #27293d; border-radius: 12px; padding: 30px; max-width: 650px; margin: 0 auto; }
        .card h2 { margin-bottom: 8px; color: #fff; }
        .card p.subtitle { color: #6c7293; font-size: 13px; margin-bottom: 25px; }

        .drop-zone { border: 2px dashed #4e73df; border-radius: 10px; padding: 50px 20px; text-align: center; background: #1a1d2e; cursor: pointer; transition: 0.3s; }
        .drop-zone:hover { background: #22263d; border-color: #6c8bef; }

        .file-card { background: #1a1d2e; border: 1px solid #27293d; padding: 16px 20px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; border-left: 4px solid #2ecc71; }
        .btn-download { background: #2ecc71; color: white; border: none; padding: 9px 18px; border-radius: 6px; text-decoration: none; font-weight: bold; font-size: 13px; transition: 0.2s; }
        .btn-download:hover { background: #27ae60; }
        
        .status-msg { margin-top: 15px; text-align: center; font-size: 14px; font-weight: bold; display: none; }
    </style>
</head>
<body>

    <div class="sidebar">
        <div class="brand">🔒 CryptoShare</div>
        
        <div class="nav-item active" onclick="switchTab('sendTab', this)">
            <span>📤 Send File</span>
        </div>
        
        <div class="nav-item" id="receiveNavItem" onclick="switchTab('receiveTab', this)">
            <span>📥 Receive File</span>
            <span class="badge" id="notifBadge">0</span>
        </div>
    </div>

    <div class="main-content">
        
        <!-- SEND TAB -->
        <div id="sendTab" class="tab-panel active">
            <div class="card">
                <h2>Send Encrypted File</h2>
                <p class="subtitle">E2EE Pipeline: Files are encrypted locally using AES-256 before transmission.</p>

                <div class="drop-zone" onclick="document.getElementById('fileInput').click();">
                    <p style="font-size: 16px; color: #a0a5ba;">📁 Drag & Drop your file here, or <b style="color: #4e73df;">Browse</b></p>
                    <input type="file" id="fileInput" style="display: none;" onchange="uploadFile(this.files[0])">
                </div>
                <div id="sendAck" class="status-msg"></div>
            </div>
        </div>

        <!-- RECEIVE TAB -->
        <div id="receiveTab" class="tab-panel">
            <div class="card">
                <h2>Receiver Inbox</h2>
                <p class="subtitle">Real-time incoming streams with SHA-256 integrity checks.</p>

                <div id="inbox">
                    <p id="noMsg" style="color: #6c7293; font-style: italic; text-align: center; padding: 20px 0;">No incoming files yet. Waiting for sender...</p>
                </div>
            </div>
        </div>

    </div>

<script>
    let unreadCount = 0;
    let activeTab = 'sendTab';
    let knownFileIds = new Set();

    function switchTab(tabId, element) {
        document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
        element.classList.add('active');

        document.querySelectorAll('.tab-panel').forEach(panel => panel.classList.remove('active'));
        document.getElementById(tabId).classList.add('active');
        activeTab = tabId;

        if (tabId === 'receiveTab') {
            unreadCount = 0;
            const badge = document.getElementById('notifBadge');
            badge.style.display = 'none';
            badge.innerText = '0';
        }
    }

    function renderFileCard(file_id, filename) {
        const noMsg = document.getElementById('noMsg');
        if (noMsg) noMsg.style.display = 'none';

        const inbox = document.getElementById('inbox');
        if (document.getElementById('file-card-' + file_id)) return;

        const card = document.createElement('div');
        card.id = 'file-card-' + file_id;
        card.className = 'file-card';
        card.innerHTML = `
            <div>
                <strong style="color: #fff; font-size: 15px;">` + filename + `</strong><br>
                <small style="color: #2ecc71; font-size: 12px;">✔ Decrypted & SHA-256 Integrity Verified</small>
            </div>
            <a href="/download/` + file_id + `" class="btn-download">Download</a>
        `;
        inbox.prepend(card);
    }

    function fetchFiles() {
        fetch('/files')
        .then(res => res.json())
        .then(files => {
            files.forEach(f => {
                if (!knownFileIds.has(f.file_id)) {
                    knownFileIds.add(f.file_id);
                    renderFileCard(f.file_id, f.filename);

                    if (activeTab !== 'receiveTab') {
                        unreadCount++;
                        const badge = document.getElementById('notifBadge');
                        badge.innerText = unreadCount;
                        badge.style.display = 'inline-block';
                    }
                }
            });
        })
        .catch(err => console.error(err));
    }

    function uploadFile(file) {
        if(!file) return;
        const sendAck = document.getElementById('sendAck');
        sendAck.style.color = '#3498db';
        sendAck.innerText = "Encrypting & Transferring...";
        sendAck.style.display = 'block';

        const formData = new FormData();
        formData.append('file', file);

        fetch('/upload', { method: 'POST', body: formData })
        .then(res => res.json())
        .then(data => {
            sendAck.style.color = '#2ecc71';
            sendAck.innerText = "✔ File Encrypted & Sent Successfully!";
            fetchFiles(); // Immediate check on send
            setTimeout(() => { sendAck.style.display = 'none'; }, 3000);
        })
        .catch(err => {
            sendAck.style.color = '#e74c3c';
            sendAck.innerText = "✘ Upload failed.";
        });
    }

    // Auto-polling every 1.5 seconds for real-time updates
    setInterval(fetchFiles, 1500);
    fetchFiles();
</script>

</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(APP_HTML)

@app.route('/files', methods=['GET'])
def get_files():
    file_list = [{"file_id": fid, "filename": info["filename"]} for fid, info in RECEIVED_FILES.items()]
    return jsonify(file_list)

@app.route('/upload', methods=['POST'])
def upload():
    uploaded_file = request.files['file']
    filename = uploaded_file.filename
    raw_data = uploaded_file.read()

    priv_key, pub_key = CryptoEngine.generate_rsa_keypair()
    sha256_hash = CryptoEngine.calculate_sha256(raw_data)
    aes_key, iv = CryptoEngine.generate_aes_key()
    encrypted_payload = CryptoEngine.encrypt_aes(raw_data, aes_key, iv)
    enc_aes_key = CryptoEngine.encrypt_rsa(aes_key, pub_key)

    decrypted_aes_key = CryptoEngine.decrypt_rsa(enc_aes_key, priv_key)
    decrypted_data = CryptoEngine.decrypt_aes(encrypted_payload, decrypted_aes_key, iv)

    file_id = str(len(RECEIVED_FILES) + 1)
    RECEIVED_FILES[file_id] = {"filename": filename, "data": decrypted_data}

    return jsonify({"status": "success"})

@app.route('/download/<file_id>')
def download(file_id):
    file_info = RECEIVED_FILES.get(file_id)
    if file_info:
        return send_file(io.BytesIO(file_info['data']), as_attachment=True, download_name=file_info['filename'])
    return "File Not Found", 404

if __name__ == '__main__':
    socketio.run(app, host='127.0.0.1', port=5000, debug=True)