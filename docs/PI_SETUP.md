# Raspberry Pi Setup Guide — Cloud Rover

Complete setup guide for the Pi edge controller. Follow these steps to go from a blank SD card to a fully configured rover brain.

## Hardware

| Component | Model | Notes |
|-----------|-------|-------|
| Board | Raspberry Pi 3 Model B v1.2 | 1GB RAM, aarch64 |
| Camera | ArduCam IMX708 (12MP) | CSI ribbon cable |
| OS | Raspberry Pi OS Desktop (64-bit) | Debian 13 Trixie, Kernel 6.12 |
| Storage | 16GB+ microSD | Class 10 or better |

## Quick Setup (Automated)

If you have a freshly flashed Pi OS, run the automated script:

```bash
# From your Mac (must be on same network as Pi):
scp scripts/pi-setup.sh pi:~/
ssh pi "bash ~/pi-setup.sh"
```

Or directly on the Pi:

```bash
curl -fsSL https://raw.githubusercontent.com/viktor1223/cloud-rover/main/scripts/pi-setup.sh | bash
```

## Manual Setup

### 1. Flash the SD Card

Download [Raspberry Pi OS Desktop 64-bit](https://www.raspberrypi.com/software/operating-systems/) (Trixie release).

From macOS:

```bash
# Find your SD card
diskutil list external

# Unmount (replace disk4 with your disk)
diskutil unmountDisk /dev/disk4

# Flash (replace with your image path and disk)
xz -dc ~/Downloads/raspios-trixie-arm64.img.xz | sudo dd of=/dev/rdisk4 bs=4m status=progress

# Eject
sync && diskutil eject /dev/disk4
```

### 2. First Boot Configuration

Mount the boot partition and configure:

```bash
# Enable SSH
touch /Volumes/bootfs/ssh
```

Edit `/Volumes/bootfs/network-config` for WiFi:

```yaml
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
        YOUR_WIFI_SSID:
          password: "YOUR_WIFI_PASSWORD"
```

### 3. SSH Key Setup (from Mac)

```bash
# Generate key (if you don't have one)
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519

# Copy to Pi
ssh-copy-id -i ~/.ssh/id_ed25519 viktor@pi-brain.local

# Add to SSH config (~/.ssh/config)
Host pi
    HostName pi-brain.local
    User viktor
    IdentityFile ~/.ssh/id_ed25519
```

### 4. Fix Common First-Boot Issues

```bash
# Fix home directory ownership (cloud-init sometimes sets root)
sudo chown -R viktor:viktor /home/viktor

# Fix hostname resolution
sudo sh -c 'echo "127.0.1.1 pi-brain" >> /etc/hosts'
```

### 5. Camera Configuration (ArduCam IMX708)

Edit `/boot/firmware/config.txt`:

```ini
# Disable auto-detect (required for ArduCam IMX708)
camera_auto_detect=0

# Add IMX708 overlay (at end of file)
dtoverlay=imx708
```

Reboot and verify:

```bash
sudo reboot
# After reboot:
rpicam-hello --list-cameras
dmesg | grep imx708
```

Expected output: `imx708 [4608x2592 10-bit RGGB]`

### 6. Install System Packages

```bash
sudo apt-get update
sudo apt-get install -y \
    git \
    python3-pip \
    python3-venv \
    python3-gpiozero \
    python3-pigpio \
    python3-picamera2 \
    python3-requests \
    python3-pil \
    python3-libcamera \
    i2c-tools \
    rpicam-apps \
    curl
```

### 7. Install GitHub CLI

```bash
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] \
    https://cli.github.com/packages stable main" \
    | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt-get update
sudo apt-get install -y gh
```

### 8. Clone and Test

```bash
gh auth login
git clone https://github.com/viktor1223/cloud-rover.git ~/cloud-rover
cd ~/cloud-rover

# Test camera
rpicam-still -o /tmp/test.jpg --width 640 --height 480
python3 pi/camera_test.py
```

## VS Code Remote Development

Develop on your Mac, run on the Pi:

1. Install **Remote - SSH** extension in VS Code
2. `Cmd+Shift+P` → "Remote-SSH: Connect to Host" → `pi`
3. Open folder `/home/viktor/cloud-rover`

## Verified Package Versions

Captured from working setup (2026-06-07):

| Package | Version |
|---------|---------|
| Raspberry Pi OS | Debian 13 (Trixie) |
| Kernel | 6.12.75+rpt-rpi-v8 |
| Python | 3.13.5 |
| picamera2 | 0.3.34-1 |
| libcamera | 0.7.1+rpt20260429 |
| rpicam-apps | 1.12.0-1 |
| gpiozero | 2.0.1 |
| pigpio | 1.78 |
| Pillow | 11.1.0 |
| requests | 2.32.3 |
| i2c-tools | 4.4-2 |
| git | 2.47.3 |
| gh (GitHub CLI) | 2.93.0 |

## Troubleshooting

### Camera not detected
- Check ribbon cable is fully seated (blue side faces ethernet port on Pi 3)
- Verify `dtoverlay=imx708` in `/boot/firmware/config.txt`
- Verify `camera_auto_detect=0`
- Run `dmesg | grep imx708` — should show `camera module ID`

### SSH connection refused
- Ensure `ssh` file exists in boot partition
- Check Pi IP: connect a monitor and run `hostname -I`

### sudo: cannot execute binary file
- This means architecture mismatch — verify you flashed the 64-bit image
- Check with `uname -m` — should say `aarch64`
