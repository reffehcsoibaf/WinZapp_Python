"""WhatsApp settings: profile and privacy of the paired account.

No window is opened (CLAUDE.md): the rules are plain functions, the server
calls are exercised against a fake ``api_post``, and what needs wx is checked
from the source text.
"""

import json
import re
from pathlib import Path

import pytest

import main_window.whatsapp_account as mixin_module
from core import whatsapp_account as account
from main_window.whatsapp_account import WhatsAppAccountMixin

ROOT = Path(__file__).resolve().parent.parent / "client"
LOCALES = sorted(
    p.stem for p in (ROOT / "languages").glob("*.json") if p.stem != "language_map"
)


def _read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


class FakeResponse:
    def __init__(self, status=200, body=None, text=""):
        self.status_code = status
        self.ok = status < 400
        self._body = body
        self.text = text or json.dumps(body or {})

    def json(self):
        if self._body is None:
            raise ValueError("not json")
        return self._body


class Window(WhatsAppAccountMixin):
    wpp_server = "http://127.0.0.1"
    wpp_port = 21465
    token = "TOKEN"


@pytest.fixture
def calls(monkeypatch):
    """Replace api_post; each call is recorded as (url, kwargs). Set
    ``calls.answer`` to the response (or an exception) to return."""
    recorded = []

    class Recorder(list):
        answer = FakeResponse(200, {"status": "success"})

    recorder = Recorder()

    def fake_post(url, **kwargs):
        recorder.append((url, kwargs))
        if isinstance(recorder.answer, Exception):
            raise recorder.answer
        return recorder.answer

    monkeypatch.setattr(mixin_module, "api_post", fake_post)
    return recorder


class TestSwitches:
    def test_both_stay_off_until_the_pinned_wa_js_has_the_fixes(self):
        """4.6.0 throws in both (wa-js#3658 and #3659). Flipping these is the
        whole change that turns the features on."""
        assert account.PRIVACY_TAB_ENABLED is False
        assert account.PROFILE_NAME_ENABLED is False

    def test_a_name_left_in_a_disabled_field_never_reaches_the_server(self):
        changes = account.profile_changes("Someone", "hi", None)
        assert changes.name == ""
        assert changes.status == "hi"

    def test_the_name_is_sent_once_enabled(self):
        changes = account.profile_changes("  Someone ", "", None, name_enabled=True)
        assert changes.name == "Someone"


class TestProfileChanges:
    def test_nothing_filled_is_empty(self):
        assert account.profile_changes("", "   ", None).empty
        assert account.profile_changes(None, None, "").empty

    def test_a_photo_alone_is_a_change(self):
        assert not account.profile_changes("", "", "C:/p.jpg").empty

    def test_the_status_is_trimmed(self):
        assert account.profile_changes("", "  Available ", None).status == "Available"


class TestPrivacyFields:
    def test_the_six_settings_the_server_accepts(self):
        assert [f.setting for f in account.PRIVACY_FIELDS] == [
            "lastSeen", "online", "about", "profilePicture", "readReceipts", "groupAdd",
        ]

    def test_the_server_maps_exactly_those_settings(self):
        server = _read("api_patches", "src", "controller", "deviceController.ts")
        block = server[server.index("const PRIVACY_SETTERS"):]
        block = block[: block.index("};")]
        assert set(re.findall(r"^\s+(\w+):", block, re.M)) == {
            f.setting for f in account.PRIVACY_FIELDS
        }

    def test_every_option_text_is_an_i18n_key_that_exists(self):
        pt = json.loads(_read("languages", "pt-BR.json"))
        keys = {f.label_key for f in account.PRIVACY_FIELDS}
        keys |= {key for f in account.PRIVACY_FIELDS for _v, key in f.options}
        assert [k for k in sorted(keys) if k not in pt] == []

    def test_option_index_finds_the_current_value(self):
        field = account.PRIVACY_FIELDS[0]
        assert account.option_index(field, "contacts") == 1

    def test_an_unknown_value_leaves_the_dropdown_unselected(self):
        field = account.PRIVACY_FIELDS[0]
        assert account.option_index(field, "contact_blacklist") == -1
        assert account.option_index(field, None) == -1


class TestChangedPrivacy:
    LOADED = {
        "lastSeen": "all", "online": "all", "about": "contacts",
        "profilePicture": "all", "readReceipts": "all", "groupAdd": "contacts",
    }

    def test_nothing_chosen_differently_sends_nothing(self):
        chosen = {
            f.setting: account.option_index(f, self.LOADED[f.setting])
            for f in account.PRIVACY_FIELDS
        }
        assert account.changed_privacy(self.LOADED, chosen) == []

    def test_only_the_changed_setting_is_sent(self):
        chosen = {
            f.setting: account.option_index(f, self.LOADED[f.setting])
            for f in account.PRIVACY_FIELDS
        }
        chosen["readReceipts"] = 1  # On -> Off
        assert account.changed_privacy(self.LOADED, chosen) == [("readReceipts", "none")]

    def test_a_dropdown_never_set_is_left_alone(self):
        assert account.changed_privacy(self.LOADED, {"lastSeen": -1}) == []
        assert account.changed_privacy(self.LOADED, {}) == []

    def test_an_index_past_the_options_is_ignored(self):
        assert account.changed_privacy(self.LOADED, {"groupAdd": 9}) == []


