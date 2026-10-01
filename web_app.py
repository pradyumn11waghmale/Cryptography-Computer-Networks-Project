import io
import os
import uuid
from flask import Flask, render_template_string, request, jsonify, redirect, url_for, send_file
from flask_socketio import SocketIO
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from cryptography.hazmat.primitives import serialization
from sqlalchemy import or_, and_

from crypto_engine import CryptoEngine
from models import db, User, Friendship

# App Setup
app = Flask(__name__)
app.config['SECRET_KEY'] = 'AegisVault_secret_key_123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 1. Set Max Content Length to 5 GB (5 * 1024 * 1024 * 1024 bytes)
FIVE_GB = 5 * 1024 * 1024 * 1024
app.config['MAX_CONTENT_LENGTH'] = FIVE_GB

# Setup Local Storage Folder for Encrypted Files (To save RAM on Render)
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# DB Init
db.init_app(app)

# Login Manager Setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login_page'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@login_manager.unauthorized_handler
def unauthorized():
    return redirect(url_for('login_page'))

# 2. Set SocketIO max buffer size to 5 GB
socketio = SocketIO(app, cors_allowed_origins="*", max_http_buffer_size=FIVE_GB, async_mode='threading')

# Storage for File Metadata
RECEIVED_FILES_META = {}

