"""Large, centered progress display for USB transfers and package exports."""
import re
import time
import tkinter as tk
from tkinter import ttk


def progress_value(message, mode):
    """Return a stage-aware percentage, or None while work is unmeasured."""
    match = re.search(r':?\s*(\d+)/(\d+)', message)
    if not match or int(match[2]) == 0:
        return None
    current, total = int(match[1]), int(match[2])
    fraction = max(0, min(1, current/total))
    if mode == 'prepared':
        if message.startswith('Checking radio data:'):
            return 20*fraction
        if message.startswith('Checking affected blocks:'):
            return 20+80*fraction
    elif mode in ('uploaded', 'restored'):
        if message.startswith('Checking transfer:'):
            return 10*fraction
        if message.startswith(('Uploading block ', 'Restoring block ')):
            return 10+80*max(0, (current-1)/total)
        if message.startswith(('Uploaded block ', 'Restored block ')):
            return 10+80*fraction
        if message.startswith('Verifying resource:'):
            return 90+10*fraction
    return None


class TransferProgress(tk.Toplevel):
    def __init__(self, parent, mode):
        super().__init__(parent)
        self.mode = mode
        self.started = time.monotonic()
        self.tick = None
        title = {'prepared': 'Preparing USB upload', 'uploaded': 'Uploading wallpapers',
                 'restored': 'Restoring wallpapers', 'export': 'Building wallpaper package'}[mode]
        self.title(title)
        self.transient(parent)
        self.resizable(False, False)
        self.protocol('WM_DELETE_WINDOW', lambda: None)
        panel = ttk.Frame(self, padding=26)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text=title, font=('Segoe UI', 20, 'bold')).pack(anchor='w')
        self.percent = ttk.Label(panel, text='Working…', font=('Segoe UI', 30, 'bold'), foreground='#146bba')
        self.percent.pack(anchor='w', pady=(14, 5))
        style = ttk.Style(self)
        style.configure('Upload.Horizontal.TProgressbar', thickness=24)
        self.bar = ttk.Progressbar(panel, mode='indeterminate', length=490,
                                   style='Upload.Horizontal.TProgressbar')
        self.bar.pack(fill='x', pady=(0, 12))
        self.bar.start(12)
        self.detail = ttk.Label(panel, text='Starting…', wraplength=490)
        self.detail.pack(anchor='w')
        self.elapsed = ttk.Label(panel)
        self.elapsed.pack(anchor='w', pady=(12, 0))
        if mode != 'export':
            ttk.Label(panel, text='Keep USB and transmitter power connected.').pack(anchor='w', pady=(8, 0))
        self.update_idletasks()
        x = parent.winfo_rootx()+(parent.winfo_width()-self.winfo_reqwidth())//2
        y = parent.winfo_rooty()+(parent.winfo_height()-self.winfo_reqheight())//2
        self.geometry(f'+{max(0,x)}+{max(0,y)}')
        self.grab_set()
        self._tick()

    def update_message(self, message):
        self.detail.configure(text=message)
        value = progress_value(message, self.mode)
        if value is not None:
            self.bar.stop()
            self.bar.configure(mode='determinate', value=value)
            self.percent.configure(text=f'{int(value)}%')

    def _tick(self):
        seconds = int(time.monotonic()-self.started)
        self.elapsed.configure(text=f'Elapsed: {seconds//60}:{seconds%60:02d}')
        self.tick = self.after(1000, self._tick)

    def destroy(self):
        if self.tick is not None:
            self.after_cancel(self.tick)
            self.tick = None
        self.bar.stop()
        super().destroy()
