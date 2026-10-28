# Johnnywrt AI build entry

This repository's default `master` branch is the upstream ImageBuilder baseline. The user's customized Johnnywrt firmware and canonical maintenance notes are on **`Johnny`**.

Before modifying Johnnywrt, starting or rerunning its build, or publishing firmware:

1. Read the complete [Johnny branch AGENTS.md](https://github.com/Johnnnnnnnyx/ImmortalWrt-ImageBuilder/blob/Johnny/AGENTS.md).
2. Read the complete [MAINTENANCE.md](https://github.com/Johnnnnnnnyx/ImmortalWrt-ImageBuilder/blob/Johnny/MAINTENANCE.md), including its pre-build checklist, confirmed failures, test dependencies, and upgrade compatibility requirements.
3. Work from `Johnny` or a verified Johnnywrt release. Preserve existing user changes when switching checkouts. Do not build the customized firmware from upstream `master` or overwrite `Johnny` with it.
4. Inspect the latest Actions result before retrying a failure, fix its cause, and pass the required tests before publishing. Building an image does not authorize flashing a running router.

Keep detailed maintenance notes on `Johnny` so there is one canonical source. The current user's explicit instructions take precedence over these repository notes.
