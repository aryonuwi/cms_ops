# Architecture Decision Records

Catatan **kenapa** project ini dibentuk seperti sekarang. Dibaca oleh agent/AI
dan developer baru sebelum mengubah apa pun yang menyentuh keputusan di bawah.

Format tiap entri: Konteks → Keputusan → Konsekuensi → Cara membalik.
Entri berstatus **Accepted** tidak boleh dibalik tanpa persetujuan user.

---

## ADR-001 — Package project bernama `config`, bukan `ops_views`

**Tanggal:** 2026-09-03 · **Status:** Accepted

**Konteks.** Hasil `startproject` menaruh settings di `ops_views/ops_views/`.
Dua level nama yang sama membingungkan, dan mengaburkan batas antara kerangka
project dan isi fitur.

**Keputusan.** Rename jadi `config/`. `DJANGO_SETTINGS_MODULE` menjadi
`config.settings.local` / `config.settings.production`.

**Konsekuensi.** Jelas mana kerangka (`config/`) dan mana isi (`apps/`).
Konvensi ini umum di project Django berskala, jadi developer baru langsung
paham. `config/` **tidak boleh** berisi business logic.

**Cara membalik.** Rename folder + update `DJANGO_SETTINGS_MODULE` di
`manage.py`, `wsgi.py`, `asgi.py`, systemd unit, dan `.env`.

---

## ADR-002 — PostgreSQL satu-satunya engine, tanpa fallback SQLite

**Tanggal:** 2026-09-03 · **Status:** Accepted

**Konteks.** Default Django adalah SQLite. Menjalankan SQLite di lokal dan
PostgreSQL di production menyembunyikan perbedaan nyata: operator JSON,
waktu evaluasi constraint, urutan collation, perilaku `SELECT FOR UPDATE`,
dan tipe kolom. Bug seperti ini baru muncul saat deploy.

**Keputusan.** PostgreSQL 17 di semua environment. `base.py` **tidak punya
default** untuk `DATABASE_URL` dan menolak start kalau engine yang di-resolve
bukan postgres. Postgres lokal disediakan lewat `docker-compose.yml`.

**Konsekuensi.** Developer baru butuh Docker (atau Postgres native) sebelum
bisa jalan — trade-off yang disengaja. `psycopg[binary]` masuk
`requirements/base.txt`, bukan hanya production.

**Cara membalik.** Jangan. Kalau benar-benar perlu SQLite untuk satu kasus,
bikin settings module terpisah, jangan longgarkan `base.py`.

---

## ADR-003 — Custom user model sejak migrasi pertama

**Tanggal:** 2026-09-03 · **Status:** Accepted

**Konteks.** Mengganti `AUTH_USER_MODEL` setelah tabel terbentuk butuh migrasi
data manual di setiap FK ke user di seluruh project. Biayanya naik terus
seiring umur project.

**Keputusan.** `apps.accounts.User` (`AbstractUser` + UUID pk) dibuat sebelum
`migrate` pertama. `username` dihapus, login pakai email yang unik dan
di-normalisasi lowercase.

**Konsekuensi.** `createsuperuser` meminta email. Kode yang mengasumsikan
`user.username` akan gagal — gunakan `user.email`.

**Cara membalik.** Praktis tidak bisa setelah ada data. Ubah field di dalam
model yang sudah ada, jangan ganti modelnya.

---

## ADR-004 — Modular per fitur dengan batas service/selector

**Tanggal:** 2026-09-03 · **Status:** Accepted

**Konteks.** Target jangka panjang project ini adalah bisa memecah fitur jadi
microservice. Yang biasanya menghalangi bukan ukuran kode, tapi kopling:
import model lintas app dan ForeignKey lintas app membuat tabel tidak bisa
dipisah.

**Keputusan.** Tiap module hanya diakses lewat `services.py` (tulis) dan
`selectors.py` (baca). Tidak ada import model lintas module. Tidak ada FK
lintas module — pakai `UUIDField`. `apps.common` boleh dipakai semua module,
tapi tidak boleh bergantung pada module manapun.

**Konsekuensi.** Ada satu lapis tak-langsung yang terasa berlebihan untuk
project sekecil ini sekarang. Itu memang harganya: saat pemisahan terjadi,
`selectors.py` tinggal diganti jadi HTTP client dan pemanggilnya nol
perubahan. Integritas referensial lintas module jadi tanggung jawab aplikasi,
bukan database.

