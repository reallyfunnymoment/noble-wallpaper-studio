"""Native desktop editor. Launch via Start Editor.cmd."""
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import queue
import threading
import math
import logging
from PIL import Image, ImageTk
from transfer_progress import TransferProgress
from app_version import APP_NAME, VERSION
from app_paths import DATA_DIR, stock_resource_path, original_updater_path, backup_directory
from firmware_reference import import_updater, read_stock_resource
from editor_core import (ROOT, SLOTS, LABELS, DEFAULTS, WIDTH, HEIGHT, load_image,
                         stock_project, render, quantize_preview, save_project,
                         load_project, export_package, THEMES, theme_transform, project_theme)


class Editor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f'{APP_NAME} {VERSION}')
        self.geometry('1120x790')
        self.minsize(980, 730)
        self.configure(bg='#eef2f6')
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10))
        style.configure('TFrame', background='#eef2f6')
        style.configure('TLabel', background='#eef2f6', foreground='#243247')
        style.configure('Title.TLabel', font=('Segoe UI', 21, 'bold'))
        style.configure('Heading.TLabel', font=('Segoe UI', 11, 'bold'))
        style.configure('TButton', padding=(10, 7))
        style.configure('Accent.TButton', background='#146bba', foreground='white')
        try:
            self.slots = stock_project()
        except (OSError, ValueError) as error:
            messagebox.showerror('Reference data needs attention', str(error), parent=self)
            # Let users repair a damaged imported reference through the setup button.
            from PIL import Image
            self.slots = {slot: dict(name=LABELS[slot], image=Image.new('RGB', (WIDTH, HEIGHT), '#203449'),
                                    settings=DEFAULTS.copy(), radio_theme=0) for slot in SLOTS}
        self.slot = 'model'
        self.project_path = None
        self.dirty = False
        self.busy = False
        self.loading = False
        self.pending = None
        self.photos = {}
        self.results = queue.Queue()
        self.radio_results = queue.Queue()
        self.radio_busy = False
        self.usb_results = queue.Queue()
        self.usb_busy = False
        self.transfer_window = None
        self.export_progress = None
        self.variables = {}
        self.numeric_inputs = {}
        self.status = tk.StringVar(value='Ready. Choose a slot, then import a photo or edit the stock image.')
        if not stock_resource_path().is_file():
            self.status.set('Import photos to begin. For stock images and USB uploads, choose Import firmware reference.')
        self.rgb565 = tk.BooleanVar(value=True)
        self.name = tk.StringVar()
        self.sync_theme = tk.BooleanVar(value=True)
        self.radio_theme = tk.StringVar(value=THEMES[0])
        self._build()
        self._load_controls()
        self._thumbnails()
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(100, self._poll_export)

    def _build(self):
        header = ttk.Frame(self, padding=(22, 16))
        header.pack(fill='x')
        ttk.Label(header, text='Noble Wallpaper Studio', style='Title.TLabel').pack(side='left')
        ttk.Label(header, text=f'{VERSION}  •  NB4+  •  Firmware 1.0.31 only').pack(side='right')
        toolbar = ttk.Frame(self, padding=(22, 0, 22, 12))
        toolbar.pack(fill='x')
        for label, command in [('New', self.new), ('Open project…', self.open),
                               ('Save project', self.save), ('Save as…', lambda: self.save(True))]:
            ttk.Button(toolbar, text=label, command=command).pack(side='left', padx=(0, 7))
        self.export_button = ttk.Button(toolbar, text='Export radio package…',
                                       style='Accent.TButton', command=self.export)
        self.export_button.pack(side='right')
        usbbar = ttk.Frame(self, padding=(22, 0, 22, 10))
        usbbar.pack(fill='x')
        self.radio_button = ttk.Button(usbbar, text='Check radio connection', command=self.check_radio)
        self.radio_button.pack(side='left', padx=(0, 7))
        self.upload_button = ttk.Button(usbbar, text='Upload wallpapers via USB…', command=self.prepare_usb)
        self.upload_button.pack(side='left', padx=(0, 7))
        self.restore_button = ttk.Button(usbbar, text='Restore USB session…', command=self.restore_usb)
        self.restore_button.pack(side='left')
        ttk.Button(usbbar, text='Import firmware reference…', command=self.setup_reference).pack(side='right')
        body = ttk.Frame(self, padding=(22, 0, 22, 12))
        body.pack(fill='both', expand=True)
        left = ttk.Frame(body, width=200)
        left.pack(side='left', fill='y', padx=(0, 18))
        ttk.Label(left, text='WALLPAPER SLOTS', style='Heading.TLabel').pack(anchor='w', pady=(0, 8))
        self.slot_buttons = {}
        for slot in SLOTS:
            button = ttk.Button(left, text=LABELS[slot], compound='top',
                                command=lambda s=slot: self.select(s), width=21)
            button.pack(fill='x', pady=(0, 8))
            self.slot_buttons[slot] = button
        ttk.Label(left, text='These are the three selectable\nslots on the transmitter.\n\nProject labels stay on the PC.',
                  wraplength=190).pack(anchor='w', pady=8)
        center = ttk.Frame(body)
        center.pack(side='left', fill='both', expand=True)
        self.heading = ttk.Label(center, style='Heading.TLabel')
        self.heading.pack(pady=(0, 8))
        self.canvas = tk.Canvas(center, bg='#152033', highlightthickness=0, cursor='fleur')
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>', lambda e: self.schedule_render())
        self.canvas.bind('<ButtonPress-1>', self.drag_start)
        self.canvas.bind('<B1-Motion>', self.drag)
        self.canvas.bind('<MouseWheel>', self.wheel)
        ttk.Label(center, text='Drag to position • Mouse wheel to zoom').pack(pady=(8, 3))
        ttk.Checkbutton(center, text='Preview transmitter colors (RGB565)', variable=self.rgb565,
                        command=self.schedule_render).pack()
        right_host = ttk.Frame(body)
        right_host.pack(side='right', fill='y', padx=(18, 0))
        controls = tk.Canvas(right_host, width=285, bg='#eef2f6', highlightthickness=0)
        controls.pack(side='left', fill='both', expand=True)
        scrollbar = ttk.Scrollbar(right_host, orient='vertical', command=controls.yview)
        scrollbar.pack(side='right', fill='y')
        controls.configure(yscrollcommand=scrollbar.set)
        right = ttk.Frame(controls)
        controls_window = controls.create_window((0, 0), window=right, anchor='nw')
        right.bind('<Configure>', lambda e: controls.configure(scrollregion=controls.bbox('all')))
        controls.bind('<Configure>', lambda e: controls.itemconfigure(controls_window, width=e.width))
        ttk.Label(right, text='EDIT SELECTED WALLPAPER', style='Heading.TLabel').pack(anchor='w', pady=(0, 8))
        ttk.Button(right, text='Import photo…', command=self.import_photo, style='Accent.TButton').pack(fill='x')
        ttk.Label(right, text='Project label').pack(anchor='w', pady=(10, 2))
        entry = ttk.Entry(right, textvariable=self.name)
        entry.pack(fill='x')
        self.name.trace_add('write', lambda *_: self.name_changed())
        ttk.Label(right, text='Transmitter theme (all slots)').pack(anchor='w', pady=(12, 2))
        theme_combo = ttk.Combobox(right, textvariable=self.radio_theme, values=THEMES, state='readonly')
        theme_combo.pack(fill='x')
        theme_combo.bind('<<ComboboxSelected>>', self.radio_theme_changed)
        ttk.Label(right, text='Match System → Theme on the radio. After switching themes, upload again to keep photo colors.',
                  wraplength=270).pack(anchor='w', pady=(4, 4))
        self.theme_checkbox = ttk.Checkbutton(right, text='Keep Character artwork consistent',
                                              variable=self.sync_theme, command=self.theme_changed)
        self.theme_checkbox.pack(anchor='w', pady=(6, 0))
        self.variables['fit'] = tk.StringVar(value='Fill')
        row = ttk.Frame(right)
        row.pack(fill='x', pady=(9, 0))
        ttk.Label(row, text='Sizing').pack(side='left')
        combo = ttk.Combobox(row, textvariable=self.variables['fit'], values=('Fill', 'Fit'), state='readonly', width=10)
        combo.pack(side='right')
        combo.bind('<<ComboboxSelected>>', lambda e: self.change())
        for key, label, low, high in [('rotation', 'Rotation (degrees)', -180, 180),
                                      ('zoom', 'Zoom (0.1–4×)', 0.1, 4), ('x', 'Horizontal position', 0, 1),
                                      ('y', 'Vertical position', 0, 1), ('brightness', 'Brightness', 0, 2),
                                      ('contrast', 'Contrast', 0, 2), ('saturation', 'Color', 0, 2),
                                      ('sharpness', 'Sharpness', 0, 3)]:
            line = ttk.Frame(right)
            line.pack(fill='x', pady=(7, 0))
            ttk.Label(line, text=label).pack(side='left')
            variable = tk.DoubleVar(value=DEFAULTS[key])
            self.variables[key] = variable
            text = tk.StringVar(value=f'{DEFAULTS[key]:g}')
            self.numeric_inputs[key] = (text, low, high)
            if key == 'rotation':
                number = ttk.Spinbox(line, textvariable=text, width=8, justify='right',
                                     from_=low, to=high, increment=0.1,
                                     command=lambda k=key: self.commit_number(k))
            else:
                number = ttk.Entry(line, textvariable=text, width=8, justify='right')
            number.pack(side='right')
            variable.trace_add('write', lambda *_, v=variable, t=text: t.set(f'{v.get():.6g}'))
            number.bind('<Return>', lambda e, k=key: self.commit_number(k))
            number.bind('<FocusOut>', lambda e, k=key: self.commit_number(k))
            number.bind('<Escape>', lambda e, k=key: self.cancel_number(k))
            ttk.Scale(right, from_=low, to=high, variable=variable,
                      command=lambda _: self.change()).pack(fill='x')
        row = ttk.Frame(right)
        row.pack(fill='x', pady=(10, 5))
        ttk.Button(row, text='Rotate 90°', command=self.rotate).pack(side='left', expand=True, fill='x')
        ttk.Button(row, text='Mirror', command=self.flip).pack(side='left', expand=True, fill='x', padx=(5, 0))
        ttk.Button(right, text='Reset adjustments', command=self.reset).pack(fill='x', pady=3)
        ttk.Button(right, text='Restore stock image', command=self.restore).pack(fill='x', pady=3)
        ttk.Button(right, text='Save selected PNG…', command=self.save_png).pack(fill='x', pady=3)
        ttk.Label(self, textvariable=self.status, padding=(22, 8), wraplength=1000).pack(fill='x')
        self.bind('<Control-s>', lambda e: self.save())
        self.bind('<Control-o>', lambda e: self.open())

    def commit_number(self, key):
        text, low, high = self.numeric_inputs[key]
        previous = self.variables[key].get()
        if text.get() == f'{previous:.6g}':
            return 'break'
        try:
            value = float(text.get().strip())
            if not math.isfinite(value):
                raise ValueError('Expected a finite number')
        except ValueError:
            text.set(f'{previous:.6g}')
            self.status.set(f'Enter a number from {low:g} to {high:g}. Previous value restored.')
            return 'break'
        bounded = max(low, min(high, value))
        self.variables[key].set(bounded)
        if bounded != previous:
            self.change()
        if bounded != value:
            self.status.set(f'Value limited to the allowed range: {low:g} to {high:g}.')
        return 'break'

    def cancel_number(self, key):
        self.numeric_inputs[key][0].set(f'{self.variables[key].get():.6g}')
        return 'break'

    def commit_numbers(self):
        for key in self.numeric_inputs:
            self.commit_number(key)

    def _load_controls(self):
        self.loading = True
        entry = self.slots[self.slot]
        self.name.set(entry['name'])
        self.radio_theme.set(THEMES[project_theme(self.slots)])
        self.sync_theme.set(self.slots['character'].get('sync_theme_variant', True))
        self.theme_checkbox.configure(state='normal' if self.slot == 'character' else 'disabled')
        for key, variable in self.variables.items():
            value = entry['settings'][key]
            variable.set((value+180)%360-180 if key == 'rotation' else value)
        for slot, button in self.slot_buttons.items():
            button.configure(style='Accent.TButton' if slot == self.slot else 'TButton')
        self.heading.configure(text=LABELS[self.slot])
        self.loading = False
        self.schedule_render()

    def mark_dirty(self):
        self.dirty = True
        self.title(f'{APP_NAME} {VERSION} — Unsaved changes')

    def setup_reference(self):
        if self.busy or self.usb_busy or self.radio_busy:
            return False
        path = filedialog.askopenfilename(parent=self, title='Choose original Noble NB4+ EN 1.0.31-4 updater',
                                         filetypes=[('FlySky updater', '*.exe')])
        if not path:
            return False
        self.status.set('Verifying the updater and importing reference data…')
        self.update_idletasks()
        try:
            folder = import_updater(path)
            self.status.set(f'Firmware reference ready. Local reference and recovery storage: {DATA_DIR}')
            messagebox.showinfo('Reference imported',
                                'The updater was verified and read as a data file. It was not executed.\n\n'
                                'New or Restore stock image now loads the original wallpapers.\n\n'
                                f'Reference saved in:\n{folder}', parent=self)
            return True
        except Exception as error:
            self.status.set('Reference import failed. Your project is still available.')
            messagebox.showerror('Could not import firmware reference', str(error), parent=self)
            return False

    def ensure_reference(self):
        try:
            read_stock_resource()
            return True
        except (OSError, ValueError):
            messagebox.showinfo('Firmware reference required',
                                'Select your unchanged Noble NB4+ EN 1.0.31-4 updater. '
                                'The editor reads its reference data without running it.', parent=self)
            return self.setup_reference()

    def name_changed(self):
        if not self.loading:
            self.slots[self.slot]['name'] = self.name.get()[:100]
            self.mark_dirty()

    def theme_changed(self):
        if not self.loading and self.slot == 'character':
            self.slots['character']['sync_theme_variant'] = self.sync_theme.get()
            self.mark_dirty()

    def radio_theme_changed(self, event=None):
        if not self.loading:
            theme = THEMES.index(self.radio_theme.get())
            for entry in self.slots.values():
                entry['radio_theme'] = theme
            self.mark_dirty()
            self.schedule_render()
            self.status.set(f'Colors prepared for {THEMES[theme]}. Match this theme on the transmitter before viewing.')

    def change(self):
        if self.loading:
            return
        for key, variable in self.variables.items():
            self.slots[self.slot]['settings'][key] = variable.get()
        self.mark_dirty()
        self.schedule_render()

    def schedule_render(self):
        if self.pending:
            self.after_cancel(self.pending)
        self.pending = self.after(65, self.draw)

    def draw(self):
        self.pending = None
        image = render(self.slots[self.slot]['image'], self.slots[self.slot]['settings'])
        if self.rgb565.get():
            image = quantize_preview(image, theme=project_theme(self.slots))
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        scale = min((width-28)/WIDTH, (height-28)/HEIGHT)
        scale = max(.1, scale)
        self.preview_scale = scale
        image = image.resize((round(WIDTH*scale), round(HEIGHT*scale)), Image.Resampling.LANCZOS)
        self.preview_photo = ImageTk.PhotoImage(image)
        self.canvas.delete('all')
        self.canvas.create_image(width//2, height//2, image=self.preview_photo)
        self._thumbnail(self.slot)

    def _thumbnail(self, slot):
        image = render(self.slots[slot]['image'], self.slots[slot]['settings'])
        image.thumbnail((70, 87), Image.Resampling.LANCZOS)
        self.photos[slot] = ImageTk.PhotoImage(image)
        self.slot_buttons[slot].configure(image=self.photos[slot])

    def _thumbnails(self):
        for slot in SLOTS:
            self._thumbnail(slot)

    def select(self, slot):
        self.commit_numbers()
        self.slot = slot
        self._load_controls()

    def drag_start(self, event):
        self.drag_origin = (event.x, event.y, self.variables['x'].get(), self.variables['y'].get())
        self.drag_image_size = self.slots[self.slot]['image'].rotate(
            self.slots[self.slot]['settings']['rotation'], expand=True).size

    def drag(self, event):
        if not hasattr(self, 'drag_origin'):
            return
        x, y, px, py = self.drag_origin
        settings = self.slots[self.slot]['settings']
        w, h = self.drag_image_size
        scale = (max if settings['fit'] == 'Fill' else min)(WIDTH/w, HEIGHT/h) * settings['zoom']
        for key, delta, available, initial in [('x', event.x-x, WIDTH-round(w*scale), px),
                                                ('y', event.y-y, HEIGHT-round(h*scale), py)]:
            if available:
                self.variables[key].set(max(0, min(1, initial + delta / self.preview_scale / available)))
        self.change()

    def wheel(self, event):
        self.variables['zoom'].set(max(0.1, min(4, round(self.variables['zoom'].get() + (0.1 if event.delta > 0 else -0.1), 6))))
        self.change()

    def rotate(self):
        self.commit_numbers()
        self.variables['rotation'].set((self.variables['rotation'].get()+270)%360-180)
        self.change()

    def flip(self):
        settings = self.slots[self.slot]['settings']
        settings['flip'] = not settings['flip']
        self.mark_dirty()
        self.schedule_render()

    def reset(self):
        self.slots[self.slot]['settings'] = DEFAULTS.copy()
        self.mark_dirty()
        self._load_controls()

    def restore(self):
        theme = project_theme(self.slots)
        self.slots[self.slot] = stock_project()[self.slot]
        self.slots[self.slot]['radio_theme'] = theme
        self.mark_dirty()
        self._load_controls()

    def import_photo(self):
        path = filedialog.askopenfilename(title='Import photo', filetypes=[('Images', '*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff'), ('All files', '*.*')])
        if path:
            try:
                image = load_image(path)
                self.slots[self.slot] = dict(name=Path(path).stem[:100], image=image, settings=DEFAULTS.copy(),
                                            radio_theme=project_theme(self.slots))
                self.mark_dirty()
                self._load_controls()
                self.status.set(f'Imported {image.width} × {image.height}. Drag the preview to choose your crop.')
            except Exception as error:
                messagebox.showerror('Could not import image', str(error))

    def may_discard(self):
        self.commit_numbers()
        if self.usb_busy:
            messagebox.showinfo('USB transfer in progress', 'Wait for the USB operation to finish before closing or replacing the project.')
            return False
        if self.busy:
            messagebox.showinfo('Export in progress', 'Please wait for the package export to finish.')
            return False
        if self.dirty:
            answer = messagebox.askyesnocancel('Save your project?', 'Save your changes before continuing?')
            if answer is None:
                return False
            if answer:
                return self.save()
        return True

    def new(self):
        if self.may_discard():
            self.slots = stock_project()
            self.project_path = None
            self.saved()
            self._load_controls()
            self._thumbnails()

    def saved(self):
        self.dirty = False
        self.title(f'{APP_NAME} {VERSION}' + (f' — {self.project_path.name}' if self.project_path else ''))

    def save(self, save_as=False):
        self.commit_numbers()
        path = self.project_path if not save_as else None
        if path is None:
            path = filedialog.asksaveasfilename(title='Save editable project', defaultextension='.nb4project',
                                              filetypes=[('NB4 wallpaper project', '*.nb4project')])
        if not path:
            return False
        try:
            save_project(path, self.slots)
            self.project_path = Path(path)
            self.saved()
            self.status.set(f'Project saved: {path}')
            return True
        except Exception as error:
            messagebox.showerror('Could not save project', str(error))
            return False

    def open(self):
        if not self.may_discard():
            return
        path = filedialog.askopenfilename(title='Open project', filetypes=[('NB4 wallpaper project', '*.nb4project')])
        if path:
            try:
                slots = load_project(path)
                self.slots = slots
                self.project_path = Path(path)
                self.saved()
                self._load_controls()
                self._thumbnails()
                self.status.set(f'Opened {path}')
            except Exception as error:
                messagebox.showerror('Could not open project', str(error))

    def save_png(self):
        self.commit_numbers()
        path = filedialog.asksaveasfilename(title='Save selected wallpaper', defaultextension='.png',
                                          initialfile=f'{self.slot}_wallpaper.png', filetypes=[('PNG image', '*.png')])
        if path:
            try:
                quantize_preview(render(self.slots[self.slot]['image'], self.slots[self.slot]['settings']),
                                 theme=project_theme(self.slots)).save(path, format='PNG')
                self.status.set(f'Saved 320 × 398 transmitter-color PNG: {path}')
            except Exception as error:
                messagebox.showerror('Could not save PNG', str(error))

    def export(self):
        self.commit_numbers()
        if self.busy or self.usb_busy:
            return
        if not self.ensure_reference():
            return
        updater = original_updater_path()
        if not updater.exists():
            path = filedialog.askopenfilename(title='Choose original Noble NB4+ 1.0.31-4 updater', filetypes=[('Updater', '*.exe')])
            if not path:
                return
            updater = Path(path)
        parent = filedialog.askdirectory(title='Choose parent folder for a NEW wallpaper package')
        if not parent:
            return
        from tkinter.simpledialog import askstring
        name = askstring('New export folder', 'Package folder name:', initialvalue='My NB4 Wallpapers', parent=self)
        if name is None:
            return
        if not name.strip() or name in ('.', '..') or any(c in name for c in '<>:"/\\|?*') or name.endswith((' ', '.')):
            messagebox.showerror('Invalid folder name', 'Enter a simple new folder name without path separators or special characters.')
            return
        destination = Path(parent) / name
        snapshot = {s: dict(name=e['name'], image=e['image'].copy(), settings=e['settings'].copy(),
                            radio_theme=e.get('radio_theme', 0),
                            sync_theme_variant=e.get('sync_theme_variant', True)) for s, e in self.slots.items()}
        self.busy = True
        self.export_progress = TransferProgress(self, 'export')
        self.export_progress.update_message('Preparing images and verifying package checksums…')
        self.export_button.configure(state='disabled')
        self.status.set('Building package and verifying checksums…')
        def worker():
            try:
                export_package(destination, snapshot, updater)
                self.results.put((True, str(destination)))
            except Exception as error:
                self.results.put((False, str(error)))
        threading.Thread(target=worker, daemon=True).start()

    def check_radio(self):
        if self.radio_busy or self.usb_busy:
            return
        self.radio_busy = True
        self.radio_button.configure(state='disabled')
        self.status.set('Checking the FlySky connection…')
        def worker():
            try:
                from radio_info_probe import probe
                self.radio_results.put((True, probe()))
            except Exception as error:
                self.radio_results.put((False, str(error)))
        threading.Thread(target=worker, daemon=True).start()

    def _poll_export(self):
        try:
            success, result = self.radio_results.get_nowait()
            self.radio_busy = False
            self.radio_button.configure(state='normal')
            if success:
                matches = (result['application_version_word'] == '0000001f'
                           and result['application_variant_word'] == '00010000')
                if matches:
                    summary = 'Noble NB4+ connected. Reported version matches the 1.0.31 reference.'
                else:
                    summary = 'FlySky radio connected. Its reported version differs from the editor reference.'
                self.status.set(summary)
                messagebox.showinfo('Radio connection', summary + '\n\nThe radio answered the device-information request. '
                                    'This check does not upload images or change settings.\n\n'
                                    'To upload, put the transmitter in update mode and choose Upload wallpapers via USB.')
            else:
                self.status.set('Could not verify the radio connection.')
                messagebox.showerror('Radio connection', 'Connect the Noble NB4+ in USB Function mode and close other '
                                     'software using it, then try again.\n\n' + result)
        except queue.Empty:
            pass
        self._poll_usb()
        try:
            success, result = self.results.get_nowait()
            self.busy = False
            if self.export_progress is not None:
                self.export_progress.destroy()
                self.export_progress = None
            self.export_button.configure(state='normal')
            if success:
                self.status.set(f'Exported and verified all three wallpapers: {result}')
                messagebox.showinfo('Package exported', f'All three wallpapers exported to:\n{result}\n\nIncludes previews, editable project, Data.bin, and the unchanged original updater.\n\nDevice behavior is not hardware tested. The updater has not been run.')
            else:
                self.status.set('Export failed. Your project is still available.')
                messagebox.showerror('Could not export package', result)
        except queue.Empty:
            pass
        self.after(100, self._poll_export)

    def _usb_state(self, busy):
        self.usb_busy = busy
        for button in (self.upload_button, self.restore_button, self.radio_button):
            button.configure(state='disabled' if busy else 'normal')

    def _usb_worker(self, job, operation):
        self._usb_state(True)
        self.transfer_window = TransferProgress(self, job)
        self.transfer_window.update_message('Preparing images and checking the radio…' if job == 'prepared'
                                             else 'Checking the saved transfer and radio…')
        def worker():
            try:
                result = operation(lambda message: self.usb_results.put(('progress', message)))
                self.usb_results.put((job, result))
            except Exception as error:
                self.usb_results.put(('error', str(error)))
        threading.Thread(target=worker, daemon=True).start()

    def prepare_usb(self):
        if self.usb_busy or self.radio_busy or self.busy:
            return
        if not self.ensure_reference():
            return
        self.commit_numbers()
        snapshot = {s: dict(name=e['name'], image=e['image'].copy(), settings=e['settings'].copy(),
                            radio_theme=e.get('radio_theme', 0),
                            sync_theme_variant=e.get('sync_theme_variant', True))
                    for s, e in self.slots.items()}
        self.status.set('Preparing USB upload: checking the radio and saving recovery data…')
        def prepare(progress):
            from patch_wallpaper import patch_resource, patch_character_theme
            from wallpaper_usb import prepare_upload
            target = read_stock_resource()
            theme = project_theme(snapshot)
            for slot in SLOTS:
                rgb = theme_transform(render(snapshot[slot]['image'], snapshot[slot]['settings']), theme).tobytes()
                target, _, _ = patch_resource(target, rgb, slot)
                if slot == 'character' and snapshot[slot].get('sync_theme_variant', True):
                    target, _, _ = patch_character_theme(target, rgb)
            folder, manifest = prepare_upload(bytes(target), progress)
            save_project(folder/'wallpapers.nb4project', snapshot)
            for slot in SLOTS:
                quantize_preview(render(snapshot[slot]['image'], snapshot[slot]['settings']), theme=theme).save(folder/f'{slot}_preview.png')
            return folder, manifest, {s: e['name'] for s, e in snapshot.items()}, THEMES[theme]
        self._usb_worker('prepared', prepare)

    def restore_usb(self):
        if self.usb_busy or self.radio_busy or self.busy:
            return
        folder = filedialog.askdirectory(title='Select saved USB session folder', initialdir=str(backup_directory()))
        if not folder:
            return
        try:
            from wallpaper_usb import load_session
            manifest = load_session(folder)
        except Exception as error:
            messagebox.showerror('Invalid recovery session', str(error))
            return
        if manifest['state'] == 'prepared':
            messagebox.showinfo('Nothing to restore', 'This session was prepared but no upload was started.')
            return
        if messagebox.askyesno('Restore previous wallpapers?',
                              'Keep the radio in update mode. Restore the wallpaper data saved before this USB session?\n\n'
                              'This writes the saved image-data blocks to the transmitter.\n\n'+folder):
            from wallpaper_usb import execute_upload
            self._usb_worker('restored', lambda progress: execute_upload(folder, confirmed=True, restore=True, progress=progress))

    def _poll_usb(self):
        # Drain progress updates in one pass; workers never touch Tk widgets.
        for _ in range(200):
            try:
                kind, result = self.usb_results.get_nowait()
            except queue.Empty:
                return
            if kind == 'progress':
                self.status.set(result)
                if self.transfer_window is not None:
                    self.transfer_window.update_message(result)
                continue
            if self.transfer_window is not None:
                self.transfer_window.destroy()
                self.transfer_window = None
            self._usb_state(False)
            if kind == 'error':
                self.status.set('USB operation stopped. See the error and recovery information.')
                messagebox.showerror('USB operation stopped', result)
            elif kind == 'prepared':
                folder, manifest, names, theme = result
                if not manifest['blocks']:
                    self.status.set('The radio already matches these wallpapers. No upload needed.')
                    messagebox.showinfo('Already up to date', 'These wallpapers already match the radio.')
                    continue
                slots = manifest['plan']['changed_slots']
                summary = '\n'.join(f'• {LABELS[slot]}: {names[slot]}' for slot in slots)
                if messagebox.askyesno('Confirm USB wallpaper upload',
                                      f'Upload these changed slots?\n\n{summary}\n\n'
                                      f'Match transmitter theme: {theme}. Switching themes later requires another upload for correct colors.\n\n'
                                      f'{len(manifest["blocks"])} image-data blocks will be written. Application firmware is excluded.\n\n'
                                      f'Recovery files and previews:\n{folder}\n\n'
                                      'Keep USB and transmitter power connected throughout the transfer.\n\nStart upload?'):
                    from wallpaper_usb import execute_upload
                    self._usb_worker('uploaded', lambda progress, f=folder: execute_upload(f, confirmed=True, progress=progress))
                else:
                    self.status.set(f'Upload canceled; prepared files saved in {folder}')
            elif kind in ('uploaded', 'restored'):
                verb = 'Uploaded' if kind == 'uploaded' else 'Restored'
                self.status.set(f'{verb} and verified wallpaper data. Restart the transmitter to view it.')
                messagebox.showinfo('USB operation verified',
                                    f'{verb} wallpaper data; all resource checksums match.\n\n'
                                    'Restart the transmitter to view the wallpapers. The application firmware was not rewritten.')

    def close(self):
        if self.may_discard():
            self.destroy()

    def report_callback_exception(self, exc_type, error, traceback):
        logging.error('Editor action failed', exc_info=(exc_type, error, traceback))
        messagebox.showerror('Editor action failed',
                             f'{error}\n\nYour project is still open. See the application log in:\n{DATA_DIR}', parent=self)


if __name__ == '__main__':
    from logging.handlers import RotatingFileHandler
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(level=logging.INFO, handlers=[RotatingFileHandler(
            DATA_DIR/'studio.log', maxBytes=500_000, backupCount=2, encoding='utf-8')])
        logging.info('%s %s started', APP_NAME, VERSION)
        Editor().mainloop()
    except Exception as error:
        logging.exception('Startup failed')
        messagebox.showerror('Could not start Noble Wallpaper Studio',
                             f'{error}\n\nCheck the application log in:\n{DATA_DIR}')
        raise SystemExit(1)
