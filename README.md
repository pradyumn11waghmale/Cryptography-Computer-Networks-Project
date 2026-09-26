# 🔒 CryptoShare - End-to-End Encrypted File Sharing Platform

CryptoShare is a high-security, web-based End-to-End Encrypted (E2EE) file-sharing platform. It allows users to send and receive files securely through a single-page dashboard with real-time transfer status and dynamic notification updates.

---

## ✨ Features

* **End-to-End Encryption (E2EE):** Combines **AES-256** (symmetric key encryption for file contents) and **RSA-2048** (asymmetric key exchange).
* **SHA-256 Integrity Verification:** Generates cryptographic hashes to ensure files are not tampered with during transmission.
* **Modern SPA Dashboard:** Integrated single-page application (SPA) featuring a sidebar switcher for **Send** and **Receive** views.
* **Real-time Notifications:** Live badge counters and polling updates for immediate incoming file alerts.
* **Public Tunneling:** Ready for remote access and public demonstration via **Ngrok** tunneling.

---

## 🛠️ Tech Stack

* **Backend:** Python 3.x, Flask, Flask-SocketIO
* **Cryptography:** Python `cryptography` library (AES-256, RSA-2048, SHA-256)
* **Frontend:** Dynamic HTML5, CSS3 (Dark Theme), JavaScript (Fetch API & Event Polling)
* **Tunneling & Deployment:** Ngrok / Render

---

## 🚀 Getting Started Locally

### 1. Prerequisites
Ensure you have Python 3.8+ installed on your system.

### 2. Installation
Clone the repository and install required dependencies:




python web_app.py
Open your browser and navigate to:
http://127.0.0.1:5000

🌐 Public Access via Ngrok
To test remote transfers or share the portal across different networks:

Download and authenticate Ngrok.

Run the tunnel command while the Flask app is running:


ngrok http 5000
Access the generated forwarding URL (e.g., https://your-tunnel-name.ngrok-free.dev).

🛡️ Security Architecture
Key Generation: Unique RSA-2048 key pairs are generated for secure key encapsulation.

File Encryption: Payload data is encrypted using an ephemeral AES-256 symmetric key.

Key Exchange: The AES key is wrapped/encrypted using RSA before transmission.

Decryption & Hash Check: Receiver decrypts the AES key, extracts the original file payload, and validates integrity via SHA-256.

📜 License
This project is open-source and available under the MIT License.