**Cara membalik.** Kalau microservice dibatalkan, aturan ini bisa dilonggarkan
— tapi lakukan sadar dan sekaligus, jangan bocor sedikit-sedikit.

---

## ADR-005 — UUID sebagai primary key

**Tanggal:** 2026-09-03 · **Status:** Accepted

**Konteks.** Integer sekuensial membocorkan jumlah baris lewat URL, dan
berhenti unik begitu satu module punya database sendiri.

**Keputusan.** `apps.common.models.BaseModel` memberi UUIDv4 pk +
`created_at`/`updated_at`. Semua model feature memakainya.

**Konsekuensi.** Index sedikit lebih besar dan insert acak. Untuk beban kerja
panel operasional ini tidak signifikan. Kalau nanti ada tabel dengan volume
insert sangat tinggi, pertimbangkan UUIDv7 (terurut waktu) untuk tabel itu saja.

---

## ADR-006 — Event bus in-process, bukan langsung ke broker

**Tanggal:** 2026-09-03 · **Status:** Accepted

**Konteks.** Efek samping lintas module (kirim email saat user daftar, dsb.)
kalau ditulis sebagai panggilan langsung akan mengunci module. Tapi memasang
Kafka/RabbitMQ sekarang adalah infrastruktur yang belum dibutuhkan.

**Keputusan.** `apps/common/events.py` — bus in-process, publish sinkron
setelah commit (`transaction.on_commit`). Subscriber yang error di-log dan
dilewati, meniru perilaku broker.

**Konsekuensi.** Bentuk kode publisher/subscriber sudah final. Saat pindah ke
broker sungguhan, hanya fungsi `publish()` yang berubah. Sekarang belum ada
retry dan belum ada jaminan pengiriman — jangan pakai bus ini untuk hal yang
tidak boleh hilang (mis. transaksi finansial) sebelum broker terpasang.

---

## ADR-007 — Sidebar & URL dirakit dari module, bukan daftar terpusat

**Tanggal:** 2026-09-03 · **Status:** Accepted

**Konteks.** Daftar terpusat (menu, registry fitur) jadi titik konflik merge
dan bikin module tidak benar-benar bisa dicabut — hapus module, menunya
tertinggal dan admin error.

**Keputusan.** Tiap module mendeklarasikan `NAVIGATION` di `navigation.py`-nya.
`apps/common/navigation.py` mengumpulkan per request lewat dotted-path callable
yang didukung Unfold, diurutkan dengan key `order`, dan **menelan error**
per-module.

**Konsekuensi.** Tambah module → menu muncul sendiri. Hapus module → menunya
ikut hilang. Module yang navigation-nya rusak hanya hilang dari menu, tidak
menjatuhkan admin. Konsekuensi lain: menu dirakit tiap request admin — murah,
tapi jangan taruh query database di dalam `navigation.py`.

---

## ADR-008 — Settings fail-closed

**Tanggal:** 2026-09-03 · **Status:** Accepted

**Konteks.** Kecelakaan produksi paling umum di Django adalah proses yang tetap
mau start dengan konfigurasi tidak aman: `DEBUG=True`, secret key default,
`ALLOWED_HOSTS` kosong.

**Keputusan.** `production.py` tidak memberi default untuk `DJANGO_SECRET_KEY`
dan `DJANGO_ALLOWED_HOSTS`; `base.py` tidak memberi default untuk
`DATABASE_URL`. Default keamanan dipasang ketat di `base.py` lalu **dilonggarkan**
di `local.py` — sehingga override yang lupa ditulis gagal ke arah aman.

**Konsekuensi.** Salah konfigurasi = proses menolak start dengan pesan jelas,
bukan jalan diam-diam dalam keadaan rentan. Setiap environment wajib punya
`.env` atau env var yang lengkap.

---

## ADR-009 — `requirements/` sebagai sumber kebenaran, `requirements.txt` hanya pointer

**Tanggal:** 2026-09-03 · **Status:** Accepted

**Konteks.** Dependency dipecah per environment di `requirements/`
(`base` / `local` / `production`). Tapi `pip install -r requirements.txt`
sudah jadi refleks banyak orang, dan `pip freeze > requirements.txt` juga
refleks yang sama kuatnya. Sekali file itu ditimpa hasil freeze, isinya
menduplikasi `base.txt` — dua daftar untuk satu hal, dan keduanya langsung
mulai melenceng. Ini sudah pernah terjadi di repo ini.

