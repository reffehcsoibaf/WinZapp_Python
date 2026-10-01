"""WhatsAppAccountMixin — part of MainWindow (see main_window/__init__.py).

The account's own profile (name, About text, photo) and its account-wide
privacy settings, as the "WhatsApp settings" dialog
(ui/dialogs/whatsapp_settings_dialog.py) uses them. Everything here is a call to
the local WPPConnect server; every method returns an error string (or None on
success) instead of raising, so the dialog can list each failure on its own.

Methods run with ``self`` bound to the MainWindow instance.

Profile name, About and photo go through WPPConnect Server's own routes
(change-username, profile-status, set-profile-pic). Privacy has no route there:
``/privacy`` and ``/privacy/set`` are added by this repo's api_patches and call
wa-js's ``WPP.privacy`` directly.
"""

import json
import logging
import os

from core.api_client import api_post


class WhatsAppAccountMixin:
    """Profile and privacy settings of the paired WhatsApp account."""

    def _account_api(self, route: str) -> tuple[str, dict]:
        """(url, JSON headers) of a local server route for this session."""
        url = f"{self.wpp_server}:{self.wpp_port}/api/{self.token}/{route}"
        return url, {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _account_error_detail(response) -> str:
        """The full error a route reports, not just its generic top-level
        "message" ("Error on set profile name."): the actual failure — a
        wa-js/WPPConnect exception — lives in the response's own "error"
        field, and dropping it made every failure look the same."""
        try:
            body = response.json()
        except Exception:
            return response.text[:500]
        message = body.get("message", "")
        error = body.get("error")
        if error and error != message:
            error_str = (
                error if isinstance(error, str)
                else json.dumps(error, ensure_ascii=False)
            )
            return f"{message} ({error_str})" if message else error_str
        return message or response.text[:500]

    def open_whatsapp_settings(self, event=None):
        """File > WhatsApp settings: the profile (and privacy) dialog."""
        from ui.dialogs.whatsapp_settings_dialog import WhatsAppSettingsDialog

        dialog = WhatsAppSettingsDialog(self, self)
        try:
            dialog.ShowModal()
        finally:
            dialog.Destroy()

    # ── Profile ───────────────────────────────────────────────────────────────

    def set_profile_name(self, name: str) -> "str | None":
        """Sets the account's displayed WhatsApp name. Error string, or None."""
        url, headers = self._account_api("change-username")
        try:
            response = api_post(url, json={"name": name}, headers=headers, timeout=15)
            return None if response.ok else self._account_error_detail(response)
        except Exception as exc:
            return str(exc)

    def set_profile_status(self, status: str) -> "str | None":
        """Sets the account's About text. Error string, or None."""
        url, headers = self._account_api("profile-status")
        try:
            response = api_post(url, json={"status": status}, headers=headers, timeout=15)
            return None if response.ok else self._account_error_detail(response)
        except Exception as exc:
            return str(exc)

    def set_profile_pic(self, image_path: str) -> "str | None":
        """Uploads *image_path* as the account's profile photo. Error string,
        or None. A profile photo is always small, so a plain ``files=`` upload
        is enough (no streaming body, unlike send_media)."""
        url, headers = self._account_api("set-profile-pic")
        headers.pop("Content-Type")  # multipart sets its own, with the boundary
        try:
            with open(image_path, "rb") as handle:
                files = {"file": (os.path.basename(image_path), handle, "image/jpeg")}
                response = api_post(url, files=files, headers=headers, timeout=30)
            return None if response.ok else self._account_error_detail(response)
        except Exception as exc:
            return str(exc)

    # ── Privacy ───────────────────────────────────────────────────────────────

    def fetch_privacy_settings(self) -> "dict | None":
        """Every account-wide privacy field in one call: lastSeen, online,
        about, profilePicture, readReceipts, groupAdd, status. None on any
        failure — the caller treats that as "could not load" and must not
        overwrite what the dialog already shows."""
        url, headers = self._account_api("privacy")
        try:
            response = api_post(url, json={}, headers=headers, timeout=15)
            if response.status_code not in (200, 201):
                logging.warning("[fetch_privacy_settings] HTTP %s", response.status_code)
                return None
            body = response.json()
            return body.get("response") if isinstance(body, dict) else None
        except Exception as exc:
            logging.warning("[fetch_privacy_settings] %s", type(exc).__name__)
            return None

    def set_privacy_setting(self, setting: str, value: str) -> "str | None":
        """Applies one privacy setting. *setting* is one of lastSeen, online,
        about, profilePicture, readReceipts, groupAdd ("who sees my status"
        needs a contact picker and is not handled). None on success, or an
        error message prefixed with the setting, so partial failures across
        several settings are each visible."""
        url, headers = self._account_api("privacy/set")
        try:
            response = api_post(
                url, json={"setting": setting, "value": value},
                headers=headers, timeout=15,
            )
            if response.status_code in (200, 201):
                return None
            return f"{setting}: {self._account_error_detail(response)}"
        except Exception as exc:
            return f"{setting}: {exc}"
