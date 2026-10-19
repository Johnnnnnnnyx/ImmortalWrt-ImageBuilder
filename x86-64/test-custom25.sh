#!/bin/sh
set -eu

cd "$(dirname "$0")/.."
hook=x86-64/31-zerotier-interface

# The router's UCI/ubus services are external to this host. Record the actual
# RPC emitted by the hook, rather than requiring a running OpenWrt router.
uci() {
    case "$*" in
        '-q get network.zerotier.proto') echo "${TEST_PROTO:-none}" ;;
        '-q get zerotier.global.enabled') echo "${TEST_ENABLED:-1}" ;;
        *) return 1 ;;
    esac
}
ubus() { printf '%s\n' "$*"; }

check() {
    expected="$1"
    shift
    actual="$(env_test "$@")"
    if [ "$actual" != "$expected" ]; then
        printf 'FAIL: %s\nExpected: %s\nActual: %s\n' "$*" "$expected" "$actual" >&2
        exit 1
    fi
}
env_test() (
    ACTION="$1" DEVICENAME="$2" TEST_ENABLED="${3:-1}" TEST_PROTO="${4:-none}"
    . "$hook"
)

check 'call network.interface.zerotier add_device {"name":"ztabc12345","link-ext":true}' add ztabc12345
check 'call network.interface.zerotier remove_device {"name":"ztabc12345","link-ext":true}' remove ztabc12345 0
check 'call network.interface.zerotier add_device {"name":"ztnew67890","link-ext":true}' add ztnew67890
check '' add eth0
check '' change ztabc12345
check '' add ztabc12345 0
check '' add ztabc12345 1 static
check '' add 'ztbad"name'
check '' add ztabc123456789012345
printf 'PASS: ZeroTier interface lifecycle and input guards (9 cases)\n'
