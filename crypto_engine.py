import os
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

class CryptoEngine:
    """
    AegisVault - Core Security Engine
    Handles RSA Key Generation, AES-256 Payload Encryption, and SHA-256 Hashing.
    """

    @staticmethod
    def generate_rsa_keypair():
        """Generates a 2048-bit RSA Public and Private Key pair."""
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        public_key = private_key.public_key()
        return private_key, public_key

    @staticmethod
    def generate_aes_key():
        """Generates a random 256-bit (32 bytes) AES Key and 16-byte IV."""
        aes_key = os.urandom(32)  # 256 bits
        iv = os.urandom(16)       # 128 bits initialization vector
        return aes_key, iv

    @staticmethod
    def encrypt_aes(data: bytes, aes_key: bytes, iv: bytes) -> bytes:
        """Encrypts raw byte payload using AES-256-CTR mode."""
        cipher = Cipher(algorithms.AES(aes_key), modes.CTR(iv))
        encryptor = cipher.encryptor()
        return encryptor.update(data) + encryptor.finalize()

    @staticmethod
    def decrypt_aes(ciphertext: bytes, aes_key: bytes, iv: bytes) -> bytes:
        """Decrypts AES-256-CTR ciphertext back to original raw bytes."""
        cipher = Cipher(algorithms.AES(aes_key), modes.CTR(iv))
        decryptor = cipher.decryptor()
        return decryptor.update(ciphertext) + decryptor.finalize()

    @staticmethod
    def encrypt_rsa(data: bytes, public_key) -> bytes:
        """Encrypts small secrets (like AES Key) using RSA Public Key."""
        return public_key.encrypt(
            data,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

    @staticmethod
    def decrypt_rsa(ciphertext: bytes, private_key) -> bytes:
        """Decrypts RSA ciphertext using Receiver's Private Key."""
        return private_key.decrypt(
            ciphertext,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

    @staticmethod
    def calculate_sha256(data: bytes) -> str:
        """Generates SHA-256 Hash Fingerprint for data integrity check."""
        digest = hashes.Hash(hashes.SHA256())
        digest.update(data)
        return digest.finalize().hex()


# --- Quick Self-Test Block ---
if __name__ == "__main__":
    print("[+] Testing Crypto Engine...")
    
    # 1. Sample Data
    original_data = b"Hello, AegisVault E2EE File Transfer Project!"
    print(f"Original Text: {original_data.decode()}")

    # 2. RSA Keys Setup
    priv_key, pub_key = CryptoEngine.generate_rsa_keypair()

    # 3. AES Encryption Test
    aes_key, iv = CryptoEngine.generate_aes_key()
    encrypted_payload = CryptoEngine.encrypt_aes(original_data, aes_key, iv)
    print(f"Encrypted Ciphertext (Garbled): {encrypted_payload}")

    # 4. RSA Key Exchange Test (Encrypting AES Key with Public Key)
    encrypted_aes_key = CryptoEngine.encrypt_rsa(aes_key, pub_key)

    # 5. Decryption at Receiver Side
    decrypted_aes_key = CryptoEngine.decrypt_rsa(encrypted_aes_key, priv_key)
    decrypted_payload = CryptoEngine.decrypt_aes(encrypted_payload, decrypted_aes_key, iv)
    print(f"Decrypted Text: {decrypted_payload.decode()}")

    # 6. Integrity Verification
    original_hash = CryptoEngine.calculate_sha256(original_data)
    received_hash = CryptoEngine.calculate_sha256(decrypted_payload)
    print(f"SHA-256 Hash Match: {original_hash == received_hash} ({received_hash[:16]}...)")
    
    print("[+] Crypto Engine Test Successful!")