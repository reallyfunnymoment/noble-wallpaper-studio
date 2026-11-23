"""Native Tk smoke checks. No USB access or device writes."""
import unittest
from pathlib import Path
from unittest.mock import patch
from wallpaper_editor import Editor, THEMES, project_theme
from transfer_progress import TransferProgress


class EditorUITests(unittest.TestCase):
    def setUp(self):
        self.editor = Editor()
        self.editor.withdraw()
        self.editor.update_idletasks()
        self.addCleanup(self.editor.destroy)

    def test_typed_rotation_and_shortcut(self):
        editor = self.editor
        editor.numeric_inputs['rotation'][0].set('12.35')
        editor.commit_number('rotation')
        self.assertEqual(editor.slots['model']['settings']['rotation'], 12.35)
        editor.rotate()
        self.assertAlmostEqual(editor.slots['model']['settings']['rotation'], 102.35)
        editor.select('character')
        editor.select('model')
        self.assertAlmostEqual(editor.variables['rotation'].get(), 102.35)
        editor.numeric_inputs['rotation'][0].set('nan')
        editor.commit_number('rotation')
        self.assertAlmostEqual(editor.variables['rotation'].get(), 102.35)

    def test_theme_applies_to_all_slots_and_survives_import_and_restore(self):
        editor = self.editor
        editor.radio_theme.set(THEMES[3])
        editor.radio_theme_changed()
        self.assertEqual(project_theme(editor.slots), 3)
        editor.restore()
        self.assertEqual(project_theme(editor.slots), 3)
        with patch('wallpaper_editor.filedialog.askopenfilename', return_value='example.png'), \
                patch('wallpaper_editor.load_image', return_value=editor.slots['model']['image'].copy()):
            editor.import_photo()
        self.assertEqual(project_theme(editor.slots), 3)
        editor.select('character')
        editor.sync_theme.set(False)
        editor.theme_changed()
        self.assertFalse(editor.slots['character']['sync_theme_variant'])

    def test_large_progress_updates_and_releases_modal_grab(self):
        window = TransferProgress(self.editor, 'uploaded')
        try:
            window.update_idletasks()
            self.assertGreaterEqual(window.winfo_reqwidth(), 500)
            self.assertIsNotNone(window.grab_current())
            window.update_message('Uploaded block 1/2')
            self.assertEqual(window.percent.cget('text'), '50%')
            self.assertEqual(window.bar.cget('value'), 50)
        finally:
            window.destroy()
        self.assertIsNone(self.editor.grab_current())

    def test_canceling_reference_setup_never_starts_usb(self):
        with patch('wallpaper_editor.read_stock_resource', side_effect=FileNotFoundError), \
                patch('wallpaper_editor.messagebox.showinfo'), \
                patch('wallpaper_editor.filedialog.askopenfilename', return_value=''), \
                patch.object(self.editor, '_usb_worker') as worker:
            self.editor.prepare_usb()
        worker.assert_not_called()
        self.assertFalse(self.editor.usb_busy)
        self.assertEqual(len(self.editor.slots), 3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