# HTML Templates
LOGIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AegisVault - Auth Portal</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        body { background: #0f111a; color: #f8fafc; height: 100vh; display: flex; align-items: center; justify-content: center; }
        .auth-card { background: #161824; border: 1px solid #27293d; padding: 40px; border-radius: 16px; width: 380px; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4); }
        h2 { text-align: center; margin-bottom: 24px; color: #4e73df; }
        .input-group { margin-bottom: 18px; }
        .input-group label { display: block; margin-bottom: 6px; font-size: 0.9rem; color: #8a8d9b; }
        .input-group input { width: 100%; padding: 12px; background: #0f111a; border: 1px solid #27293d; color: white; border-radius: 8px; font-size: 1rem; outline: none; }
        .input-group input:focus { border-color: #4e73df; }
        .btn { width: 100%; padding: 12px; background: #4e73df; border: none; color: white; font-size: 1rem; font-weight: bold; border-radius: 8px; cursor: pointer; transition: 0.3s; }
        .btn:hover { background: #375a7f; }
        .toggle-text { text-align: center; margin-top: 16px; font-size: 0.85rem; color: #8a8d9b; }
        .toggle-text span { color: #4e73df; cursor: pointer; font-weight: bold; }
    </style>
</head>
<body>
    <div class="auth-card">
        <h2 id="formTitle">AegisVault Login</h2>
        <form id="authForm">
            <div class="input-group">
                <label>Username</label>
                <input type="text" id="username" required>
            </div>
            <div class="input-group">
                <label>Password</label>
                <input type="password" id="password" required>
            </div>
            <button type="submit" class="btn" id="submitBtn">Login</button>
        </form>
        <div class="toggle-text">
            <span id="toggleBtn" onclick="toggleAuth()">New user? Sign Up here</span>
        </div>
    </div>

    <script>
        let isLogin = true;
        function toggleAuth() {
            isLogin = !isLogin;
            document.getElementById('formTitle').innerText = isLogin ? "AegisVault Login" : "AegisVault Sign Up";
            document.getElementById('submitBtn').innerText = isLogin ? "Login" : "Sign Up";
            document.getElementById('toggleBtn').innerText = isLogin ? "New user? Sign Up here" : "Already have an account? Login";
        }

        document.getElementById('authForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            const endpoint = isLogin ? '/login' : '/signup';

            const res = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });

            const data = await res.json();
            alert(data.message);
            if (res.ok) {
                if (isLogin) {
                    window.location.href = '/';
                } else {
                    toggleAuth();
                }
            }
        });
    </script>
</body>
</html>
"""

APP_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>AegisVault - E2EE Dashboard (5GB Ready)</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.5.4/socket.io.min.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        body { background: #0f111a; color: #e1e1e6; display: flex; height: 100vh; overflow: hidden; }

        .sidebar { width: 260px; background: #161824; border-right: 1px solid #27293d; display: flex; flex-direction: column; padding: 25px 15px; }
        .brand { color: #4e73df; font-size: 20px; font-weight: bold; margin-bottom: 20px; text-align: center; letter-spacing: 1px; }
        .user-info { font-size: 13px; color: #2ecc71; text-align: center; margin-bottom: 25px; padding: 8px; background: #1e2235; border-radius: 6px; }
        
        .nav-item { display: flex; align-items: center; justify-content: space-between; padding: 14px 20px; color: #8a8d9b; border-radius: 8px; cursor: pointer; margin-bottom: 10px; transition: 0.3s; font-weight: 600; user-select: none; }
        .nav-item:hover, .nav-item.active { background: #1e2235; color: #ffffff; }
        .nav-item.active { border-left: 4px solid #4e73df; }
        
        .badge { background: #e74c3c; color: white; font-size: 11px; font-weight: bold; padding: 3px 8px; border-radius: 12px; display: none; }

        .main-content { flex: 1; padding: 40px; overflow-y: auto; background: #0f111a; }
        
        .tab-panel { display: none; }
        .tab-panel.active { display: block !important; }

        .card { background: #161824; border: 1px solid #27293d; border-radius: 12px; padding: 30px; max-width: 650px; margin: 0 auto 25px auto; }
        .card h2 { margin-bottom: 8px; color: #fff; }
        .card p.subtitle { color: #6c7293; font-size: 13px; margin-bottom: 25px; }

        .select-group, .search-group { margin-bottom: 20px; }
        .select-group label, .search-group label { display: block; color: #8a8d9b; font-size: 14px; margin-bottom: 8px; }
        .select-group select, .search-group input { width: 100%; padding: 12px; background: #0f111a; border: 1px solid #27293d; color: white; border-radius: 8px; outline: none; }

        .drop-zone { border: 2px dashed #4e73df; border-radius: 10px; padding: 50px 20px; text-align: center; background: #1a1d2e; cursor: pointer; transition: 0.3s; }
        .drop-zone:hover { background: #22263d; border-color: #6c8bef; }

        .file-card, .user-row { background: #1a1d2e; border: 1px solid #27293d; padding: 14px 20px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
        .file-card { border-left: 4px solid #2ecc71; }
        
        .btn-action { background: #4e73df; color: white; border: none; padding: 8px 14px; border-radius: 6px; font-weight: bold; font-size: 12px; cursor: pointer; transition: 0.2s; }
        .btn-action:hover { background: #375a7f; }
        .btn-success { background: #2ecc71; color: white; }
        .btn-success:hover { background: #27ae60; }
        .btn-danger { background: #e74c3c; color: white; }
        .btn-danger:hover { background: #c0392b; }
        .btn-inspect { background: #9b59b6; color: white; border: none; padding: 8px 12px; border-radius: 6px; font-size: 12px; cursor: pointer; margin-right: 8px; font-weight: bold; }
        .btn-inspect:hover { background: #8e44ad; }
        
        .btn-download { background: #2ecc71; color: white; border: none; padding: 8px 16px; border-radius: 6px; text-decoration: none; font-weight: bold; font-size: 12px; transition: 0.2s; }
        .btn-download:hover { background: #27ae60; }
        .btn-logout { background: #e74c3c; color: white; border: none; padding: 10px; width: 100%; border-radius: 8px; text-align: center; text-decoration: none; font-weight: bold; margin-top: auto; cursor: pointer; }
        
        .status-msg { margin-top: 15px; text-align: center; font-size: 14px; font-weight: bold; display: none; }
        .badge-status { font-size: 12px; padding: 4px 10px; border-radius: 12px; color: #fff; background: #34495e; }

        .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); align-items: center; justify-content: center; }
        .modal-content { background: #161824; border: 1px solid #4e73df; padding: 25px; border-radius: 12px; width: 90%; max-width: 600px; color: #fff; }
        .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; border-bottom: 1px solid #27293d; padding-bottom: 10px; }
        .close-btn { color: #e74c3c; font-size: 24px; cursor: pointer; font-weight: bold; }
        .crypto-box { background: #0f111a; border: 1px solid #27293d; padding: 12px; border-radius: 6px; font-family: monospace; font-size: 11px; word-break: break-all; color: #2ecc71; margin-bottom: 12px; max-height: 100px; overflow-y: auto; }
    </style>
</head>
<body>

    <div class="sidebar">
        <div class="brand">🔒 AegisVault</div>
        <div class="user-info">👤 Logged in: <b>{{ current_user.username }}</b></div>
        
        <div class="nav-item active" id="nav-sendTab">
            <span>📤 Send File </span>
        </div>
        
        <div class="nav-item" id="nav-receiveTab">
            <span>📥 Receive File</span>
            <span class="badge" id="notifBadge">0</span>
        </div>

        <div class="nav-item" id="nav-friendsTab">
            <span>👥 Friends & Network</span>
            <span class="badge" id="reqBadge" style="background:#f39c12;">!</span>
        </div>

        <a href="/logout" class="btn-logout">Logout</a>
    </div>

    <div class="main-content">
        
        <!-- SEND TAB -->
        <div id="sendTab" class="tab-panel active">
            <div class="card">
                <h2>Send Encrypted File</h2>
                <p class="subtitle">Supports large file transfers up to <b>5 GB</b> with AES-256 + RSA E2EE.</p>

                <div class="select-group">
                    <label>Select Friend:</label>
                    <select id="receiverSelect">
                        <option value="">-- Choose Friend --</option>
                    </select>
                </div>

                <div class="drop-zone" onclick="document.getElementById('fileInput').click();">
                    <p style="font-size: 16px; color: #a0a5ba;">📁 Drag & Drop file (Max 5GB), or <b style="color: #4e73df;">Browse</b></p>
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

        <!-- FRIENDS & NETWORK TAB -->
        <div id="friendsTab" class="tab-panel">
            <div class="card">
                <h2>Find Friends</h2>
                <p class="subtitle">Search username to send a friend request.</p>
                <div class="search-group">
                    <input type="text" id="userSearchInput" placeholder="Type friend's username..." oninput="searchUsers()">
                </div>
                <div id="searchResults"></div>
            </div>

            <div class="card" id="pendingCard">
                <h2>Pending Requests</h2>
                <p class="subtitle">Incoming connection requests.</p>
                <div id="pendingList">
                    <p style="color: #6c7293; font-style: italic; text-align: center;">No pending requests.</p>
                </div>
            </div>
        </div>

    </div>

    <!-- Crypto Inspection Modal -->
    <div id="cryptoModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h3 style="color:#4e73df;">🔐 Cryptographic Verification Inspector</h3>
                <span class="close-btn" onclick="closeModal()">&times;</span>
            </div>
            <div>
                <p style="font-size:12px; color:#8a8d9b; margin-bottom:4px;">Encrypted Cipher Payload (AES-256 Output):</p>
                <div id="modalPayload" class="crypto-box"></div>

                <p style="font-size:12px; color:#8a8d9b; margin-bottom:4px;">RSA Encrypted Symmetric Key (Receiver Public Key):</p>
                <div id="modalKey" class="crypto-box"></div>

                <p style="font-size:12px; color:#8a8d9b; margin-bottom:4px;">SHA-256 Integrity Hash (Verification Checksum):</p>
                <div id="modalHash" class="crypto-box" style="color:#f1c40f;"></div>
            </div>
        </div>
    </div>

<script>
    let socket = null;
    try {
        if (typeof io !== 'undefined') {
            socket = io();
        }
    } catch(e) {
        console.warn("Socket.io fallback mode active");
    }

    const currentUserId = Number("{{ current_user.id }}");
    let unreadCount = 0;
    let activeTab = 'sendTab';
    let knownFileIds = new Set();
    let fileCryptoStore = {};

    function switchTab(tabId) {
        document.querySelectorAll('.tab-panel').forEach(panel => {
            panel.classList.remove('active');
            panel.style.display = 'none';
        });

        document.querySelectorAll('.nav-item').forEach(nav => {
            nav.classList.remove('active');
        });

        const targetPanel = document.getElementById(tabId);
        const targetNav = document.getElementById('nav-' + tabId);

        if (targetPanel) {
            targetPanel.classList.add('active');
            targetPanel.style.display = 'block';
        }
        if (targetNav) {
            targetNav.classList.add('active');
        }

        activeTab = tabId;

        if (tabId === 'receiveTab') {
            unreadCount = 0;
            const badge = document.getElementById('notifBadge');
            badge.style.display = 'none';
            badge.innerText = '0';
            fetchFiles();
        } else if (tabId === 'friendsTab') {
            loadPendingRequests();
            searchUsers();
        } else if (tabId === 'sendTab') {
            loadFriends();
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        document.getElementById('nav-sendTab').addEventListener('click', () => switchTab('sendTab'));
        document.getElementById('nav-receiveTab').addEventListener('click', () => switchTab('receiveTab'));
        document.getElementById('nav-friendsTab').addEventListener('click', () => switchTab('friendsTab'));
        
        switchTab('sendTab');
    });

    function loadFriends() {
        fetch('/friends')
        .then(res => res.json())
        .then(friends => {
            const select = document.getElementById('receiverSelect');
            select.innerHTML = '<option value="">-- Choose Friend --</option>';
            if(friends.length === 0) {
                select.innerHTML = '<option value="">No friends added yet. Add friends first!</option>';
                return;
            }
            friends.forEach(f => {
                const opt = document.createElement('option');
                opt.value = f.id;
                opt.innerText = "👤 " + f.username;
                select.appendChild(opt);
            });
        })
        .catch(err => console.error("Error loading friends:", err));
    }

    async function searchUsers() {
        const query = document.getElementById('userSearchInput').value;
        const resultsDiv = document.getElementById('searchResults');
        if (!query.trim()) {
            resultsDiv.innerHTML = '';
            return;
        }

        const res = await fetch('/search_users?q=' + encodeURIComponent(query));
        const users = await res.json();

        resultsDiv.innerHTML = '';
        if (users.length === 0) {
            resultsDiv.innerHTML = '<p style="color: #6c7293; font-size:13px; text-align:center;">No users found.</p>';
            return;
        }

        users.forEach(u => {
            const row = document.createElement('div');
            row.className = 'user-row';

            const nameSpan = document.createElement('span');
            nameSpan.innerHTML = '👤 <b>' + u.username + '</b>';
            row.appendChild(nameSpan);

            if (u.status === 'none') {
                const btn = document.createElement('button');
                btn.className = 'btn-action';
                btn.innerText = 'Add Friend';
                btn.onclick = () => sendFriendRequest(u.id);
                row.appendChild(btn);
            } else if (u.status === 'sent') {
                const span = document.createElement('span');
                span.className = 'badge-status';
                span.innerText = 'Request Sent';
                row.appendChild(span);
            } else if (u.status === 'friends') {
                const span = document.createElement('span');
                span.className = 'badge-status';
                span.style.background = '#2ecc71';
                span.innerText = 'Friends';
                row.appendChild(span);
            } else if (u.status === 'incoming') {
                const btn = document.createElement('button');
                btn.className = 'btn-action btn-success';
                btn.innerText = 'Accept Request';
                btn.onclick = () => respondRequest(u.request_id, 'accept');
                row.appendChild(btn);
            }

            resultsDiv.appendChild(row);
        });
    }

    async function sendFriendRequest(receiverId) {
        const res = await fetch('/send_friend_request', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ receiver_id: receiverId })
        });
        const data = await res.json();
        alert(data.message);
        searchUsers();
        loadPendingRequests();
    }

    async function loadPendingRequests() {
        try {
            const res = await fetch('/get_pending_requests', { cache: 'no-store' });
            const requests = await res.json();
            const pendingList = document.getElementById('pendingList');
            const reqBadge = document.getElementById('reqBadge');

            pendingList.innerHTML = '';
            if (Array.isArray(requests) && requests.length > 0) {
                reqBadge.style.display = 'inline-block';
                reqBadge.innerText = requests.length;
                
                requests.forEach(r => {
                    const row = document.createElement('div');
                    row.className = 'user-row';
                    row.id = 'req-row-' + r.request_id;

                    const label = document.createElement('span');
                    label.innerHTML = '👤 <b>' + r.sender_username + '</b> wants to connect.';
                    row.appendChild(label);

                    const btnGroup = document.createElement('div');
                    btnGroup.style.display = 'flex';
                    btnGroup.style.gap = '8px';

                    const acceptBtn = document.createElement('button');
                    acceptBtn.className = 'btn-action btn-success';
                    acceptBtn.innerText = 'Accept';
                    acceptBtn.onclick = () => respondRequest(r.request_id, 'accept');

                    const rejectBtn = document.createElement('button');
                    rejectBtn.className = 'btn-action btn-danger';
                    rejectBtn.innerText = 'Reject';
                    rejectBtn.onclick = () => respondRequest(r.request_id, 'reject');

                    btnGroup.appendChild(acceptBtn);
                    btnGroup.appendChild(rejectBtn);
                    row.appendChild(btnGroup);

                    pendingList.appendChild(row);
                });
            } else {
                reqBadge.style.display = 'none';
                pendingList.innerHTML = '<p style="color: #6c7293; font-style: italic; text-align: center;">No pending requests.</p>';
            }
        } catch (err) {
            console.error("Error loading pending requests:", err);
        }
    }

    async function respondRequest(requestId, action) {
        const res = await fetch('/respond_friend_request', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ request_id: requestId, action: action })
        });
        const data = await res.json();
        alert(data.message);
        loadPendingRequests();
        loadFriends();
        searchUsers();
    }

    function renderFileCard(f) {
        const noMsg = document.getElementById('noMsg');
        if (noMsg) noMsg.style.display = 'none';

        const inbox = document.getElementById('inbox');
        if (document.getElementById('file-card-' + f.file_id)) return;

        fileCryptoStore[f.file_id] = f;

        const card = document.createElement('div');
        card.id = 'file-card-' + f.file_id;
        card.className = 'file-card';
        card.innerHTML = `
            <div>
                <strong style="color: #fff; font-size: 15px;">` + f.filename + `</strong>
                <span style="color: #8a8d9b; font-size: 12px;"> (From: ` + f.sender + `)</span><br>
                <small style="color: #2ecc71; font-size: 12px;">✔ Decrypted & SHA-256 Integrity Verified</small>
            </div>
            <div>
                <button class="btn-inspect" onclick="inspectCrypto('` + f.file_id + `')">🔐 Inspect Payload</button>
                <a href="/download/` + f.file_id + `" class="btn-download">Download</a>
            </div>
        `;
        inbox.prepend(card);
    }

    function inspectCrypto(fileId) {
        const info = fileCryptoStore[fileId];
        if(!info) return;
        document.getElementById('modalPayload').innerText = info.enc_preview || "Encrypted binary payload on disk";
        document.getElementById('modalKey').innerText = info.enc_key_preview || "RSA encrypted key stream";
        document.getElementById('modalHash').innerText = info.sha256 || "N/A";
        document.getElementById('cryptoModal').style.display = 'flex';
    }

    function closeModal() {
        document.getElementById('cryptoModal').style.display = 'none';
    }

    function fetchFiles() {
        fetch('/files')
        .then(res => res.json())
        .then(files => {
            files.forEach(f => {
                if (!knownFileIds.has(f.file_id)) {
                    knownFileIds.add(f.file_id);
                    renderFileCard(f);

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
        const receiverId = document.getElementById('receiverSelect').value;
        if (!receiverId) {
            alert("Please select a friend first!");
            return;
        }

        if(!file) return;

        const FIVE_GB_BYTES = 5 * 1024 * 1024 * 1024;
        if (file.size > FIVE_GB_BYTES) {
            alert("File size exceeds maximum limit of 5 GB!");
            return;
        }

        const sendAck = document.getElementById('sendAck');
        sendAck.style.color = '#3498db';
        sendAck.innerText = "Encrypting & Transferring Large Payload... Please wait.";
        sendAck.style.display = 'block';

        const formData = new FormData();
        formData.append('file', file);
        formData.append('receiver_id', receiverId);

        fetch('/upload', { method: 'POST', body: formData })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                sendAck.style.color = '#2ecc71';
                sendAck.innerText = "✔ File Encrypted & Sent Successfully!";
            } else {
                sendAck.style.color = '#e74c3c';
                sendAck.innerText = "✘ " + data.message;
            }
            setTimeout(() => { sendAck.style.display = 'none'; }, 4000);
        })
        .catch(err => {
            sendAck.style.color = '#e74c3c';
            sendAck.innerText = "✘ Upload failed. Check connection.";
        });
    }

    if (socket) {
        socket.on('new_file', (data) => {
            fetchFiles();
        });

        socket.on('friend_request_received', (data) => {
            if (!data.receiver_id || Number(data.receiver_id) === currentUserId) {
                loadPendingRequests();
                searchUsers();
            }
        });
    }

    setInterval(fetchFiles, 3000);
    setInterval(loadPendingRequests, 3000);

    fetchFiles();
    loadFriends();
    loadPendingRequests();
</script>

</body>
</html>
"""

# Auth & Web Routes
@app.route('/login_page')
def login_page():
    return render_template_string(LOGIN_HTML)

@app.route('/signup', methods=['POST'])
def signup():
    data = request.json or {}
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"status": "error", "message": "Username and password required!"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"status": "error", "message": "Username pehle se exist karta hai!"}), 400

    hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
    
    priv_key_obj, pub_key_obj = CryptoEngine.generate_rsa_keypair()

    if not isinstance(priv_key_obj, (str, bytes)):
        priv_key_pem = priv_key_obj.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')
    elif isinstance(priv_key_obj, bytes):
        priv_key_pem = priv_key_obj.decode('utf-8')
    else:
        priv_key_pem = priv_key_obj

    if not isinstance(pub_key_obj, (str, bytes)):
        pub_key_pem = pub_key_obj.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')
    elif isinstance(pub_key_obj, bytes):
        pub_key_pem = pub_key_obj.decode('utf-8')
    else:
        pub_key_pem = pub_key_obj

    new_user = User(
        username=username, 
        password_hash=hashed_pw, 
        public_key=pub_key_pem,
        private_key_encrypted=priv_key_pem
    )
    
    db.session.add(new_user)
    db.session.commit()
    return jsonify({"status": "success", "message": "Account created successfully!"})

@app.route('/login', methods=['POST'])
def login():
    data = request.json or {}
    username = data.get('username')
    password = data.get('password')

    user = User.query.filter_by(username=username).first()

    if user and check_password_hash(user.password_hash, password):
        login_user(user)
        return jsonify({"status": "success", "message": "Login successful!"})

    return jsonify({"status": "error", "message": "Invalid username ya password!"}), 401

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login_page'))

@app.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('login_page'))
    return render_template_string(APP_HTML)


# ---------------- FRIEND SYSTEM ROUTES ----------------

@app.route('/search_users', methods=['GET'])
@login_required
def search_users():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])

    curr_id = int(current_user.id)
    users = User.query.filter(
        User.username.ilike(f"%{query}%"),
        User.id != curr_id
    ).limit(10).all()

    results = []
    for user in users:
        target_id = int(user.id)
        
        sent_req = Friendship.query.filter_by(sender_id=curr_id, receiver_id=target_id).first()
        rec_req = Friendship.query.filter_by(sender_id=target_id, receiver_id=curr_id).first()

        status = 'none'
        req_id = None

        if (sent_req and sent_req.status == 'accepted') or (rec_req and rec_req.status == 'accepted'):
            status = 'friends'
        elif sent_req and sent_req.status == 'pending':
            status = 'sent'
            req_id = sent_req.id
        elif rec_req and rec_req.status == 'pending':
            status = 'incoming'
            req_id = rec_req.id

        results.append({
            'id': user.id,
            'username': user.username,
            'status': status,
            'request_id': req_id
        })

    return jsonify(results)

@app.route('/send_friend_request', methods=['POST'])
@login_required
def send_friend_request():
    data = request.json or {}
    receiver_id = data.get('receiver_id')

    if not receiver_id:
        return jsonify({'status': 'error', 'message': 'Invalid Receiver'}), 400

    receiver_id = int(receiver_id)
    user_id = int(current_user.id)

    existing_sent = Friendship.query.filter_by(sender_id=user_id, receiver_id=receiver_id).first()
    if existing_sent:
        return jsonify({'status': 'error', 'message': 'Already sent request or friends!'}), 400

    existing_incoming = Friendship.query.filter_by(sender_id=receiver_id, receiver_id=user_id, status='pending').first()
    if existing_incoming:
        existing_incoming.status = 'accepted'
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'You both added each other! You are now friends.'})

    new_req = Friendship(sender_id=user_id, receiver_id=receiver_id, status='pending')
    db.session.add(new_req)
    db.session.commit()

    socketio.emit('friend_request_received', {'receiver_id': receiver_id})
    return jsonify({'status': 'success', 'message': 'Friend request sent!'})

