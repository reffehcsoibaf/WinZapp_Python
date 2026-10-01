---
paths:
  - "client/api_patches/package.json"
  - "client/core/whatsapp_account.py"
---

# wa-js pin

**Read `docs/traps/wa-js-pin.md` before changing these files.** Short form:

The Privacy tab and the display name need wa-js 4.6.1 or newer (4.6.0 has neither fix). `PRIVACY_TAB_ENABLED` and `PROFILE_NAME_ENABLED` are on only because of that pin; a test fails if the pin goes below 4.6.1 while either is on. After any pin move, check sending, Status, calls and groups on a real account.
