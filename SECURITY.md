# Security Notice

This repository contains hardcoded cryptographic keys and OAuth credentials
that are shared across all installations.

## Affected credentials (need rotation by Mammotion):
- RSA private key in `pymammotion/http/encryption.py`
- APP_SECRET in `pymammotion/const.py`
- MAMMOTION_CLIENT_SECRET in `pymammotion/const.py`
- MAMMOTION_OUATH2_CLIENT_SECRET in `pymammotion/const.py`

## Recommendations:
1. Mammotion should rotate all shared secrets
2. RSA key pair should be per-device, not shared
3. OAuth client secrets should be fetched from a secure backend
4. Consider using certificate pinning for cloud communications
