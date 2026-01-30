# WhatsApp Blast Tool

Aplikasi desktop berbasis Python untuk mengirim pesan WhatsApp massal menggunakan Selenium Web Automation.

## Fitur
- **GUI Modern**: Dibuat menggunakan PyQt6.
- **Support Excel**: Upload dan preview data target (.xlsx).
- **Editor Pesan**: Mendukung format teks (Bold, Italic, dll) dan Dynamic Variables (misal: `{Name}`).
- **Kirim Gambar**: Bisa menyertakan lampiran gambar.
- **Environment Persistence**: Menyimpan sesi login WhatsApp Web Anda (tidak perlu scan QR setiap kali jalan).
- **Kontrol Pengiriman**: Pengaturan Delay (detik) dan Batas Maksimum Pesan.

## Cara Instalasi (Jika pindah komputer)

1. Pastikan Python 3 terinstall.
2. Buat virtual environment dan install dependencies:
   ```bash
   python3 -m venv venvwhatsapp
   ./venvwhatsapp/bin/pip install -r requirements.txt
   ```

## Cara Menjalankan

```bash
./venvwhatsapp/bin/python main.py
```

## Format Excel
Gunakan file `template.xlsx` sebagai acuan.
- Kolom **Phone** (Wajib): Nomor telepon dengan kode negara (contoh: `628123456789`).
- Kolom Lain (Opsional): Bisa digunakan sebagai variabel di pesan.

## Catatan Penting
- Aplikasi ini menggunakan **Google Chrome**. Pastikan Chrome sudah terinstall.
- Saat pertama kali jalan, Anda perlu scan QR Code WhatsApp Web. Sesi akan tersimpan untuk penggunaan berikutnya jika Path Environment benar.
- Jangan menutup jendela Chrome yang terbuka secara manual saat proses pengiriman sedang berlangsung.
