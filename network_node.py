import socket
import os
import base64
from cryptography.hazmat.primitives import serialization
from crypto_engine import CryptoEngine
from protocol import Protocol

HOST = '127.0.0.1'
PORT = 5001

def start_receiver():
    print("\n[+] Initializing Receiver Node...")
    priv_key, pub_key = CryptoEngine.generate_rsa_keypair()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen(1)
    print(f"[+] Receiver listening on {HOST}:{PORT}")

    conn, addr = server.accept()
    print(f"[+] Connection accepted from {addr}")

    try:
        # 1. Send Public Key
        pub_key_pem = pub_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        conn.sendall(len(pub_key_pem).to_bytes(4, 'big') + pub_key_pem)

        # 2. Receive JSON Header
        metadata = Protocol.unpack_header(conn)
        print(f"[+] Received Metadata for file: {metadata['filename']}")

        # 3. Decode Encrypted Keys
        enc_aes_key = base64.b64decode(metadata['encrypted_aes_key'])
        iv = base64.b64decode(metadata['iv'])

        # 4. Decrypt AES Key
        aes_key = CryptoEngine.decrypt_rsa(enc_aes_key, priv_key)

        # 5. Receive Payload
        encrypted_data = b""
        payload_size = metadata['payload_size']
        while len(encrypted_data) < payload_size:
            chunk = conn.recv(4096)
            if not chunk:
                break
            encrypted_data += chunk

        # 6. Decrypt Payload
        decrypted_data = CryptoEngine.decrypt_aes(encrypted_data, aes_key, iv)

        # 7. Integrity Check
       # 7. Integrity Check
        received_hash = CryptoEngine.calculate_sha256(decrypted_data)
        if received_hash == metadata['sha256']:
            save_name = "received_" + metadata['filename']
            with open(save_name, "wb") as f:
                f.write(decrypted_data)
                f.flush()  # Buffer clear karke disk par immediate save karega
            print(f"[✔] SUCCESS: File downloaded safely as '{save_name}' (Integrity Verified!)")
        else:
            print("[✘] ERROR: File Integrity Check Failed!")

    finally:
        conn.close()
        server.close()

def start_sender(file_path):
    if not os.path.exists(file_path):
        print(f"[✘] File not found: {file_path}")
        return

    print(f"\n[+] Sending File: {file_path}")
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect((HOST, PORT))

    try:
        # 1. Receive Public Key
        pk_len = int.from_bytes(client.recv(4), 'big')
        pub_key_pem = client.recv(pk_len)
        pub_key = serialization.load_pem_public_key(pub_key_pem)

        # 2. Read and Encrypt File
        with open(file_path, "rb") as f:
            raw_data = f.read()

        sha256_hash = CryptoEngine.calculate_sha256(raw_data)
        aes_key, iv = CryptoEngine.generate_aes_key()
        encrypted_payload = CryptoEngine.encrypt_aes(raw_data, aes_key, iv)
        enc_aes_key = CryptoEngine.encrypt_rsa(aes_key, pub_key)

        # 3. Create JSON Header
        metadata = {
            "filename": os.path.basename(file_path),
            "payload_size": len(encrypted_payload),
            "sha256": sha256_hash,
            "encrypted_aes_key": base64.b64encode(enc_aes_key).decode('utf-8'),
            "iv": base64.b64encode(iv).decode('utf-8')
        }

        # 4. Send Packet
        packet = Protocol.pack_message(metadata, encrypted_payload)
        client.sendall(packet)
        print("[+] File Encrypted & Sent Successfully!")

    finally:
        client.close()

if __name__ == "__main__":
    choice = input("Enter mode (1 for Receiver / 2 for Sender): ").strip()
    if choice == "1":
        start_receiver()
    elif choice == "2":
        path = input("Enter file path to send: ").strip()
        start_sender(path)
    else:
        print("Invalid choice!")