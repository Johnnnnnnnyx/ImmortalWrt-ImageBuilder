#!/bin/sh
set -eu
root=$(pwd)
# Pin the public 0.13.0 backend before unrelated NAS refactoring.
git clone https://github.com/istoreos/quickstart.git quickstart-source
git -C quickstart-source checkout fa23fc890b3881595027af5a8e9e1771620f81b8
git -C quickstart-source apply "$root/x86-64/quickstart-immortal.patch"
cp x86-64/quickstart-feeds-test.go quickstart-source/backend/service/johnny_feeds_test.go
mkdir -p files/usr/sbin
cd quickstart-source/backend
go test ./...
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath \
    -ldflags '-s -w -X main.BuildVersion=johnny-feeds-1' \
    -o "$root/files/usr/sbin/quickstart" ./cmd/backend
chmod 755 "$root/files/usr/sbin/quickstart"
