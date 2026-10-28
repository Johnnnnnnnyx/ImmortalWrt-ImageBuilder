#!/bin/sh
# Run on an x86/64 EFI SquashFS test guest. All writes are in a scratch folder.
set -e
script=${1:-/usr/libexec/johnny-update}
candidate=${2:-}
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
sed '/^case "${1:-status}" in/,$d' "$script" | sed "s|^work=/tmp/johnny-update$|work=$tmp/state|" > "$tmp/library"
. "$tmp/library"
latest=Johnnywrt-ISO-25.12.2-100
fixture() {
    printf '{"target":"%s","format":"%s","version":"%s","tag":"%s","rootfs_mb":%s}\n' \
        "$1" "$2" "$3" "$4" "$5" > "$work/firmware.json"
}
fixture x86/64 squashfs-combined-efi 25.12.2 "$latest" 1024
(validate_metadata)
for invalid in target format version tag size; do
    case "$invalid" in
        target) fixture aarch64 squashfs-combined-efi 25.12.2 "$latest" 1024 ;;
        format) fixture x86/64 ext4-combined-efi 25.12.2 "$latest" 1024 ;;
        version) fixture x86/64 squashfs-combined-efi 26.12.0 "$latest" 1024 ;;
        tag) fixture x86/64 squashfs-combined-efi 25.12.2 wrong 1024 ;;
        size) fixture x86/64 squashfs-combined-efi 25.12.2 "$latest" 2048 ;;
    esac
    if (validate_metadata); then echo "FAIL: accepted invalid $invalid"; exit 1; fi
done
printf test-image > "$work/$image"
printf '%064d  %s\n' 0 "$image" > "$work/SHA256SUMS"
if (verify_image); then echo 'FAIL: accepted corrupt image'; exit 1; fi
if [ -n "$candidate" ]; then
    cp "$candidate" "$work/$image"
    (cd "$work" && sha256sum "$image") > "$work/SHA256SUMS"
    (verify_image)
    echo 'PASS: real firmware hash, full partition map and sysupgrade -T'
fi
echo 'PASS: updater accepts matching layout; rejects target, format, series, tag, partition and hash mismatches'
