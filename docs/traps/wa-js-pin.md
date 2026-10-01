# The Privacy tab and the display name need wa-js 4.6.1 or newer

> Why `@wppconnect/wa-js` in `api_patches/package.json` is `4.6.1` and not
> `4.6.0`, and what has to change if it is ever pinned lower.

`4.6.0` has two bugs that the WhatsApp settings window
(`ui/dialogs/whatsapp_settings_dialog.py`) runs into. Both are fixed in
**4.6.1** (published 2026-10-02):

- **Privacy tab**: the six `WPP.privacy.set*` setters threw
  `setPrivacyForOneCategory is not a function`
  ([wa-js#3658](https://github.com/wppconnect-team/wa-js/issues/3658)), fixed by
  wa-js PR #3632.
- **Display name**: `Whatsapp.setProfileName()` threw
  `n.functions.setPushname is not a function`
  ([wa-js#3659](https://github.com/wppconnect-team/wa-js/issues/3659)), fixed by
  wa-js PR #3682.

Both are the same class of bug: an internal minified reference wa-js expects
inside WhatsApp Web's own JS, gone or renamed after Meta's "Comet" module-system
migration. The fixes register the lazy modules before reading the function.

`PRIVACY_TAB_ENABLED` and `PROFILE_NAME_ENABLED` in `core/whatsapp_account.py`
are `True` **only because of this pin**. `tests/test_whatsapp_account.py` fails
if the pin goes below 4.6.1 while either switch is on.

## What moving from 4.6.0 to 4.6.1 brings with it

4.6.1 is not just those two fixes: it is 78 commits past 4.6.0 (media
encrypt/upload, status posting, group and community jobs, call and event
registration, the lazy-module loader). Nothing in `src/` was removed or renamed
and every `WPP.*` member this repo references that exists in 4.6.0 still exists,
but that is a read of the API surface, not a homologation: the send-compatibility
contract (`docs/traps/send-contract.md`) was validated against 4.6.0, so sending,
Status posting, voice/video calls and group actions need a check on a real
account whenever this pin moves.

## If the pin has to go back to 4.6.0

Set both switches to `False`. The Privacy tab, the name field and the
`/privacy` routes then disappear, and About text and photo (which need no wa-js
fix) keep working.

## The Privacy tab does not fail silently

Even on a wa-js that has the fixes, the privacy calls can answer `200` and still
return nothing usable or change nothing, when WhatsApp Web changes internally.
The window therefore reports an answer it cannot read, and reads the values back
after applying and names any setting that did not take effect
(`core/whatsapp_account.py`: `unreadable()`, `not_confirmed()`).