**Keputusan.** `requirements.txt` hanya berisi `-r requirements/local.txt`
plus komentar peringatan. Semua dependency langsung ditulis manual dengan pin
`==` di `requirements/base.txt`. Tidak ada lock file hasil freeze.

**Konsekuensi.** Satu tempat untuk diedit, tidak bisa melenceng. Perintah yang
sudah dihafal orang tetap jalan. Harganya: tidak ada pinning transitif penuh —
dependency turunan yang penting (`asgiref`, `sqlparse`) di-pin manual sebagai
gantinya. Kalau nanti butuh reproducibility yang lebih ketat, naik ke
pip-tools atau uv dengan lock file terpisah, **bukan** dengan menimpa
`requirements.txt`.

**Cara membalik.** Ganti isi `requirements.txt` dengan output `pip freeze`, dan
hapus paragraf peringatannya di README + AGENTS.md supaya tidak saling
bertentangan.

---

## ADR-010 — Lokasi virtualenv tidak dipatok

**Tanggal:** 2026-09-03 · **Status:** Accepted

**Konteks.** Virtualenv sempat dipindah ke dalam repo (`env/`), lalu dihapus
lagi; yang terpakai justru `../env` di sebelah repo. Mematok salah satu
membuat `Makefile` rusak setiap kali orang memilih yang lain.

**Keputusan.** `Makefile` mendeteksi `env/bin/python`, lalu `../env/bin/python`,
dan berhenti dengan pesan jelas kalau tidak ada. Keduanya sah. `env/` sudah ada
di `.gitignore` sehingga varian di dalam repo tidak pernah ikut ter-commit.

**Konsekuensi.** Perintah `make` jalan di kedua layout tanpa konfigurasi. Kalau
menulis perintah manual di dokumen, sebutkan bahwa prefix-nya bisa `env/bin/`
atau `../env/bin/`.

---

## ADR-011 — Memakai container PostgreSQL bersama, bukan container per project

**Tanggal:** 2026-09-03 · **Status:** Accepted · **Menggantikan sebagian ADR-002**

**Konteks.** Awalnya project ini punya `docker-compose.yml` sendiri yang
menjalankan `postgres:17-alpine` di port 5432. Ternyata mesin development sudah
menjalankan container `postgres` (image yang sama, versi 17.11) di port host
**55432**, dipakai bersama project lain. Menjalankan dua instance PostgreSQL
untuk satu mesin berarti dua kali memori, dua tempat backup, dan port 5432 yang
mudah bentrok.

**Keputusan.** Hapus `docker-compose.yml`. Project memakai container `postgres`
yang sudah ada, dengan **database dan role sendiri**: database `ops_views`
milik role `ops_user`, terpisah dari `appsdb` milik project lain. Isolasi
dijaga di level database, bukan container. `ops_user` diberi `CREATEDB` supaya
test runner bisa membuat `test_ops_views`.

**Konsekuensi.** Satu instance PostgreSQL untuk semua project di mesin ini.
Harganya: container itu jadi milik bersama — `docker rm`, `docker volume rm`,
atau restart sembarangan akan menjatuhkan project lain, jadi perintah itu
dilarang di `AGENTS.md` §8. Setup per mesin tidak lagi satu perintah
`docker compose up`; role dan database harus dibuat sekali secara manual
(langkahnya ada di README). `make verify` bergantung pada `make db-status`
supaya gate tidak lolos saat container mati.

**Catatan keamanan.** Role `ops_user` masih bisa CONNECT ke `appsdb` karena
PostgreSQL memberi hak itu ke `PUBLIC` secara default. Tidak dicabut di sini
karena `appsdb` milik project lain dan mencabut hak `PUBLIC` di sana
mempengaruhi role lain juga. Kalau isolasi ketat dibutuhkan, pemilik `appsdb`
yang menjalankan `REVOKE CONNECT ON DATABASE appsdb FROM PUBLIC;`.

**Cara membalik.** Buat lagi `docker-compose.yml` dengan service postgres di
port lain (jangan 5432 maupun 55432), arahkan `DATABASE_URL` ke sana, dan
kembalikan target `up`/`down` di `Makefile`.

---

## ADR-012 — Hak akses menu berbasis Group + grant personal (`apps.access`)

