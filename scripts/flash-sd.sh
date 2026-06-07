#!/bin/bash
# =============================================================================
# Cloud Rover — Flash SD Card Script (macOS)
#
# Downloads and flashes Raspberry Pi OS to a microSD card, then pre-configures
# SSH, WiFi, user account, and hostname for headless first boot.
#
# Usage:
#   bash scripts/flash-sd.sh [--wifi-ssid SSID] [--wifi-pass PASS] [--user USER]
#
# Prerequisites:
#   - macOS with USB SD card reader
#   - microSD card (16GB+)
# =============================================================================
set -e

# Defaults
WIFI_SSID=""
WIFI_PASS=""
PI_USER="viktor"
PI_HOSTNAME="pi-brain"
IMAGE_URL="https://downloads.raspberrypi.com/raspios_arm64/images/raspios_arm64-2026-04-21/2026-04-21-raspios-trixie-arm64.img.xz"
IMAGE_SHA256="2b016db1eafc3f642eacfe5a1d9bf9e49be8b8caa0360c293901bf7b88bdebca"
IMAGE_FILE="/tmp/raspios.img.xz"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --wifi-ssid) WIFI_SSID="$2"; shift 2;;
        --wifi-pass) WIFI_PASS="$2"; shift 2;;
        --user) PI_USER="$2"; shift 2;;
        --hostname) PI_HOSTNAME="$2"; shift 2;;
        *) echo "Unknown option: $1"; exit 1;;
    esac
done

echo "============================================================"
echo "  Cloud Rover — Flash SD Card"
echo "============================================================"
echo "  User:     $PI_USER"
echo "  Hostname: $PI_HOSTNAME"
echo "  WiFi:     ${WIFI_SSID:-'(will prompt)'}"
echo "============================================================"

# Prompt for WiFi if not provided
if [ -z "$WIFI_SSID" ]; then
    read -rp "WiFi SSID: " WIFI_SSID
    read -rsp "WiFi Password: " WIFI_PASS
    echo ""
fi

# ------------------------------------------------------------------
# 1. Download image
# ------------------------------------------------------------------
if [ -f "$IMAGE_FILE" ]; then
    echo "[1/5] Verifying existing download..."
    ACTUAL_SHA=$(shasum -a 256 "$IMAGE_FILE" | awk '{print $1}')
    if [ "$ACTUAL_SHA" = "$IMAGE_SHA256" ]; then
        echo "  ✓ Image already downloaded and verified"
    else
        echo "  ✗ Checksum mismatch, re-downloading..."
        rm -f "$IMAGE_FILE"
    fi
fi

if [ ! -f "$IMAGE_FILE" ]; then
    echo "[1/5] Downloading Raspberry Pi OS Desktop 64-bit..."
    curl -L -o "$IMAGE_FILE" "$IMAGE_URL" --progress-bar
    ACTUAL_SHA=$(shasum -a 256 "$IMAGE_FILE" | awk '{print $1}')
    if [ "$ACTUAL_SHA" != "$IMAGE_SHA256" ]; then
        echo "  ✗ ERROR: SHA256 mismatch!"
        echo "    Expected: $IMAGE_SHA256"
        echo "    Got:      $ACTUAL_SHA"
        exit 1
    fi
    echo "  ✓ Download verified (SHA256 matches)"
fi

# ------------------------------------------------------------------
# 2. Find SD card
# ------------------------------------------------------------------
echo "[2/5] Looking for SD card..."
EXTERNAL_DISKS=$(diskutil list external 2>/dev/null | grep "^/dev/" | awk '{print $1}')

if [ -z "$EXTERNAL_DISKS" ]; then
    echo "  ✗ No external disk found. Insert your microSD card and try again."
    exit 1
fi

echo "  External disks found:"
for disk in $EXTERNAL_DISKS; do
    SIZE=$(diskutil info "$disk" | grep "Disk Size" | awk -F: '{print $2}' | xargs)
    echo "    $disk — $SIZE"
done

DISK=$(echo "$EXTERNAL_DISKS" | head -1)
read -rp "  Flash to $DISK? This will ERASE ALL DATA. (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "  Aborted."
    exit 0
fi

# ------------------------------------------------------------------
# 3. Flash image
# ------------------------------------------------------------------
echo "[3/5] Flashing image to ${DISK}..."
RDISK=$(echo "$DISK" | sed 's/disk/rdisk/')
diskutil unmountDisk "$DISK"
xz -dc "$IMAGE_FILE" | sudo dd of="$RDISK" bs=4m status=progress
sync

# ------------------------------------------------------------------
# 4. Configure boot partition
# ------------------------------------------------------------------
echo "[4/5] Configuring first boot..."
sleep 3
diskutil mountDisk "$DISK"
sleep 2

BOOT="/Volumes/bootfs"
if [ ! -d "$BOOT" ]; then
    echo "  ✗ Boot partition not found at $BOOT"
    exit 1
fi

# Enable SSH
touch "$BOOT/ssh"

# Configure WiFi
cat > "$BOOT/network-config" << NETEOF
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
      optional: true
  wifis:
    wlan0:
      dhcp4: true
      optional: false
      access-points:
        ${WIFI_SSID}:
          password: "${WIFI_PASS}"
NETEOF

# Configure user account
HASHED_PASS=$(openssl passwd -6 "changeme")
cat > "$BOOT/user-data" << USEREOF
#cloud-config
hostname: ${PI_HOSTNAME}
keyboard:
  model: pc105
  layout: us
ssh_pwauth: true
users:
- name: ${PI_USER}
  gecos: Cloud Rover User
  groups: users,adm,dialout,audio,netdev,video,plugdev,cdrom,games,input,gpio,spi,i2c,render,sudo
  shell: /bin/bash
  lock_passwd: false
  passwd: ${HASHED_PASS}
  sudo: ALL=(ALL) NOPASSWD:ALL
package_update: true
packages:
- avahi-daemon
- git
- curl
USEREOF

# Configure camera
sed -i '' 's/camera_auto_detect=1/camera_auto_detect=0/' "$BOOT/config.txt" 2>/dev/null || true
echo "dtoverlay=imx708" >> "$BOOT/config.txt"

echo "  ✓ SSH enabled"
echo "  ✓ WiFi configured"
echo "  ✓ User '$PI_USER' created (password: changeme — CHANGE ON FIRST LOGIN)"
echo "  ✓ Camera overlay configured"

# ------------------------------------------------------------------
# 5. Eject
# ------------------------------------------------------------------
echo "[5/5] Ejecting SD card..."
sync && diskutil eject "$DISK"

echo ""
echo "============================================================"
echo "  SD Card Ready!"
echo "============================================================"
echo ""
echo "  1. Insert SD into Pi, power on"
echo "  2. Wait 2-3 min for first boot"
echo "  3. From Mac: ssh ${PI_USER}@${PI_HOSTNAME}.local"
echo "     Password: changeme (change it immediately!)"
echo "  4. Run: bash ~/pi-setup.sh (or scp scripts/pi-setup.sh first)"
echo ""
echo "============================================================"