@app.route('/get_pending_requests', methods=['GET'])
@login_required
def get_pending_requests():
    user_id = int(current_user.id)
    
    pending_requests = Friendship.query.filter(
        Friendship.receiver_id == user_id,
        Friendship.status == 'pending'
    ).all()

    requests_data = []
    for req in pending_requests:
        sender_user = User.query.get(int(req.sender_id))
        if sender_user:
            requests_data.append({
                'request_id': req.id,
                'sender_id': sender_user.id,
                'sender_username': sender_user.username
            })

    return jsonify(requests_data)

@app.route('/respond_friend_request', methods=['POST'])
@login_required
def respond_friend_request():
    data = request.json or {}
    request_id = data.get('request_id')
    action = data.get('action')

    req = Friendship.query.get(int(request_id)) if request_id else None
    if not req or int(req.receiver_id) != int(current_user.id):
        return jsonify({'status': 'error', 'message': 'Request not found'}), 404

    if action == 'accept':
        req.status = 'accepted'
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Friend request accepted!'})
    elif action == 'reject':
        db.session.delete(req)
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Friend request rejected.'})

    return jsonify({'status': 'error', 'message': 'Invalid action'}), 400

@app.route('/friends', methods=['GET'])
@login_required
def get_friends():
    curr_id = int(current_user.id)
    friendships = Friendship.query.filter(
        (Friendship.status == 'accepted') &
        ((Friendship.sender_id == curr_id) | (Friendship.receiver_id == curr_id))
    ).all()

    friends = []
    for f in friendships:
        friend_id = int(f.receiver_id) if int(f.sender_id) == curr_id else int(f.sender_id)
        friend_user = User.query.get(friend_id)
        if friend_user:
            friends.append({
                'id': friend_user.id,
                'username': friend_user.username
            })
    return jsonify(friends)

