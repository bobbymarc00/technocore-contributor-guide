# 🇮🇩 Technocore Indonesia

> A community-built Indonesian guide for running Technocore DID directly from Android using Termux.

[![Platform](https://img.shields.io/badge/Platform-Android-green)](https://www.android.com/)
[![Terminal](https://img.shields.io/badge/Terminal-Termux-black)](https://termux.dev/)
[![Python](https://img.shields.io/badge/Python-3.x-blue)](https://www.python.org/)
[![Contribution](https://img.shields.io/badge/Technocore-Contribution-brightgreen)](#verified-contribution)
[![Language](https://img.shields.io/badge/Language-Bahasa%20Indonesia-red)](#)

---

## ✨ About This Project

**Technocore Indonesia** adalah panduan komunitas untuk membantu pengguna Indonesia mencoba Technocore DID dari perangkat Android.

Fokus utama repository ini:

- setup Technocore melalui **Termux**
- membuat dan menggunakan **DID**
- mengirim signed message
- mencatat public contribution
- troubleshooting `cryptography` pada Python 3.14 / Termux
- backup identity dengan aman

Tujuannya adalah menurunkan barrier bagi pengguna yang tidak memiliki VPS atau PC tetapi ingin belajar dan berkontribusi ke ekosistem Technocore.

> [!NOTE]
> Repository ini merupakan **community contribution** dan bukan dokumentasi resmi Flop Labs atau Technocore.

---

## 🧠 What is a DID?

Technocore menggunakan decentralized identity atau **DID** sebagai identitas public untuk menandatangani aktivitas.

Format public DID terlihat seperti:

```text
did:key:z6Mk...
```

DID dapat digunakan untuk menghubungkan berbagai signed activity dengan identity yang sama.

---

## 🔐 Security First

> [!WARNING]
> Jangan pernah membagikan file atau credential privat kepada siapa pun.

### Aman untuk dibagikan

```text
did:key:z6Mk...
```

Public DID memang dibuat untuk menjadi public identifier.

### Jangan pernah dibagikan

```text
identity.pem
private key
passphrase
seed phrase
```

`identity.pem` adalah bagian penting dari identity lokal.

Jangan pernah commit file tersebut ke GitHub.

---

# 🚀 Quick Start — Android / Termux

## 1. Install Termux Dependencies

Buka Termux dan jalankan:

```bash
pkg update && pkg upgrade -y
pkg install python git clang rust libffi openssl python-cryptography -y
```

Cek instalasi:

```bash
python --version
git --version
```

---

## 2. Clone Technocore DID Starter

```bash
cd ~
git clone https://github.com/zunmax/technocore-did-starter.git
cd technocore-did-starter
```

---

## 3. Create Python Environment

Untuk Termux dengan Python terbaru:

```bash
python -m venv --system-site-packages .venv
source .venv/bin/activate
```

Cek `cryptography`:

```bash
python -c "import cryptography; print(cryptography.__version__)"
```

Jika keluar nomor versi tanpa error, environment siap digunakan.

---

# 🪪 Create Your Technocore DID

Jalankan:

```bash
python technocore_agent.py init
```

Kamu akan diminta membuat passphrase.

Gunakan passphrase minimal 12 karakter dan simpan dengan aman.

Setelah berhasil, terminal akan menampilkan DID seperti:

```text
did:key:z6Mk...
```

> [!IMPORTANT]
> Jangan jalankan `init` lagi jika kamu ingin mempertahankan identity yang sama.

Untuk melihat DID yang sudah ada:

```bash
python technocore_agent.py did
```

Masukkan passphrase identity ketika diminta.

---

# 📡 Send Your First Signed Message

Contoh check-in ke Technocore lobby:

```bash
python technocore_agent.py say lobby "Hello Technocore, joining as a new contributor from Indonesia."
```

Response Technocore dapat berisi data seperti:

```text
room
seq
timestamp
from
nonce
text
```

Contoh:

```text
room: lobby
seq: 123456
from: did:key:z6Mk...
```

`seq` adalah sequence number aktivitas tersebut.

---

# 🛠️ Create a Useful Contribution

Contribution tidak harus berupa code.

Beberapa contoh contribution:

| Type | Example |
|---|---|
| 📚 Tutorial | Guide setup Technocore |
| 🌐 Translation | Documentation Bahasa Indonesia |
| 🧵 Content | Educational X thread |
| 🔬 Research | Analysis / protocol research |
| 🧰 Tool | Verification / utility tool |
| 🎥 Video | Setup tutorial |
| 🖼️ Infographic | DID / Technocore explanation |

Prinsip utamanya:

> Build something that actually helps another person understand, use, or discover Technocore.

---

# 📝 Record a Contribution

Setelah contribution dipublikasikan dan memiliki public URL, record menggunakan DID yang sama.

Contoh:

```bash
python technocore_agent.py say technocore "I published a Technocore contribution: YOUR_PUBLIC_URL"
```

Ganti:

```text
YOUR_PUBLIC_URL
```

dengan URL contribution sebenarnya.

Setelah berhasil, cari:

```json
"posted": {
  "seq": 123456
}
```

Simpan sequence tersebut.

---

# ✅ Verified Contribution

Repository ini sendiri merupakan Technocore community contribution untuk membantu pengguna Indonesia menjalankan DID dari Android.

### Contribution

https://github.com/bobbymarc00/technocore-indonesia

### Technocore Record

| Field | Value |
|---|---|
| Room | `technocore` |
| Sequence | `996657` |
| Status | ✅ **VERIFIED** |
| Contribution | Android / Termux Indonesian Guide |

Contribution tersebut telah diverifikasi terhadap public Technocore record.

---

# 📱 Why Android?

Banyak guide crypto / agent infrastructure mengasumsikan pengguna memiliki:

```text
Linux VPS
Desktop
Mac
Dedicated server
```

Padahal untuk aktivitas dasar DID dan signed messaging, pengguna Android juga bisa ikut berpartisipasi.

Dengan Termux:

```text
Android
   ↓
Termux
   ↓
Python
   ↓
Technocore DID
   ↓
Signed Activity
```

Ini membuat onboarding lebih mudah bagi komunitas mobile-first.

---

# ♻️ Returning Later

Setelah setup pertama selesai, kamu tidak perlu install ulang semuanya.

Buka Termux:

```bash
cd ~/technocore-did-starter
source .venv/bin/activate
```

Kemudian cek identity:

```bash
python technocore_agent.py did
```

Atau kirim activity baru:

```bash
python technocore_agent.py say lobby "Hello again Technocore."
```

---

# 💾 Backup Your Identity

File penting:

```text
identity.pem
```

Backup file tersebut ke tempat privat.

Simpan passphrase secara terpisah.

Jika pindah HP atau komputer, identity yang sama dapat dipertahankan selama kamu memiliki identity file dan passphrase yang benar.

> [!CAUTION]
> Jangan pernah upload `identity.pem` ke GitHub, Google Drive publik, Discord, Telegram, atau tempat publik lainnya.

---

# 🧩 Termux Python 3.14 Troubleshooting

Pada beberapa perangkat Android, `cryptography` yang diinstall langsung lewat pip dapat menghasilkan error seperti:

```text
ImportError: dlopen failed: cannot locate symbol "PyModule_Type"
```

Solusi yang berhasil digunakan:

```bash
pip uninstall cryptography -y
pkg install python-cryptography -y
```

Kemudian buat ulang environment:

```bash
deactivate
rm -rf .venv

python -m venv --system-site-packages .venv
source .venv/bin/activate
```

Test:

```bash
python -c "import cryptography; print(cryptography.__version__)"
```

Jika versi `cryptography` muncul, coba kembali:

```bash
python technocore_agent.py did
```

---

# 🗺️ Contribution Flow

```text
Create DID
    ↓
Send signed activity
    ↓
Build something useful
    ↓
Publish contribution
    ↓
Record public URL
    ↓
Receive sequence number
    ↓
Verify contribution
    ↓
Build contributor history
```

---

# 🤝 Contributing

Jika kamu menemukan:

- masalah Termux
- troubleshooting baru
- improvement dokumentasi
- typo
- solusi Android
- integration baru

silakan fork repository atau buat contribution sendiri.

Semakin banyak dokumentasi lokal, semakin mudah pengguna baru memahami teknologi ini.

---

# ⚠️ Disclaimer

This repository is a community-created educational resource.

It is **not official documentation** from Flop Labs or Technocore.

Creating a DID, sending activity, or making contributions does **not guarantee**:

```text
$FLOP allocation
airdrop eligibility
token rewards
financial rewards
```

Final eligibility, if any, is determined by the relevant project team.

---

## 🇮🇩 Built for the Indonesian Technocore Community

From Android.

No VPS required for basic DID contribution workflow.
