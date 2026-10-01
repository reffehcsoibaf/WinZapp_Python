"""Rules behind the "WhatsApp settings" dialog (ui/dialogs/whatsapp_settings_dialog.py).

No wx here, so all of it is tested without opening a window. The calls to the
local server live in main_window/whatsapp_account.py.
"""

from dataclasses import dataclass

# Both features need a wa-js newer than the 4.6.0 this repo pins (see
# docs/traps/send-contract.md for the pinning rules):
#
# * Privacy: the six WPP.privacy.set* setters throw "setPrivacyForOneCategory is
#   not a function" on 4.6.0 (wppconnect-team/wa-js#3658, fixed by PR #3632).
# * Display name: Whatsapp.setProfileName() throws "setPushname is not a
#   function" on 4.6.0 (wppconnect-team/wa-js#3659, fixed by PR #3682).
#
# Off until the pinned wa-js carries both fixes. Flipping them is the whole
# change: the tab, the routes (api_patches /privacy, /privacy/set) and the
# strings are already in place, and the calls are covered by tests. About text
# and photo go through WPPConnect Server's own routes and work on 4.6.0.
PRIVACY_TAB_ENABLED = False
PROFILE_NAME_ENABLED = False


@dataclass(frozen=True)
class PrivacyField:
    """One account-wide privacy setting.

    ``setting`` is the name the server and WPP.privacy use; ``options`` pairs
    the raw value WhatsApp expects with the i18n key of the text shown for it.
    """
    setting: str
    label_key: str
    options: tuple


_EVERYONE = ("all", "wa_privacy_opt_all")
_CONTACTS = ("contacts", "wa_privacy_opt_contacts")
_NOBODY = ("none", "wa_privacy_opt_none")

# "Who sees my Status" is not here: it needs a contact picker, not a dropdown.
PRIVACY_FIELDS = (
    PrivacyField("lastSeen", "wa_privacy_last_seen_label",
                 (_EVERYONE, _CONTACTS, _NOBODY)),
    PrivacyField("online", "wa_privacy_online_label",
                 (_EVERYONE, ("match_last_seen", "wa_privacy_opt_match_last_seen"))),
    PrivacyField("about", "wa_privacy_about_label",
                 (_EVERYONE, _CONTACTS, _NOBODY)),
    PrivacyField("profilePicture", "wa_privacy_profile_pic_label",
                 (_EVERYONE, _CONTACTS, _NOBODY)),
    PrivacyField("readReceipts", "wa_privacy_read_receipts_label",
                 (("all", "wa_privacy_opt_on"), ("none", "wa_privacy_opt_off"))),
    PrivacyField("groupAdd", "wa_privacy_group_add_label",
                 (_EVERYONE, _CONTACTS)),
)


def option_index(field: PrivacyField, current) -> int:
    """Position of *current* among the field's options, or -1 when WhatsApp
    answered something this list does not know (a value added after this was
    written): the dropdown is then left unselected instead of guessing."""
    for index, (value, _label_key) in enumerate(field.options):
        if value == current:
            return index
    return -1


def unreadable(settings) -> bool:
    """True when WhatsApp answered but no field holds a value this dialog knows.

    That is not an error to the server (it said 200), so without this check the
    dialog would show six empty dropdowns and look as if it worked. It happens
    when wa-js can reach the privacy call but not the data behind it, e.g. after
    WhatsApp Web changes an internal module.
    """
    if not isinstance(settings, dict):
        return True
    return all(
        option_index(field, settings.get(field.setting)) == -1
        for field in PRIVACY_FIELDS
    )


def not_confirmed(requested: list, readback) -> list:
    """The settings among *requested* that WhatsApp does not report back as set.

    *requested* is the (setting, value) list that was sent, *readback* a fresh
    read afterwards. A setter can answer "success" and still do nothing (the
    server only knows the call returned), so the only proof is reading the value
    again. An unreadable *readback* confirms nothing: every setting is returned.
    """
    if unreadable(readback):
        return [setting for setting, _value in requested]
    return [
        setting for setting, value in requested
        if readback.get(setting) != value
    ]


def changed_privacy(loaded: dict, chosen: dict) -> list:
    """(setting, value) pairs to send, only for what actually changed.

    *loaded* is what WhatsApp reported; *chosen* maps a setting to the index
    picked in its dropdown (-1 or missing = never set, so left alone). Sending
    only differences keeps the number of calls — and of possible failures — to
    what the person changed.
    """
    changes = []
    for field in PRIVACY_FIELDS:
        index = chosen.get(field.setting, -1)
        if not 0 <= index < len(field.options):
            continue
        value = field.options[index][0]
        if loaded.get(field.setting) != value:
            changes.append((field.setting, value))
    return changes


@dataclass(frozen=True)
class ProfileChanges:
    """What the Profile tab will send. An empty text means "keep as is"."""
    name: str = ""
    status: str = ""
    photo: str = ""

    @property
    def empty(self) -> bool:
        return not (self.name or self.status or self.photo)


def profile_changes(name: str, status: str, photo, *,
                    name_enabled: bool = PROFILE_NAME_ENABLED) -> ProfileChanges:
    """The changes to send from the raw field values.

    The name is dropped whatever the field holds while it is switched off, so a
    value left in a disabled control can never reach the server.
    """
    return ProfileChanges(
        name=(name or "").strip() if name_enabled else "",
        status=(status or "").strip(),
        photo=photo or "",
    )