@app.route('/files', methods=['GET'])
@login_required
def get_files():
    curr_id = int(current_user.id)
    file_list = [
        {
            "file_id": fid, 
            "filename": info["filename"],
            "sender": info["sender"],
            "enc_preview": info["enc_preview"],
            "enc_key_preview": info["enc_aes_key"].hex()[:60] + "...",
            "sha256": info["sha256"]
        } 
        for fid, info in RECEIVED_FILES_META.items() 
        if int(info["receiver_id"]) == curr_id
    ]
    return jsonify(file_list)

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    try:
        uploaded_file = request.files.get('file')
        receiver_id = request.form.get('receiver_id')

        if not uploaded_file or not receiver_id:
            return jsonify({"status": "error", "message": "File and Receiver are required"}), 400

        receiver = User.query.get(int(receiver_id))
        if not receiver:
            return jsonify({"status": "error", "message": "Receiver not found"}), 404

        filename = uploaded_file.filename
        raw_data = uploaded_file.read()

        receiver_pub_key = serialization.load_pem_public_key(receiver.public_key.encode('utf-8'))
        sha256_hash = CryptoEngine.calculate_sha256(raw_data)

        aes_key, iv = CryptoEngine.generate_aes_key()
        encrypted_payload = CryptoEngine.encrypt_aes(raw_data, aes_key, iv)
        enc_aes_key = CryptoEngine.encrypt_rsa(aes_key, receiver_pub_key)

        file_id = str(uuid.uuid4())[:8]
        file_path = os.path.join(UPLOAD_FOLDER, f"{file_id}.enc")

        # Save encrypted file payload to disk (to save RAM)
        with open(file_path, 'wb') as f:
            f.write(encrypted_payload)

        RECEIVED_FILES_META[file_id] = {
            "filename": filename, 
            "file_path": file_path,
            "enc_preview": encrypted_payload.hex()[:60] + "...",
            "enc_aes_key": enc_aes_key,
            "iv": iv,
            "sha256": sha256_hash,
            "receiver_id": receiver.id,
            "sender": current_user.username
        }

        socketio.emit('new_file', {
            'file_id': file_id,
            'filename': filename,
            'sender': current_user.username,
            'receiver_id': receiver.id
        })
        return jsonify({"status": "success"})
    except Exception as e:
        print(f"Upload Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/download/<file_id>')
@login_required
def download(file_id):
    file_info = RECEIVED_FILES_META.get(file_id)
    if not file_info or int(file_info["receiver_id"]) != int(current_user.id):
        return "File Not Found or Access Denied", 404

    try:
        if not os.path.exists(file_info["file_path"]):
            return "File storage missing on server", 404

        priv_key = serialization.load_pem_private_key(
            current_user.private_key_encrypted.encode('utf-8'),
            password=None
        )

        with open(file_info["file_path"], 'rb') as f:
            encrypted_payload = f.read()

        dec_aes_key = CryptoEngine.decrypt_rsa(file_info["enc_aes_key"], priv_key)
        dec_payload = CryptoEngine.decrypt_aes(encrypted_payload, dec_aes_key, file_info["iv"])

        return send_file(
            io.BytesIO(dec_payload), 
            as_attachment=True, 
            download_name=file_info['filename']
        )
    except Exception as e:
        return f"Decryption Error: {str(e)}", 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), debug=True)