class TestAnAnswerWithNothingInIt:
    """The call returned 200 but the data behind it was unreachable: six empty
    dropdowns would look like a working tab that ignores you."""

    GOOD = {
        "lastSeen": "all", "online": "all", "about": "contacts",
        "profilePicture": "all", "readReceipts": "all", "groupAdd": "contacts",
    }

    def test_a_complete_answer_is_readable(self):
        assert account.unreadable(self.GOOD) is False

    def test_one_known_field_is_enough_to_be_readable(self):
        assert account.unreadable({"readReceipts": "none"}) is False

    @pytest.mark.parametrize("answer", [
        None, [], "ok", {}, {"lastSeen": None, "online": ""},
        {"status": "all"},                                       # only the Status field came back
        {"lastSeen": "everyone", "readReceipts": "enabled"},     # a vocabulary it does not know
        {"lastSeen": {"value": "all"}},                          # a shape it does not know
    ])
    def test_an_answer_with_no_value_it_knows_is_unreadable(self, answer):
        assert account.unreadable(answer) is True


class TestASetterThatDidNothing:
    """A setter can answer "success" and change nothing. Only a fresh read says."""

    GOOD = TestAnAnswerWithNothingInIt.GOOD

    def test_what_took_effect_is_confirmed(self):
        readback = dict(self.GOOD, readReceipts="none")
        assert account.not_confirmed([("readReceipts", "none")], readback) == []

    def test_a_value_that_did_not_change_is_named(self):
        # asked for "none", WhatsApp still says "all"
        assert account.not_confirmed([("readReceipts", "none")], self.GOOD) == ["readReceipts"]

    def test_only_the_ones_that_failed_are_named(self):
        readback = dict(self.GOOD, lastSeen="none")
        sent = [("lastSeen", "none"), ("about", "none")]
        assert account.not_confirmed(sent, readback) == ["about"]

    def test_an_unreadable_read_back_confirms_nothing(self):
        sent = [("lastSeen", "none"), ("about", "none")]
        assert account.not_confirmed(sent, None) == ["lastSeen", "about"]
        assert account.not_confirmed(sent, {}) == ["lastSeen", "about"]

    def test_nothing_sent_nothing_to_confirm(self):
        assert account.not_confirmed([], self.GOOD) == []


class TestProfileCalls:
    def test_the_name_goes_to_change_username(self, calls):
        assert Window().set_profile_name("Ana") is None
        url, kwargs = calls[0]
        assert url == "http://127.0.0.1:21465/api/TOKEN/change-username"
        assert kwargs["json"] == {"name": "Ana"}
        assert kwargs["headers"]["Authorization"] == "Bearer TOKEN"

    def test_the_status_goes_to_profile_status(self, calls):
        assert Window().set_profile_status("Busy") is None
        assert calls[0][0].endswith("/profile-status")
        assert calls[0][1]["json"] == {"status": "Busy"}

    def test_the_photo_is_a_multipart_upload_without_a_forced_content_type(
        self, calls, tmp_path
    ):
        photo = tmp_path / "me.jpg"
        photo.write_bytes(b"\xff\xd8jpeg")
        assert Window().set_profile_pic(str(photo)) is None
        url, kwargs = calls[0]
        assert url.endswith("/set-profile-pic")
        assert "Content-Type" not in kwargs["headers"]
        assert kwargs["files"]["file"][0] == "me.jpg"

    def test_a_missing_photo_is_an_error_string_not_an_exception(self, calls):
        assert "No such file" in Window().set_profile_pic("/nope/x.jpg")
        assert calls == []

    def test_the_real_reason_of_a_failure_is_reported(self, calls):
        calls.answer = FakeResponse(
            500,
            {"message": "Error on set profile name.", "error": "setPushname is not a function"},
        )
        error = Window().set_profile_name("Ana")
        assert "Error on set profile name." in error
        assert "setPushname is not a function" in error

    def test_a_non_json_failure_still_says_something(self, calls):
        calls.answer = FakeResponse(502, None, text="Bad gateway")
        assert Window().set_profile_status("x") == "Bad gateway"

    def test_a_dead_server_is_an_error_string(self, calls):
        calls.answer = ConnectionError("refused")
        assert Window().set_profile_status("x") == "refused"