**Tanggal:** 2026-09-03 · **Status:** Accepted

**Konteks.** Panel operasional butuh mengelompokkan user dan mengatur siapa
boleh membuka menu mana — per grup maupun perorangan. Django sudah punya
`Group`/`Permission`, tapi `Permission` terikat per-model (`view_user`, dsb.),
bukan per-menu, sehingga tidak bisa langsung dipakai sebagai "hak akses menu"
yang dikelola operator.

**Keputusan.** Module baru `apps.access`:

- Grouping tetap memakai `auth.Group` — bukan model Role baru; user→grup
  tetap dikelola lewat admin `accounts.User`.
- `Feature` = katalog menu (slug unik), di-seed dari deklarasi `navigation.py`
  tiap module lewat `sync_features` (idempotent, tidak pernah menghapus
  feature yang hilang dari kode, dan tidak menyentuh kolom operator:
  description, required_permission, is_active).
- `FeatureGrant` = satu keputusan akses: feature → group ATAU user, dengan
  efek allow/deny. Referensi user disimpan `UUIDField` (R4).
- Satu titik evaluasi: `selectors.user_can_access` — fail-closed: default
  deny, `deny` > `allow` pada level yang sama, personal > group, superuser
  bypass, user non-aktif ditolak semua.
- Dua lapis otorisasi: **visibility** (`FeatureGrant`) dan **enforcement**
  (`has_perm`), dijembatani `Feature.required_permission` (opsional, diisi
  operator) supaya user tidak melihat menu yang akan menolaknya 403.
- Penulisan grant lewat `services.grant_feature` (upsert + event
  `access.feature_granted`), penghapusan lewat `services.revoke_feature`.

**Konsekuensi.** Setelah deploy, operator non-superuser melihat sidebar
kosong sampai `sync_features` dijalankan dan grant dibuat — itu memang
default-deny-nya. Module baru cukup menambah key `feature` di item
`navigation.py`-nya untuk masuk katalog. `FeatureGrant.group` memakai FK ke
`auth.Group` (framework bersama, setara `User.groups`), beda dari referensi
user yang `UUIDField`.

**Cara membalik.** Hapus `apps.access`, kembalikan tiap `can_*` di
`navigation.py` ke `has_perm` murni, dan drop tabel `access_feature` /
`access_featuregrant`.

---

## ADR-013 — Status akun user sebagai enum `status`

**Tanggal:** 2026-09-03 · **Status:** Accepted

**Konteks.** `is_active` adalah boolean tunggal: cukup untuk "boleh login /
tidak", tapi tidak bisa membedakan user yang dinonaktifkan permanen dari yang
ditangguhkan sementara. Operasi (suspend sementara vs deactivate permanen)
jadi tidak bisa dibedakan saat dilihat kembali, dan "aktifkan lagi" tidak bisa
dibedakan dari "cabut suspend".

**Keputusan.** Field enum `User.status` (`IntegerChoices`): 1 = ACTIVE,
0 = INACTIVE, 2 = SUSPENDED. `is_active` tetap jadi gerbang auth
`ModelBackend` Django (tanpa backend custom), tapi diturunkan dari `status` di
satu titik invariant `User.save()`: `is_active = (status == ACTIVE)`.
Manajemen status/grup/permission (dan `is_staff`/`is_superuser`) superuser-only
di admin. Migrasi `0002_user_status` menambahkan field dan mem-backfill user
`is_active=False` menjadi INACTIVE.

**Konsekuensi.** Satu sumber kebenaran (`status`) dan `is_active` tidak mungkin
melenceng lagi. Admin menampilkan `status` (enum) bukan `is_active`. Kelemahan
sebelumnya (non-superuser bisa menaikkan `is_staff`) ditutup lewat readonly
fields. Backfill memakai `queryset.update` supaya invariant `save()` tidak
menimpa sinyal `is_active` yang sedang dipindahkan.

**Cara membalik.** Hapus field `status` + tambah migrasi baru (R10: jangan
ubah migrasi lama) yang memetakan balik status ke `is_active`, dan kembalikan
`User.save()` serta `_create_user` ke perilaku `is_active` langsung.

---

## ADR-014 — Alias publik `cms_ops`, identifier internal tidak berubah

**Tanggal:** 2026-09-04 · **Status:** Accepted

