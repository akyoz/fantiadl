import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import os
import sys
import threading

class ImageViewerWindow(tk.Toplevel):
    def __init__(self, parent, folder_path):
        super().__init__(parent)
        self.title("Image Viewer")
        self.geometry("1200x800")

        # --- Style ---
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure('.', background='#282c34', foreground='#abb2bf')
        self.style.configure('TFrame', background='#282c34')
        self.style.configure('TButton', padding=6, relief='flat', background='#4b5263', foreground='#abb2bf')
        self.style.map('TButton', background=[('active', '#52596b')])
        self.style.configure('TLabel', background='#282c34', foreground='#abb2bf')
        self.style.configure('Treeview', 
                             rowheight=60, 
                             fieldbackground='#282c34', 
                             background='#282c34', 
                             foreground='#abb2bf',
                             bordercolor="#282c34",
                             lightcolor="#282c34",
                             darkcolor="#282c34")
        self.style.configure('Treeview.Heading', 
                             background='#3c4049', 
                             foreground='#abb2bf', 
                             relief='flat')
        self.style.map('Treeview.Heading', background=[('active', '#52596b')])
        self.style.configure("Horizontal.TProgressbar", 
                             background='#4b5263', 
                             troughcolor='#282c34',
                             bordercolor="#282c34",
                             lightcolor="#4b5263",
                             darkcolor="#4b5263")

        # --- Data ---
        self.image_info = []
        self.thumbnails = []

        # --- Layout ---
        self.main_frame = ttk.Frame(self, style='TFrame')
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.top_frame = ttk.Frame(self.main_frame, style='TFrame')
        self.top_frame.pack(fill=tk.X, padx=10, pady=5)

        self.content_frame = ttk.Frame(self.main_frame, style='TFrame')
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.content_frame.grid_columnconfigure(1, weight=1)
        self.content_frame.grid_rowconfigure(0, weight=1)

        # --- Widgets ---
        self.select_button = ttk.Button(self.top_frame, text="フォルダを選択", command=self.select_folder_dialog)
        self.select_button.pack(side=tk.LEFT)

        self.status_label = ttk.Label(self.top_frame, text="フォルダを選択してください。", style='TLabel')
        self.status_label.pack(side=tk.LEFT, padx=10)

        self.progressbar = ttk.Progressbar(self.top_frame, orient='horizontal', mode='determinate', style="Horizontal.TProgressbar")

        # Treeview for table display
        self.tree_frame = ttk.Frame(self.content_frame, style='TFrame')
        self.tree_frame.grid(row=0, column=0, sticky='nswe', padx=(0, 5))
        self.tree_frame.grid_rowconfigure(0, weight=1)
        self.tree_frame.grid_columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            self.tree_frame,
            columns=('num', 'name', 'folder', 'size'),
            show='headings'
        )
        self.tree.grid(row=0, column=0, sticky='nswe')

        self.tree.heading('num', text='番号')
        self.tree.heading('name', text='ファイル名')
        self.tree.heading('folder', text='フォルダ')
        self.tree.heading('size', text='サイズ')

        self.tree.column('num', width=50, anchor='center')
        self.tree.column('name', width=250)
        self.tree.column('folder', width=150)
        self.tree.column('size', width=100, anchor='e')

        self.scrollbar = ttk.Scrollbar(self.tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.scrollbar.grid(row=0, column=1, sticky='ns')
        self.tree.config(yscrollcommand=self.scrollbar.set)

        # Image Preview Label
        self.preview_label = ttk.Label(self.content_frame, text="画像プレビュー", style='TLabel', anchor=tk.CENTER)
        self.preview_label.grid(row=0, column=1, sticky='nswe', padx=(5, 0))

        # --- Bindings ---
        self.tree.bind('<<TreeviewSelect>>', self.on_tree_select)
        self.tree.bind('<Double-1>', self.show_full_size_image)
        self.tree.bind('<Return>', self.show_full_size_image)

        if folder_path:
            self.load_folder(folder_path)

    def select_folder_dialog(self):
        folder_path = filedialog.askdirectory()
        if folder_path:
            self.load_folder(folder_path)

    def load_folder(self, folder_path):
        self.clear_tree()
        self.progressbar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.status_label.config(text="ファイル数を計算中...")
        self.update_idletasks() # Ensure UI updates before starting thread
        threading.Thread(target=self.load_images_thread, args=(folder_path,), daemon=True).start()

    def format_size(self, size_bytes):
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024**2:
            return f"{size_bytes/1024:.1f} KB"
        else:
            return f"{size_bytes/1024**2:.1f} MB"

    def load_images_thread(self, folder_path):
        supported = (".png", ".jpg", ".jpeg", ".gif", ".bmp")
        thumb_size = (50, 50)

        paths_to_process = []
        for root, _, files in os.walk(folder_path):
            for f in files:
                if f.lower().endswith(supported):
                    paths_to_process.append(os.path.join(root, f))
        
        total_files = len(paths_to_process)
        if total_files == 0:
            if self.winfo_exists():
                self.after(0, self.populate_tree, [])
            return

        if self.winfo_exists():
            self.after(0, self.progressbar.config, {'maximum': total_files, 'value': 0})

        image_info_list = []
        for i, path in enumerate(paths_to_process):
            if not self.winfo_exists():
                return
            try:
                img = Image.open(path)
                img.thumbnail(thumb_size, Image.Resampling.LANCZOS)
                info = {
                    'num': i + 1,
                    'path': path,
                    'name': os.path.basename(path),
                    'folder': os.path.basename(os.path.dirname(path)),
                    'size': self.format_size(os.path.getsize(path)),
                    'thumb': img
                }
                image_info_list.append(info)

                if (i + 1) % 10 == 0 or (i + 1) == total_files:
                    if self.winfo_exists():
                        self.after(0, self.update_progress, i + 1, total_files)
            except Exception as e:
                print(f"Error processing {path}: {e}")
        
        if self.winfo_exists():
            self.after(0, self.populate_tree, image_info_list)

    def clear_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.image_info = []
        self.thumbnails = []

    def update_progress(self, value, total):
        if self.progressbar.winfo_exists():
            self.progressbar['value'] = value
            self.status_label.config(text=f"読み込み中... {value} / {total}")

    def populate_tree(self, image_info_list):
        if not self.tree.winfo_exists():
            return
        self.clear_tree()
        if self.progressbar.winfo_exists():
            self.progressbar.pack_forget()
        self.image_info = image_info_list
        self.thumbnails = [ImageTk.PhotoImage(info['thumb']) for info in self.image_info]

        for i, info in enumerate(self.image_info):
            if not self.tree.winfo_exists():
                return
            self.tree.insert(
                '', 
                'end', 
                iid=i, 
                image=self.thumbnails[i],
                values=(info['num'], info['name'], info['folder'], info['size'])
            )
        
        if self.image_info:
            if self.status_label.winfo_exists():
                self.status_label.config(text=f"{len(self.image_info)} 個の画像が見つかりました。")
            if self.tree.winfo_exists():
                self.tree.selection_set('0')
                self.tree.focus_set()
                self.tree.focus('0')
        else:
            if self.status_label.winfo_exists():
                self.status_label.config(text="選択されたフォルダに画像は見つかりませんでした。")

    def on_tree_select(self, event=None):
        selection = self.tree.selection()
        if not selection:
            return
        
        selected_index = int(selection[0])
        image_path = self.image_info[selected_index]['path']

        try:
            image = Image.open(image_path)
            w, h = image.size
            max_w = self.preview_label.winfo_width()
            max_h = self.preview_label.winfo_height()
            if max_w < 50 or max_h < 50: max_w, max_h = 800, 600

            ratio = min(max_w/w, max_h/h)
            new_w, new_h = int(w * ratio), int(h * ratio)

            resized_image = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
            photo_image = ImageTk.PhotoImage(resized_image)
            
            self.preview_label.config(image=photo_image, text="")
            self.preview_label.image = photo_image
        except Exception as e:
            self.preview_label.config(image=None, text=f"プレビューの読み込みエラー:\n{e}")

    def show_full_size_image(self, event=None):
        selection = self.tree.selection()
        if not selection:
            return
        
        initial_index = int(selection[0])
        FullscreenViewer(self, self.image_info, initial_index)

class FullscreenViewer(tk.Toplevel):
    def __init__(self, parent, image_info, initial_index):
        super().__init__(parent)
        self.image_info = image_info
        self.current_fullscreen_index = initial_index
        self.fullscreen_photo_ref = None
        self.hide_overlay_timer = None

        self.configure(bg='black')
        self.attributes('-fullscreen', True)
        self.focus_set()

        self._create_styles()
        self._create_widgets()
        self._bind_events()

        self.update_fullscreen_image()
        self.show_overlay()

    def _create_styles(self):
        style = ttk.Style()
        style.configure("Fullscreen.TFrame", background="black")
        style.configure("Fullscreen.TLabel", background="black", foreground="white", font=("Helvetica", 12))
        style.configure("Fullscreen.TButton", background="#202020", foreground="white", font=("Helvetica", 16, 'bold'), relief='flat')
        style.map("Fullscreen.TButton", background=[('active', '#404040')])

    def _create_widgets(self):
        self.img_label = ttk.Label(self, style="Fullscreen.TLabel")
        self.img_label.pack(expand=True)

        self.top_overlay = ttk.Frame(self, style="Fullscreen.TFrame")
        self.bottom_overlay = ttk.Frame(self, style="Fullscreen.TFrame")

        self.filename_label = ttk.Label(self.top_overlay, text="", style="Fullscreen.TLabel")
        self.filename_label.pack(side=tk.LEFT, padx=10, pady=5)
        self.count_label = ttk.Label(self.top_overlay, text="", style="Fullscreen.TLabel")
        self.count_label.pack(side=tk.RIGHT, padx=10, pady=5)

        self.sequence_scale = ttk.Scale(self.bottom_overlay, from_=0, to=len(self.image_info)-1, orient='horizontal')
        self.sequence_scale.pack(fill=tk.X, expand=True, padx=10, pady=5)

        self.prev_button = ttk.Button(self, text="<", style="Fullscreen.TButton")
        self.next_button = ttk.Button(self, text=">", style="Fullscreen.TButton")

    def _bind_events(self):
        self.sequence_scale.config(command=self.seek_image)
        self.prev_button.config(command=self.prev_image)
        self.next_button.config(command=self.next_image)

        self.bind('<Motion>', self.show_overlay)
        self.bind('<Escape>', self.close_fullscreen)
        self.bind('<space>', self.close_fullscreen)
        self.bind('<Return>', self.close_fullscreen)
        self.img_label.bind('<Button-1>', self.close_fullscreen)

        self.bind('<Right>', self.next_image)
        self.bind('<Down>', self.next_image)
        self.bind('<Left>', self.prev_image)
        self.bind('<Up>', self.prev_image)
        
        self.bind('<MouseWheel>', self.on_mouse_wheel) # Windows
        self.bind('<Button-4>', self.on_mouse_wheel)   # Linux scroll up
        self.bind('<Button-5>', self.on_mouse_wheel)   # Linux scroll down

    def update_fullscreen_image(self, update_scale=True):
        image_path = self.image_info[self.current_fullscreen_index]['path']
        filename = os.path.basename(image_path)
        self.title(filename)
        try:
            img = Image.open(image_path)
            screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
            w, h = img.size
            ratio = min(screen_w / w, screen_h / h)
            new_w, new_h = int(w * ratio), int(h * ratio)
            
            resized_image = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            self.fullscreen_photo_ref = ImageTk.PhotoImage(resized_image)
            self.img_label.config(image=self.fullscreen_photo_ref)

            self.filename_label.config(text=filename)
            self.count_label.config(text=f"{self.current_fullscreen_index + 1} / {len(self.image_info)}")
            if update_scale:
                self.sequence_scale.set(self.current_fullscreen_index)

        except Exception as e:
            self.destroy()
            messagebox.showerror("画像エラー", f"画像の読み込み中にエラーが発生しました:\n{e}")

    def next_image(self, e=None):
        if self.current_fullscreen_index < len(self.image_info) - 1:
            self.current_fullscreen_index += 1
            self.update_fullscreen_image()

    def prev_image(self, e=None):
        if self.current_fullscreen_index > 0:
            self.current_fullscreen_index -= 1
            self.update_fullscreen_image()

    def seek_image(self, value):
        index = int(float(value))
        if self.current_fullscreen_index != index:
            self.current_fullscreen_index = index
            self.update_fullscreen_image(update_scale=False)

    def close_fullscreen(self, e=None):
        if self.hide_overlay_timer:
            self.after_cancel(self.hide_overlay_timer)
        self.destroy()

    def show_overlay(self, e=None):
        self.top_overlay.place(relx=0, rely=0, relwidth=1, height=40)
        self.bottom_overlay.place(relx=0, rely=1, anchor='sw', relwidth=1, height=40)
        self.prev_button.place(relx=0, rely=0.5, anchor='w', width=50, height=100)
        self.next_button.place(relx=1, rely=0.5, anchor='e', width=50, height=100)
        
        if self.hide_overlay_timer:
            self.after_cancel(self.hide_overlay_timer)
        self.hide_overlay_timer = self.after(2500, self.hide_overlay)

    def hide_overlay(self):
        self.top_overlay.place_forget()
        self.bottom_overlay.place_forget()
        self.prev_button.place_forget()
        self.next_button.place_forget()

    def on_mouse_wheel(self, event):
        # Cross-platform mouse wheel handling
        if event.delta > 0 or event.num == 4:
            self.prev_image()
        elif event.delta < 0 or event.num == 5:
            self.next_image()