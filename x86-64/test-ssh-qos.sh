#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
# Exercise the exact upstream launch line, not a simulated patch function.
printf '%s\n' '#!/bin/sh' 'procd_set_param command "$PROG" -F -P "$pid_file"' > "$tmp/init"
sh x86-64/johnny-ssh-qos "$tmp/init"
grep -Fqx 'procd_set_param command "$PROG" -F -z -P "$pid_file"' "$tmp/init"
cp "$tmp/init" "$tmp/once"
sh x86-64/johnny-ssh-qos "$tmp/init"
cmp "$tmp/once" "$tmp/init"
printf '%s\n' 'unexpected upstream startup' > "$tmp/init"
cp "$tmp/init" "$tmp/before"
if sh x86-64/johnny-ssh-qos "$tmp/init"; then
    echo 'FAIL: unknown startup layout was accepted' >&2
    exit 1
fi
cmp "$tmp/before" "$tmp/init"
echo 'PASS: SSH QoS patch, idempotence and upstream-change guard'
