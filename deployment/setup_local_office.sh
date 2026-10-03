#!/usr/bin/env bash
# ==============================================================================
# Momento Local Office & Headless LibreOffice Setup Script for Ubuntu VPS
# (Designed for Ubuntu 22.04 / 24.04 on Contabo / DigitalOcean / Linode)
# ==============================================================================

set -euo pipefail

echo "========================================================"
echo "  Setting up Momento Local Self-Hosted Office Engine   "
echo "========================================================"

# 1. Update APT repository lists
echo "[1/4] Updating package lists..."
sudo apt update -y

# 2. Install headless LibreOffice, Writer, Calc, and universal fonts
echo "[2/4] Installing headless LibreOffice and system typography fonts..."
sudo apt install -y --no-install-recommends \
    libreoffice \
    libreoffice-writer \
    libreoffice-calc \
    fonts-dejavu \
    fonts-dejavu-core \
    fonts-dejavu-extra \
    fonts-liberation \
    fonts-noto-core \
    default-jre-headless

# 3. Create dedicated exports directory and ensure proper file permissions
EXPORTS_DIR="/var/www/momento/exports"
DOWNLOADS_DIR="/var/www/momento/downloads"

echo "[3/4] Ensuring export storage directories exist..."
sudo mkdir -p "${EXPORTS_DIR}"
sudo mkdir -p "${DOWNLOADS_DIR}"

if id -u www-data >/dev/null 2>&1; then
    sudo chown -R www-data:www-data "${EXPORTS_DIR}" "${DOWNLOADS_DIR}"
    sudo chmod -R 775 "${EXPORTS_DIR}" "${DOWNLOADS_DIR}"
    echo "Permissions assigned to www-data."
fi

# 4. Verification
echo "[4/4] Verifying headless LibreOffice installation..."
if command -v libreoffice >/dev/null 2>&1; then
    echo "✓ LibreOffice binary located at: $(command -v libreoffice)"
    libreoffice --version
    echo "✓ Momento Local Office Engine is ready for self-hosted DOCX, PDF, XLSX, and ODS generation!"
else
    echo "✗ Error: LibreOffice installation could not be verified."
    exit 1
fi

echo "========================================================"
echo "  Installation Complete!                               "
echo "========================================================"
