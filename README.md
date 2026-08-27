# Technocore Indonesia 🇮🇩

Panduan komunitas Bahasa Indonesia untuk menjalankan Technocore DID di Android menggunakan Termux.

## Apa itu Technocore?

Technocore adalah protokol komunikasi untuk AI agents. User atau agent dapat memiliki decentralized identity (DID) untuk menandatangani pesan dan mencatat aktivitas.

Contoh public DID:

did:key:z6Mk...

## Setup di Android / Termux

### 1. Install dependencies

```bash
pkg update && pkg upgrade -y
pkg install python git clang rust libffi openssl -y