class TestPrivacyCalls:
    def test_fetch_returns_the_settings(self, calls):
        calls.answer = FakeResponse(200, {"status": "success", "response": {"lastSeen": "all"}})
        assert Window().fetch_privacy_settings() == {"lastSeen": "all"}
        assert calls[0][0].endswith("/privacy")

    def test_a_failed_fetch_is_none_never_an_empty_dict(self, calls):
        """The dialog must be able to tell "could not load" from "loaded"."""
        calls.answer = FakeResponse(500, {"message": "x"})
        assert Window().fetch_privacy_settings() is None
        calls.answer = ConnectionError("refused")
        assert Window().fetch_privacy_settings() is None

    def test_set_sends_the_setting_and_the_value(self, calls):
        assert Window().set_privacy_setting("readReceipts", "none") is None
        url, kwargs = calls[0]
        assert url.endswith("/privacy/set")
        assert kwargs["json"] == {"setting": "readReceipts", "value": "none"}

    def test_a_failure_names_the_setting_so_partial_errors_are_readable(self, calls):
        calls.answer = FakeResponse(
            500,
            {"message": "Error setting privacy.lastSeen",
             "error": "setPrivacyForOneCategory is not a function"},
        )
        error = Window().set_privacy_setting("lastSeen", "none")
        assert error.startswith("lastSeen: ")
        assert "setPrivacyForOneCategory is not a function" in error


class TestWiring:
    DIALOG = _read("ui", "dialogs", "whatsapp_settings_dialog.py")
    CHROME = _read("main_window", "window_chrome.py")

    def test_the_menu_item_opens_the_dialog(self):
        assert "_ID_WA_SETTINGS" in self.CHROME
        assert "self.open_whatsapp_settings" in self.CHROME
        assert "menu_settings_whatsapp" in self.CHROME

    def test_the_menu_item_is_relabelled_on_a_language_change(self):
        assert "FindItemById(self._ID_WA_SETTINGS).SetItemLabel" in self.CHROME

    def test_the_mixin_is_part_of_the_main_window(self):
        main = _read("main.py")
        assert "WhatsAppAccountMixin" in main
        assert main.count("WhatsAppAccountMixin") == 2  # import + base class

    def test_the_privacy_tab_is_only_built_when_enabled(self):
        assert self.DIALOG.count("if account.PRIVACY_TAB_ENABLED:") == 2

    def test_an_unreadable_answer_is_a_window_and_is_spoken(self):
        assert "account.unreadable(settings)" in self.DIALOG
        assert "wa_privacy_unreadable_msg" in self.DIALOG

    def test_the_dialog_reads_the_values_back_after_applying(self):
        assert "mw.fetch_privacy_settings()" in self.DIALOG
        assert "account.not_confirmed(" in self.DIALOG
        assert "wa_privacy_not_confirmed_msg" in self.DIALOG

    def test_the_server_routes_exist_for_both_calls(self):
        routes = _read("api_patches", "src", "routes", "index.ts")
        controller = _read("api_patches", "src", "controller", "deviceController.ts")
        for path, function in (("/privacy", "getPrivacySettings"),
                               ("/privacy/set", "setPrivacySetting")):
            assert f"'/api/:session{path}'" in routes
            assert f"DeviceController.{function}" in routes
            assert f"export async function {function}" in controller

    def test_no_diagnostic_route_ships(self):
        routes = _read("api_patches", "src", "routes", "index.ts")
        assert "debug-find-module" not in routes

    def test_the_dialog_never_logs_what_the_server_answered(self):
        assert "logging" not in self.DIALOG


class TestStringsInEveryLocale:
    NEEDED = (
        ["menu_settings_whatsapp", "wa_settings_dialog_title", "wa_settings_tab_profile",
         "wa_settings_tab_privacy", "profile_name_label", "profile_status_label",
         "profile_photo_label", "profile_save_button", "profile_save_success",
         "profile_name_unavailable_note", "wa_privacy_loading",
         "wa_privacy_nothing_changed", "wa_privacy_apply_button",
         "wa_privacy_unreadable_msg", "wa_privacy_not_confirmed_msg"]
    )

    @pytest.mark.parametrize("locale", LOCALES)
    def test_every_string_exists_and_is_not_empty(self, locale):
        strings = json.loads(_read("languages", f"{locale}.json"))
        assert [k for k in self.NEEDED if not str(strings.get(k, "")).strip()] == []

    @pytest.mark.parametrize("locale", LOCALES)
    def test_the_menu_label_has_no_mnemonic(self, locale):
        """Every letter in the File menu is taken; an '&' here would clash."""
        strings = json.loads(_read("languages", f"{locale}.json"))
        assert "&" not in strings["menu_settings_whatsapp"]

    def test_every_key_the_dialog_asks_for_is_declared(self):
        pt = json.loads(_read("languages", "pt-BR.json"))
        used = set(re.findall(r'i18n\.t\(\s*"([a-z0-9_]+)"', Wired.DIALOG))
        assert [k for k in sorted(used) if k not in pt] == []


class Wired:
    DIALOG = _read("ui", "dialogs", "whatsapp_settings_dialog.py")


class TestTheNotConfirmedMessage:
    @pytest.mark.parametrize("locale", LOCALES)
    def test_the_settings_placeholder_survives_translation(self, locale):
        strings = json.loads(_read("languages", f"{locale}.json"))
        assert "{settings}" in strings["wa_privacy_not_confirmed_msg"]
        strings["wa_privacy_not_confirmed_msg"].format(settings="x")  # no stray braces
