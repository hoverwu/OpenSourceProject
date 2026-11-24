# -*- coding: utf-8 -*-
"""EBX modal/open regression tests (hoverwu / 0.1.0)."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import ebx_mcp_server as server


class EBXMCPOpenTests(unittest.TestCase):
    def test_discard_button_accepts_mnemonic_suffix(self):
        buttons = [
            SimpleNamespace(ControlTypeName="ButtonControl", Name="是(Y) Alt+Y"),
            SimpleNamespace(ControlTypeName="ButtonControl", Name="否(N) Alt+N"),
        ]
        with patch.object(server, "_iter", return_value=buttons), \
                patch.object(server, "_click_element") as click:
            name = server._click_button(SimpleNamespace(), ("否", "No"))
        self.assertEqual(name, "否(N) Alt+N")
        click.assert_called_once_with(buttons[1])

    def test_open_handles_existing_modal_before_activating_main_window(self):
        modal = SimpleNamespace(Name="")
        with patch.object(server.os.path, "isfile", return_value=True), \
                patch.object(server, "_main_window", return_value=object()), \
                patch.object(server, "_find_visible_dialog", side_effect=[modal, None, None]), \
                patch.object(server, "_dialog_buttons", return_value=[]), \
                patch.object(server, "_click_button", return_value="否(N) Alt+N") as discard, \
                patch.object(server, "_activate", return_value=True) as activate, \
                patch.object(server, "_send_combo"), \
                patch.object(server, "_click_rel"), \
                patch.object(server, "_wait_file_dialog", return_value=None), \
                patch.object(server.time, "sleep"):
            result = server.ebx_open("test.ebxprj", discard_unsaved=True)
        discard.assert_called_once_with(modal, ("否", "No"))
        activate.assert_called_once_with()
        self.assertEqual(result["error"], "打开对话框未出现")


if __name__ == "__main__":
    unittest.main()
