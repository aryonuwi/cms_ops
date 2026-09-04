# CMS Ops

> Alias publik project ini: **`cms_ops`** — dipakai untuk judul admin
> (`DJANGO_SITE_TITLE`) dan komunikasi. Identifier internal **tidak berubah**:
> repo `ops_views`, package `config`, database `ops_views`
> (lihat [ADR-014](docs/DECISIONS.md#adr-014--alias-publik-cms_ops-identifier-internal-tidak-berubah)).

Django 6.1 operations panel with a [Unfold](https://unfoldadmin.com/) admin, split
settings per environment, and a **modular-per-feature** layout designed so any
feature can later be lifted out into its own service.

---

## Daftar isi

0. [Aturan untuk AI agent / developer baru](#aturan-untuk-ai-agent--developer-baru)
1. [Ringkasan stack](#ringkasan-stack)
2. [Struktur project](#struktur-project)
3. [Arsitektur modular](#arsitektur-modular)
4. [Menjalankan di lokal](#menjalankan-di-lokal)
5. [Konfigurasi environment](#konfigurasi-environment)
6. [Database](#database)
7. [Menambah feature module baru](#menambah-feature-module-baru)
8. [Mengelola dependency](#mengelola-dependency)
9. [Testing](#testing)
10. [Setup server (production)](#setup-server-production)
11. [Checklist keamanan](#checklist-keamanan)
12. [Troubleshooting](#troubleshooting)

---

## Aturan untuk AI agent / developer baru

Project ini punya beberapa keputusan yang **tidak boleh dibalik tanpa sengaja** —
PostgreSQL tanpa fallback, batas antar-module, settings fail-closed. Supaya
keputusan itu bertahan melewati pergantian sesi, developer, agent, atau model AI,
aturannya disimpan di repo, bukan di ingatan siapa pun:

| File | Isi |
|---|---|
| [`AGENTS.md`](AGENTS.md) | Aturan kerja + 10 larangan + Definition of Done. Dimuat otomatis oleh OpenCode |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | **Kenapa** tiap keputusan diambil (ADR) |

**Kalau kamu agent AI yang baru masuk ke repo ini: baca `AGENTS.md` dulu, sampai
habis, sebelum menulis kode.** Lalu sebelum melapor selesai, jalankan gate-nya:

```bash
make verify
```

Kalau kamu mengambil keputusan arsitektur baru, tulis satu entri ADR di
`docs/DECISIONS.md`. Keputusan yang tidak tertulis akan dibalik oleh agent
berikutnya.

---

## Ringkasan stack

| Komponen | Pilihan |
|---|---|
| Framework | Django 6.1 |
| Admin UI | django-unfold 0.104.1 |
| Config | django-environ (12-factor, `.env` / env vars) |
| Database | **PostgreSQL 17 di semua environment** via `psycopg[binary]` 3.3 |
| Postgres lokal | Container `postgres` bersama, port 55432 |
| App server | Gunicorn (WSGI) atau Uvicorn (ASGI) |
| Auth | Custom user model, login pakai **email** |
| Python | 3.14 |

---

## Struktur project

```
ops_views/                    # repo root - semua perintah dijalankan dari sini
├── manage.py
├── Makefile                  # make db-status / migrate / test / verify
├── AGENTS.md                 # aturan kerja untuk AI agent  <-- baca ini
├── README.md
├── .env                      # rahasia lokal (gitignored)
├── .env.example              # template, aman di-commit
├── .gitignore
├── env/                      # virtualenv (gitignored)
├── docs/
│   └── DECISIONS.md          # ADR - kenapa tiap keputusan diambil
├── requirements.txt
├── requirements/
│   ├── base.txt              # dependency semua environment
│   ├── local.txt
│   └── production.txt
├── config/                   # project config, BUKAN tempat business logic
│   ├── settings/
│   │   ├── base.py           # shared, tanpa satu pun secret literal
│   │   ├── local.py          # development
│   │   └── production.py     # hardened, fail-closed
│   ├── urls.py               # hanya mounting point tiap module
│   ├── wsgi.py
│   └── asgi.py
└── apps/                     # semua feature module
    ├── common/               # shared kernel
    │   ├── models.py         # BaseModel, TimeStampedModel, UUID pk
    │   ├── events.py         # event bus in-process
    │   ├── admin.py          # BaseModelAdmin (Unfold)
    │   ├── navigation.py     # perakit sidebar
    │   ├── views.py          # /health/live, /health/ready
    │   └── urls.py
    └── accounts/             # contoh feature module lengkap
        ├── models.py
        ├── services.py       # write API  (satu-satunya jalur ubah state)
        ├── selectors.py      # read API
        ├── events.py         # fakta yang dipublikasikan module ini
        ├── handlers.py       # langganan ke event module lain
        ├── navigation.py     # kontribusi menu sidebar
        ├── admin.py
        ├── migrations/
        └── tests/
    └── access/               # hak akses menu: katalog Feature + grant
        ├── models.py         # Feature, FeatureGrant (→ auth.Group | user UUID)
        ├── services.py       # grant_feature / revoke_feature / sync_features
        ├── selectors.py      # user_can_access - titik evaluasi tunggal
        ├── management/commands/sync_features.py
        └── ...
```

> Package project bernama **`config`**, bukan `ops_views`, supaya jelas mana
> "kerangka" (config) dan mana "isi" (apps). `DJANGO_SETTINGS_MODULE` mengikuti:
> `config.settings.local` / `config.settings.production`.

---

## Arsitektur modular

Tujuannya: setiap module bisa dicabut jadi microservice **tanpa menyentuh module
lain**. Ada tiga aturan yang menjaga itu.

### Aturan 1 — Module berkomunikasi lewat `services` / `selectors`, bukan model

```python
# ❌ JANGAN - mengunci dua module ke satu database
from apps.accounts.models import User
user = User.objects.get(pk=user_id)

# ✅ LAKUKAN - kontrak yang stabil
from apps.accounts import selectors
user = selectors.get_user_by_id(user_id)
```

Saat `accounts` dipindah ke service sendiri, isi `selectors.py` diganti jadi HTTP
client. Pemanggilnya tidak berubah satu baris pun.

| File | Perannya |
|---|---|
| `selectors.py` | Semua **baca**. Tidak boleh mengubah state. |
| `services.py` | Semua **tulis**. Validasi + transaksi + publish event ada di sini — bukan di view/admin. |
| `models.py` | Bentuk data. Internal module, tidak diimpor lintas module. |

### Aturan 2 — Efek samping lintas module lewat event, bukan panggilan langsung

`apps/common/events.py` adalah bus in-process. Publisher tidak tahu siapa
subscriber-nya:

```python
# apps/accounts/services.py
transaction.on_commit(
    lambda: publish(events.user_registered(user_id=user.pk, email=user.email))
)

# module lain, di AppConfig.ready()
bus.subscribe("accounts.user_registered", send_welcome_email)
```

Subscriber yang error di-log dan dilewati — satu module tidak bisa menjatuhkan
yang lain, persis seperti perilaku message broker. Saat pindah ke microservice,
**hanya `publish()` di file ini yang diganti** ke Kafka/RabbitMQ/SNS.

### Aturan 3 — Tidak ada daftar terpusat

- **Sidebar**: tiap module menaruh `NAVIGATION` di `navigation.py`-nya sendiri.
  `apps/common/navigation.py` mengumpulkan dan mengurutkannya per request.
  Tambah module → menunya muncul sendiri. Hapus module → menunya ikut hilang.
- **URL**: satu baris `include()` per module di [config/urls.py](config/urls.py).
  Memindah module ke service lain = hapus satu baris, arahkan gateway ke sana.
- **Dependency**: setiap module boleh bergantung pada `apps.common`.
  `apps.common` **tidak boleh** bergantung pada module manapun. Graf-nya asiklik.

### Hak akses menu (access control)

`apps.access` mengatur siapa boleh melihat menu mana — per grup
(`auth.Group`) maupun perorangan (grant personal). Kuncinya:

- Tiap module mendeklarasikan key `feature` (slug unik) pada item
  `navigation.py`-nya; `manage.py sync_features` mencatatnya ke katalog
  `Feature` (idempotent, tidak menyentuh kolom operator).
- Grant dikelola lewat admin **Access → Feature grants**: satu keputusan =
  feature + (group **atau** user) + efek `allow`/`deny`.
- Evaluasi tunggal di `apps.access.selectors.user_can_access` — fail-closed:
  default deny, `deny` > `allow` se-level, personal > group, superuser
  bypass, user non-aktif ditolak semua.
- Visibility dan enforcement tidak saling menggantikan: `has_perm` tetap
  yang menjaga endpoint; `Feature.required_permission` (opsional)
  menjembatani keduanya supaya tidak ada "menu terlihat tapi 403".
  Lihat [ADR-012](docs/DECISIONS.md#adr-012--hak-akses-menu-berbasis-group--grant-personal-appsaccess).

Status akun user kini eksplisit lewat `User.Status` (1 = aktif, 0 = nonaktif,
2 = suspend). `is_active` diturunkan dari status tersebut (satu titik invariant
di `User.save()`), dan hanya superuser yang boleh mengubah
status/grup/permission/`is_staff`/`is_superuser`. Lihat
[ADR-013](docs/DECISIONS.md#adr-013--status-akun-user-sebagai-enum-status).

### Kenapa UUID sebagai primary key

`apps/common/models.py` menyediakan `BaseModel` dengan UUID pk. Integer sekuensial
membocorkan jumlah baris dan berhenti unik begitu satu module punya database
sendiri. UUID tetap valid melintasi batas service.

---

## Menjalankan di lokal

Prasyarat: Python 3.14, Git, dan Docker (untuk PostgreSQL lokal).

```bash
git clone <repo-url> ops_views
cd ops_views

# 1. Virtualenv (di dalam repo, sudah masuk .gitignore)
python3.14 -m venv env
source env/bin/activate            # Windows: env\Scripts\activate

# 2. Dependency
pip install -r requirements/local.txt

# 3. Environment
cp .env.example .env
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
#    ^ salin hasilnya ke DJANGO_SECRET_KEY di .env
chmod 600 .env

# 4. Pastikan container PostgreSQL bersama jalan
make db-status                     # kalau mati: docker start postgres

# 5. Database + akun admin
#    Role & database `ops_views` dibuat sekali per mesin - lihat bagian Database
make migrate
make seed                          # akun admin dari DJANGO_SEED_ADMIN_* di .env
#    atau: make superuser          # interaktif, diminta EMAIL (bukan username)

# 6. Jalankan
make run                           # atau: make run PORT=8100
```

Kalau lebih suka PostgreSQL native daripada Docker, lihat
[Menyiapkan PostgreSQL](#menyiapkan-postgresql) lalu sesuaikan `DATABASE_URL`
di `.env` — sisanya sama.

> Tidak ada mode SQLite. Kalau `DATABASE_URL` kosong atau menunjuk ke engine
> selain PostgreSQL, proses **menolak start** — itu disengaja, lihat
> [ADR-002](docs/DECISIONS.md#adr-002--postgresql-satu-satunya-engine-tanpa-fallback-sqlite).

| URL | Isi |
|---|---|
| http://127.0.0.1:8000/ | Landing page (publik, tanpa login) |
| http://127.0.0.1:8000/admin/ | Admin panel (Unfold) |
| http://127.0.0.1:8000/health/live/ | Liveness probe |
| http://127.0.0.1:8000/health/ready/ | Readiness probe (cek koneksi DB) |

Landing page dan admin memakai bahasa visual yang sama. Tampilan admin
di-override lewat `UNFOLD["STYLES"]` yang menunjuk ke
`apps/common/static/common/admin.css` — hook resmi Unfold, jadi upgrade paket
tidak menabraknya. Berkas itu dimuat **sebelum** `styles.css` milik Unfold,
sehingga aturannya diberi awalan `body`/`html.dark` supaya menang lewat
spesifisitas, bukan `!important`.

Perintah harian (`make help` untuk daftar lengkap):

```bash
make db-status / db-logs   # container PostgreSQL bersama
make migrations            # setelah ubah model
make migrate
make seed                  # akun admin pertama (idempotent)
make test                  # test suite
make dbshell               # psql ke database aktif
make verify                # GATE: check + migrasi + test + audit keamanan
```

`make verify` adalah yang harus hijau sebelum sebuah perubahan dianggap
selesai — sama dengan gate di [AGENTS.md §7](AGENTS.md).

---

## Konfigurasi environment

Semua konfigurasi dibaca dari environment variable (`.env` di lokal, env var
asli di server). **Tidak ada satu pun secret di dalam kode.**

| Variable | Default | Keterangan |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.local` | `config.settings.production` di server |
| `DJANGO_SECRET_KEY` | — **wajib** | Tanpa ini proses menolak start |
| `DJANGO_DEBUG` | `False` di base, `True` di local | Wajib `False` di production |
| `DJANGO_ALLOWED_HOSTS` | — wajib di production | Dipisah koma |
| `DJANGO_ADMIN_URL` | `admin/` | Ubah di production untuk mengurangi bot login |
| `DJANGO_SITE_TITLE` | `CMS Ops` | Judul admin (tab browser & header sidebar) — alias publik `cms_ops` |
| `DJANGO_SEED_ADMIN_EMAIL` | kosong | Email admin pertama untuk `make seed` |
| `DJANGO_SEED_ADMIN_PASSWORD` | kosong | Password admin pertama — **ganti di luar lokal** |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | kosong | Wajib diisi kalau pakai HTTPS + domain |
| `DATABASE_URL` | — **wajib** | Harus `postgres://...`. Engine lain ditolak |
| `DATABASE_CONN_MAX_AGE` | `60` (local) / `600` (prod) | Connection pooling |
| `DATABASE_SSLMODE` | `require` | `disable` hanya untuk Postgres di loopback |
| `DATABASE_CONNECT_TIMEOUT` | `10` | Detik sebelum menyerah menyambung |
| `DATABASE_APPLICATION_NAME` | `ops_views` | Label di `pg_stat_activity` |
| `EMAIL_URL` | `consolemail://` | `smtp://user:pass@host:587/?tls=True` |
| `DJANGO_TIME_ZONE` | `Asia/Jakarta` | |
| `DJANGO_LOG_LEVEL` | `INFO` | |
| `DJANGO_ADMINS` | kosong | `Nama:email@domain` — penerima laporan error 500 |

### Akun admin pertama (seeder)

`make seed` (= `manage.py seed_admin`) membuat satu akun superuser dari
`.env`, supaya setup di mesin baru tidak perlu prompt interaktif:

```bash
make seed
# admin: admin@ops.local dibuat
```

Nilai default untuk development sudah terisi di `.env.example`:

| | |
|---|---|
| Email | `admin@ops.local` |
| Password | `OpsViews!Dev2026` |

> **Kredensial ini bukan rahasia.** Nilainya ada di `.env.example` yang
> ter-commit, jadi siapa pun yang bisa membaca repo tahu isinya. Aman untuk
> mesin lokal, **tidak pernah** untuk host yang bisa dijangkau orang lain.

Sifat perintahnya:

- **Idempotent** — kalau email itu sudah ada, perintah melewatinya dan tidak
  menyentuh password maupun profil akun yang sudah dipakai. Boleh dijalankan
  berulang seperti `sync_features`.
- **Lewat service** (R5) — memakai `services.register_user`, jadi validator
  password tetap jalan dan event `accounts.user_registered` tetap terbit.
  Password lemah ditolak di sini, bukan diam-diam diterima.
- **Fail-closed** — kalau `DJANGO_SEED_ADMIN_*` kosong, perintah berhenti
  dengan pesan jelas, bukan membuat akun asal-asalan.
- **Menolak jalan saat `DEBUG=False`** kecuali diberi `--force`. Ini yang
  mencegah `.env.example` disalin apa adanya ke server lalu ikut menanam
  kredensial yang diketahui publik.

Di server, jangan pakai seeder — pakai `make superuser`:

```bash
make superuser        # interaktif; password tidak pernah singgah di file .env
```

Kalau memang harus non-interaktif di server (mis. provisioning otomatis), isi
`DJANGO_SEED_ADMIN_*` dengan nilai yang di-generate, jalankan
`manage.py seed_admin --force`, lalu **hapus kedua baris itu dari environment**
begitu akun terbentuk.

---

**Sifat fail-closed**: `production.py` tidak menyediakan default untuk
`DJANGO_SECRET_KEY` maupun `DJANGO_ALLOWED_HOSTS`, dan `base.py` tidak
menyediakan default untuk `DATABASE_URL`. Kalau lupa diisi, proses gagal start
dengan pesan jelas — bukan diam-diam jalan dengan konfigurasi tidak aman.
Lihat [ADR-008](docs/DECISIONS.md#adr-008--settings-fail-closed).

---

## Database

**PostgreSQL 17 di semua environment.** Lokal, staging dan production memakai
engine yang sama supaya perbedaan perilaku antar-backend (operator JSON, waktu
evaluasi constraint, urutan collation, `SELECT FOR UPDATE`) tidak pernah muncul
mendadak saat deploy. Tidak ada fallback SQLite —
[ADR-002](docs/DECISIONS.md#adr-002--postgresql-satu-satunya-engine-tanpa-fallback-sqlite).

Satu variable mengatur koneksinya:

```bash
# lokal (container `postgres` bersama, port host 55432)
DATABASE_URL=postgres://ops_user:PASSWORD@127.0.0.1:55432/ops_views
DATABASE_SSLMODE=disable        # loopback, tidak perlu TLS

# production
DATABASE_URL=postgres://ops_user:PASSWORD@db.internal:5432/ops_views
DATABASE_SSLMODE=require        # wajib kalau DB tidak satu host
```

Yang sudah aktif di [base.py](config/settings/base.py):

| Setting | Nilai | Gunanya |
|---|---|---|
| `CONN_MAX_AGE` | 60 lokal / 600 prod | Koneksi dipakai ulang, tidak buka-tutup tiap request |
| `CONN_HEALTH_CHECKS` | `True` | Koneksi basi dideteksi sebelum dipakai |
| `sslmode` | env, default `require` | Fail secure — harus sengaja diturunkan |
| `connect_timeout` | 10 detik | Worker tidak menggantung pada host yang mati |
| `application_name` | `ops_views` | Terlihat di `pg_stat_activity` saat melacak lock |

Boot-nya fail-closed di dua titik: `DATABASE_URL` tidak ada → gagal start;
`DATABASE_URL` menunjuk engine non-postgres → gagal start dengan pesan eksplisit.

### PostgreSQL lokal — container bersama (cara yang dipakai project ini)

Project ini **tidak menjalankan container PostgreSQL-nya sendiri**. Ia memakai
container `postgres` yang sudah berjalan di mesin development dan dipakai
bersama beberapa project — lihat
[ADR-011](docs/DECISIONS.md#adr-011--memakai-container-postgresql-bersama-bukan-container-per-project).

| | |
|---|---|
| Nama container | `postgres` |
| Image | `postgres:17-alpine` |
| Port di host | **55432** (bukan 5432) |
| Superuser container | `usr_pro` |
| Database project ini | `ops_views`, owner `ops_user` |

Isolasi antar project dijaga di level database, bukan container: `ops_views`
punya database dan role sendiri, terpisah dari `appsdb` milik project lain di
container yang sama.

```bash
make db-status     # container jalan & healthy?
make db-logs       # ikuti lognya
make dbshell       # psql ke database project ini
docker start postgres   # kalau sedang mati
```

`make verify` menolak jalan kalau container-nya mati, jadi tidak ada gate yang
lolos gara-gara database kebetulan tidak tersambung.

#### Menyiapkan database project di container bersama

Sekali saja, per mesin. Jalankan dari host:

```bash
# ganti dengan password acak, mis. python3 -c "import secrets;print(secrets.token_urlsafe(24))"
PGPASS='password-acak-yang-kuat'

docker exec -i postgres psql -U usr_pro -d appsdb -v ON_ERROR_STOP=1 <<SQL
CREATE ROLE ops_user WITH LOGIN PASSWORD '$PGPASS';
ALTER ROLE ops_user SET client_encoding TO 'utf8';
ALTER ROLE ops_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE ops_user SET timezone TO 'Asia/Jakarta';
ALTER ROLE ops_user CREATEDB;   -- dibutuhkan test runner untuk bikin test_ops_views
CREATE DATABASE ops_views OWNER ops_user ENCODING 'UTF8';
SQL

docker exec -i postgres psql -U usr_pro -d ops_views -v ON_ERROR_STOP=1 <<'SQL'
GRANT ALL ON SCHEMA public TO ops_user;
REVOKE ALL ON DATABASE ops_views FROM PUBLIC;
SQL
```

Lalu isi `DATABASE_URL` di `.env` dengan password yang sama:

```
DATABASE_URL=postgres://ops_user:<PGPASS>@127.0.0.1:55432/ops_views
```

```bash
make migrate
make superuser
```

> Kalau container `postgres` dipakai bersama project lain, **jangan** jalankan
> `docker rm`, `docker volume rm`, atau `DROP DATABASE appsdb` — kamu akan
> menghapus data project lain. Untuk membuang data project ini saja:
> `DROP DATABASE ops_views;`

### Menyiapkan PostgreSQL native (alternatif, dan cara di server)

```bash
sudo -u postgres psql <<'SQL'
CREATE DATABASE ops_views;
CREATE USER ops_user WITH PASSWORD 'ganti-password-ini';
ALTER ROLE ops_user SET client_encoding TO 'utf8';
ALTER ROLE ops_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE ops_user SET timezone TO 'Asia/Jakarta';
GRANT ALL PRIVILEGES ON DATABASE ops_views TO ops_user;
\c ops_views
GRANT ALL ON SCHEMA public TO ops_user;
SQL

make migrate
```

Pastikan di server PostgreSQL hanya listen di `127.0.0.1`
(`listen_addresses = 'localhost'` di `postgresql.conf`), atau di private network
dengan `DATABASE_SSLMODE=require`.

Verifikasi koneksi kapan saja:

```bash
curl -s localhost:8000/health/ready/
# {"status": "ok", "checks": {"database:default": "ok"}}
```

### Backup

```bash
pg_dump -Fc -U ops_user ops_views > ops_views_$(date +%F).dump
pg_restore -U ops_user -d ops_views --clean ops_views_2026-09-03.dump
```

---

## Menambah feature module baru

Contoh menambah module `incidents`:

```bash
cd ops_views
mkdir -p apps/incidents/{migrations,tests}
touch apps/incidents/__init__.py apps/incidents/migrations/__init__.py \
      apps/incidents/tests/__init__.py
```

**1. `apps/incidents/apps.py`**

```python
from django.apps import AppConfig

class IncidentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.incidents"
    verbose_name = "Incidents"

    def ready(self):
        from . import handlers  # noqa: F401
```

**2. `apps/incidents/models.py`**

```python
from django.db import models
from apps.common.models import BaseModel

class Incident(BaseModel):          # UUID pk + created_at/updated_at
    title = models.CharField(max_length=200)
    resolved_at = models.DateTimeField(null=True, blank=True)

    # Referensi lintas module disimpan sebagai id, BUKAN ForeignKey -
    # FK ke tabel module lain mengunci keduanya di satu database.
    reported_by_id = models.UUIDField(db_index=True)
```

**3. `apps/incidents/admin.py`**

```python
from django.contrib import admin
from apps.common.admin import BaseModelAdmin
from .models import Incident

@admin.register(Incident)
class IncidentAdmin(BaseModelAdmin):    # BaseModelAdmin = Unfold styling
    list_display = ("title", "created_at", "resolved_at")
    search_fields = ("title",)
```

**4. `apps/incidents/navigation.py`**

```python
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

def can_view(request):
    return request.user.has_perm("incidents.view_incident")

NAVIGATION = [{
    "title": _("Incidents"),
    "separator": True,
    "order": 20,                     # urutan di sidebar
    "items": [{
        "title": _("All incidents"),
        "icon": "warning",           # nama Material Symbols
        "link": reverse_lazy("admin:incidents_incident_changelist"),
        "permission": "apps.incidents.navigation.can_view",
        "feature": "incidents.list",  # slug untuk katalog akses (opsional)
    }],
}]
```

Lalu jalankan `env/bin/python manage.py sync_features` supaya feature baru
masuk katalog akses dan bisa di-grant ke group/user.

**5. Daftarkan** — dua baris, selesai:

```python
# config/settings/base.py
LOCAL_APPS = ["apps.common", "apps.accounts", "apps.incidents"]

# config/urls.py (hanya kalau module punya HTTP endpoint)
path("api/incidents/", include("apps.incidents.urls")),
```

```bash
python manage.py makemigrations incidents && python manage.py migrate
```

Menu sidebar muncul otomatis — tidak ada file terpusat yang perlu diedit.

### Saat tiba waktunya pecah jadi microservice

1. Copy folder `apps/<module>/` + `apps/common/` ke repo baru.
2. Ganti isi `selectors.py`/`services.py` module *lain* yang dipanggil menjadi
   HTTP client.
3. Ganti `publish()` di `apps/common/events.py` jadi producer broker.
4. Hapus baris `include()`-nya dari `config/urls.py`, arahkan gateway ke service baru.

Karena tidak ada FK lintas module dan tidak ada import model lintas module,
tidak ada tabel yang perlu dipecah paksa.

---

## Mengelola dependency

### Versi minimum

| Kebutuhan | Minimum | Dipakai sekarang | Catatan |
|---|---|---|---|
| Python | 3.12 | **3.14** | `Requires-Python: >=3.12` di Django 6.1 dan django-unfold |
| PostgreSQL | 15 | **17** | Django 6.1 menolak start di bawah ini (`minimum_database_version`) |
| Docker Engine | 20.10 | — | Untuk mengakses container `postgres` bersama |
| pip | 23.0 | 26.0 | Butuh dukungan `[extras]` di requirements |

| Paket | Versi ter-pin | Kenapa versi ini |
|---|---|---|
| `Django` | `==6.1` | Basis project. Naik minor = baca release notes dulu |
| `django-environ` | `==0.14.0` | Parser `DATABASE_URL` / `EMAIL_URL` |
| `django-unfold` | `==0.104.1` | Tema admin. Terikat erat ke versi Django |
| `psycopg[binary]` | `==3.3.5` | Driver PostgreSQL. `[binary]` = tanpa compile |
| `asgiref`, `sqlparse` | ter-pin | Dependency turunan Django, di-pin agar build reprodusibel |
| `gunicorn` | `==23.0.0` | Production saja |

### Struktur file

Sumber kebenaran ada di `requirements/`, **bukan** di `requirements.txt`:

```
requirements/
├── base.txt          # dipakai semua environment  <-- hampir selalu di sini
├── local.txt         # -r base.txt + tool development
└── production.txt    # -r base.txt + gunicorn

requirements.txt      # cuma pointer ke requirements/local.txt
```

`requirements.txt` ada supaya `pip install -r requirements.txt` yang sudah
dihafal orang tetap jalan. **Jangan pernah menimpanya dengan `pip freeze`** —
begitu ditimpa, isinya menduplikasi `base.txt` dan keduanya langsung mulai
melenceng. Kalau butuh daftar persis apa yang terpasang, jalankan
`pip freeze` ke stdout, bukan ke file ini.

### Aturan pinning

- Selalu `==`, tidak pernah `>=` atau tanpa versi. Build yang sama harus
  menghasilkan environment yang sama, hari ini maupun enam bulan lagi.
- Dependency baru masuk ke `base.txt` kecuali benar-benar hanya dipakai satu
  environment.
- Satu baris komentar kalau alasan pemilihannya tidak jelas dari nama paketnya.

> Contoh di bawah menulis `env/bin/pip`. Kalau virtualenv kamu ada di sebelah
> repo (`../env`), pakai `../env/bin/pip` — `make` mendeteksi keduanya sendiri.

### Menambah dependency

Butuh persetujuan dulu — lihat [AGENTS.md §6](AGENTS.md).

```bash
env/bin/pip install nama-paket                    # cek versi yang terpasang
env/bin/pip show nama-paket | grep -i version

# tambahkan barisnya ke requirements/base.txt secara manual, dengan ==
echo "nama-paket==1.2.3" >> requirements/base.txt

make verify                                       # wajib hijau
```

### Menaikkan versi (update)

Naikkan **satu paket per satu commit**. Kalau ada yang rusak, penyebabnya
langsung ketahuan tanpa perlu bisect.

```bash
# 1. Lihat apa yang tertinggal
env/bin/pip list --outdated

# 2. Naikkan satu paket
env/bin/pip install --upgrade "django-unfold==0.105.0"

# 3. Samakan pin-nya di requirements/base.txt

# 4. Gate wajib hijau
make verify

# 5. Untuk Django/Unfold, cek juga admin-nya secara visual
make run    # buka /admin/, pastikan tema Unfold tidak rusak
```

Kalau gagal: `env/bin/pip install "nama-paket==<versi-lama>"`, kembalikan
pin-nya, dan catat kenapa versi itu ditahan sebagai komentar di `base.txt`.

### Update keamanan

```bash
env/bin/pip install pip-audit
env/bin/pip-audit -r requirements/production.txt
```

Advisory Django diumumkan di <https://groups.google.com/g/django-announce>.
Rilis patch (`6.1.x`) aman dinaikkan segera; minor (`6.2`) baca release notes
dan catatan deprecation dulu.

### Setelah update, di server

```bash
cd /srv/ops_views
sudo -u ops env/bin/pip install -r requirements/production.txt
sudo -u ops env/bin/python manage.py migrate --noinput
sudo -u ops env/bin/python manage.py collectstatic --noinput
sudo systemctl restart ops_views.service
curl -sf https://ops.example.com/health/ready/ || echo "GAGAL - rollback"
```

---

## Testing

Test memakai database sementara `test_ops_views` di container yang sama, jadi
container `postgres` harus jalan dan `ops_user` harus punya hak `CREATEDB`.

```bash
make test                                        # semua
env/bin/python manage.py test apps.accounts   # satu module
python manage.py test apps.accounts.tests.test_services -v 2

# lebih cepat: hashing password lemah khusus test
DJANGO_FAST_PASSWORD_HASHER=True python manage.py test apps --parallel
```

Test suite saat ini mencakup service layer accounts, isolasi kegagalan event bus,
health endpoint, matriks precedence akses menu, upsert/event grant, dan sinkron
katalog feature.

---

## Setup server (production)

Contoh berikut untuk Ubuntu 22.04/24.04 + Nginx + Gunicorn + PostgreSQL +
systemd. Sesuaikan path dan nama domain.

### 1. Paket sistem

```bash
sudo apt update
sudo apt install -y python3.14 python3.14-venv python3-pip \
    postgresql postgresql-contrib nginx git ufw
```

### 2. User khusus aplikasi (jangan jalankan sebagai root)

```bash
sudo adduser --system --group --home /srv/ops_views ops
sudo mkdir -p /srv/ops_views && sudo chown ops:ops /srv/ops_views
```

### 3. Deploy kode

```bash
sudo -u ops -H bash
cd /srv/ops_views
git clone <repo-url> .
python3.14 -m venv env
./env/bin/pip install -r requirements/production.txt
exit
```

### 4. Database

Ikuti [Menyiapkan PostgreSQL native](#menyiapkan-postgresql-native-alternatif-dan-cara-di-server)
di atas. Container bersama yang dipakai di development adalah alat development —
jangan dipakai di production.

### 5. File environment

```bash
sudo -u ops tee /srv/ops_views/.env >/dev/null <<'EOF'
DJANGO_SETTINGS_MODULE=config.settings.production
DJANGO_SECRET_KEY=<hasil get_random_secret_key(), 50 karakter acak>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=ops.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://ops.example.com
DJANGO_ADMIN_URL=panel-9f2c/
DATABASE_URL=postgres://ops_user:PASSWORD@127.0.0.1:5432/ops_views
DATABASE_SSLMODE=disable   # ganti ke require kalau DB tidak di host ini
DATABASE_CONN_MAX_AGE=600
EMAIL_URL=smtp://user:pass@smtp.example.com:587/?tls=True
DEFAULT_FROM_EMAIL=ops@example.com
DJANGO_ADMINS=Ops Team:ops@example.com
EOF

sudo chown ops:ops /srv/ops_views/.env
sudo chmod 600 /srv/ops_views/.env    # hanya ops yang bisa baca
```

`DJANGO_SEED_ADMIN_*` sengaja **tidak** ada di sini: akun admin server dibuat
interaktif di langkah berikutnya, supaya passwordnya tidak pernah tersimpan di
file. `seed_admin` juga menolak jalan saat `DEBUG=False` tanpa `--force`.

### 6. Migrasi + static + verifikasi

```bash
cd /srv/ops_views
sudo -u ops env/bin/python manage.py check --deploy --fail-level WARNING
sudo -u ops env/bin/python manage.py migrate
sudo -u ops env/bin/python manage.py collectstatic --noinput
sudo -u ops env/bin/python manage.py createsuperuser   # bukan seed_admin
```

`check --deploy` harus lolos **tanpa satu pun warning** sebelum lanjut.

### 7. Gunicorn via systemd

`/etc/systemd/system/ops_views.socket`:

```ini
[Unit]
Description=ops_views gunicorn socket

[Socket]
ListenStream=/run/ops_views.sock
SocketUser=www-data
SocketMode=0660

[Install]
WantedBy=sockets.target
```

`/etc/systemd/system/ops_views.service`:

```ini
[Unit]
Description=ops_views gunicorn daemon
Requires=ops_views.socket
After=network.target postgresql.service

[Service]
User=ops
Group=ops
WorkingDirectory=/srv/ops_views
Environment=DJANGO_SETTINGS_MODULE=config.settings.production
ExecStart=/srv/ops_views/env/bin/gunicorn \
    --workers 3 \
    --threads 2 \
    --timeout 60 \
    --graceful-timeout 30 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --access-logfile - \
    --error-logfile - \
    --bind unix:/run/ops_views.sock \
    config.wsgi:application
ExecReload=/bin/kill -s HUP $MAINPID
Restart=always
RestartSec=5

# Hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/srv/ops_views/media /run
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true

[Install]
WantedBy=multi-user.target
```

> Jumlah worker: mulai dari `(2 × jumlah core) + 1`, lalu sesuaikan dari metrik.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ops_views.socket
sudo systemctl status ops_views.service
```

### 8. Nginx

`/etc/nginx/sites-available/ops_views`:

```nginx
upstream ops_views_app {
    server unix:/run/ops_views.sock fail_timeout=0;
}

server {
    listen 80;
    server_name ops.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name ops.example.com;

    ssl_certificate     /etc/letsencrypt/live/ops.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ops.example.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;

    client_max_body_size 10M;
    server_tokens off;

    # Static file dilayani nginx, jangan lewat Django
    location /static/ {
        alias /srv/ops_views/staticfiles/;
        expires 30d;
        access_log off;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias /srv/ops_views/media/;
        expires 7d;
        access_log off;
    }

    location = /health/live/ { access_log off; proxy_pass http://ops_views_app; }

    location / {
        proxy_pass http://ops_views_app;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;   # dibaca SECURE_PROXY_SSL_HEADER
        proxy_redirect off;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/ops_views /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

> `X-Forwarded-Proto` wajib dikirim. `production.py` mempercayai header itu lewat
> `SECURE_PROXY_SSL_HEADER` — tanpa nginx yang men-set-nya, redirect HTTPS akan
> berputar tak berujung.

### 9. TLS + firewall

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d ops.example.com

sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

### 10. Deploy ulang

```bash
cd /srv/ops_views
sudo -u ops git pull
sudo -u ops env/bin/pip install -r requirements/production.txt
sudo -u ops env/bin/python manage.py migrate --noinput
sudo -u ops env/bin/python manage.py collectstatic --noinput
sudo systemctl restart ops_views.service
curl -sf https://ops.example.com/health/ready/ || echo "DEPLOY GAGAL"
```

### Monitoring

Arahkan probe orchestrator/uptime ke:

| Endpoint | Untuk |
|---|---|
| `/health/live/` | Restart probe — proses hidup? |
| `/health/ready/` | Traffic probe — DB tersambung? Balas `503` kalau tidak |

---

## Checklist keamanan

Yang **sudah** dikonfigurasi di repo ini:

- [x] Tidak ada secret di dalam kode — semuanya dari environment
- [x] `.env` masuk `.gitignore`, `.env.example` yang di-commit
- [x] `DEBUG=False` permanen di production settings
- [x] Production **gagal start** tanpa `DJANGO_SECRET_KEY` / `DJANGO_ALLOWED_HOSTS`
- [x] HSTS 1 tahun + preload + include subdomains
- [x] `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`
- [x] `SESSION_COOKIE_HTTPONLY`, `SameSite=Lax` untuk session & CSRF
- [x] `X_FRAME_OPTIONS=DENY`, nosniff, `Referrer-Policy: same-origin`
- [x] Panjang password minimum 12 karakter (default Django 8)
- [x] URL admin bisa dipindah lewat `DJANGO_ADMIN_URL`
- [x] Hanya superuser yang bisa memberi hak staff/superuser/permission
- [x] Seeder admin menolak jalan saat `DEBUG=False` tanpa `--force`
- [x] Batas upload 5 MB (`DATA_UPLOAD_MAX_MEMORY_SIZE`)
- [x] Static file production pakai `ManifestStaticFilesStorage` (hashed)
- [x] `manage.py check --deploy --fail-level WARNING` lolos bersih
- [x] Boot ditolak kalau `DATABASE_URL` hilang atau bukan PostgreSQL
- [x] `sslmode` default `require` — harus sengaja diturunkan
- [x] Postgres lokal terikat `127.0.0.1`, tidak terbuka ke jaringan
- [x] Aturan arsitektur terkunci di `AGENTS.md` + `docs/DECISIONS.md`

Yang harus **kamu** lakukan di server:

- [ ] Buat akun admin lewat `make superuser`, **bukan** `make seed` — kredensial
      di `.env.example` diketahui publik lewat repo
- [ ] `chmod 600 .env`, dimiliki user aplikasi
- [ ] `SECRET_KEY` unik per environment — jangan pakai ulang dari dev
- [ ] PostgreSQL hanya listen di `127.0.0.1` (atau private network + `sslmode=require`)
- [ ] Backup terjadwal + **restore diuji**, bukan hanya dibuat
- [ ] Jangan pernah `runserver` di production
- [ ] Rotasi `SECRET_KEY` kalau dicurigai bocor (semua session logout)

---

## Troubleshooting

| Gejala | Penyebab & solusi |
|---|---|
| `ImproperlyConfigured: Set the DJANGO_SECRET_KEY environment variable` | `.env` tidak terbaca. Cek posisi file: harus sejajar dengan `manage.py`, dan permission-nya terbaca oleh user proses. |
| `DisallowedHost` | Tambahkan domain ke `DJANGO_ALLOWED_HOSTS`. |
| Redirect HTTPS berputar tak berhenti | Nginx tidak mengirim `X-Forwarded-Proto $scheme`. |
| Admin tampil polos tanpa styling | `collectstatic` belum dijalankan, atau `location /static/` di nginx salah path. |
| Admin masih tema Django lama | `"unfold"` harus berada **sebelum** `django.contrib.admin` di `INSTALLED_APPS`. |
| `CSRF verification failed` di HTTPS | Isi `DJANGO_CSRF_TRUSTED_ORIGINS` lengkap dengan skema `https://`. |
| `Error: That port is already in use` | Port 8000 dipakai app lain di mesin ini. `make run PORT=8100`, atau cari pemakainya: `lsof -nP -iTCP:8000 -sTCP:LISTEN`. |
| `502 Bad Gateway` | `sudo systemctl status ops_views` dan `sudo journalctl -u ops_views -n 50`. |
| `/health/ready/` balas 503 | DB tidak tersambung — cek `DATABASE_URL`, service postgres, dan firewall. |
| `no such table` setelah ganti DB | `make migrate` di database yang baru. |
| `ImproperlyConfigured: Set the DATABASE_URL environment variable` | `.env` belum berisi `DATABASE_URL`. Tidak ada fallback SQLite — itu disengaja. |
| `This project targets PostgreSQL. DATABASE_URL resolved to 'sqlite3'` | `DATABASE_URL` menunjuk engine yang salah. Perbaiki URL-nya, jangan longgarkan `base.py`. |
| `connection refused` ke port 55432 | Container belum jalan: `docker start postgres`, lalu `make db-status`. |
| `password authentication failed` | Password di `DATABASE_URL` tidak cocok dengan role `ops_user` di container. Setel ulang: `docker exec -it postgres psql -U usr_pro -d appsdb -c "ALTER ROLE ops_user PASSWORD '...';"` |
| `permission denied to create database` saat `make test` | Test runner butuh bikin `test_ops_views`: `docker exec postgres psql -U usr_pro -d appsdb -c "ALTER ROLE ops_user CREATEDB;"` |
| `database "ops_views" does not exist` | Role & database belum dibuat di container. Lihat [Menyiapkan database project](#menyiapkan-database-project-di-container-bersama). |
