"""HTTPS local. O celular só libera o microfone em HTTPS confiável.

Uma autoridade certificadora (CA) própria, instalada uma vez no iPhone, assina o
certificado do servidor. A CA tem restrição de nomes: só vale para IPs de rede
local e localhost. Mesmo que alguém pegue a chave dela, não consegue se passar
por outro site no seu celular.
"""
import ipaddress
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from . import config

CA_CERT = config.DATA / "ca.pem"
CA_KEY = config.DATA / "ca-key.pem"
CERT = config.DATA / "cert.pem"
KEY = config.DATA / "key.pem"

_LOCAL_NETS = ["192.168.0.0/16", "10.0.0.0/8", "172.16.0.0/12", "127.0.0.0/8"]


def _write_key(path, key):
    path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))


def _ensure_ca():
    if CA_CERT.exists() and CA_KEY.exists():
        cert = x509.load_pem_x509_certificate(CA_CERT.read_bytes())
        key = serialization.load_pem_private_key(CA_KEY.read_bytes(), password=None)
        return cert, key
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Companheiro de ingles - CA local")])
    now = datetime.now(timezone.utc)
    constraints = x509.NameConstraints(
        permitted_subtrees=[x509.IPAddress(ipaddress.ip_network(n)) for n in _LOCAL_NETS]
        + [x509.DNSName("localhost")],
        excluded_subtrees=None,
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, key_cert_sign=True, crl_sign=True, content_commitment=False,
            key_encipherment=False, data_encipherment=False, key_agreement=False,
            encipher_only=False, decipher_only=False,
        ), critical=True)
        .add_extension(constraints, critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    _write_key(CA_KEY, key)
    CA_CERT.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print("[https] CA local nova gerada: instale de novo no iPhone (/pair)")
    return cert, key


def _covers(ca: x509.Certificate, ips: list[str]) -> bool:
    if not (CERT.exists() and KEY.exists()):
        return False
    cert = x509.load_pem_x509_certificate(CERT.read_bytes())
    if cert.issuer != ca.subject:
        return False  # certificado antigo, autoassinado
    if cert.not_valid_after_utc < datetime.now(timezone.utc) + timedelta(days=7):
        return False
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    have = {str(ip) for ip in san.get_values_for_type(x509.IPAddress)}
    return set(ips) <= have


def ensure(ips: list[str]) -> tuple[str, str]:
    """Garante um certificado do servidor, assinado pela CA, que cubra os IPs desta máquina."""
    ca, ca_key = _ensure_ca()
    if not _covers(ca, ips):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.now(timezone.utc)
        # Só IPs de rede local: a CA não assina outros (e o iPhone recusaria).
        local = [ip for ip in sorted(set(ips) | {"127.0.0.1"})
                 if any(ipaddress.ip_address(ip) in ipaddress.ip_network(n) for n in _LOCAL_NETS)]
        san = [x509.DNSName("localhost")] + [x509.IPAddress(ipaddress.ip_address(ip)) for ip in local]
        cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Companheiro de ingles")]))
            .issuer_name(ca.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=800))  # o iPhone exige no máximo 825 dias
            .add_extension(x509.SubjectAlternativeName(san), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(
                digital_signature=True, key_encipherment=True, content_commitment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False,
                encipher_only=False, decipher_only=False,
            ), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256())
        )
        _write_key(KEY, key)
        CERT.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        print("[https] certificado do servidor gerado")
    return str(CERT), str(KEY)


def ca_der() -> bytes:
    """A CA no formato que o iPhone instala como perfil."""
    return x509.load_pem_x509_certificate(CA_CERT.read_bytes()).public_bytes(serialization.Encoding.DER)


def ca_fingerprint() -> str:
    fp = x509.load_pem_x509_certificate(CA_CERT.read_bytes()).fingerprint(hashes.SHA256()).hex().upper()
    return " ".join(fp[i:i + 2] for i in range(0, len(fp), 2))
