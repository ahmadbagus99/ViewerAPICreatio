# Creatio API Viewer

Creatio API Viewer receives OpenAPI documents from approved Scanner
installations, serves public Swagger documentation, and provides an
authenticated administration interface.

The Viewer can run locally with JSON storage, use PostgreSQL, or be deployed
with Docker Compose.

## Requirements

For local PowerShell deployment:

- Windows PowerShell 5.1 or PowerShell 7
- Python 3.10 or newer
- PostgreSQL only when the `postgres` storage backend is selected

For container deployment:

- Docker Desktop or Docker Engine
- Docker Compose v2

## Local Quick Start

Open PowerShell in the Viewer repository and run:

```powershell
.\setup.ps1
```

The interactive setup asks for:

1. The storage backend: JSON or PostgreSQL
2. The PostgreSQL connection URL when PostgreSQL is selected
3. The Viewer administrator username
4. The Viewer administrator password

Pressing Enter for the login prompts uses these local defaults:

```text
Username: admin
Password: admin123
```

Start the Viewer:

```powershell
.\start.ps1
```

Open the public Viewer:

```text
http://127.0.0.1:8090
```

Open the administration login:

```text
http://127.0.0.1:8090/login.html
```

Press `Ctrl+C` to stop the service.

If `start.ps1` is executed before setup, it automatically starts the
interactive setup.

## Storage Setup

### JSON

JSON storage does not require a database:

```powershell
.\setup.ps1 `
  -StorageBackend json `
  -AdminUsername "admin" `
  -AdminPassword "change-this-password"

.\start.ps1
```

Viewer data is stored under:

```text
data/catalog.json
data/scanners.json
docs/{slug}/openapi.json
```

### PostgreSQL

Run:

```powershell
.\setup.ps1 `
  -StorageBackend postgres `
  -DatabaseUrl "postgresql://user:password@localhost:5432/creatio_viewer" `
  -AdminUsername "admin" `
  -AdminPassword "change-this-password"

.\start.ps1
```

The setup script creates `.venv`, installs the PostgreSQL driver, and saves the
local configuration.

The following tables are created automatically:

```text
viewer_instances
viewer_scanners
viewer_documents
```

## Setup Options

Example:

```powershell
.\setup.ps1 `
  -StorageBackend postgres `
  -DatabaseUrl "postgresql://user:password@localhost:5432/creatio_viewer" `
  -HostAddress "127.0.0.1" `
  -Port 8090 `
  -PublicUrl "https://api-docs.example.com" `
  -AdminUsername "admin" `
  -AdminPassword "change-this-password"
```

Available parameters:

| Parameter | Description | Default |
| --- | --- | --- |
| `StorageBackend` | `json` or `postgres` | Interactive selection |
| `DatabaseUrl` | PostgreSQL connection URL | Required for PostgreSQL |
| `HostAddress` | HTTP bind address | `127.0.0.1` |
| `Port` | Viewer HTTP port | `8090` |
| `PublicUrl` | Public URL returned after publishing | Local Viewer URL |
| `AdminUsername` | Administration login username | `admin` |
| `AdminPassword` | Administration login password | `admin123` |
| `SkipInstall` | Skip Python dependency installation | Disabled |

The generated configuration is stored in:

```text
.runtime/config.json
```

It contains the database URL and administration credentials and is excluded
from Git. `start.ps1` converts this configuration into environment variables
for the Python process.

## Scanner Registration and Publishing

The Viewer only accepts publishing requests from registered Scanner
installations using Bearer tokens.

Registration flow:

1. Start the Viewer.
2. Configure the Viewer URL in Scanner Settings.
3. Select **Register Scanner** in the Scanner.
4. Open the Viewer administration page.
5. Open **Registered Scanners**.
6. Approve the pending Scanner.
7. Return to Scanner Settings and check its status.

The Scanner can publish after approval. The Viewer stores only a hash of the
Scanner token.

## Administration

Open:

```text
http://127.0.0.1:8090/login.html
```

Administrators can:

- Approve, revoke, and delete Scanner registrations
- Edit documentation metadata
- Change active or deprecated status
- Change public or private visibility
- Delete documentation and its OpenAPI document

