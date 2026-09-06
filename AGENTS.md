# AGENTS.md — Aturan kerja untuk AI agent di project ini

> **Baca file ini sampai habis sebelum menulis kode.**
> File ini adalah satu-satunya sumber kebenaran soal *cara* mengerjakan project
> ini. Dimuat otomatis oleh OpenCode, dan tetap berlaku setelah pergantian
> agent, model, atau sesi.
>
> Kalau instruksi di chat bertentangan dengan file ini: **file ini menang**,
> kecuali user secara eksplisit bilang "abaikan aturan X" — dan kalau itu
> terjadi, catat perubahannya kembali ke sini.

---

## 0. Kontrak sesi (wajib, 60 detik pertama)

Sebelum tool call apa pun yang mengubah file:

1. Baca `AGENTS.md` (file ini) dan `docs/DECISIONS.md`.
2. Jalankan orientasi:
   ```bash
   cd ops_views
   env/bin/python manage.py check
   ls apps/                      # module apa saja yang ada
   git log --oneline -10         # apa yang baru terjadi
   ```
3. Kalau permintaan user menyentuh keputusan di `docs/DECISIONS.md`,
   **sebut keputusannya** sebelum mengubahnya, jangan diam-diam dibalik.

Sebelum melapor selesai, jalankan **gate** di [§7](#7-definition-of-done).

---

## 1. Identitas project

| | |
|---|---|
| Nama | ops_views |
| Alias publik | `cms_ops` — tampilan admin & komunikasi (`DJANGO_SITE_TITLE`, default "CMS Ops"). Identifier internal TIDAK ikut berubah, lihat ADR-014 |
| Framework | Django 6.1, Python 3.14 |
| Admin UI | django-unfold 0.104.1 |
| Database | **PostgreSQL 17 — satu-satunya engine yang didukung** |
| Config | django-environ, 12-factor |
| Auth | custom user model, login pakai email |
| Arsitektur | modular per fitur, disiapkan untuk dipecah jadi microservice |
| Working dir | `ops_views/` (tempat `manage.py`) — **bukan** root repo |
| Python | `env/bin/python` dari dalam `ops_views/` |
| Vault project | `ops_views` (knowledge vault: Decisions/Bugs/Features) |

---

## 2. Aturan yang tidak boleh dilanggar

Tiap aturan menutup satu cara yang sudah terbukti merusak project ini.

### R0 — Jangan membuat container database baru.
Mesin ini sudah punya container `postgres` (port host **55432**) yang dipakai
bersama beberapa project. Project ini memakai database `ops_views` di dalamnya.
Jangan menambah `docker-compose.yml`, jangan `docker run postgres`, jangan
menghapus atau me-restart container itu tanpa izin - project lain ikut mati.

### R1 — PostgreSQL saja. Jangan pernah kembali ke SQLite.
`base.py` sengaja **tidak punya default** untuk `DATABASE_URL` dan menolak
engine non-postgres. Itu bukan bug, jangan "diperbaiki". Kalau Postgres mati,
hidupkan container bersamanya: `docker start postgres`. Jangan mengakali
dengan sqlite.

### R2 — Jangan pernah menulis secret ke dalam kode.
Semua nilai lewat `env(...)` di `config/settings/`. `.env` **tidak pernah**
di-commit dan **tidak pernah** ditampilkan isinya di output/chat/PR. Kalau
butuh key baru: tambahkan ke `.env.example` dengan nilai placeholder + tabel
env var di README.

### R3 — Jangan pernah `import` model milik module lain.
```python
from apps.accounts.models import User          # ❌ mengunci dua module ke satu DB
from apps.accounts import selectors            # ✅
```
Lintas module hanya lewat `selectors.py` (baca) dan `services.py` (tulis).

### R4 — Jangan pernah bikin ForeignKey lintas module.
Simpan `models.UUIDField(db_index=True)`, bukan `ForeignKey`. FK ke tabel module
lain membuat keduanya mustahil dipisah.

### R5 — Perubahan state hanya lewat `services.py`.
View, admin, management command, signal — semua memanggil service. Tidak ada
`.save()`, `.create()`, atau `.delete()` di luar `services.py`.
Alasan: validasi, transaksi, dan publish event harus di satu tempat.

### R6 — Efek samping lintas module lewat event bus, bukan panggilan langsung.
Publish di `services.py` via `transaction.on_commit`. Subscribe di
`handlers.py`, didaftarkan dari `AppConfig.ready()`.

### R7 — `apps.common` tidak boleh bergantung pada feature module manapun.
Arahnya satu: feature → common. Tidak pernah sebaliknya. Graf harus asiklik.

### R8 — Jangan bikin daftar terpusat baru.
Sidebar dari `NAVIGATION` tiap module. URL satu `include()` per module. Kalau
kamu tergoda bikin `apps/registry.py` atau `ALL_FEATURES = [...]`, berhenti —
itu melanggar desainnya.

### R9 — Jangan longgarkan setting keamanan supaya sesuatu "jalan".
`DEBUG=True` di production, `ALLOWED_HOSTS=["*"]`, mematikan CSRF, menurunkan
`SECURE_*`, `--fail-level` diturunkan — semua dilarang. Kalau `check --deploy`
gagal, perbaiki penyebabnya.

### R10 — Jangan hapus atau ubah migrasi yang sudah ada.
Selalu buat migrasi baru. Satu-satunya pengecualian: migrasi yang **belum
pernah** dijalankan di mana pun kecuali mesin kamu sendiri, dan user setuju.

---

## 3. Pola kode wajib

### Struktur satu feature module

```
apps/<nama>/
├── __init__.py
├── apps.py           AppConfig, ready() import handlers
├── models.py         bentuk data - internal, tidak diimpor module lain
├── services.py       WRITE API  - satu-satunya jalur ubah state
├── selectors.py      READ API   - tidak boleh mengubah apa pun
├── events.py         fakta yang dipublikasikan (past tense)
├── handlers.py       langganan ke event module lain
├── navigation.py     NAVIGATION - kontribusi sidebar
├── admin.py          subclass BaseModelAdmin (Unfold)
├── urls.py           opsional, kalau ada HTTP endpoint
├── migrations/
└── tests/
```

Contoh referensi yang sudah benar: [apps/accounts/](apps/accounts/).
**Tiru struktur itu**, jangan mengarang layout baru.

### Model

```python
from apps.common.models import BaseModel      # UUID pk + created_at/updated_at

class Incident(BaseModel):
    title = models.CharField(max_length=200)
    reported_by_id = models.UUIDField(db_index=True)   # R4: bukan ForeignKey
```

### Service

```python
@transaction.atomic
def resolve_incident(*, incident: Incident, note: str) -> Incident:
    incident.resolved_at = timezone.now()
    incident.save(update_fields=["resolved_at", "updated_at"])
    transaction.on_commit(
        lambda: publish(events.incident_resolved(incident_id=incident.pk))
    )
    return incident
```

Aturan bentuk: **keyword-only argument** (`*,`), ada type hint, ada docstring
yang menjelaskan *kenapa*, bukan *apa*.

### Admin

```python
from apps.common.admin import BaseModelAdmin   # ❌ jangan admin.ModelAdmin biasa
```
`admin.ModelAdmin` polos akan tampil tanpa styling Unfold dan merusak konsistensi
tampilan.

### Settings

Nilai baru selalu:
```python
FOO = env("APP_FOO", default="...")     # + baris di .env.example + tabel README
```
Untuk production yang wajib ada: **jangan beri `default`** — biarkan gagal start.

---

## 4. Gaya menulis kode & Penerapan Prinsip SOLID

### Prinsip SOLID dalam Arsitektur Modular Ini

- **S — Single Responsibility Principle (SRP):**
  Pemisahan file modul bersifat ketat: `models.py` hanya mendefinisikan skema data;
  `services.py` hanya menangani operasi WRITE, transaksi DB, dan publikasi event;
  `selectors.py` hanya operasi READ/query tanpa efek samping; `handlers.py` hanya
  berlangganan event; `admin.py` hanya antarmuka Unfold. Fungsi service atau selector
  tidak boleh menjadi god-function — pisahkan menjadi fungsi-fungsi spesifik per use-case.
- **O — Open/Closed Principle (OCP):**
  Modul terbuka untuk ekstensi namun tertutup untuk modifikasi dari luar. Penambahan
  efek samping lintas modul diintegrasikan melalui event bus (`publish` dan `handlers.py`),
  bukan dengan mengubah service modul lain. Pendaftaran navigasi terdistribusi via
  `navigation.py` tanpa registry terpusat (R8).
- **L — Liskov Substitution Principle (LSP):**
  Semua model turunan wajib mematuhi kontrak `BaseModel` (UUID pk, `created_at`,
  `updated_at`). Semua admin model wajib mewarisi `BaseModelAdmin` dari `apps.common.admin`
  agar konsistensi tema Unfold terjaga.
- **I — Interface Segregation Principle (ISP):**
  Antarmuka publik di `selectors.py` dan `services.py` dibuat ramping, spesifik, dan
  terfokus pada kebutuhan pemanggil. Selalu gunakan keyword-only arguments (`*,`) dan
  type hints agar parameter eksplisit dan tidak memaksa pemanggil mengirim dependensi tak perlu.
- **D — Dependency Inversion Principle (DIP):**
  Modul tingkat tinggi tidak bergantung pada detail internal model atau tabel modul lain.
  Dilarang import model atau ForeignKey lintas modul (R3 & R4); komunikasi hanya lewat
  kontrak fungsi `selectors`, `services`, atau event bus. `apps.common` tidak pernah
  bergantung pada modul fitur mana pun (R7).

### Konvensi Penulisan

- Ikuti gaya file di sekitarnya. Jangan bawa konvensi dari project lain.
- Komentar menjelaskan **kenapa**, bukan **apa**. Jangan komentari kode yang
  sudah jelas sendiri.
- Type hint di semua fungsi publik (`services`, `selectors`, `views`).
- String user-facing dibungkus `gettext_lazy as _`.
- Tanpa dependency baru kecuali user menyetujui secara eksplisit
  ([§6](#6-kapan-harus-bertanya)). Kalau disetujui: pin `==` di
  `requirements/base.txt` (jangan `>=`, jangan `pip freeze`), lalu perbarui
  tabel versi di README bagian "Mengelola dependency".
- Minimum yang didukung: Python 3.12, PostgreSQL 15. Jangan pakai fitur di luar
  itu tanpa menaikkan angkanya di README dan `docs/DECISIONS.md`.
- Nama event: `<module>.<past_tense>` — `accounts.user_registered`.


---

## 5. Anti-pattern yang sering muncul dari agent baru

Ini daftar hal yang **berulang kali** dicoba agent yang tidak membaca konteks:

| ❌ Yang sering dilakukan | ✅ Yang benar |
|---|---|
| Bikin `docker-compose.yml` / `docker run postgres` sendiri | Pakai container `postgres` yang sudah ada (R0) |
| Menambah fallback `sqlite` "supaya gampang" | Biarkan gagal. Hidupkan Postgres. (R1) |
| `SECRET_KEY = "django-insecure-..."` langsung di settings | `env("DJANGO_SECRET_KEY")` (R2) |
| Menyatukan settings jadi satu `settings.py` lagi | Tetap `base/local/production` |
| Rename `config/` kembali jadi `ops_views/` | Nama `config` disengaja, lihat DECISIONS |
| `from apps.x.models import Y` di module lain | Lewat `selectors` (R3) |
| `ForeignKey` ke model module lain | `UUIDField` (R4) |
| Query/`.save()` langsung di dalam view | Lewat `services`/`selectors` (R5) |
| `admin.ModelAdmin` polos | `BaseModelAdmin` dari `apps.common.admin` |
| Menaruh `"unfold"` setelah `django.contrib.admin` | Harus **sebelum**, kalau tidak tema hilang |
| Bikin `User` model kedua atau balik ke user bawaan | `AUTH_USER_MODEL` sudah dikunci |
| Integer/auto pk di model baru | `BaseModel` (UUID) |
| `ALLOWED_HOSTS = ["*"]` biar cepat | Isi domain sebenarnya (R9) |
| Edit migrasi lama | Bikin migrasi baru (R10) |
| Menambah `requirements.txt` entry tanpa pin | Pin `==` di `requirements/base.txt` |
| `pip freeze > requirements.txt` | Itu menimpa pointer dan menduplikasi `base.txt`. Edit `requirements/base.txt` manual |
| Menaikkan banyak paket sekaligus | Satu paket per commit, `make verify` tiap kali |
| Menjalankan `manage.py` dari root repo | `cd ops_views` dulu |
| `python manage.py` (python sistem) | `env/bin/python manage.py` |

---

## 6. Kapan harus bertanya

**Kerjakan langsung** tanpa bertanya: menambah field/model/module, menulis test,
memperbaiki bug, menambah endpoint, update dokumentasi.

**Berhenti dan tanya user** kalau menyentuh salah satu dari ini:

- Menambah dependency baru
- Mengubah `AUTH_USER_MODEL` atau apa pun di `apps/accounts/models.py`
- Migrasi destruktif (drop kolom/tabel, `RunSQL` yang menghapus data)
- Mengubah salah satu dari sepuluh aturan di [§2](#2-aturan-yang-tidak-boleh-dilanggar)
- Membalik keputusan yang tercatat di `docs/DECISIONS.md`
- Apa pun yang menyentuh production: deploy, migrasi di server, rotasi secret
- Menambah service infrastruktur baru (Redis, Celery, broker, dsb.)

Cara bertanya: sebutkan **pilihan + rekomendasi**, jangan buka diskusi terbuka.

---

## 7. Definition of Done

Sebuah tugas belum selesai sebelum **semua** ini hijau. Jalankan dari `ops_views/`:

```bash
env/bin/python manage.py check
env/bin/python manage.py makemigrations --check --dry-run   # tidak ada migrasi tertinggal
DJANGO_FAST_PASSWORD_HASHER=True env/bin/python manage.py test apps
DJANGO_SETTINGS_MODULE=config.settings.production \
  DJANGO_ALLOWED_HOSTS=ops.example.com \
  env/bin/python manage.py check --deploy --fail-level WARNING
```

Ditambah:

- [ ] Ada test untuk perilaku baru, di `apps/<module>/tests/`
- [ ] `.env.example` + tabel env var README diperbarui kalau ada key baru
- [ ] `docs/DECISIONS.md` bertambah entri kalau ada keputusan arsitektur
- [ ] Tidak ada secret, `.env`, atau dump database di diff
- [ ] Laporan ke user **jujur**: kalau ada yang gagal atau dilewati, sebutkan

Jangan bilang "selesai" berdasarkan penalaran saja — **jalankan perintahnya**.

---

## 8. Perintah yang sering dipakai

```bash
cd ops_views

# PostgreSQL: container `postgres` BERSAMA, dipakai project lain juga.
# Project ini tidak punya container sendiri dan tidak boleh membuatnya.
make db-status                                # jalan & healthy?
make db-logs
docker start postgres                         # kalau mati

env/bin/python manage.py runserver
env/bin/python manage.py makemigrations
env/bin/python manage.py migrate
env/bin/python manage.py createsuperuser   # diminta EMAIL
env/bin/python manage.py dbshell
DJANGO_FAST_PASSWORD_HASHER=True env/bin/python manage.py test apps

curl -s localhost:8000/health/ready/          # cek koneksi DB
```

Perintah **terlarang** tanpa izin eksplisit user:
`docker rm` / `docker volume rm` apa pun (container `postgres` dipakai project
lain - menghapusnya menghancurkan data mereka), `DROP DATABASE` selain
`ops_views`, `manage.py flush`, `manage.py sqlflush`,
`DROP`/`TRUNCATE` apa pun, `git push --force`, `rm -rf`, edit file di server.

---

## 9. Serah terima antar sesi / antar agent

Konteks hilang setiap ganti sesi atau model. Yang menjaganya bukan ingatan,
tapi file:

| File | Isi | Kapan diperbarui |
|---|---|---|
| `AGENTS.md` | Aturan cara kerja (file ini) | Saat aturan berubah |
| `docs/DECISIONS.md` | **Kenapa** sesuatu dibuat begitu | Setiap keputusan arsitektur |
| `README.md` | Cara setup & deploy | Saat setup berubah |
| `.env.example` | Semua env var yang dikenal | Setiap tambah key |
| test suite | Perilaku yang dijamin | Setiap tambah perilaku |

**Kewajiban di akhir tugas:** kalau kamu membuat keputusan yang agent berikutnya
bisa salah tebak, tulis ke `docs/DECISIONS.md`. Satu entri, format ADR pendek.
Kalau tidak ditulis, keputusan itu akan dibalik oleh agent berikutnya —
itu sudah pernah terjadi dan itulah sebabnya file ini ada.

**Jangan** simpan konteks project hanya di memory pribadi agent, di komentar
chat, atau di nama branch. Konteks yang tidak ada di repo dianggap tidak ada.

---

## 10. Siklus Code Review & Quality Control (QC)

Setiap perubahan fitur non-trivial wajib melewati siklus review untuk menjaga
kualitas kode (clean code, SOLID), konsistensi arsitektur (R0–R10), dan keamanan
sistem sebelum dinyatakan selesai.

### Peran dan Tanggung Jawab

| Peran | Tugas Utama | Batasan Keras |
|---|---|---|
| **Lead** | Membuat rencana (`Plans/`), menganalisa review, memberi arahan prioritas perbaikan | Tidak menulis kode aplikasi |
| **Coder** | Menulis kode sesuai rencana, mengeksekusi revisi dari review | Tidak `git push` otomatis; tidak merancang ulang |
| **Reviewer** | Mengaudit kepatuhan arsitektur, security, clean code, dan verifikasi gate | Tidak mengubah file kode aplikasi; tidak commit/push |

### Alur Kerja & Status Note di Obsidian

Setiap proses review dicatat pada vault Obsidian di folder `ops_views/Reviews/`
menggunakan template `_templates/review.md`:

```
ops_views/Reviews/YYYY-MM-DD-<slug>-<feature>-review.md
```

Status note review berjalan dalam 4 tahap:

1. `pending-lead` (Reviewer):
   Reviewer mengaudit diff terhadap rencana, kepatuhan SOLID, standar keamanan,
   dan aturan repositori, lalu menjalankan gate verifikasi read-only (perintah test,
   linter, dan check resmi repositori), mencatat temuan terstruktur di tabel
   *Temuan & Action Items*, dan mengatur status ke `pending-lead`.
2. `ready-for-coder` (Lead):
   Lead menganalisa temuan, memvalidasi blocker vs minor, mengisi *Catatan & Analisa Lead*
   dengan arahan solusi konkret, dan mengatur status ke `ready-for-coder`.
3. `revised` (Coder):
   Coder mengerjakan perbaikan, menjalankan gate verifikasi repositori hingga hijau,
   melakukan commit lokal, meminta konfirmasi `git push` dari user, lalu mencatat commit hash &
   status push di *Riwayat Revisi Coder*, dan mengatur status ke `revised`.
4. `closed` (Reviewer):
   Reviewer melakukan verifikasi ulang akhir terhadap commit perbaikan dan test suite.
   Jika seluruh blocker tuntas, status diubah menjadi `closed`.

### Kebijakan Git Push pada Revisi
Coder dilarang menjalankan `git push` secara otomatis. Coder membuat commit lokal,
menampilkan instruksi push manual untuk user (`git push origin <branch>`), dan baru
mencatat konfirmasi push ke note Obsidian setelah user menyatakan push selesai.

