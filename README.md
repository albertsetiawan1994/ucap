# Ucap — Bicara, bukan mengetik

Ucap adalah aplikasi dikte suara untuk Windows 10/11. Tahan satu tombol pintas, bicara, lalu lepas:
teks yang sudah rapi langsung muncul di posisi kursor, di aplikasi apa pun (WhatsApp, Telegram, Slack,
Teams, Outlook, Word, Chrome, dan lainnya).

Suara Anda dikirim **sekali** ke Gemini API (Google), yang mengubahnya menjadi teks bersih: tanpa
"eh", "emm", "anu", lengkap dengan tanda baca, dan sesuai gaya tulisan aplikasi tujuan.

---

## Fitur

**Alur utama**
- **Tahan untuk bicara**: tahan `Ctrl+Win` (bisa diganti), bicara, lepas → teks disisipkan.
- **Mode bebas tangan**: ketuk tombol pintas **dua kali** cepat untuk mulai, ketuk **sekali** lagi untuk berhenti.
- **Esc** membatalkan rekaman kapan saja.
- **Bar melayang** kecil di tengah bawah layar aktif: gelombang suara langsung, lalu status "Memproses".
  Bar ini tidak pernah mengambil fokus dari aplikasi Anda.
- Rekaman lebih pendek dari ±0,3 detik atau yang hening diabaikan.
- Rekaman tetap berjalan ±0,3 detik setelah tombol dilepas, supaya kata terakhir tidak terpotong.
- Suara yang pelan dikeraskan otomatis (hingga 8×) sebelum dikirim, supaya kata yang diucapkan pelan tidak
  terlewat. Kata yang kurang jelas tetap ditulis sebagai tebakan terbaik, bukan dibuang.

**Pembersihan otomatis oleh Gemini**
- Transkripsi sesuai bahasa yang diucapkan, termasuk campuran dalam satu kalimat (Otomatis), atau pilih salah satu
  dari 21 bahasa, termasuk **Hokkien Medan** (campur Indonesia/Inggris, ditulis dengan ejaan Latin gaya chat
  Medan: `Gua ai khi pasar, lu mau ikut bo?`) dan **Hokkien (aksara Han)** (kata tanpa aksara umum ditulis dalam
  Pe̍h-ōe-jī). Mode Otomatis juga menulis Hokkien Indonesia dengan ejaan Latin.
- Aksara non-Latin diberi ejaan Latin dalam kurung: Mandarin → Pinyin, Hokkien → Pe̍h-ōe-jī, Jepang → romaji,
  Korea → romanisasi, lainnya → transliterasi umum. Contoh: `我们明天开会。(Wǒmen míngtiān kāihuì.)`.
  Bisa dimatikan di tab Umum. Berlaku juga untuk transkrip dan notulen rapat.
- Menghapus kata pengisi: eh, em, emm, anu, apa namanya, um, uh, like.
- Menambah tanda baca dan huruf kapital.
- Menerapkan koreksi lisan: "jam 5... eh maksudnya jam 6" → "jam 6"; "5, actually 6pm" → "6pm".
- Daftar yang diucapkan menjadi daftar bernomor/berpoin; ucapan panjang dibagi menjadi paragraf.
- Ejaan dari **Kamus pribadi** dipakai persis.
- **Gaya tulisan per aplikasi** (Formal / Santai / Sangat santai).
- Tidak pernah menjawab atau menuruti isi dikte — hanya menuliskannya.

**Menyisipkan teks**
- Clipboard Anda dicadangkan → teks ditempel dengan `Ctrl+V` → clipboard lama dikembalikan.
- Jika menempel tidak bisa (misalnya jendela tujuan berjalan sebagai Administrator), teks tetap ada di
  clipboard dan muncul pemberitahuan: tinggal tekan `Ctrl+V` sendiri.

