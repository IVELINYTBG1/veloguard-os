# VeloGuardOS release signing

The updater **refuses any `veloguard` update whose manifest isn't signed by the
pinned key** in this directory (`veloguard-release.pem`). The private key never
lives in the repo or on user machines — only on your offline/release signer.

## One-time: create the release keypair

```bash
# private key — keep OFFLINE, never commit, never ship
openssl ecparam -name prime256v1 -genkey -noout -out veloguard-release.key
# public key — this is what ships in veloguard/keys/veloguard-release.pem
openssl ec -in veloguard-release.key -pubout -out veloguard-release.pem
```

## Per release: sign the manifest

```bash
# manifest.json describes the latest versions + artifact + sha256
openssl dgst -sha256 -sign veloguard-release.key \
    -out manifest.json.sig manifest.json
# publish manifest.json + manifest.json.sig + the artifact tarball
```

## Manifest format

```json
{
  "veloguard": {
    "version": "0.2.0",
    "artifact": "https://updates.veloguardos.org/veloguard-0.2.0.tar.gz",
    "sha256": "<sha256 of the tarball>"
  },
  "kernel": { "version": "7.2.0", "tag": "v7.2", "notes": "rebased fragments" }
}
```

The manifest is the root of trust: it's signed, and it carries the artifact's
sha256, so the artifact is trusted transitively. Rotate the key by shipping a new
public key in a signed `veloguard` update (key continuity).
