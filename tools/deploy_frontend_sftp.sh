#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[deploy] %s\n' "$*"
}

die() {
  printf '[deploy][error] %s\n' "$*" >&2
  exit 1
}

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    die "Missing required environment variable: ${name}"
  fi
}

http_fetch_200() {
  local url="$1"
  local label="$2"
  local tmp
  local status

  tmp="$(mktemp)"
  status="$(curl -L -s -o "${tmp}" -w '%{http_code}' "${url}")"
  if [[ "${status}" != "200" ]]; then
    rm -f "${tmp}"
    die "HTTP check failed for ${label}: status=${status}, url=${url}"
  fi
  printf '%s\n' "${tmp}"
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${ROOT_DIR}/frontend/dist"
APP_BASE_URL="${APP_BASE_URL:-https://kikidoko.student-subscription.com}"
APP_BASE_URL="${APP_BASE_URL%/}"
BACKUP_BASE="${BACKUP_BASE:-/tmp/kikidoko-release-backup}"
RELEASE_ID="${RELEASE_ID:-$(date +%Y%m%d-%H%M%S)}"
BACKUP_DIR="${BACKUP_BASE}/${RELEASE_ID}"
SFTP_PORT="${SFTP_PORT:-22}"

require_env "SFTP_HOST"
require_env "SFTP_USER"
require_env "REMOTE_DOCROOT"

[[ -d "${DIST_DIR}" ]] || die "Build output not found: ${DIST_DIR}"

for file in index.html japan-prefectures.geojson terms.html privacy-policy.html vite.svg; do
  [[ -f "${DIST_DIR}/${file}" ]] || die "Required file not found in dist: ${file}"
done

for dir in assets brand; do
  [[ -d "${DIST_DIR}/${dir}" ]] || die "Required directory not found in dist: ${dir}"
done

js_asset="$(grep -oE 'assets/index-[^"]+\.js' "${DIST_DIR}/index.html" | head -n 1 || true)"
css_asset="$(grep -oE 'assets/index-[^"]+\.css' "${DIST_DIR}/index.html" | head -n 1 || true)"
[[ -n "${js_asset}" ]] || die "Could not detect JS asset in dist/index.html"
[[ -n "${css_asset}" ]] || die "Could not detect CSS asset in dist/index.html"

mkdir -p "${BACKUP_DIR}"

BACKUP_BATCH="${BACKUP_DIR}/backup.sftp.batch"
UPLOAD_BATCH="${BACKUP_DIR}/upload.sftp.batch"
ROLLBACK_BATCH="${BACKUP_DIR}/rollback.sftp.batch"
ROLLBACK_SCRIPT="${BACKUP_DIR}/rollback.sh"

{
  printf 'lcd "%s"\n' "${BACKUP_DIR}"
  printf 'cd "%s"\n' "${REMOTE_DOCROOT}"
  printf -- '-get index.html\n'
  printf -- '-get japan-prefectures.geojson\n'
  printf -- '-get terms.html\n'
  printf -- '-get privacy-policy.html\n'
  printf -- '-get vite.svg\n'
  printf -- '-get -r assets\n'
  printf -- '-get -r brand\n'
  printf 'bye\n'
} > "${BACKUP_BATCH}"

{
  printf 'lcd "%s"\n' "${DIST_DIR}"
  printf 'cd "%s"\n' "${REMOTE_DOCROOT}"
  printf 'put index.html\n'
  printf 'put japan-prefectures.geojson\n'
  printf 'put terms.html\n'
  printf 'put privacy-policy.html\n'
  printf 'put vite.svg\n'
  printf 'put -r assets\n'
  printf 'put -r brand\n'
  printf 'bye\n'
} > "${UPLOAD_BATCH}"

{
  printf 'lcd "%s"\n' "${BACKUP_DIR}"
  printf 'cd "%s"\n' "${REMOTE_DOCROOT}"
  printf -- '-put index.html\n'
  printf -- '-put japan-prefectures.geojson\n'
  printf -- '-put terms.html\n'
  printf -- '-put privacy-policy.html\n'
  printf -- '-put vite.svg\n'
  printf -- '-put -r assets\n'
  printf -- '-put -r brand\n'
  printf 'bye\n'
} > "${ROLLBACK_BATCH}"

cat > "${ROLLBACK_SCRIPT}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
sftp -P "${SFTP_PORT}" -b "${ROLLBACK_BATCH}" "${SFTP_USER}@${SFTP_HOST}"
echo "Rollback completed from ${BACKUP_DIR}"
EOF
chmod +x "${ROLLBACK_SCRIPT}"

log "Release ID: ${RELEASE_ID}"
log "Backing up remote files to ${BACKUP_DIR}"
sftp -P "${SFTP_PORT}" -b "${BACKUP_BATCH}" "${SFTP_USER}@${SFTP_HOST}"

log "Uploading frontend assets (excluding dist/blog)"
sftp -P "${SFTP_PORT}" -b "${UPLOAD_BATCH}" "${SFTP_USER}@${SFTP_HOST}"

log "Running HTTP verification"
root_tmp="$(http_fetch_200 "${APP_BASE_URL}/" "/")"
if ! grep -q 'id="root"' "${root_tmp}"; then
  rm -f "${root_tmp}"
  die "Root page does not contain id=\"root\""
fi
rm -f "${root_tmp}"

blog_tmp="$(http_fetch_200 "${APP_BASE_URL}/blog/" "/blog/")"
if ! grep -Eiq 'wp-content|wp-includes|wp-json|wordpress' "${blog_tmp}"; then
  rm -f "${blog_tmp}"
  die "/blog/ does not look like WordPress response"
fi
rm -f "${blog_tmp}"

guide_tmp="$(http_fetch_200 "${APP_BASE_URL}/blog/guide/research-equipment-sharing-basics/" "/blog/guide/...")"
rm -f "${guide_tmp}"

terms_tmp="$(http_fetch_200 "${APP_BASE_URL}/terms.html" "/terms.html")"
rm -f "${terms_tmp}"

privacy_tmp="$(http_fetch_200 "${APP_BASE_URL}/privacy-policy.html" "/privacy-policy.html")"
rm -f "${privacy_tmp}"

js_tmp="$(http_fetch_200 "${APP_BASE_URL}/${js_asset}" "JS asset")"
rm -f "${js_tmp}"

css_tmp="$(http_fetch_200 "${APP_BASE_URL}/${css_asset}" "CSS asset")"
rm -f "${css_tmp}"

log "Deployment finished successfully."
log "Backup directory: ${BACKUP_DIR}"
log "Rollback script: ${ROLLBACK_SCRIPT}"