**Fitur lanjutan**
- **Kamus pribadi**: nama klien, istilah teknis, singkatan. Bisa ditambah langsung dari Riwayat ("Tambah ke kamus").
- **Snippet**: frasa pemicu → isi panjang (tanda tangan email, tautan, alamat, bio). Diganti secara lokal,
  tidak peka huruf besar/kecil maupun tanda baca, baik saat diucapkan sendirian maupun di tengah kalimat.
- **Gaya per aplikasi**: dideteksi dari nama .exe aplikasi yang aktif. Bawaan: aplikasi pesan dan chat kerja =
  Santai, email/dokumen = Formal, plus gaya bawaan untuk aplikasi lain. Semua bisa diubah.
- **Riwayat**: 100 dikte terakhir (waktu, aplikasi, teks) dengan Salin / Sisipkan ulang. Disimpan di
  `%APPDATA%\Ucap\history.json`. Audio **tidak** disimpan, kecuali Anda menyalakan opsinya
  (file .wav di `%APPDATA%\Ucap\audio`, hanya 100 terakhir yang disimpan).

**Fitur tambahan**
- **Mode Perintah**: pilih teks, tahan `Alt+Win` (bisa diganti), ucapkan perintah ("buat lebih singkat",
  "terjemahkan ke Inggris"), lepas → teks terpilih diganti hasilnya.
