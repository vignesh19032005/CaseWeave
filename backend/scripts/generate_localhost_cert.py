"""
Stage 15 — TLS for localhost. Generates a self-signed cert valid for
localhost/127.0.0.1, suitable for local pilot testing over HTTPS. NOT a
real deployment cert (no real domain, browsers will warn once per machine
until trusted) — that's Stage 20's deployment-infra job. Run once:
python scripts/generate_localhost_cert.py
"""
import datetime
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

CERT_DIR = Path(__file__).parent.parent / "certs"


def generate():
    CERT_DIR.mkdir(exist_ok=True)
    key_path = CERT_DIR / "localhost.key"
    cert_path = CERT_DIR / "localhost.crt"

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "CaseWeave local dev"),
    ])

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=825))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(__import__("ipaddress").ip_address("127.0.0.1")),
            ]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    print(f"Generated {cert_path} and {key_path}")
    print("Run the API over HTTPS with:")
    print(f'  uvicorn api:app --port 8010 --ssl-keyfile certs/localhost.key --ssl-certfile certs/localhost.crt')
    print("Browser will warn once (self-signed, expected for localhost) — safe to accept for local testing.")


if __name__ == "__main__":
    generate()