## Docker Deployment

The Docker deployment performs these operations:

1. Builds a Viewer image with Python and PowerShell
2. Creates a PostgreSQL container and database
3. Waits until PostgreSQL is healthy
4. Runs `setup.ps1` inside the Viewer container
5. Runs `start.ps1` inside the Viewer container

### First Run

Run:

```powershell
.\deploy-docker.ps1
```

On the first run, the script creates:

```text
.env.docker
```

It then stops so the generated file can be reviewed. Update at least:

```env
POSTGRES_PASSWORD=change-this-db-password
VIEWER_PUBLIC_URL=http://localhost:8090
VIEWER_ADMIN_USERNAME=admin
VIEWER_ADMIN_PASSWORD=change-this-admin-password
VIEWER_SESSION_SECRET=replace-with-a-long-random-secret
VIEWER_COOKIE_SECURE=false
```

For an HTTPS production deployment, set:

```env
VIEWER_PUBLIC_URL=https://api-docs.example.com
VIEWER_COOKIE_SECURE=true
```

Deploy after saving the configuration:

```powershell
.\deploy-docker.ps1 -Detached
```

The default URL is:

```text
http://localhost:8090
```

### Docker Commands

View logs:

```powershell
docker compose --env-file .env.docker logs -f viewer
```

Stop the deployment:

```powershell
docker compose --env-file .env.docker down
```

Stop and remove the PostgreSQL and runtime volumes:

```powershell
docker compose --env-file .env.docker down -v
```

The `-v` option permanently deletes the Docker-managed Viewer database.

## Environment Variable Reference

The local script workflow sets most variables automatically. Deployment
platforms may configure:

```env
HOST=0.0.0.0
PORT=8090
STORAGE_BACKEND=postgres
DATABASE_URL=postgresql://user:password@localhost:5432/creatio_viewer
VIEWER_PUBLIC_URL=https://api-docs.example.com
VIEWER_ADMIN_USERNAME=admin
VIEWER_ADMIN_PASSWORD=change-this-admin-password
VIEWER_SESSION_SECRET=generate-a-long-random-secret
VIEWER_COOKIE_SECURE=true
```

Variable purposes:

| Variable | Purpose |
| --- | --- |
| `HOST` | HTTP bind address |
| `PORT` | Viewer HTTP port |
| `STORAGE_BACKEND` | `json` or `postgres` |
| `DATABASE_URL` | PostgreSQL connection URL |
| `VIEWER_PUBLIC_URL` | Public base URL used in publish responses |
| `VIEWER_ADMIN_USERNAME` | Administration login username |
| `VIEWER_ADMIN_PASSWORD` | Administration login password |
| `VIEWER_SESSION_SECRET` | Secret used to sign administration sessions |
| `VIEWER_COOKIE_SECURE` | Sends the session cookie only through HTTPS |

See `.env.example` for a direct environment-variable template and
`.env.docker.example` for Docker Compose. The Python server does not
automatically load `.env` files.

## API Summary

```text
GET    /api/catalog
POST   /api/scanners/register
GET    /api/scanner/status
POST   /api/publish
POST   /api/admin/login
POST   /api/admin/logout
GET    /api/admin/instances
GET    /api/admin/scanners
PUT    /api/admin/instances/{slug}
PUT    /api/admin/scanners/{scannerId}
DELETE /api/admin/instances/{slug}
DELETE /api/admin/scanners/{scannerId}
```

## Security Notes

- Use strong administration and database passwords.
- Set a long, random `VIEWER_SESSION_SECRET`.
- Use HTTPS in production.
- Set `VIEWER_COOKIE_SECURE=true` only when the Viewer is served through HTTPS.
- Keep `.runtime/config.json`, `.env`, and `.env.docker` out of Git.
- Rotate a Scanner registration by deleting it in the Viewer and registering
  it again from the Scanner.

## Repository Safety

The repository `.gitignore` excludes:

- `.runtime/` local configuration
- `.venv/` Python virtual environments
- `.env` files and secrets while retaining example files
- Python caches and test artifacts
- Runtime log files
- Common editor and operating-system files

