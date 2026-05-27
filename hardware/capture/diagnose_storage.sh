#!/bin/bash
# Quick storage diagnostic for EduPulse Pi
# Run this on the Raspberry Pi when SSDs are not showing up

echo "=== EduPulse Storage Diagnosis ==="
echo "Date: $(date)"
echo

echo "=== Block Devices (lsblk) ==="
lsblk -f
echo

echo "=== USB Devices ==="
lsusb || echo "lsusb not available"
echo

echo "=== dmesg (last 50 lines mentioning usb/sd/nvme) ==="
dmesg | grep -iE 'usb|sd |nvme|ssd|block' | tail -30
echo

echo "=== Mounted Filesystems ==="
mount | grep -E 'sd|nvme|mmc'
echo

echo "=== df -h ==="
df -h
echo

echo "=== Checking for common SSD mount points ==="
for dir in /mnt /data /ssd /storage /media; do
    if [ -d "$dir" ]; then
        echo "Contents of $dir:"
        ls -la "$dir" 2>/dev/null | head -10
        echo
    fi
done

echo "=== Recommendations ==="
echo "1. If SSDs are USB: try different USB ports (preferably blue USB 3.0)"
echo "2. Check power — some SSD enclosures need external power"
echo "3. Run:  sudo fdisk -l    to see if partitions exist but are not mounted"
echo "4. If NVMe: check if the PCIe adapter/HAT is properly seated and powered"
echo
echo "Please paste the full output of this script + 'sudo fdisk -l' if SSDs are still missing."