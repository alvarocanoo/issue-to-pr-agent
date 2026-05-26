# Postgres — local dev with `pgsql-portable`

Used from Week 3 onwards (run metadata + JSONB traces). Production goes in Docker/managed Postgres.

## Why `pgsql-portable`

The user has `C:\Users\acano\pgsql-portable\pgsql\bin` available (Postgres 16.14) — no Docker
required for the DB layer. Container tooling is reserved for the sandbox (see [adr/003-sandbox.md](adr/003-sandbox.md)).

## One-time init

```powershell
$pg = "C:\Users\acano\pgsql-portable\pgsql\bin"
$data = "C:\Users\acano\pgsql-portable\data"

# init data dir (first run only)
& "$pg\initdb.exe" -D $data -U itp --pwfile=(@'
itp
'@ | New-TemporaryFile | Tee-Object | Out-Null; (Get-Item .).FullName)

# start server
& "$pg\pg_ctl.exe" -D $data -l "$data\logfile" start

# create DB matching DATABASE_URL in .env
& "$pg\psql.exe" -U itp -h localhost -c "CREATE DATABASE itp;"
```

## Daily start / stop

```powershell
$pg = "C:\Users\acano\pgsql-portable\pgsql\bin"
$data = "C:\Users\acano\pgsql-portable\data"
& "$pg\pg_ctl.exe" -D $data -l "$data\logfile" start
& "$pg\pg_ctl.exe" -D $data stop
```

## Verify

```powershell
& "$pg\psql.exe" -U itp -h localhost -d itp -c "SELECT version();"
```

`DATABASE_URL` in `.env` defaults to `postgresql://itp:itp@localhost:5432/itp`.
