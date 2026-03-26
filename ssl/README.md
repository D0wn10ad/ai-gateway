# SSL Certificates

Place your SSL certificate and private key in this directory:

- `chat.crt` — SSL certificate (can include intermediate chain)
- `chat.key` — SSL private key

## Generating a CSR

If your certificate authority requires a CSR, create a SAN config file (`san.cnf`):

```ini
[req]
default_bits = 2048
prompt = no
distinguished_name = dn
req_extensions = v3_req

[dn]
CN = chat.example.edu

[v3_req]
subjectAltName = @alt_names

[alt_names]
DNS.1 = chat.example.edu
DNS.2 = litellm.example.edu
```

Then generate the CSR:

```bash
openssl req -new -newkey rsa:2048 -nodes -keyout chat.key -out chat.csr -config san.cnf
```

Submit `chat.csr` to your certificate authority. When you receive the certificate, save it as `chat.crt`.

## After Renewal

```bash
docker compose restart nginx
```

## Self-Signed (Development Only)

```bash
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout chat.key -out chat.crt \
  -days 365 -subj '/CN=chat.example.edu' \
  -addext 'subjectAltName=DNS:chat.example.edu,DNS:litellm.example.edu'
```
