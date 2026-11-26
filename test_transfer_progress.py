import unittest
from transfer_progress import progress_value


class ProgressTests(unittest.TestCase):
    def test_live_backup_stages(self):
        self.assertEqual(progress_value('Inspecting backup blocks: 1/2', 'prepared'), 25)
        self.assertEqual(progress_value('Backing up current wallpapers: 1/2 (about 4 min remaining)', 'prepared'), 55)
        self.assertEqual(progress_value('Checking recovered data: 1/2', 'prepared'), 85)
    def test_stages_advance_through_complete_upload_and_restore(self):
        for mode, start, done in [('uploaded', 'Uploading', 'Uploaded'),
                                  ('restored', 'Restoring', 'Restored')]:
            messages = ['Checking transfer: 1/2', 'Checking transfer: 2/2',
                        f'{start} block 1/2', f'{done} block 1/2',
                        f'{start} block 2/2', f'{done} block 2/2',
                        'Verifying resource: 1/2 bytes', 'Verifying resource: 2/2 bytes']
            self.assertEqual([progress_value(m, mode) for m in messages],
                             [5, 10, 10, 50, 50, 90, 95, 100])

    def test_preparation_and_unmeasured_work(self):
        self.assertEqual(progress_value('Checking radio data: 1/2', 'prepared'), 10)
        self.assertEqual(progress_value('Checking affected blocks: 1/2', 'prepared'), 60)
        self.assertIsNone(progress_value('Preparing images…', 'prepared'))
        self.assertIsNone(progress_value('Checking affected blocks: 0/0', 'prepared'))
        self.assertIsNone(progress_value('Exporting 1/2', 'export'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