**Konteks.** Project perlu dikenal dengan nama publik `cms_ops` (branding,
komunikasi, judul panel). Tapi identifier internal sudah terpakai di banyak
tempat yang masing-masing sudah jadi keputusan tersendiri: package project
`config` (ADR-001), database & role `ops_views`/`ops_user` di container
PostgreSQL bersama (ADR-011), folder repo, slug vault knowledge `ops_views`,
serta nama service/nginx di dokumen deploy. Rename penuh berbiaya tinggi
(migrasi, systemd, container bersama) dan tidak memberi nilai fungsional.

**Keputusan.** `cms_ops` menjadi **alias** — bukan rename. Yang memakai alias:
- Tampilan admin: `UNFOLD["SITE_TITLE"]`/`SITE_HEADER`, dibaca dari
  `DJANGO_SITE_TITLE` (default `"CMS Ops"`) — bisa dioverride per environment
  tanpa ubah kode.
- Judul README dan baris identitas AGENTS.md.

Identifier internal **tetap**: package `config`, database `ops_views`,
role `ops_user`, folder repo `ops_views`, slug vault `ops_views`,
`DATABASE_APPLICATION_NAME`.

**Konsekuensi.** Ada dua nama untuk satu project: alias publik `cms_ops` dan
nama internal `ops_views`. Dokumen selalu menyebut hubungan keduanya di satu
tempat (README + tabel identitas AGENTS.md). Agent berikutnya **jangan**
menyeragamkan dengan merename package/database/vault — itu membalik ADR-001
dan/atau ADR-011.

**Cara membalik.** Hapus alias dari README, AGENTS.md, dan default
`DJANGO_SITE_TITLE` di `base.py`. Kalau rename penuh benar-benar diinginkan,
buat ADR baru yang secara eksplisit menggantikan ADR-001 dan ADR-011, lalu
jalankan migrasinya sebagai proyek terpisah — bukan efek samping dari alias.

---

## ADR-015 — Redis untuk cache lewat container bersama

**Tanggal:** 2026-09-04 · **Status:** Accepted

