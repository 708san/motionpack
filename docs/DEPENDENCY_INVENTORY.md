# Dependency inventory

The file docs/DEPENDENCY_INVENTORY.json is generated offline from the repository's hash-pinned Python requirements, npm v3 lockfile, and workflow Action/image references.

Regenerate and validate it with:

~~~sh
python3 tools/dependency_inventory.py
python3 tools/dependency_inventory.py --check
python3 -m unittest tests.test_dependency_inventory -v
~~~

The generator uses only the Python standard library. It does not contact registries, install packages, or execute dependency code. Python requirements must have exact versions and SHA-256 hashes; GitHub Actions must use full commit SHAs; workflow container images must use SHA-256 digests. Unsupported or unpinned declarations fail closed so a new syntax cannot disappear from the inventory silently. Registry URLs are restricted to credential-free HTTPS on registry.npmjs.org; a different source requires an explicit reviewed change.

License fields distinguish upstream license-file evidence, maintainer-documented metadata, and metadata declared in package-lock.json. These records are provenance for review, not a legal conclusion. The selected MotionPack software license remains undecided.

This is a scoped dependency inventory, not a complete Software Bill of Materials (SBOM). It does not enumerate packages bundled into GitHub Actions, OCI images, GitHub-hosted runner images, or native libraries inside binary wheels. The Playwright OCI image is digest-pinned, but its OS/browser package inventory and licenses remain unassessed. Complete these gaps and review dependency advisories before v1.0 release. The drift check verifies that the checked-in JSON matches this generator and the tracked declarations; it does not prove the generator is complete or tamper-proof.
