#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cert_dir="$ROOT/.camera-feed"
host="$(/usr/sbin/scutil --get LocalHostName).local"
mkdir -p "$cert_dir"

if [[ -f "$cert_dir/ca.crt" && -f "$cert_dir/server.crt" && -f "$cert_dir/server.key" ]] && \
   openssl x509 -in "$cert_dir/server.crt" -noout -checkend 86400 >/dev/null && \
   openssl x509 -in "$cert_dir/server.crt" -noout -ext subjectAltName | grep -Fq "DNS:$host"; then
  exit 0
fi

openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
  -subj "/CN=SeaStreet Camera Local CA" \
  -keyout "$cert_dir/ca.key" -out "$cert_dir/ca.crt"

openssl req -newkey rsa:2048 -nodes -subj "/CN=$host" \
  -keyout "$cert_dir/server.key" -out "$cert_dir/server.csr"

openssl x509 -req -days 825 -sha256 \
  -in "$cert_dir/server.csr" -CA "$cert_dir/ca.crt" -CAkey "$cert_dir/ca.key" \
  -CAcreateserial -out "$cert_dir/server.crt" \
  -extfile <(printf "subjectAltName=DNS:%s,DNS:localhost,IP:127.0.0.1\nextendedKeyUsage=serverAuth\n" "$host")

chmod 600 "$cert_dir/ca.key" "$cert_dir/server.key"
