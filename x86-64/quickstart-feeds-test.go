package service

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestJohnnyCurrentSourceKeepsActualRoot(t *testing.T) {
	old := readGuideSoftSourceFile
	defer func() { readGuideSoftSourceFile = old }()
	for _, root := range []string{"https://downloads.immortalwrt.org/", "https://mirrors.ustc.edu.cn/immortalwrt/"} {
		readGuideSoftSourceFile = func(path string) ([]byte, error) {
			if path == "/etc/openwrt_release" {
				return []byte("DISTRIB_ID='ImmortalWrt'\n"), nil
			}
			return []byte("src/gz immortalwrt_base " + root + "releases/25.12.2/packages/x86_64/base\n" + root + "releases/25.12.2/packages/x86_64/base/packages.adb\n"), nil
		}
		got, err := newDefaultGuideSoftSourceReader().ReadCurrentSource(context.Background())
		if err != nil || got.URL != root {
			t.Fatalf("want %s, got %#v, %v", root, got, err)
		}
	}
}

func TestJohnnyCatalogRejectsWrongDistribution(t *testing.T) {
	old := readGuideSoftSourceFile
	defer func() { readGuideSoftSourceFile = old }()
	readGuideSoftSourceFile = func(string) ([]byte, error) { return []byte("DISTRIB_ID='ImmortalWrt'\n"), nil }
	list, err := newDefaultGuideSoftSourceReader().ListSources(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	for _, source := range list {
		if strings.Contains(source.URL, "openwrt") {
			t.Fatalf("wrong distribution offered: %s", source.URL)
		}
	}
	if resolveGuideSoftSourceByIdentity("OpenWrtHttps").Identity != "" {
		t.Fatal("accepted incompatible source")
	}
	if resolveGuideSoftSourceByIdentity("ImmortalWrt").URL != "https://downloads.immortalwrt.org/" {
		t.Fatal("official source missing")
	}
}

func TestJohnnySwitchPreservesCurrentABIAndCustomFeeds(t *testing.T) {
	dir := t.TempDir()
	current, rom := filepath.Join(dir, "feeds"), filepath.Join(dir, "rom")
	original := "# keep this comment\nhttps://downloads.immortalwrt.org/releases/25.12.2/packages/x86_64/base/packages.adb\nhttps://downloads.immortalwrt.org/releases/25.12.2/targets/x86/64/kmods/6.12.103-1-0413601b1c3f0490e17f340fe09229ea/packages.adb\nhttps://dl.miaomiaowux.com/meowx/openwrt/openwrt-25.12/x86_64/meowx/packages.adb\nhttps://custom.example/packages.adb\n"
	if err := os.WriteFile(current, []byte(original), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(rom, []byte("https://downloads.immortalwrt.org/releases/25.12.0/packages/x86_64/base/packages.adb\n"), 0644); err != nil {
		t.Fatal(err)
	}
	if err := replaceGuideSoftSource("https://mirrors.ustc.edu.cn/immortalwrt/", rom, current); err != nil {
		t.Fatal(err)
	}
	got, _ := os.ReadFile(current)
	want := strings.ReplaceAll(original, "https://downloads.immortalwrt.org/", "https://mirrors.ustc.edu.cn/immortalwrt/")
	if string(got) != want {
		t.Fatalf("source switch damaged live configuration:\n%s", got)
	}
	if err := replaceGuideSoftSource("https://downloads.immortalwrt.org/", rom, current); err != nil {
		t.Fatal(err)
	}
	got, _ = os.ReadFile(current)
	if string(got) != original {
		t.Fatal("round trip changed current configuration")
	}
	info, _ := os.Stat(current)
	if info.Mode().Perm() != 0600 {
		t.Fatal("file permissions changed")
	}
}

// On OpenWrt this also reproduces the actual homepage failure without changing configuration.
func TestJohnnyAPKCheckDoesNotInventDetachedSignature(t *testing.T) {
	if !canAccessPath("/etc/apk/repositories.d/distfeeds.list") {
		t.Skip("router integration check")
	}
	got, err := getApkDistFeedUrlForCheck()
	if err != nil {
		t.Fatal(err)
	}
	if !strings.HasSuffix(got, "/base/packages.adb") {
		t.Fatalf("not a real APK index: %s", got)
	}
}

func TestJohnnyProbeStillReportsRealFailures(t *testing.T) {
	for _, status := range []int{http.StatusOK, http.StatusNotFound} {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(status) }))
		checker := NewNetworkOnlineChecker()
		checker.doCheck("test", server.URL+"/base/packages.adb")
		server.Close()
		want := NetworkOnlineOK
		if status == http.StatusNotFound {
			want = NetworkOnlineFailedSoftSource
		}
		if checker.status != want {
			t.Fatalf("HTTP %d: got %v, want %v", status, checker.status, want)
		}
	}
}

func TestJohnnyOpkgSwitchPreservesCustomAndMirrorPrefix(t *testing.T) {
	file := filepath.Join(t.TempDir(), "distfeeds.conf")
	original := "src/gz immortalwrt_base https://mirrors.ustc.edu.cn/immortalwrt/releases/24.10.5/packages/x86_64/base\nsrc/gz custom https://custom.example/feed\n"
	if err := os.WriteFile(file, []byte(original), 0600); err != nil {
		t.Fatal(err)
	}
	if err := replaceGuideSoftSource("https://downloads.immortalwrt.org/", "unused", file); err != nil {
		t.Fatal(err)
	}
	got, _ := os.ReadFile(file)
	want := "src/gz immortalwrt_base https://downloads.immortalwrt.org/releases/24.10.5/packages/x86_64/base\nsrc/gz custom https://custom.example/feed\n"
	if string(got) != want {
		t.Fatalf("opkg configuration damaged: %s", got)
	}
}