- **Tempel dikte terakhir**: `Alt+Shift+Z` (bisa diganti) atau menu tray.
- **Perintah "kirim"** (mati bawaan, nyalakan di tab Umum): dikte yang diakhiri "tekan enter" / "press enter" menekan Enter setelah menempel.
- **Mati per aplikasi**: di tab Gaya per aplikasi pilih gaya *Mati* untuk aplikasi tertentu (mis. game).
- **Rapat**: rekam rapat lewat mikrofon (potongan 5 menit diproses di latar belakang), lalu dibuat notulen:
  ringkasan, poin penting, keputusan, tindak lanjut. Transkrip dan notulen disimpan di
  `%APPDATA%\Ucap\meetings.json`; audio tidak disimpan. Bagian yang gagal diproses bisa dicoba lagi.
  **Tanya notulen**: ajukan pertanyaan tentang semua rapat yang pernah dicatat.
  Suara dari speaker (peserta rapat online) ikut direkam lewat WASAPI loopback; matikan di tab Rapat jika
  tidak mau. Jika perangkat keluaran tidak mendukung, hanya mikrofon yang dipakai dan statusnya ditampilkan.
  Daftar rapat bisa dicari, diubah judulnya, dan diekspor ke file .md.
  **Tombol mulai/stop rapat**: `Alt+Shift+M` (bisa diganti di tab Umum).
  **Nama pembicara**: transkrip memakai nama asli bila ada petunjuk, yaitu perkenalan diri ("saya Andi dari
  tim IT"), dipanggil/dipersilakan ("silakan Pak Budi"), atau dari layar aplikasi rapat. Untuk yang terakhir,
  setiap 15 detik Ucap mengambil tangkapan layar jendela panggilan (Zoom, Teams, Webex, Google Meet di
  browser, dll., hanya bila judul jendelanya menunjukkan panggilan) lalu mengirimnya ke Gemini bersama
  audio; tidak disimpan. Jendela yang tertutup jendela lain ikut tertangkap apa adanya. Bisa dimatikan di tab
  Rapat. Nama yang sudah dikenali dipakai lagi di bagian rapat berikutnya.
  **Saran tindak lanjut (AI)**: bagian tambahan di notulen berisi saran dari AI (pertanyaan terbuka, risiko,
  agenda berikutnya), terpisah dari keputusan dan tindak lanjut yang benar-benar disepakati.
- **Peringatan tombol bentrok**: tombol pintas yang sama atau saling mencakup ditolak saat direkam, dan
  diberi tanda jika sudah tersimpan seperti itu.
- **Konteks jendela**: judul jendela aktif (mis. nama kontak di WhatsApp, nama file di VS Code) dikirim ke
  Gemini sebagai petunjuk ejaan. Bisa dimatikan di tab Umum.
- **Mode kode**: di editor kode (VS Code, Cursor, JetBrains, Visual Studio, Sublime, Notepad++, Zed) ucapan
  seperti "snake case user id" ditulis `user_id`, "main dot py" ditulis `main.py`.
- **Statistik**: kata hari ini / 7 hari, total, kecepatan rata-rata, hari beruntun.
- **Ekspor/impor pengaturan** (JSON, tanpa kunci API).

**Pengaturan** (klik ikon Ucap di system tray)
Tombol pintas, mikrofon, bahasa ucapan, kunci API Gemini (disimpan di **Windows Credential Manager**,
tidak pernah di file biasa; hingga 10 kunci, tersamar, masing-masing dengan **Uji kunci**), nama model, kamus, snippet, gaya per
aplikasi, jalankan saat Windows mulai, bunyi penanda. Tampilan dalam Bahasa Indonesia, bisa diganti ke English (tombol ID/EN).

---

## Mendapatkan kunci Gemini API gratis

1. Buka **https://aistudio.google.com/apikey** dan masuk dengan akun Google.
2. Klik **Create API key** (Buat kunci API), lalu salin kuncinya (diawali `AIza…`).
3. Buka Ucap → tab **Gemini** → isi label (mis. `Project A`) dan tempel kunci → **Tambah kunci** → **Uji kunci**.

### Beberapa kunci (hingga 10)

Tingkat gratis Gemini punya batas permintaan **per menit** dan **per hari**, dihitung **per project
Google Cloud** dan per model. Kunci-kunci dari project yang sama berbagi satu kuota, jadi menambah kunci
kedua dari project yang sama tidak membantu. Buat kunci di **project berbeda** milik Anda
(di aistudio.google.com/apikey pilih *Create API key in new project*), lalu tambahkan masing-masing di Ucap.

- Kunci dicoba **berurutan dari atas**; ubah urutan dengan ▲/▼. Centang di kiri menyalakan/mematikan kunci.
- Untuk setiap model, Ucap mencoba setiap kunci aktif. Pindah ke kunci berikutnya **hanya** jika kuota habis
  (429 / RESOURCE_EXHAUSTED). Setelah kuota semua kunci habis untuk model itu, Ucap pindah ke model berikutnya:
  model pilihan → `gemini-3.1-flash-lite` → `gemini-3.5-flash-lite` → `gemini-3.6-flash`
  (yang tidak ada di daftar akun Anda dilewati).
- Jika model sibuk (503 / high demand), tidak ditemukan (404), atau terlalu lambat, Ucap langsung pindah ke
  model berikutnya dengan urutan kunci yang sama.
- Kunci yang ditolak (tidak valid) ditandai **Tidak valid** dan dilewati sampai Anda menekan **Uji kunci** lagi.
- Batas per dikte: maksimal 8 percobaan dan ±30 detik. Jika semuanya gagal, muncul pesan yang jelas dan
  audio disimpan sementara di memori: klik bar melayang atau menu tray **Coba lagi dikte terakhir** untuk
  mencoba sekali lagi (audio tidak ditulis ke disk).

**Ingatan kuota** — supaya tidak membuang permintaan:
- Kuota **harian** habis → pasangan (kunci, model) itu dilewati sampai tengah malam waktu Pasifik
  (America/Los_Angeles, termasuk perubahan musim panas), yaitu saat Google mereset kuota harian.
  Tab Gemini menampilkan jam resetnya dalam waktu lokal Anda.
- Kuota **per menit** habis → jeda sesuai `retryDelay` dari Google, atau 60 detik.
- Status ini disimpan di `%APPDATA%\Ucap\quota.json` (tanpa kunci rahasia), jadi tetap berlaku setelah Ucap
  dibuka ulang. Tab Gemini juga menampilkan jumlah permintaan hari ini per kunci dan model (dihitung di komputer ini).
- Setelah dikte yang memakai kunci/model cadangan, bar melayang menampilkan sebentar
  mis. `via Project B · 3.1-flash-lite`, dan kolom **Via** di Riwayat mencatat kunci + model.

Pengguna versi lama: kunci tunggal yang sudah tersimpan otomatis menjadi kunci #1 berlabel **Utama**.

### Memilih model

- Model bawaan: **`gemini-3.5-flash-lite`** — tercepat untuk dikte (±1 detik per permintaan).
- Daftar model di tab Gemini diambil langsung dari akun Anda (tombol **Muat ulang daftar**, juga diperbarui
  saat **Uji kunci**). Hanya model teks yang ditampilkan, urut: flash-lite → flash → pro, versi terbaru dulu.
  Daftar disimpan, jadi tetap ada saat offline. Jika daftar gagal dimuat, dipakai daftar cadangan:
  `gemini-3.5-flash-lite`, `gemini-3.6-flash`, `gemini-3.1-flash-lite`.
- Anda juga bisa mengetik nama model sendiri.
- **Uji kunci** memeriksa kunci (daftar model) lalu mengirim satu permintaan kecil ke model yang dipilih,
  dan menampilkan waktu jawabnya. Model yang lebih besar (mis. `gemini-3.8-flash`) bisa jauh lebih lambat
  atau sering "sibuk". Daftar model diambil dari kunci valid pertama.
- Urutan cadangan model dijelaskan di bagian *Beberapa kunci* di atas.
- Nama model lama (`gemini-flash-latest`, `gemini-flash-lite-latest`, `gemini-2.5-flash`,
  `gemini-2.5-flash-lite`) sudah tidak tersedia untuk pengguna baru; pengaturan lama otomatis dipindah ke
  model bawaan.

---

## Menjalankan

Butuh **Python 3.11** (centang "Add Python to PATH" saat memasang).

Klik dua kali **`run.bat`**. Pertama kali, skrip ini membuat folder `.venv`, memasang paket yang
dibutuhkan, lalu menjalankan Ucap. Ikon Ucap (gelembung oranye) muncul di system tray, di pojok kanan bawah.

Menjalankan tes (opsional):

```
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q tests
```

## Membuat file .exe

Klik dua kali **`build_exe.bat`**. Skrip ini memasang PyInstaller, menjalankan tes, lalu membuat
**`dist\Ucap.exe`** — satu file, tanpa jendela konsol. File ini bisa disalin ke komputer lain tanpa Python.

### Pembaruan lewat GitHub Releases

Saat dibuka, Ucap memeriksa rilis terbaru di GitHub (sekali per start). Jika ada versi lebih baru, muncul
pemberitahuan dan menu tray **Unduh Ucap x.y.z…** membuka halaman rilis di browser. Ucap **tidak** mengunduh
atau menjalankan file sendiri; Anda yang mengunduh dan mengganti `Ucap.exe`. Bisa dimatikan di tab Umum.

Merilis versi baru:
1. Isi `UPDATE_REPO` di `ucap/updater.py` dengan `pemilik/nama-repo` (sekali saja).
2. Naikkan `__version__` di `ucap/__init__.py`, lalu jalankan `build_exe.bat`.
3. Buat rilis dengan tag yang sama (mis. `v1.2.0`) dan lampirkan `dist\Ucap.exe`:
   `gh release create v1.2.0 dist\Ucap.exe --title "Ucap 1.2.0" --notes "..."`

---

## Mengatasi masalah

**Mikrofon tidak terdengar / "Mikrofon sedang dipakai"**
- Buka *Settings → Privacy & security → Microphone*. Nyalakan **Microphone access** dan
  **Let desktop apps access your microphone**.
- Tutup aplikasi lain yang mungkin memakai mikrofon secara eksklusif (aplikasi rapat, perekam).
- Pilih mikrofon yang benar di Ucap → tab Umum → Mikrofon.

**Tombol pintas tidak bereaksi**
- Ucap memakai *keyboard hook* global. Beberapa antivirus menganggap ini mencurigakan (karena mirip
  keylogger) dan memblokirnya. Tambahkan Ucap (atau `Ucap.exe` / folder proyek) ke daftar pengecualian antivirus.
  Ucap tidak menyimpan atau mengirim apa pun yang Anda ketik — hook hanya memantau tombol pintas.
- Pastikan kombinasi tidak dipakai aplikasi lain. Ganti lewat tab Umum → **Rekam tombol…**.
- Hanya satu Ucap yang bisa berjalan pada satu waktu.

**Teks tidak tertempel di aplikasi tertentu**
- Windows melarang aplikasi biasa mengirim tombol ke jendela yang berjalan **sebagai Administrator**
  (misalnya Command Prompt atau Task Manager yang dibuka "Run as administrator"). Ucap mendeteksinya dan
  meninggalkan teks di clipboard — tekan `Ctrl+V` sendiri. Atau jalankan Ucap sebagai Administrator juga.
- Beberapa aplikasi (game, remote desktop) menolak tempel dari `Ctrl+V`. Teksnya ada di Riwayat untuk disalin.

**Menu Start terbuka saat melepas tombol**
- Ucap mengirim satu tombol "kosong" agar menu Start tidak terbuka. Jika masih terjadi, ganti tombol pintas
  (misalnya `Ctrl+Alt` atau `Right Ctrl`).

**"Tidak ada koneksi internet ke Gemini"**
- Ucap butuh internet untuk mengirim audio ke Gemini. Periksa koneksi, proxy, atau firewall kantor.

**"Kunci API Gemini tidak valid" / "Model tidak ditemukan"**
- Salin ulang kunci dari aistudio.google.com/apikey, simpan, lalu klik **Uji kunci**.
- Kembalikan nama model ke `gemini-3.5-flash-lite`, atau klik **Muat ulang daftar** dan pilih dari daftar.

**"Gemini sedang sibuk atau terlalu lambat"**
- Model sedang ramai (503 / high demand). Ucap sudah mencoba satu model cadangan; tunggu sebentar, atau pilih
  model flash-lite yang lebih ringan.

---

## Privasi

- Kunci API hanya disimpan di Windows Credential Manager (layanan "Ucap", satu entri per kunci).
  Label, urutan dan status kunci ada di `settings.json`; kunci rahasia tidak pernah ditulis ke pengaturan,
  log, riwayat, atau `quota.json`.
- Audio dikirim ke Google Gemini untuk diproses dan tidak disimpan di komputer, kecuali Anda menyalakan opsinya.
- Pengaturan dan riwayat ada di `%APPDATA%\Ucap`. Hapus folder itu untuk mengatur ulang.

## Struktur kode

| Modul | Isi |
|---|---|
| `ucap/audio.py` | Rekam mikrofon 16 kHz mono, deteksi hening/terlalu pendek, WAV |
| `ucap/hotkey.py` | Mesin status tahan / ketuk-dua-kali / Esc + hook keyboard global |
| `ucap/gemini_client.py` | Prompt sistem, strategi kunci → model per dikte, pemetaan pesan galat |
| `ucap/keypool.py` | Daftar kunci, ingatan kuota (reset tengah malam Pasifik), hitungan permintaan |
| `ucap/snippets.py` | Pembersihan keluaran + ekspansi snippet |
| `ucap/inserter.py` | Cadangkan clipboard → Ctrl+V → kembalikan; deteksi jendela admin |
| `ucap/styles.py` | Gaya per aplikasi dan deteksi aplikasi aktif |
| `ucap/storage.py` | Pengaturan, riwayat, kunci API (keyring), jalankan saat Windows mulai |
| `ucap/ui/` | Bar melayang, jendela pengaturan, ikon tray, tema |
| `tests/` | Tes pytest (Gemini di-mock) |
