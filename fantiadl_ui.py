# -*- coding: utf-8 -*- 

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import threading
import queue
import os
import sys
import subprocess
import shlex
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta # pyright: ignore[reportMissingModuleSource]
from dotenv import load_dotenv, find_dotenv # pyright: ignore[reportMissingImports]
import csv
import traceback
from functools import partial

# modelsから新しい関数をインポート
from models import FantiaDownloader, update_cookies_via_login
from image_viewer import ImageViewerWindow

class ConfigEditorWindow(tk.Toplevel):
    """
    設定ファイルを編集するためのウィンドウ。
    .envとIDリストを分かりやすく編集できるUIを提供。
    """
    def __init__(self, parent, update_command=None):
        super().__init__(parent)
        self.title("設定ファイル編集")
        self.geometry("700x550")
        self.update_command = update_command

        # .envファイルから設定を読み込む
        load_dotenv(override=True) # type: ignore

        self.files_to_edit = {
            ".env": find_dotenv() or ".env",
            "IDリスト": os.getenv('TSV_FILE', 'id_list.txt'),
            "Cookie": os.getenv('COOKIE_FILE', 'cookies.txt')
        }

        # UIウィジェットを保持する辞書
        self.text_widgets = {}
        self.id_list_tree = None
        self.env_entries = {}
        self.option_vars = {}
        self.update_button = None
        self.update_status_label = None
        
        self.cookie_update_queue = queue.Queue()
        self.cookie_thread_running = False

        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(expand=True, fill="both")

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(pady=5, expand=True, fill="both")

        # 各設定タブを作成
        for display_name, filepath in self.files_to_edit.items():
            tab_frame = ttk.Frame(self.notebook, padding="5")
            self.notebook.add(tab_frame, text=display_name)

            if display_name == ".env":
                self._create_env_editor(tab_frame)
            elif display_name == "IDリスト":
                self._create_id_list_editor(tab_frame)
            elif display_name == "Cookie":
                self._create_cookie_editor(tab_frame)
            
            # ファイルの内容を読み込んでUIに反映
            self._load_content(display_name, filepath)

        # 保存・閉じるボタン
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=(5, 0), fill="x")
        save_button = ttk.Button(button_frame, text="保存して閉じる", command=self.save_files)
        save_button.pack(side=tk.RIGHT, padx=5)
        close_button = ttk.Button(button_frame, text="閉じる", command=self.destroy)
        close_button.pack(side=tk.RIGHT)

        self.transient(parent)
        self.grab_set()

    def _create_env_editor(self, parent_frame):
        """ .env ファイル編集用のUIを作成する """
        # 基本設定フレーム
        env_vars_frame = ttk.LabelFrame(parent_frame, text="基本設定", padding=10)
        env_vars_frame.pack(fill="x", padx=5, pady=5)
        env_vars_frame.columnconfigure(1, weight=1)

        env_var_definitions = {
            "DL_DIR": "ダウンロード先ディレクトリ",
            "TSV_FILE": "IDリストファイル名",
            "COOKIE_FILE": "Cookieファイル名",
            "SKIP_FILE": "スキップリストファイル名"
        }

        for i, (var, desc) in enumerate(env_var_definitions.items()):
            ttk.Label(env_vars_frame, text=f"{desc} ({var}):").grid(row=i, column=0, sticky="w", padx=5, pady=3)
            entry = ttk.Entry(env_vars_frame, width=60)
            entry.grid(row=i, column=1, sticky="ew", padx=5, pady=3)
            self.env_entries[var] = entry
            if var == "DL_DIR":
                browse_button = ttk.Button(env_vars_frame, text="参照...", command=self._browse_dl_dir)
                browse_button.grid(row=i, column=2, padx=5)

        # オプション設定フレーム
        options_frame = ttk.LabelFrame(parent_frame, text="ダウンロードオプション (OPTIONS)", padding=10)
        options_frame.pack(fill="x", expand=True, padx=5, pady=5)

        option_flags = {
            "-i": "(-i) エラー発生時もダウンロードを継続する (--ignore-errors)",
            "-s": "(-s) サーバー側のファイル名を使用する (--use-server-filenames)",
            "-r": "(-r) 不完全な投稿に .incomplete ファイルを追加する (--mark-incomplete-posts)",
            "-m": "(-m) メタデータ（アイコン、ヘッダー等）を保存する (--dump-metadata)",
            "-x": "(-x) 投稿を解析して外部リンクを探す (--parse-for-external-links)",
            "-t": "(-t) 投稿のサムネイルをダウンロードする (--download-thumbnail)",
        }

        for i, (flag, desc) in enumerate(option_flags.items()):
            var = tk.BooleanVar()
            cb = ttk.Checkbutton(options_frame, text=desc, variable=var)
            cb.grid(row=i, column=0, sticky="w", padx=5, pady=2)
            self.option_vars[flag] = var

    def _browse_dl_dir(self):
        directory = filedialog.askdirectory(parent=self)
        if directory:
            self.env_entries["DL_DIR"].delete(0, tk.END)
            self.env_entries["DL_DIR"].insert(0, directory)

    def _create_id_list_editor(self, parent_frame):
        """IDリストを編集するためのTreeviewとボタンを作成する"""
        editor_frame = ttk.Frame(parent_frame)
        editor_frame.pack(expand=True, fill="both")

        columns = ('id', 'name')
        self.id_list_tree = ttk.Treeview(editor_frame, columns=columns, show='headings')
        self.id_list_tree.heading('id', text='ID')
        self.id_list_tree.heading('name', text='名前')
        self.id_list_tree.column('id', width=100, anchor='w')
        self.id_list_tree.column('name', width=300, anchor='w')

        vsb = ttk.Scrollbar(editor_frame, orient="vertical", command=self.id_list_tree.yview)
        hsb = ttk.Scrollbar(editor_frame, orient="horizontal", command=self.id_list_tree.xview)
        self.id_list_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side='right', fill='y')
        hsb.pack(side='bottom', fill='x')
        self.id_list_tree.pack(expand=True, fill='both')
        self.id_list_tree.bind('<Double-1>', self._on_tree_double_click)

        button_frame = ttk.Frame(parent_frame)
        button_frame.pack(fill='x', pady=5)
        add_button = ttk.Button(button_frame, text="行を追加", command=self._add_id_row)
        add_button.pack(side=tk.LEFT, padx=5)
        delete_button = ttk.Button(button_frame, text="選択した行を削除", command=self._delete_id_row)
        delete_button.pack(side=tk.LEFT, padx=5)
        if self.update_command:
            self.update_button = ttk.Button(button_frame, text="フォローリスト更新", command=self.update_command)
            self.update_button.pack(side=tk.LEFT, padx=5)
            self.update_status_label = ttk.Label(button_frame, text="")
            self.update_status_label.pack(side=tk.LEFT)

    def _create_cookie_editor(self, parent_frame):
        """ Cookie編集用のUIを作成する """
        login_frame = ttk.Frame(parent_frame)
        login_frame.pack(fill="x", pady=(0, 5))
        self.cookie_update_button = ttk.Button(
            login_frame, text="ブラウザでログインしてCookieを更新", command=self._run_cookie_update)
        self.cookie_update_button.pack(side=tk.LEFT)
        self.cookie_status_label = ttk.Label(login_frame, text="")
        self.cookie_status_label.pack(side=tk.LEFT, padx=10)

        text_area = scrolledtext.ScrolledText(parent_frame, wrap=tk.WORD, width=80, height=25, background="#3c4049", foreground="#abb2bf")
        text_area.pack(expand=True, fill="both")
        self.text_widgets["Cookie"] = text_area

    def _load_content(self, display_name, filepath):
        """ファイルの内容を適切なウィジェットに読み込む"""
        if display_name == ".env":
            load_dotenv(find_dotenv(), override=True) # type: ignore
            for var, entry in self.env_entries.items():
                entry.delete(0, tk.END)
                entry.insert(0, os.getenv(var, ''))
            options_str = os.getenv('OPTIONS', '')
            try:
                options = shlex.split(options_str)
            except ValueError:
                options = options_str.split() # Fallback for unquoted strings
            for flag, var in self.option_vars.items():
                var.set(flag in options)

        elif display_name == "IDリスト":
            if not self.id_list_tree: return
            for i in self.id_list_tree.get_children(): self.id_list_tree.delete(i)
            try:
                with open(filepath, 'r', encoding='utf-8', newline='') as f:
                    reader = csv.reader(f)
                    try: next(reader)
                    except StopIteration: return
                    for row in reader:
                        if len(row) >= 2: self.id_list_tree.insert('', 'end', values=(row[0].strip(), row[1].strip()))
                        elif len(row) == 1: self.id_list_tree.insert('', 'end', values=(row[0].strip(), ''))
            except FileNotFoundError: pass
            except Exception as e: messagebox.showerror("エラー", f"IDリストファイルの読み込み中にエラー: {e}", parent=self)

        elif display_name == "Cookie":
            text_area = self.text_widgets.get("Cookie")
            if not text_area: return
            text_area.config(state="normal")
            text_area.delete("1.0", tk.END)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    text_area.insert('1.0', f.read())
            except FileNotFoundError:
                text_area.insert('1.0', f"# ファイルが見つかりませんでした: {filepath}\n# 保存時にこの名前で新規作成されます。")
            except Exception as e:
                 text_area.insert('1.0', f"# ファイルの読み込み中にエラー: {e}")

    def save_files(self):
        """ウィジェットの内容を各ファイルに保存する"""
        try:
            # .env ファイルの保存
            env_filepath = self.files_to_edit[".env"]
            if not env_filepath or env_filepath == ".env":
                env_filepath = ".env"
            env_content = []
            for var, entry in self.env_entries.items():
                value = entry.get().strip()
                # 値にスペースが含まれる可能性を考慮して引用符で囲む
                env_content.append(f'{var}="{value}"')
            selected_options = [flag for flag, var in self.option_vars.items() if var.get()]
            options_str = " ".join(selected_options)
            env_content.append(f'OPTIONS="{options_str}"')
            with open(env_filepath, 'w', encoding='utf-8') as f:
                f.write("\n".join(env_content) + "\n")

            # IDリストの保存
            if self.id_list_tree:
                filepath = self.files_to_edit["IDリスト"]
                with open(filepath, 'w', encoding='utf-8', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['id', 'name'])
                    for item_id in self.id_list_tree.get_children():
                        values = self.id_list_tree.item(item_id, 'values')
                        if values and (str(values[0]).strip() or str(values[1]).strip()):
                            writer.writerow(values)

            # Cookieファイルの保存
            if "Cookie" in self.text_widgets:
                content = self.text_widgets["Cookie"].get("1.0", "end-1c")
                filepath = self.files_to_edit["Cookie"]
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)

            messagebox.showinfo("成功", "ファイルが正常に保存されました。", parent=self)
            self.destroy()
        except Exception as e:
            messagebox.showerror("エラー", f"ファイルの保存中にエラーが発生しました: {e}", parent=self)
            traceback.print_exc()

    def _on_tree_double_click(self, event):
        region = self.id_list_tree.identify("region", event.x, event.y) # pyright: ignore[reportOptionalMemberAccess]
        if region != "cell": return
        item_id = self.id_list_tree.focus() # pyright: ignore[reportOptionalMemberAccess]
        column = self.id_list_tree.identify_column(event.x) # pyright: ignore[reportOptionalMemberAccess]
        x, y, width, height = self.id_list_tree.bbox(item_id, column) # pyright: ignore[reportOptionalMemberAccess]
        entry_var = tk.StringVar(value=self.id_list_tree.set(item_id, column)) # pyright: ignore[reportOptionalMemberAccess]
        entry = ttk.Entry(self.id_list_tree, textvariable=entry_var) # pyright: ignore[reportOptionalMemberAccess]
        entry.place(x=x, y=y, width=width, height=height)
        entry.focus_set()
        entry.selection_range(0, tk.END)
        def on_done(e):
            self.id_list_tree.set(item_id, column, entry_var.get()) # type: ignore
            entry.destroy()
        entry.bind('<FocusOut>', on_done)
        entry.bind('<Return>', on_done)
        entry.bind('<Escape>', lambda e: entry.destroy())

    def _add_id_row(self):
        if self.id_list_tree: self.id_list_tree.insert('', 'end', values=("", ""))

    def _delete_id_row(self):
        if not self.id_list_tree: return
        selected_items = self.id_list_tree.selection()
        if not selected_items: 
            messagebox.showinfo("情報", "削除する行を選択してください。", parent=self)
            return
        if messagebox.askyesno("確認", f"{len(selected_items)}行を削除しますか？", parent=self):
            for item in selected_items: self.id_list_tree.delete(item)

    def _run_cookie_update(self):
        if self.cookie_thread_running: return
        self.cookie_thread_running = True
        self.cookie_update_button.config(state="disabled")
        self.cookie_status_label.config(text="準備中...")
        threading.Thread(target=self._cookie_update_worker, daemon=True).start()
        self.after(100, self._process_cookie_queue)

    def _process_cookie_queue(self):
        try:
            while True:
                msg_type, value = self.cookie_update_queue.get_nowait()
                if msg_type == "status": self.cookie_status_label.config(text=value)
                elif msg_type == "reload": self._load_content("Cookie", self.files_to_edit["Cookie"])
                elif msg_type == "done":
                    self.cookie_thread_running = False
                    self.cookie_update_button.config(state="normal")
                    return
        except queue.Empty:
            pass
        if self.cookie_thread_running: self.after(100, self._process_cookie_queue)

    def _cookie_update_worker(self):
        cookie_filepath = self.files_to_edit["Cookie"]
        def status_callback(message):
            self.cookie_update_queue.put(("status", message))
        success = update_cookies_via_login(cookie_filepath, status_callback)
        if success:
            status_callback("完了: Cookieを更新しました。エディタの内容を再読み込みします。")
            self.cookie_update_queue.put(("reload", None))
        else:
            status_callback("失敗: Cookieを更新できませんでした。詳細はログを確認してください。")
        self.cookie_update_queue.put(("done", None))


