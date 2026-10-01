"""WhatsApp settings: the paired account's own profile and privacy.

Not WinZapp's settings (that is SettingsDialog): these live on WhatsApp's
servers, are reached through the local server (main_window/whatsapp_account.py)
and are applied with their own button, so closing the dialog never discards
anything.

Every call to the server runs on a worker thread and reports back through
``wx.CallAfter``: a call can take several seconds, and a frozen window is
indistinguishable from a crashed program for a screen-reader user. The result
is also spoken (``main_window.output``) because a changing static label is not
announced on its own.
"""

import os
import threading

import wx

from core import whatsapp_account as account


class WhatsAppSettingsDialog(wx.Dialog):
    def __init__(self, parent, main_window):
        self.main_window = main_window
        i18n = main_window.i18n
        super().__init__(
            parent,
            title=i18n.t("wa_settings_dialog_title"),
            size=(480, 520),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self._i18n = i18n
        self._privacy_loaded = None  # what WhatsApp reported, once it did

        panel = wx.Panel(self)
        outer = wx.BoxSizer(wx.VERTICAL)
        self._notebook = wx.Notebook(panel)
        self._build_profile_tab(i18n)
        if account.PRIVACY_TAB_ENABLED:
            self._build_privacy_tab(i18n)
        outer.Add(self._notebook, 1, wx.EXPAND | wx.ALL, 8)

        # OK, not Close: each tab saves through its own button, so closing
        # never discarded anything — same wording as the other dialogs.
        ok_button = wx.Button(panel, wx.ID_OK, i18n.t("ok"))
        ok_button.Bind(wx.EVT_BUTTON, lambda event: self.EndModal(wx.ID_OK))
        outer.Add(ok_button, 0, wx.ALL | wx.ALIGN_RIGHT, 8)
        panel.SetSizer(outer)

        frame = wx.BoxSizer(wx.VERTICAL)
        frame.Add(panel, 1, wx.EXPAND)
        self.SetSizer(frame)
        self.Bind(wx.EVT_CLOSE, lambda event: self.EndModal(wx.ID_OK))

        if account.PRIVACY_TAB_ENABLED:
            self._load_privacy()

    # ── Profile ───────────────────────────────────────────────────────────────

    def _build_profile_tab(self, i18n):
        panel = wx.Panel(self._notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(panel, label=i18n.t("profile_blank_note")), 0, wx.ALL, 8)

        sizer.Add(wx.StaticText(panel, label=i18n.t("profile_name_label")), 0,
                  wx.LEFT | wx.TOP, 8)
        self._name_field = wx.TextCtrl(panel)
        sizer.Add(self._name_field, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 8)
        if not account.PROFILE_NAME_ENABLED:
            self._name_field.Disable()
            note = wx.StaticText(panel, label=i18n.t("profile_name_unavailable_note"))
            note.Wrap(400)
            sizer.Add(note, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)

        sizer.Add(wx.StaticText(panel, label=i18n.t("profile_status_label")), 0,
                  wx.LEFT | wx.TOP, 8)
        self._status_field = wx.TextCtrl(panel)
        sizer.Add(self._status_field, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 8)

        sizer.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 8)
        sizer.Add(wx.StaticText(panel, label=i18n.t("profile_photo_label")), 0, wx.ALL, 8)
        choose = wx.Button(panel, label=i18n.t("profile_choose_photo_button"))
        choose.Bind(wx.EVT_BUTTON, self._on_choose_photo)
        sizer.Add(choose, 0, wx.LEFT | wx.RIGHT, 8)
        self._photo_path = None
        self._photo_label = wx.StaticText(panel, label=i18n.t("profile_no_photo_chosen"))
        sizer.Add(self._photo_label, 0, wx.ALL, 8)

        self._profile_message = wx.StaticText(panel, label="")
        sizer.Add(self._profile_message, 0, wx.ALL, 8)
        self._save_button = wx.Button(panel, label=i18n.t("profile_save_button"))
        self._save_button.Bind(wx.EVT_BUTTON, self._on_save_profile)
        sizer.Add(self._save_button, 0, wx.ALL, 8)

        panel.SetSizer(sizer)
        self._notebook.AddPage(panel, i18n.t("wa_settings_tab_profile"))

    def _on_choose_photo(self, event):
        i18n = self._i18n
        with wx.FileDialog(
            self, i18n.t("profile_choose_photo_button"),
            wildcard=i18n.t("profile_photo_wildcard"),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as chooser:
            if chooser.ShowModal() != wx.ID_OK:
                return
            self._photo_path = chooser.GetPath()
        self._photo_label.SetLabel(os.path.basename(self._photo_path))

    def _on_save_profile(self, event):
        i18n = self._i18n
        changes = account.profile_changes(
            self._name_field.GetValue(), self._status_field.GetValue(), self._photo_path
        )
        if changes.empty:
            wx.MessageBox(
                i18n.t("profile_nothing_to_save"),
                i18n.t("error").format(app_name=self.main_window.app_name),
                wx.OK | wx.ICON_ERROR, self,
            )
            return

        self._save_button.Disable()
        self._profile_message.SetLabel(i18n.t("profile_saving"))
        self.main_window.output(i18n.t("profile_saving"))
        mw = self.main_window

        def work():
            errors = []
            for label_key, value, call in (
                ("profile_name_label", changes.name, mw.set_profile_name),
                ("profile_status_label", changes.status, mw.set_profile_status),
                ("profile_photo_label", changes.photo, mw.set_profile_pic),
            ):
                if value:
                    error = call(value)
                    if error:
                        errors.append(f"{i18n.t(label_key)}: {error}")
            wx.CallAfter(self._on_profile_saved, errors)

        threading.Thread(target=work, daemon=True).start()

    def _on_profile_saved(self, errors):
        if not self:  # closed while the server was still answering
            return
        i18n = self._i18n
        self._save_button.Enable()
        self._profile_message.SetLabel("")
        if errors:
            wx.MessageBox(
                i18n.t("profile_save_partial_error") + "\n\n" + "\n".join(errors),
                i18n.t("error").format(app_name=self.main_window.app_name),
                wx.OK | wx.ICON_ERROR, self,
            )
            return
        wx.MessageBox(
            i18n.t("profile_save_success"), i18n.t("wa_settings_tab_profile"),
            wx.OK | wx.ICON_INFORMATION, self,
        )
        self._name_field.SetValue("")
        self._status_field.SetValue("")
        self._photo_path = None
        self._photo_label.SetLabel(i18n.t("profile_no_photo_chosen"))

    # ── Privacy (only while account.PRIVACY_TAB_ENABLED) ──────────────────────

    def _build_privacy_tab(self, i18n):
        panel = wx.Panel(self._notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(panel, label=i18n.t("wa_privacy_section_label")), 0, wx.ALL, 8)

        self._privacy_choices = {}
        for field in account.PRIVACY_FIELDS:
            sizer.Add(wx.StaticText(panel, label=i18n.t(field.label_key)), 0,
                      wx.LEFT | wx.TOP | wx.RIGHT, 8)
            choice = wx.Choice(
                panel, choices=[i18n.t(label_key) for _value, label_key in field.options]
            )
            choice.Disable()  # until WhatsApp has told us the current values
            self._privacy_choices[field.setting] = choice
            sizer.Add(choice, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

        self._privacy_message = wx.StaticText(panel, label=i18n.t("wa_privacy_loading"))
        sizer.Add(self._privacy_message, 0, wx.ALL, 8)
        self._apply_button = wx.Button(panel, label=i18n.t("wa_privacy_apply_button"))
        self._apply_button.Disable()
        self._apply_button.Bind(wx.EVT_BUTTON, self._on_apply_privacy)
        sizer.Add(self._apply_button, 0, wx.ALL, 8)

        panel.SetSizer(sizer)
        self._notebook.AddPage(panel, i18n.t("wa_settings_tab_privacy"))

    def _load_privacy(self):
        def work():
            settings = self.main_window.fetch_privacy_settings()
            wx.CallAfter(self._on_privacy_loaded, settings)

        threading.Thread(target=work, daemon=True).start()

    def _on_privacy_loaded(self, settings):
        if not self:
            return
        if not settings:
            self._privacy_message.SetLabel(self._i18n.t("wa_privacy_load_failed"))
            return
        if account.unreadable(settings):
            # WhatsApp answered, but with nothing this window understands.
            # Silent empty dropdowns look like a working tab that ignores you,
            # so say so, in a window and aloud.
            message = self._i18n.t("wa_privacy_unreadable_msg")
            self._privacy_message.SetLabel(message)
            self.main_window.output(message)
            wx.MessageBox(
                message,
                self._i18n.t("error").format(app_name=self.main_window.app_name),
                wx.OK | wx.ICON_ERROR, self,
            )
            return
        self._privacy_loaded = settings
        self._privacy_message.SetLabel("")
        for field in account.PRIVACY_FIELDS:
            choice = self._privacy_choices[field.setting]
            choice.SetSelection(
                account.option_index(field, settings.get(field.setting, ""))
            )
            choice.Enable()
        self._apply_button.Enable()

    def _on_apply_privacy(self, event):
        i18n = self._i18n
        chosen = {
            setting: choice.GetSelection()
            for setting, choice in self._privacy_choices.items()
        }
        changes = account.changed_privacy(self._privacy_loaded or {}, chosen)
        if not changes:
            self._privacy_message.SetLabel(i18n.t("wa_privacy_nothing_changed"))
            self.main_window.output(i18n.t("wa_privacy_nothing_changed"))
            return
        self._apply_button.Disable()
        mw = self.main_window

        self._privacy_message.SetLabel(i18n.t("profile_saving"))
        self.main_window.output(i18n.t("profile_saving"))

        def work():
            errors = []
            for setting, value in changes:
                error = mw.set_privacy_setting(setting, value)
                if error:
                    errors.append(error)
            # A setter that answered "success" may still have done nothing:
            # read the values back, and only believe what WhatsApp reports.
            sent = [(s, v) for s, v in changes
                    if s not in {line.split(":", 1)[0] for line in errors}]
            readback = mw.fetch_privacy_settings() if sent else None
            unconfirmed = account.not_confirmed(sent, readback) if sent else []
            wx.CallAfter(self._on_privacy_applied, changes, errors, unconfirmed, readback)

        threading.Thread(target=work, daemon=True).start()

    def _on_privacy_applied(self, changes, errors, unconfirmed=(), readback=None):
        if not self:
            return
        i18n = self._i18n
        self._apply_button.Enable()
        failed = {line.split(":", 1)[0] for line in errors} | set(unconfirmed)
        for setting, value in changes:
            if setting not in failed and self._privacy_loaded is not None:
                self._privacy_loaded[setting] = value  # confirmed by the read-back
        if not errors and unconfirmed:
            # No error anywhere, and still nothing changed on WhatsApp: the
            # case that looks exactly like success. Name what did not stick.
            names = ", ".join(
                i18n.t(field.label_key)
                for field in account.PRIVACY_FIELDS if field.setting in unconfirmed
            )
            message = i18n.t("wa_privacy_not_confirmed_msg").format(settings=names)
            self._privacy_message.SetLabel(message)
            self.main_window.output(message)
            wx.MessageBox(
                message,
                i18n.t("error").format(app_name=self.main_window.app_name),
                wx.OK | wx.ICON_ERROR, self,
            )
            return
        if errors:
            self._privacy_message.SetLabel(i18n.t("wa_privacy_apply_partial_error"))
            wx.MessageBox(
                "\n".join(errors),
                i18n.t("error").format(app_name=self.main_window.app_name),
                wx.OK | wx.ICON_ERROR, self,
            )
        else:
            self._privacy_message.SetLabel(i18n.t("wa_privacy_apply_success"))
            self.main_window.output(i18n.t("wa_privacy_apply_success"))
