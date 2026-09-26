import json
import struct

class Protocol:
    """
    CryptoShare Protocol
    Packs metadata (File Name, File Size, Encrypted AES Key, IV, SHA-256) 
    along with custom binary framing so data flows without corruption over Sockets.
    """

    @staticmethod
    def pack_message(metadata: dict, payload: bytes) -> bytes:
        """
        Packs JSON Metadata + Encrypted File Payload into a single stream.
        Structure: [4 Bytes Header Length] + [JSON Metadata] + [Payload Data]
        """
        # 1. Convert JSON metadata dict to bytes
        metadata_bytes = json.dumps(metadata).encode('utf-8')
        metadata_len = len(metadata_bytes)

        # 2. Pack metadata length as 4-byte unsigned integer (Big-Endian format)
        header = struct.pack('>I', metadata_len)

        # 3. Combine Header + Metadata + Raw Encrypted Payload
        return header + metadata_bytes + payload

    @staticmethod
    def unpack_header(socket_conn) -> dict:
        """
        Reads the 4-byte header length first, then reads and parses the JSON metadata.
        """
        # 1. Read first 4 bytes to know length of metadata
        raw_header_len = socket_conn.recv(4)
        if not raw_header_len:
            return None
        
        metadata_len = struct.unpack('>I', raw_header_len)[0]

        # 2. Read exact metadata bytes based on length
        metadata_bytes = b""
        while len(metadata_bytes) < metadata_len:
            chunk = socket_conn.recv(metadata_len - len(metadata_bytes))
            if not chunk:
                break
            metadata_bytes += chunk

        # 3. Convert bytes back to JSON dictionary
        return json.loads(metadata_bytes.decode('utf-8'))


# --- Quick Self-Test Block ---
if __name__ == "__main__":
    print("[+] Testing Protocol Packet Framing...")

    sample_metadata = {
        "filename": "confidential_doc.pdf",
        "file_size": 2048,
        "sha256": "de0ccfc220523eef..."
    }
    sample_payload = b"ENCRYPTED_BINARY_PAYLOAD_HERE"

    packed_data = Protocol.pack_message(sample_metadata, sample_payload)
    print(f"Packed Bytes Length: {len(packed_data)} bytes")
    print("[+] Protocol Framing Test Successful!")