class ListDisplayDialog(tk.Toplevel):
    """
    リストを表示し、選択や確認を行うための汎用ダイアログ。
    """
    def __init__(self, parent, title, message, items, ok_text="OK", cancel_text="キャンセル", selection_mode=False):
        super().__init__(parent)
        self.title(title)
        self.geometry("600x400")

        self.result = False
        self.selected_items = []
        self.selection_mode = selection_mode

        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(expand=True, fill="both")
        main_frame.rowconfigure(1, weight=1)
        main_frame.columnconfigure(0, weight=1)

        label = ttk.Label(main_frame, text=message)
        label.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))

        tree_frame = ttk.Frame(main_frame)
        tree_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=5)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        columns = ('selected', 'id', 'name') if selection_mode else ('number', 'id', 'name')
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='headings')

        if selection_mode:
            self.tree.heading('selected', text='選択')
            self.tree.column('selected', width=50, anchor='center', stretch=False)
        else:
            self.tree.heading('number', text='項番')
            self.tree.column('number', width=50, anchor='center', stretch=False)

        self.tree.heading('id', text='ID')
        self.tree.heading('name', text='ファンクラブ名')
        self.tree.column('id', width=100, anchor='w')
        self.tree.column('name', width=350, anchor='w')

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        self.item_data = {}
        for i, (item_id, name) in enumerate(items, 1):
            if selection_mode:
                tree_item_id = self.tree.insert('', 'end', values=("☐", item_id, name))
                self.item_data[tree_item_id] = {"id": item_id, "name": name, "selected": False}
            else:
                self.tree.insert('', 'end', values=(i, item_id, name))

        if selection_mode:
            self.tree.bind('<Button-1>', self._toggle_selection)

        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        button_frame.columnconfigure(1, weight=1)

        if self.selection_mode:
            select_all_button = ttk.Button(button_frame, text="すべて選択", command=self._select_all)
            select_all_button.grid(row=0, column=0, sticky="w", padx=5)
            deselect_all_button = ttk.Button(button_frame, text="すべて解除", command=self._deselect_all)
            deselect_all_button.grid(row=0, column=1, sticky="w")

        dialog_button_frame = ttk.Frame(button_frame)
        dialog_button_frame.grid(row=0, column=2, sticky="e")

        ok_button = ttk.Button(dialog_button_frame, text=ok_text, command=self._on_ok)
        ok_button.pack(side=tk.LEFT, padx=5)
        cancel_button = ttk.Button(dialog_button_frame, text=cancel_text, command=self._on_cancel)
        cancel_button.pack(side=tk.LEFT)

        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.wait_window(self)

    def _set_all_selection(self, selected_state):
        if not self.selection_mode: return # type: ignore
        new_char = "☑" if selected_state else "☐"
        for item_id_key in self.item_data:
            data = self.item_data[item_id_key]
            if data["selected"] != selected_state:
                data["selected"] = selected_state
                self.tree.item(item_id_key, values=(new_char, data["id"], data["name"]))

    def _select_all(self):
        self._set_all_selection(True)

    def _deselect_all(self):
        self._set_all_selection(False)

    def _toggle_selection(self, event):
        item_id_key = self.tree.identify_row(event.y) # type: ignore
        if not item_id_key: return
        data = self.item_data[item_id_key]
        data["selected"] = not data["selected"]
        new_char = "☑" if data["selected"] else "☐"
        self.tree.item(item_id_key, values=(new_char, data["id"], data["name"]))

    def _on_ok(self):
        self.result = True
        if self.selection_mode:
            self.selected_items = [ (data["id"], data["name"]) for data in self.item_data.values() if data["selected"] ]
        self.destroy()

    def _on_cancel(self):
        self.result = False
        self.selected_items = []
        self.destroy()

