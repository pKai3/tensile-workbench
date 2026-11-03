# Publishing an app update

Pushing completed changes to `main` automatically starts **Publish Workbench
release**. No separate request, manual tag or release upload is needed.

1. Commit distinct changes and update `RELEASE_NOTES.md` with useful user-facing
   notes. If the notes are unchanged since the previous version, the workflow
   generates a list from the intervening commit subjects.
2. Push to `main`. The full synthetic suite and the Windows/Mac desktop-update
   checks must pass before anything is published. Work in a feature branch when
   changes are not ready to offer to colleagues.
3. The workflow advances the patch version automatically (for example, 1.0.2 →
   1.0.3), commits only `VERSION` and release notes, and atomically pushes that
   commit plus its tag. An explicit larger version in `VERSION` is respected
   for a deliberate minor/major release. Existing versions are never reused for
   different code. A newer source push supersedes an older pending release.
4. The ZIP and checksum are uploaded to a draft release and their GitHub sizes
   and SHA-256 digests checked before making it the latest published release.
   Only then does the desktop updater offer it to colleagues. Existing published
   assets are never overwritten. An interrupted draft can be completed by
   rerunning the workflow or choosing **Run workflow → main**.
5. Fetch/fast-forward the checkout after publication to receive the generated
   version commit before starting the next change. The workflow uses GitHub's
   built-in token; its version commit does not trigger a release loop.

The workflow serializes release runs and does not cancel a publication halfway
through. A stale source commit is skipped; an atomic push refuses to overwrite
concurrent changes. If a check fails, the previous published release stays
available. Inspect the failing Actions run, fix the issue, and push again.

Keep earlier release assets available: source-ZIP installations use them to
verify their existing code before updating.

`tools/build_release.py --output <folder>` packages committed Git blobs, never
the working directory. Only tracked application/documentation/synthetic fixture
files enter the archive. The generated `workbench-release.json` records the
commit, Python series, per-file hashes and executable bits. It is installation
metadata and remains ignored by Git. Research, local settings, data symlinks,
credentials and virtual environments must never become tracked files.

The updater currently accepts standard Python 3.14 releases. A Python-series
upgrade needs an installer migration and corresponding updater support; do not
change the package metadata to bypass that check. Updater/archive format changes
need a compatible transition so older installed versions can reach the new one.

Release assets are verified through HTTPS and GitHub's asset digest, plus the
internal file manifest. They are not independently publisher-signed installers.
Protect repository and release-publishing access accordingly.
