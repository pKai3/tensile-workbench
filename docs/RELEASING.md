# Publishing an app update

Normal commits/pushes remain development work. Desktop users receive **published
numbered releases**, not every commit on `main`.

1. Complete the change and run the relevant checks, including the full test suite
   for a release. Check the Windows and Mac **Desktop update checks** workflow.
2. Increment the three-part number in `VERSION` and update `RELEASE_NOTES.md`.
   Do not reuse a published version. Commit and push these files with the change.
3. Tag that commit `vX.Y.Z` and push the tag. The **Publish Workbench release**
   workflow runs the synthetic update/launcher checks on both systems, verifies
   that the tag matches `VERSION`, and publishes the versioned ZIP plus SHA-256.
4. Confirm the release asset exists, GitHub reports its SHA-256 digest, and the
   launcher can find the release. Keep earlier release assets available: source
   ZIP installations use them to verify their existing code before updating.

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