class SelectFanclubDialog(tk.Toplevel):
    def __init__(self, parent, fanclubs):
        super().__init__(parent)
        self.title("ファンクラブを選択")
        self.geometry("400x300")
        self.selected_fanclub = None

        self.listbox = tk.Listbox(self, background="#282c34", foreground="#abb2bf", selectbackground="#4b5263", selectforeground="#abb2bf")
        self.listbox.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)

        for fanclub in fanclubs:
            self.listbox.insert(tk.END, fanclub)

        self.listbox.bind("<Double-1>", self.on_select)

        button_frame = ttk.Frame(self)
        button_frame.pack(pady=5)

        ok_button = ttk.Button(button_frame, text="OK", command=self.on_select)
        ok_button.pack(side=tk.LEFT, padx=5)

        cancel_button = ttk.Button(button_frame, text="キャンセル", command=self.destroy)
        cancel_button.pack(side=tk.LEFT, padx=5)

        self.transient(parent)
        self.grab_set()
        self.wait_window(self)

    def on_select(self, event=None):
        selection = self.listbox.curselection()
        if selection:
            self.selected_fanclub = self.listbox.get(selection[0])
        self.destroy()

class FantiadlApp:
    """
    fantiadlのリストダウンロードを実行するためのGUIアプリケーション。
    """
    def __init__(self, root):
        self.root = root
        self.root.title("Fantia Downloader GUI")
        self.root.geometry("1200x700")

        # --- Style ---
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure('.', background='#282c34', foreground='#abb2bf')
        self.style.configure('TFrame', background='#282c34')
        self.style.configure('TButton', padding=6, relief='flat', background='#4b5263', foreground='#abb2bf')
        self.style.map('TButton', background=[('active', '#52596b')])
        self.style.configure('TLabel', background='#282c34', foreground='#abb2bf')
        self.style.configure('Treeview', 
                             rowheight=25, 
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
        self.style.configure('TLabelframe', background='#282c34', bordercolor="#3c4049")
        self.style.configure('TLabelframe.Label', background='#282c34', foreground='#abb2bf')

        self.NUM_SLOTS = 2
        self.update_queue = queue.Queue()
        self.download_queue = queue.Queue()
        self.update_thread = None
        self.dispatcher_running = False
        self.last_used_slot = -1
        self.total_queued_items = 0
        self.completed_items_count = 0

        self.download_threads = [None] * self.NUM_SLOTS
        self.processes = [None] * self.NUM_SLOTS
        self.cancel_events = [threading.Event() for _ in range(self.NUM_SLOTS)]

        self.status_labels = []
        self.status_base_text = [""] * self.NUM_SLOTS
        self.per_club_progress_vars = []
        self.log_areas = []
        self.cancel_buttons = []

        main_frame = ttk.Frame(self.root, padding="10", style='TFrame')
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.rowconfigure(3, weight=1)
        main_frame.columnconfigure(0, weight=1)

        settings_frame = ttk.LabelFrame(main_frame, text="設定", padding="10")
        settings_frame.grid(row=0, column=0, sticky="ew", pady=5)
        settings_frame.columnconfigure(1, weight=1)

        ttk.Label(settings_frame, text="対象月:", style='TLabel').grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.month_var = tk.StringVar(value="current")
        self.month_entry = ttk.Entry(settings_frame, textvariable=self.month_var)
        self.month_entry.grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)
        ttk.Label(settings_frame, text="('current', 'last', 'YYYY-MM', or 'all')", style='TLabel').grid(row=0, column=2, sticky=tk.W, padx=5)

        control_frame = ttk.Frame(main_frame, style='TFrame')
        control_frame.grid(row=1, column=0, pady=5, sticky="ew")

        self.start_button = ttk.Button(control_frame, text="リストから選択してキューに追加", command=self.enqueue_downloads)
        self.start_button.pack(side=tk.LEFT, padx=(0, 5))

        self.edit_button = ttk.Button(control_frame, text="設定ファイル編集", command=self.open_editor_window)
        self.edit_button.pack(side=tk.LEFT, padx=5)

        self.open_folder_button = ttk.Button(control_frame, text="ダウンロードフォルダを開く", command=self._open_download_folder)
        self.open_folder_button.pack(side=tk.LEFT)

        self.image_viewer_button = ttk.Button(control_frame, text="画像ビューア", command=self._open_image_viewer)
        self.image_viewer_button.pack(side=tk.LEFT, padx=5)

        progress_frame = ttk.LabelFrame(main_frame, text="全体進捗", padding="10")
        progress_frame.grid(row=2, column=0, sticky="ew", pady=5)
        progress_frame.columnconfigure(0, weight=1)

        self.overall_progress_var = tk.DoubleVar()
        self.overall_progress_bar = ttk.Progressbar(progress_frame, orient="horizontal", mode="determinate", variable=self.overall_progress_var, style="Horizontal.TProgressbar")
        self.overall_progress_bar.grid(row=0, column=0, sticky="ew")
        self.overall_status_label = ttk.Label(progress_frame, text="キュー: 0件", style='TLabel')
        self.overall_status_label.grid(row=1, column=0, sticky="ew")

        bottom_pane = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        bottom_pane.grid(row=3, column=0, sticky="nsew", pady=5)

        for i in range(self.NUM_SLOTS):
            slot_frame = ttk.LabelFrame(bottom_pane, text=f"ダウンロードスロット {i + 1}", padding="10")
            bottom_pane.add(slot_frame, weight=1)
            slot_frame.rowconfigure(2, weight=1)
            slot_frame.columnconfigure(0, weight=1)

            status_label = ttk.Label(slot_frame, text="待機中...", style='TLabel')
            status_label.grid(row=0, column=0, columnspan=2, sticky="ew", pady=2)
            self.status_labels.append(status_label)

            per_club_var = tk.DoubleVar()
            per_club_bar = ttk.Progressbar(slot_frame, orient="horizontal", mode="determinate", variable=per_club_var, style="Horizontal.TProgressbar")
            per_club_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=2)
            self.per_club_progress_vars.append(per_club_var)

            log_area = scrolledtext.ScrolledText(slot_frame, wrap=tk.WORD, state='disabled', width=60, height=15, background="#3c4049", foreground="#abb2bf")
            log_area.grid(row=2, column=0, columnspan=2, sticky="nsew")
            self.log_areas.append(log_area)

            cancel_button = ttk.Button(slot_frame, text="キャンセル", command=partial(self._cancel_download, i), state="disabled")
            cancel_button.grid(row=3, column=0, pady=5, sticky="w")
            self.cancel_buttons.append(cancel_button)

    def _log(self, message, slot_id):
        log_area = self.log_areas[slot_id]
        log_area.config(state='normal')
        log_area.insert(tk.END, message + "\n")
        log_area.see(tk.END)
        log_area.config(state='disabled')

    def open_editor_window(self):
        if not hasattr(self, 'editor_window') or not self.editor_window.winfo_exists():
            self.editor_window = ConfigEditorWindow(self.root, update_command=self.start_follow_list_update) # type: ignore
        self.editor_window.focus()

    def _open_download_folder(self):
        load_dotenv(override=True)
        dl_dir = os.getenv('DL_DIR')
        if dl_dir and os.path.isdir(dl_dir):
            try:
                if sys.platform == "win32":
                    os.startfile(os.path.realpath(dl_dir))
                elif sys.platform == "darwin":
                    subprocess.run(["open", dl_dir])
                else:
                    subprocess.run(["xdg-open", dl_dir])
            except Exception as e:
                messagebox.showerror("エラー", f"フォルダを開けませんでした: {e}", parent=self.root)
        elif dl_dir:
            messagebox.showwarning("警告", f"指定されたディレクトリが見つかりません: {dl_dir}", parent=self.root)
        else:
            messagebox.showinfo("情報", "ダウンロードディレクトリが設定されていません。", parent=self.root)

    def _open_image_viewer(self):
        load_dotenv(override=True) # type: ignore
        dl_dir = os.getenv('DL_DIR')
        if dl_dir and os.path.isdir(dl_dir):
            fanclubs = [d for d in os.listdir(dl_dir) if os.path.isdir(os.path.join(dl_dir, d))]
            if not fanclubs:
                messagebox.showinfo("情報", "ダウンロードディレクトリにファンクラブのフォルダが見つかりません。", parent=self.root)
                return

            dialog = SelectFanclubDialog(self.root, fanclubs)
            if dialog.selected_fanclub:
                fanclub_dir = os.path.join(dl_dir, dialog.selected_fanclub)
                ImageViewerWindow(self.root, fanclub_dir)
        elif dl_dir:
            messagebox.showwarning("警告", f"指定されたディレクトリが見つかりません: {dl_dir}", parent=self.root)
        else:
            messagebox.showinfo("情報", "ダウンロードディレクトリが設定されていません。", parent=self.root)

    def _find_available_slot(self, preferred_slot=-1):
        if preferred_slot != -1 and (self.download_threads[preferred_slot] is None or not self.download_threads[preferred_slot].is_alive()): # type: ignore
            return preferred_slot
        for i, thread in enumerate(self.download_threads):
            if thread is None or not thread.is_alive():
                return i
        return -1

    def enqueue_downloads(self):
        load_dotenv(override=True) # type: ignore
        tsv_file = os.getenv('TSV_FILE', 'id_list.txt')
        try:
            with open(tsv_file, 'r', encoding='UTF-8') as f:
                reader = csv.reader(f)
                next(reader)
                all_clubs = [(row[0], row[1]) for row in reader if row and len(row) >= 2 and row[0].strip()]
        except (FileNotFoundError, StopIteration):
            all_clubs = []

        if not all_clubs:
            messagebox.showinfo("情報", "IDリストにダウンロード対象がありません。", parent=self.root)
            return

        dialog = ListDisplayDialog(self.root, "ダウンロードするファンクラブを選択", "ダウンロードするファンクラブをチェックしてください:", all_clubs, ok_text="キューに追加", selection_mode=True)
        if not dialog.selected_items:
            return

        for item in dialog.selected_items:
            self.download_queue.put(item)
        
        self.total_queued_items += len(dialog.selected_items)
        self._update_overall_progress()

        if not self.dispatcher_running:
            self.dispatcher_running = True
            self._dispatcher()

    def _dispatcher(self):
        if not self.download_queue.empty():
            preferred_slot = (self.last_used_slot + 1) % self.NUM_SLOTS
            slot_id = self._find_available_slot(preferred_slot=preferred_slot)

            if slot_id != -1:
                self.last_used_slot = slot_id
                fan_club = self.download_queue.get_nowait()
                month = self.month_var.get()
                self._prepare_and_run_download(month, [fan_club], slot_id)
        
        is_running = not self.download_queue.empty() or any(t and t.is_alive() for t in self.download_threads)
        if is_running:
            self.root.after(1000, self._dispatcher)
        else:
            self.dispatcher_running = False

    def _update_overall_progress(self):
        progress = (self.completed_items_count / self.total_queued_items) * 100 if self.total_queued_items > 0 else 0
        self.overall_progress_var.set(progress)
        self.overall_status_label.config(text=f"キュー: {self.download_queue.qsize()}件 / 完了: {self.completed_items_count} / 合計: {self.total_queued_items}")

    def start_follow_list_update(self):
        if self.update_thread and self.update_thread.is_alive():
            return
        self.update_thread = threading.Thread(target=self._update_follow_list_worker, daemon=True)
        self.update_thread.start()

    def _update_follow_list_worker(self):
        editor = self.editor_window
        if not editor or not editor.winfo_exists():
            return

        def gui_update(func, *args, **kwargs):
            self.root.after(0, lambda: func(*args, **kwargs))

        gui_update(editor.update_button.config, state="disabled") # pyright: ignore[reportOptionalMemberAccess]
        gui_update(editor.update_status_label.config, text="更新中...") # pyright: ignore[reportOptionalMemberAccess]

        try:
            load_dotenv(override=True)
            cookie_file = os.getenv('COOKIE_FILE', 'cookies.txt')
            tsv_file = os.getenv('TSV_FILE', 'id_list.txt')

            if not os.path.exists(cookie_file):
                raise FileNotFoundError("Cookieファイルが見つかりません。")

            downloader = FantiaDownloader(session_arg=cookie_file, quiet=True)
            clubs = downloader.get_followed_fanclubs_details()

            with open(tsv_file, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'name'])
                writer.writerows(clubs)

            gui_update(editor.update_status_label.config, text=f"{len(clubs)}件のファンクラブを保存しました。") # type: ignore
            gui_update(editor._load_content, "IDリスト", tsv_file) # type: ignore

        except Exception as e:
            error_message = f"エラー: {e}"
            gui_update(editor.update_status_label.config, text=error_message) # type: ignore
            messagebox.showerror("フォローリスト更新エラー", error_message, parent=editor)
        finally:
            gui_update(editor.update_button.config, state="normal") # pyright: ignore[reportOptionalMemberAccess]

    def _prepare_and_run_download(self, month_arg, rows_to_process, slot_id):
        self._set_ui_busy(slot_id, "準備中...")
        self.download_threads[slot_id] = threading.Thread( # type: ignore
            target=self._download_worker,
            args=(month_arg, rows_to_process, slot_id,),
            daemon=True
        )
        self.download_threads[slot_id].start()
        self.root.after(100, self._process_queue)

    def _set_ui_busy(self, slot_id, status_message):
        self.cancel_buttons[slot_id].config(state="normal")
        self.log_areas[slot_id].config(state='normal')
        self.log_areas[slot_id].delete('1.0', tk.END)
        self.log_areas[slot_id].config(state='disabled')
        self.per_club_progress_vars[slot_id].set(0)
        self.status_labels[slot_id].config(text=status_message)
        self.cancel_events[slot_id].clear()

    def _cancel_download(self, slot_id):
        self.status_labels[slot_id].config(text="キャンセル中...")
        self.cancel_events[slot_id].set()
        if self.processes[slot_id] and self.processes[slot_id].poll() is None:
            try:
                self.processes[slot_id].terminate()
            except Exception as e:
                self._log(f"プロセス終了エラー: {e}", slot_id)
        self.cancel_buttons[slot_id].config(state="disabled")

    def _download_worker(self, month_arg, rows_to_process, slot_id):
        try:
            load_dotenv(override=True) # type: ignore
            dl_dir = os.path.expandvars(os.getenv('DL_DIR', os.path.join(os.path.expanduser('~'), 'Downloads')))
            skip_file = os.getenv('SKIP_FILE', 'skip_list.txt')
            cookie_file = os.getenv('COOKIE_FILE', 'cookies.txt')
            options = os.getenv('OPTIONS', '')
            q_put = lambda type, val: self.update_queue.put((slot_id, type, val))

            fan_id, name = rows_to_process[0]
            q_put("status", f"ダウンロード中: {name}")
            q_put("per_club_progress", 0)

            processed_month_arg = None
            if month_arg:
                if month_arg.lower() == 'current':
                    processed_month_arg = datetime.now().strftime("%Y-%m")
                elif month_arg.lower() == 'last':
                    processed_month_arg = (datetime.now() - relativedelta(months=1)).strftime("%Y-%m")
                else:
                    processed_month_arg = month_arg

            command = [sys.executable, '-u', 'fantiadl.py'] + shlex.split(options) + ['-c', cookie_file, '-o', dl_dir, f"https://fantia.jp/fanclubs/{fan_id}"]
            if processed_month_arg:
                command.extend(['-d', processed_month_arg])

            collection_regex = re.compile(r"Collected (\d+) posts\.")
            downloading_regex = re.compile(r"Downloading post (\d+)...")
            total_posts = 0
            downloaded_posts = 0

            try:
                env = os.environ.copy()
                env.__setitem__('PYTHONIOENCODING', 'utf-8')
                flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                self.processes[slot_id] = subprocess.Popen( # type: ignore
                    command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding='utf-8', errors='replace', creationflags=flags, env=env
                )

                if self.processes[slot_id] and self.processes[slot_id].stdout:
                    for line in iter(self.processes[slot_id].stdout.readline, ''):
                        if self.cancel_events[slot_id].is_set(): break
                        line = line.strip()
                        q_put("log", line)
                        collection_match = collection_regex.search(line)
                        if collection_match:
                            total_posts = int(collection_match.group(1))
                            downloaded_posts = 0
                            if total_posts == 0:
                                q_put("per_club_progress", 100)

                        downloading_match = downloading_regex.search(line)
                        if downloading_match:
                            downloaded_posts += 1

                        if total_posts > 0:
                            progress = (downloaded_posts / total_posts) * 100
                            q_put("per_club_progress", progress)

                process = self.processes[slot_id]
                if process:
                    process.wait()
                    if self.cancel_events[slot_id].is_set():
                        q_put("cancelled", "ユーザーによってキャンセルされました。")
                        return

                    if process.returncode == 0:
                        q_put("per_club_progress", 100)
                        q_put("done", f"完了: {name}")
                    else:
                        q_put("error", f"エラー: {name} (コード: {process.returncode})")
                else:
                    q_put("error", f"エラー: {name} (プロセスを開始できませんでした)")

            except Exception as e:
                q_put("error", f"予期せぬエラー ({name}): {e}")
            finally:
                self.processes[slot_id] = None

        except Exception as e:
            error_info = f"ワーカーで致命的なエラー: {e}\n{traceback.format_exc()}"
            self.update_queue.put((slot_id, "error", error_info))

    def _reset_ui_state(self, slot_id, final_message="待機中..."):
        self.status_labels[slot_id].config(text=final_message)
        self.per_club_progress_vars[slot_id].set(0)
        self.cancel_buttons[slot_id].config(state="disabled")
        self.download_threads[slot_id] = None
        self.completed_items_count += 1
        self._update_overall_progress()

    def _process_queue(self):
        try:
            while True:
                slot_id, message_type, value = self.update_queue.get_nowait()

                if message_type == "per_club_progress":
                    self.per_club_progress_vars[slot_id].set(value)
                    if self.status_base_text[slot_id]:
                        self.status_labels[slot_id].config(text=f"{self.status_base_text[slot_id]} ({value:.1f}%)")
                elif message_type == "status":
                    self.status_base_text[slot_id] = value
                    self.status_labels[slot_id].config(text=value)
                elif message_type == "log":
                    self._log(value, slot_id)
                elif message_type == "done":
                    self._log(f"--- {value} ---", slot_id)
                    self._reset_ui_state(slot_id, "完了")
                elif message_type == "error":
                    self._log(f"--- {value} ---", slot_id)
                    self._reset_ui_state(slot_id, "エラー")
                elif message_type == "cancelled":
                    self._log(f"--- {value} ---", slot_id)
                    self._reset_ui_state(slot_id, "キャンセル済")

        except queue.Empty:
            if self.dispatcher_running:
                self.root.after(100, self._process_queue)


if __name__ == "__main__":
    if sys.platform == "win32":
        from ctypes import windll
        try: windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError): pass
    root = tk.Tk()
    app = FantiadlApp(root)
    root.mainloop()
