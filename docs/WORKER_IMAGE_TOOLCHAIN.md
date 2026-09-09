# Worker image dependency maintenance

The Community, Supporter activation and FH6 RTTI relay testing/development
toolchains use Miniflare, which loads sharp for Images bindings and cf.image
transforms. Support reporting also uses the Community installation. These are
development dependencies; do not remove them from security auditing.

## Current security override

Each owning package.json scopes a sharp 0.35.4 override to every Miniflare
instance, including nested Wrangler dependencies. This addresses
[GHSA-rgj7-g3m4-5g8c](https://github.com/advisories/GHSA-rgj7-g3m4-5g8c), affecting
sharp before 0.35.4. The patched prebuilt libraries include libheif 1.23.2.
Parent Wrangler, Miniflare and test-pool versions remain unchanged.

The two older relay/activation toolchains also override Miniflare's undici to
7.29.0 and require Vitest 4.1.11 or newer. Their refreshed lockfiles remove the
known undici, Vitest/mocker, PostCSS and nanoid advisories exposed by auditing
the complete toolchain. Compatible transitive build/test dependencies update
with those patches; their existing Worker runtime generations are preserved.

The corresponding package-lock.json files must be regenerated with npm, never
hand-edited or replaced by local node_modules changes. Exact locking and the
override make fresh installations reproducible. They do not replace ongoing
advisory checks or promise protection from unknown future vulnerabilities.

## Required verification

From each owning Worker directory:

```text
npm ci
npm audit --audit-level=moderate
npm run typecheck
npm test
```

From the repository root, use each Worker directory as the argument:

```text
node tools/community_worker/tools/check_image_toolchain.mjs tools/community_worker
node tools/community_worker/tools/check_image_toolchain.mjs tools/fh6_rtti_relay_worker
node tools/community_worker/tools/check_image_toolchain.mjs tools/supporter_activation_worker
```

The image check verifies all locked/installed sharp copies and each Miniflare
instance's actual resolution. It then uses small synthetic PNG/AVIF images through
native encoding/decoding, Images bindings and cf.image resizing. The synthetic
origin is intercepted locally; no artwork or network image is used. Startup alone
is insufficient because Miniflare loads sharp lazily.

CI runs the image check and dependency audit for every Linux Worker matrix entry,
plus Windows image validation and the disposable Community end-to-end workflow.
Direct Support reporting runtime tests remain required. Existing local-only
consumers must also be tested before promoting DIRTY changes; do not publish WIP
consumers merely because they share the toolchain.

## Future upgrades

Keep the override until the installed dependency graph no longer contains an
affected sharp version without it. Review upstream changes, regenerate all
affected locks and update the explicit reviewed version in the image check as
part of the same candidate. If retiring the override, replace its assertion with
the reviewed upstream dependency contract rather than deleting image tests.

Require the complete audit, native checks and real Worker/E2E suites to pass on
Windows and Linux before promotion. Do not use npm audit fix --force, ignore
development dependencies, suppress the advisory or disable a publication gate.
