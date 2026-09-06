# Shortcut untuk perintah yang sering dipakai.
# Jalankan dari direktori ini (tempat manage.py).

# Virtualenv boleh di dalam repo (env/) atau di sebelahnya (../env) - dipakai
# yang mana pun yang ada, supaya layout venv tidak mengunci perintah.
PY := $(shell \
	if   [ -x env/bin/python ];    then echo env/bin/python; \
	elif [ -x ../env/bin/python ]; then echo ../env/bin/python; \
	else echo "MISSING"; fi)

.DEFAULT_GOAL := help
.PHONY: help guard db-status db-logs redis-status redis-logs install migrations migrate superuser seed seed-dummy run shell dbshell test check deploy-check verify

guard:
	@if [ "$(PY)" = "MISSING" ]; then \
		echo "Virtualenv tidak ditemukan di env/ maupun ../env."; \
		echo "Buat dulu:  python3.14 -m venv env && make install"; \
		exit 1; fi

help:  ## Tampilkan daftar target
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n",$$1,$$2}'

# Project ini TIDAK punya container sendiri - memakai container postgres
# bersama yang sudah jalan di mesin ini. Lihat README ("Database").
PG_CONTAINER ?= postgres

db-status:  ## Cek container PostgreSQL bersama sedang jalan
	@if [ "$$(docker inspect -f '{{.State.Running}}' $(PG_CONTAINER) 2>/dev/null)" != true ]; then \
		echo "Container '$(PG_CONTAINER)' tidak jalan."; \
		echo "Hidupkan dengan:  docker start $(PG_CONTAINER)"; \
		exit 1; fi
	@echo "$(PG_CONTAINER): $$(docker inspect -f '{{.State.Status}}{{if .State.Health}} ({{.State.Health.Status}}){{end}}' $(PG_CONTAINER))"

db-logs:  ## Ikuti log PostgreSQL
	docker logs -f $(PG_CONTAINER)

# Project ini TIDAK punya container Redis sendiri - memakai container `redis`
# bersama yang sudah jalan di mesin ini. Lihat README ("Cache").
REDIS_CONTAINER ?= redis

redis-status:  ## Cek container Redis bersama sedang jalan (opsional - cache fallback ke locmem)
	@if [ "$$(docker inspect -f '{{.State.Running}}' $(REDIS_CONTAINER) 2>/dev/null)" != true ]; then \
		echo "Container '$(REDIS_CONTAINER)' tidak jalan. Cache akan fallback ke locmem."; \
		echo "Hidupkan dengan:  docker start $(REDIS_CONTAINER)"; \
		exit 1; fi
	@echo "$(REDIS_CONTAINER): $$(docker inspect -f '{{.State.Status}}{{if .State.Health}} ({{.State.Health.Status}}){{end}}' $(REDIS_CONTAINER))"

redis-logs:  ## Ikuti log Redis
	docker logs -f $(REDIS_CONTAINER)

install: guard  ## Pasang dependency development
	$(PY) -m pip install -r requirements/local.txt

migrations: guard  ## Buat migrasi baru
	$(PY) manage.py makemigrations

migrate: guard  ## Terapkan migrasi
	$(PY) manage.py migrate

superuser: guard  ## Buat akun admin (interaktif, diminta email)
	$(PY) manage.py createsuperuser

seed: guard  ## Buat akun admin pertama dari DJANGO_SEED_ADMIN_* di .env
	$(PY) manage.py seed_admin

seed-dummy: guard  ## Buat akun test non-admin dari DJANGO_SEED_DUMMY_* di .env
	$(PY) manage.py seed_dummy

# Mesin ini menjalankan beberapa app; 8000 sering sudah dipakai.
#   make run PORT=8100
PORT ?= 8000

run: guard  ## Jalankan development server (PORT=8000)
	$(PY) manage.py runserver $(PORT)

shell: guard  ## Django shell
	$(PY) manage.py shell

dbshell: guard  ## psql ke database yang sedang dipakai
	$(PY) manage.py dbshell

test: guard  ## Jalankan test suite
	DJANGO_FAST_PASSWORD_HASHER=True $(PY) manage.py test apps

check: guard  ## System check (development)
	$(PY) manage.py check

deploy-check: guard  ## Audit keamanan production, gagal pada warning apa pun
	DJANGO_SETTINGS_MODULE=config.settings.production \
	DJANGO_ALLOWED_HOSTS=ops.example.com \
	DATABASE_URL="postgres://ops:pw@127.0.0.1:5432/ops_views" \
	$(PY) manage.py check --deploy --fail-level WARNING

verify: db-status check  ## GATE - wajib hijau sebelum melapor selesai (AGENTS.md §7)
	@echo "==> migrasi tertinggal?"
	@$(PY) manage.py makemigrations --check --dry-run
	@echo "==> test"
	@$(MAKE) --no-print-directory test
	@echo "==> audit keamanan production"
	@$(MAKE) --no-print-directory deploy-check
	@echo "\n✅ semua gate hijau"
