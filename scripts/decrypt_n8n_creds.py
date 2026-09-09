import sqlite3, base64, hashlib, subprocess, tempfile, os, json

DB = r"C:\Users\nonam\smart-classroom-support\n8n_cred.sqlite"
PASS = os.environ.get("N8N_ENCRYPTION_KEY", "") or "changeme123"


def decrypt(ct_b64, password):
    raw = base64.b64decode(ct_b64)
    assert raw[:8] == b"Salted__", "not salted"
    salt = raw[8:16]
    ct = raw[16:]
    d1 = hashlib.md5(password.encode() + salt).digest()
    d2 = hashlib.md5(d1 + password.encode() + salt).digest()
    d3 = hashlib.md5(d2 + password.encode() + salt).digest()
    key = d1 + d2
    iv = d3
    return key, iv, ct


c = sqlite3.connect(DB)
for cid, name in [("YZeMXOVRdMP9FZlP", "line_bot"), ("z9Wst6gVCKgQiwW9", "db")]:
    data = c.execute("SELECT data FROM credentials_entity WHERE id=?", (cid,)).fetchone()[0]
    key, iv, ct = decrypt(data, PASS)
    inf = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
    inf.write(ct); inf.close()
    outf = tempfile.NamedTemporaryFile(delete=False, suffix=".out"); outf.close()
    subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-K", key.hex(), "-iv", iv.hex(),
                    "-in", inf.name, "-out", outf.name], check=True)
    with open(outf.name, "rb") as f:
        val = f.read()
    print(f"=== {name} ===")
    print(val.decode(errors="replace"))
    os.unlink(inf.name); os.unlink(outf.name)