**Konteks.** Project butuh cache backend nyata (bukan cuma locmem per-worker)
untuk hal-hal yang harus konsisten lintas worker/proses — mis. rate limiting
atau cache query yang mahal, seiring modul baru ditambahkan. Mesin
development sudah menjalankan container `redis` (`redis:7-alpine`, port 6379,
`requirepass` aktif) dipakai bersama project lain — pola yang sama dengan
`postgres` di [ADR-011](#adr-011--memakai-container-postgresql-bersama-bukan-container-per-project).
Django 4+ sudah punya `RedisCache` bawaan
(`django.core.cache.backends.redis.RedisCache`), jadi tidak ada alasan
menambah dependency `django-redis` hanya untuk backend cache sederhana.

**Keputusan.**
- Cache dikonfigurasi lewat satu variable, `REDIS_URL`, diparse
  `env.cache_url()` (django-environ) di [base.py](../config/settings/base.py).
  Skema `redis://` otomatis resolve ke `RedisCache` bawaan Django karena
  `django-redis` sengaja tidak diinstal (lihat `compat.choose_rediscache_driver`
  di django-environ).
- **Tidak fail-closed** seperti `DATABASE_URL`: `REDIS_URL` kosong → fallback
  `locmemcache://`. Caching itu optimisasi, bukan prasyarat boot — mesin/CI
  tanpa Redis tetap lolos `manage.py check`/`test`.
- Isolasi dari project lain di container bersama lewat **nomor database
  Redis** (bukan `0`) + **`KEY_PREFIX`** (default `"ops_views"`, override
  lewat `CACHE_KEY_PREFIX`), bukan container terpisah — karena Redis tidak
  punya konsep role/schema seperti PostgreSQL. `KEY_PREFIX` diset **eksplisit
  di `base.py`** setelah `env.cache_url()`, bukan lewat query string
  `?key_prefix=` di `REDIS_URL` — django-environ 0.14.0 menulis key dari
  query string itu sebagai `key_prefix` huruf kecil di dict `CACHES`, sementara
  Django hanya membaca `KEY_PREFIX` huruf besar di level itu, jadi lewat URL
  prefix-nya diam-diam tidak pernah terpakai (dicoba dan dikonfirmasi manual
  lewat `cache.make_key()` sebelum entri ini ditulis).
- `apps/common/views.readiness` melaporkan status tiap `CACHES` alias, tapi
  kegagalannya **tidak** menjatuhkan `healthy` — Redis down tidak boleh
  membuat pod keluar dari rotasi kalau database (yang benar-benar dibutuhkan)
  masih sehat.

**Konsekuensi.** Satu instance Redis untuk semua project di mesin ini —
`docker rm`, `docker volume rm`, atau `FLUSHALL` sembarangan menjatuhkan
project lain, dilarang di AGENTS.md §8 (sama seperti `postgres`). Isolasi
lewat nomor database + prefix lebih lemah dari isolasi role PostgreSQL:
project lain yang tahu password container tetap bisa `FLUSHDB` nomor database
manapun. Cache karena itu tidak boleh dipakai untuk apa pun yang sensitif atau
yang tidak boleh hilang. Menambah cache backend baru berarti menambah
dependency (`redis` di `requirements/base.txt`) — sudah disetujui user sesuai
gerbang di AGENTS.md §6.

**Cara membalik.** Hapus `CACHES` dari `base.py` (Django jatuh balik ke
locmem default), hapus `REDIS_URL` dari `.env`/`.env.example`/README, hapus
`redis` dari `requirements/base.txt`, dan hapus blok cache di
`apps/common/views.readiness`.

---

## ADR-016 — RBAC bertingkat: Module→Feature→Action + pohon organisasi

**Tanggal:** 2026-09-05 · **Status:** Accepted · **Menggantikan sebagian ADR-012**

**Konteks.** ADR-012 memberi dua level — `Feature` (menu) + `FeatureGrant`
(group/user, allow/deny) — dengan enforcement terpisah lewat `has_perm`.
Operator butuh akses bertingkat: katalog Module→Feature→Action yang di-scan
dari kode, hierarki organisasi dinamis (supervisor→staff→manager), dan hak
akses per posisi yang diekspresikan sebagai grant di level action (staff input,
supervisor edit+approve). Enforcement yang hanya menyembunyikan menu terbukti
tidak cukup — bug HIGH "grant/deny tidak memblokir URL".

**Keputusan.**
- Katalog berjenjang di `apps.access`: `Module` (slug == app name), `Feature`
  (`module` tetap slug string), `Action` (slug global `<feature>.<code>`).
  Di-scan dari deklarasi kode (`navigation.py` + `actions.py`) lewat
  `sync_catalog` (idempotent, never-delete); `sync_features` jadi alias deprecated.
- Pohon organisasi `OrgUnit` (parent self-FK, anti-siklus) +
  `OrgUnitMembership` (`user_id` UUIDField per R4). Level/posisi = posisi di pohon.
- `FeatureGrant` digeneralisasi: + `action` FK (nullable = seluruh feature),
  grantee 3-arah (group/user/org_unit) dengan constraint DB.
- Evaluasi tunggal `user_can(user, action_slug)`, fail-closed: scope action >
  feature; grantee personal > org_unit (termasuk leluhur) > group; deny > allow.
- **Enforcement**: admin feature module meng-override `has_*_permission` memanggil
  `user_can`; `apps.access.*` + `auth.Group` superuser-only. Ini membalik
  sebagian ADR-012 — visibility dan enforcement kini sama-sama lewat grant.

**Konsekuensi.** Grant benar-benar memblokir URL, bukan hanya menyembunyikan
menu. Operator non-superuser melihat admin kosong sampai `sync_catalog`
dijalankan dan grant dibuat (default-deny). `apps.common` tetap R7-clean.
Workflow approval (state machine record) tetap di luar scope — rencana terpisah.

**Cara membalik.** Kembalikan `has_*_permission` tiap admin ke default
`ModelAdmin`, lalu drop tabel `access_module`/`access_action`/`access_orgunit`/
`access_orgunitmembership` dan kolom `action`/`org_unit` di `access_featuregrant`
lewat migrasi baru (R10).

---

<!--
Template entri baru:

## ADR-00N — <judul singkat>

**Tanggal:** YYYY-MM-DD · **Status:** Accepted | Superseded by ADR-00X

**Konteks.** Masalah apa yang dihadapi.
**Keputusan.** Apa yang dipilih.
**Konsekuensi.** Apa yang jadi lebih mudah, apa yang jadi lebih sulit.
**Cara membalik.** Langkahnya, atau kenapa tidak bisa.
-->
