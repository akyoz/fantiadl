# -*- coding: utf-8 -*- 

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import queue
import os
import sys
import subprocess
import shlex
from datetime import datetime
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
import csv
import traceback

# modelsから新しい関数をインポート
from models import update_cookies_via_login

class ConfigEditorWindow(tk.Toplevel):
    """
    設定ファイルを編集するためのウィンドウ。
    """
    def __init__(self, parent):
        super().__init__(parent)
        self.title("設定ファイル編集")
        self.geometry("700x550") # 少し高さを増やす

        load_dotenv()

        self.files_to_edit = {
            ".env": ".env",
            "IDリスト": os.getenv('TSV_FILE', 'id_list.txt'),
            "Cookie": os.getenv('COOKIE_FILE', 'cookies.txt')
        }
        self.text_widgets = {}
        self.cookie_update_queue = queue.Queue()
        self.cookie_thread_running = False

        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(expand=True, fill="both")

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(pady=5, expand=True, fill="both")

        for display_name, filepath in self.files_to_edit.items():
            tab_frame = ttk.Frame(self.notebook, padding="5")
            self.notebook.add(tab_frame, text=display_name)

            if display_name == "Cookie":
                login_frame = ttk.Frame(tab_frame)
                login_frame.pack(fill="x", pady=(0, 5))

                self.cookie_update_button = ttk.Button(
                    login_frame,
                    text="ブラウザでログインしてCookieを更新",
                    command=self._run_cookie_update
                )
                self.cookie_update_button.pack(side=tk.LEFT)

                self.cookie_status_label = ttk.Label(login_frame, text="")
                self.cookie_status_label.pack(side=tk.LEFT, padx=10)

            text_area = scrolledtext.ScrolledText(tab_frame, wrap=tk.WORD, width=80, height=25)
            text_area.pack(expand=True, fill="both")
            self.text_widgets[display_name] = text_area

            self._load_file_content(display_name, filepath)

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=(5, 0), fill="x")

        save_button = ttk.Button(button_frame, text="保存して閉じる", command=self.save_files)
        save_button.pack(side=tk.RIGHT, padx=5)

        close_button = ttk.Button(button_frame, text="閉じる", command=self.destroy)
        close_button.pack(side=tk.RIGHT)

        self.transient(parent)
        self.grab_set()

    def _load_file_content(self, display_name, filepath):
        """指定されたファイルの内容をテキストウィジェットに読み込む"""
        text_area = self.text_widgets[display_name]
        text_area.config(state="normal")
        text_area.delete("1.0", tk.END)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                text_area.insert('1.0', f.read())
        except FileNotFoundError:
            text_area.insert('1.0', f"# ファイルが見つかりませんでした: {filepath}\n# 保存時にこの名前で新規作成されます。")
        except Exception as e:
             text_area.insert('1.0', f"# ファイルの読み込み中にエラーが発生しました: {e}")

    def _run_cookie_update(self):
        """Cookie更新プロセスを別スレッドで開始する"""
        if self.cookie_thread_running:
            return

        self.cookie_thread_running = True
        self.cookie_update_button.config(state="disabled")
        self.cookie_status_label.config(text="準備中...")
        cookie_filepath = self.files_to_edit["Cookie"]

        threading.Thread(
            target=self._cookie_update_worker,
            args=(cookie_filepath,),
            daemon=True
        ).start()
        self.after(100, self._process_cookie_queue)

    def _process_cookie_queue(self):
        """ワーカースレッドからのメッセージを処理してGUIを更新する"""
        try:
            while True:
                msg_type, value = self.cookie_update_queue.get_nowait()

                if msg_type == "status":
                    self.cookie_status_label.config(text=value)
                elif msg_type == "reload":
                    self._load_file_content("Cookie", value)
                elif msg_type == "done":
                    self.cookie_thread_running = False
                    self.cookie_update_button.config(state="normal")
                    return # ポーリングを停止

        except queue.Empty:
            pass # キューが空の場合は何もしない

        # スレッドが実行中であれば、再度このメソッドをスケジュールする
        if self.cookie_thread_running:
            self.after(100, self._process_cookie_queue)

    def _cookie_update_worker(self, cookie_filepath):
        """Playwrightを呼び出してCookieを更新するワーカースレッド"""
        def status_callback(message):
            self.cookie_update_queue.put(("status", message))

        success = update_cookies_via_login(cookie_filepath, status_callback)

        if success:
            status_callback("完了: Cookieを更新しました。エディタの内容を再読み込みします。")
            self.cookie_update_queue.put(("reload", cookie_filepath))
        else:
            status_callback("失敗: Cookieを更新できませんでした。詳細はログを確認してください。")
        
        self.cookie_update_queue.put(("done", None))

    def save_files(self):
        """テキストエリアの内容を各ファイルに保存する"""
        try:
            for display_name, text_widget in self.text_widgets.items():
                content = text_widget.get("1.0", "end-1c")
                filepath = self.files_to_edit[display_name]
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)

            messagebox.showinfo("成功", "ファイルが正常に保存されました。", parent=self)
            self.destroy()
        except Exception as e:
            messagebox.showerror("エラー", f"ファイルの保存中にエラーが発生しました: {e}", parent=self)

class FantiadlApp:
    """
    fantiadlのリストダウンロードを実行するためのGUIアプリケーション。
    """
    def __init__(self, root):
        self.root = root
        self.root.title("Fantia Downloader GUI")
        self.root.geometry("800x600")

        self.update_queue = queue.Queue()
        self.cancel_event = threading.Event()
        self.process = None
        self.download_thread = None

        # --- メインフレーム ---
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.rowconfigure(2, weight=1)
        main_frame.columnconfigure(0, weight=1)

        # --- 設定フレーム ---
        settings_frame = ttk.LabelFrame(main_frame, text="設定", padding="10")
        settings_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        settings_frame.columnconfigure(1, weight=1)

        # 対象月
        ttk.Label(settings_frame, text="対象月:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.month_var = tk.StringVar(value="current")
        self.month_entry = ttk.Entry(settings_frame, textvariable=self.month_var)
        self.month_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)
        ttk.Label(settings_frame, text="('current', 'last', or 'YYYY-MM')").grid(row=0, column=2, sticky=tk.W, padx=5)

        # 一時スキップID
        ttk.Label(settings_frame, text="一時スキップID:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.skip_ids_var = tk.StringVar()
        self.skip_ids_entry = ttk.Entry(settings_frame, textvariable=self.skip_ids_var)
        self.skip_ids_entry.grid(row=1, column=1, columnspan=2, sticky=(tk.W, tk.E), padx=5, pady=2)
        ttk.Label(settings_frame, text="(スペース区切りでIDを指定)").grid(row=2, column=1, columnspan=2, sticky=tk.W, padx=5)

        # --- 実行フレーム ---
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=1, column=0, pady=5, sticky=tk.W)

        self.start_button = ttk.Button(control_frame, text="ダウンロード開始", command=self.start_download_thread)
        self.start_button.pack(side=tk.LEFT, padx=(0, 5))

        self.edit_button = ttk.Button(control_frame, text="設定ファイル編集", command=self.open_editor_window)
        self.edit_button.pack(side=tk.LEFT)

        # --- 進捗 & ログフレーム ---
        progress_log_frame = ttk.LabelFrame(main_frame, text="進捗とログ", padding="10")
        progress_log_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        progress_log_frame.rowconfigure(2, weight=1)
        progress_log_frame.columnconfigure(0, weight=1)

        # 全体進捗バー
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            progress_log_frame, orient="horizontal", mode="determinate", variable=self.progress_var
        )
        self.progress_bar.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=5)

        # 処理中ラベル
        self.status_label = ttk.Label(progress_log_frame, text="開始待機中...")
        self.status_label.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=2)

        # ログエリア
        self.log_area = scrolledtext.ScrolledText(progress_log_frame, wrap=tk.WORD, state='disabled')
        self.log_area.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

    def _log(self, message):
        """ログエリアにメッセージを追記する"""
        self.log_area.config(state='normal')
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')

    def open_editor_window(self):
        """設定編集ウィンドウを開く。"""
        if not hasattr(self, 'editor_window') or not self.editor_window.winfo_exists():
            self.editor_window = ConfigEditorWindow(self.root)
        self.editor_window.focus() # 既に開いている場合はフォーカスを当てる

    def start_download_thread(self):
        """GUIを準備し、ダウンロード処理をバックグラウンドスレッドで開始します。"""
        self.start_button.config(text="キャンセル", command=self.cancel_download)
        self.edit_button.config(state='disabled') # 処理中は編集不可
        self.log_area.config(state='normal')
        self.log_area.delete('1.0', tk.END)
        self.log_area.config(state='disabled')
        self.progress_var.set(0)
        self.status_label.config(text="準備中...")
        self.cancel_event.clear()

        month = self.month_var.get()
        temp_skip_ids = self.skip_ids_var.get().split()

        self.download_thread = threading.Thread(
            target=self._download_worker,
            args=(month, temp_skip_ids),
            daemon=True
        )
        self.download_thread.start()
        self.root.after(100, self._process_queue)

    def cancel_download(self):
        """ダウンロード処理のキャンセルを要求します。"""
        self.status_label.config(text="キャンセル中...")
        self.cancel_event.set()
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate() # fantiadl.pyのプロセスを終了
            except Exception as e:
                self._log(f"プロセスの終了中にエラーが発生しました: {e}")
        self.start_button.config(state='disabled') # キャンセル処理中は無効化

    def _download_worker(self, month_arg, temp_skip_ids):
        """list_dl.pyのロジックを実行し、進捗をキューに送信します。"""
        try:
            load_dotenv()
            tsv_file = os.getenv('TSV_FILE', 'id_list.txt')
            default_dl_dir = os.path.join(os.path.expanduser('~'), 'Downloads')
            dl_dir = os.path.expandvars(os.getenv('DL_DIR', default_dl_dir))
            skip_file = os.getenv('SKIP_FILE', 'skip_list.txt')
            cookie_file = os.getenv('COOKIE_FILE', 'cookies.txt')
            options = os.getenv('OPTIONS', '')

            today = datetime.today()
            if month_arg == 'current':
                target_date_str = today.strftime("%Y-%m")
            elif month_arg == 'last':
                target_date_str = (today + relativedelta(months=-1)).strftime("%Y-%m")
            else:
                try:
                    datetime.strptime(month_arg, '%Y-%m')
                    target_date_str = month_arg
                except ValueError:
                    self.update_queue.put(("error", f"エラー: 月の形式が不正です。'YYYY-MM' 形式で指定してください。 (入力: {month_arg})"))
                    return

            self.update_queue.put(("log", f"対象月: {target_date_str}"))
            self.update_queue.put(("log", f"ダウンロード先: {dl_dir}"))
            self.update_queue.put(("log", f"Cookieファイル: {cookie_file}"))

            skip_ids = set()
            try:
                with open(skip_file, 'r', encoding='UTF-8') as f:
                    skip_ids = {line.strip() for line in f if line.strip()}
            except FileNotFoundError:
                self.update_queue.put(("log", f"情報: スキップリストファイル '{skip_file}' は見つかりませんでした。"))

            skip_ids.update(temp_skip_ids)

            if skip_ids:
                self.update_queue.put(("log", f"\n--- スキップ対象 ({len(skip_ids)}件) ---"))
                for skip_id in sorted(list(skip_ids)):
                    self.update_queue.put(("log", f"  - ID: {skip_id}"))
                self.update_queue.put(("log", "------------------------"))

            try:
                with open(tsv_file, 'r', encoding='UTF-8') as f:
                    reader = csv.reader(f, delimiter=',')
                    next(reader)
                    rows_to_process = [[field.strip() for field in row] for row in reader]
            except FileNotFoundError:
                self.update_queue.put(("error", f"エラー: 対象リストファイルが見つかりません: {tsv_file}"))
                return

            self.update_queue.put(("log", "\n--- ダウンロード対象 ---"))
            for row in rows_to_process:
                self.update_queue.put(("log", f"  - {row[1]} (ID: {row[0]})"))
            self.update_queue.put(("log", "------------------------\n"))

            success_count, failure_count, skipped_count = 0, 0, 0
            total_count = len(rows_to_process)

            for i, row in enumerate(rows_to_process):
                if self.cancel_event.is_set():
                    self.update_queue.put(("cancelled", "ユーザーによって処理がキャンセルされました。"))
                    return

                fan_id, name = row[0], row[1]
                self.update_queue.put(("status", f"処理中 ({i+1}/{total_count}): {name}"))

                if fan_id in skip_ids:
                    self.update_queue.put(("log", f"スキップ: {name} (ID: {fan_id}) はスキップ対象です。"))
                    skipped_count += 1
                    self.update_queue.put(("progress", ((i + 1) / total_count) * 100))
                    continue

                url = f"https://fantia.jp/fanclubs/{fan_id}"
                command = [sys.executable, '-u', 'fantiadl.py', '-q']
                if options:
                    command.extend(shlex.split(options))
                command.extend(['-c', cookie_file, '-o', dl_dir, url, '-d', target_date_str])

                try:
                    flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                    self.process = subprocess.Popen(
                        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, encoding='utf-8', errors='replace', creationflags=flags
                    )

                    if self.process.stdout:
                        for line in iter(self.process.stdout.readline, ''):
                            if self.cancel_event.is_set():
                                break # subprocessのログ読み取りを中断
                            self.update_queue.put(("log", f"[{name}] {line.strip()}"))
                    
                    self.process.wait()
                    
                    if self.cancel_event.is_set():
                        # wait()の後にもう一度チェック
                        self.update_queue.put(("cancelled", "ユーザーによって処理がキャンセルされました。"))
                        return

                    if self.process.returncode == 0:
                        success_count += 1
                    else:
                        self.update_queue.put(("log", f"エラー: {name} の処理でエラーが発生しました (リターンコード: {self.process.returncode})。\n    コマンド: {' '.join(command)}"))
                        failure_count += 1

                except FileNotFoundError:
                    self.update_queue.put(("log", f"エラー: 'fantiadl.py' が見つかりません。スクリプトと同じディレクトリに配置してください。"))
                    failure_count += 1
                    break # fantiadl.pyがない場合は続行不可能
                except Exception as e:
                    self.update_queue.put(("log", f"予期せぬエラー ({name}): {e}"))
                    failure_count += 1
                finally:
                    self.process = None

                self.update_queue.put(("progress", ((i + 1) / total_count) * 100))

            if self.cancel_event.is_set():
                return

            summary = [
                "\n\n--- 処理結果サマリー ---",
                f"  成功: {success_count}件", f"  失敗: {failure_count}件",
                f"  スキップ: {skipped_count}件", f"  合計: {total_count}件",
                "--------------------------"
            ]
            self.update_queue.put(("done", "\n".join(summary)))

        except Exception as e:
            error_info = f"ワーカーで致命的なエラーが発生しました: {e}\n{traceback.format_exc()}"
            self.update_queue.put(("error", error_info))

    def _reset_ui_state(self):
        """ボタンとステータスを初期状態に戻します。"""
        self.start_button.config(text="ダウンロード開始", command=self.start_download_thread, state='normal')
        self.edit_button.config(state='normal')
        self.progress_var.set(0)

    def _process_queue(self):
        """キューからメッセージを取得し、GUIを更新します。"""
        try:
            while True:
                message_type, value = self.update_queue.get_nowait()
                if message_type == "progress":
                    self.progress_var.set(value)
                elif message_type == "status":
                    self.status_label.config(text=value)
                elif message_type == "log":
                    self._log(value)
                elif message_type == "done":
                    self._log(value)
                    self.status_label.config(text="完了しました")
                    self._reset_ui_state()
                    messagebox.showinfo("完了", "ダウンロード処理が完了しました。", parent=self)
                    return # 処理終了
                elif message_type == "error":
                    self.status_label.config(text="エラーが発生しました")
                    self._log(value)
                    self._reset_ui_state()
                    messagebox.showerror("エラー", value.splitlines()[0])
                    return # 処理終了
                elif message_type == "cancelled":
                    self.status_label.config(text="キャンセルされました")
                    self._log(value)
                    self._reset_ui_state()
                    messagebox.showwarning("キャンセル", "処理がキャンセルされました。", parent=self)
                    return # 処理終了

        except queue.Empty:
            if self.download_thread and self.download_thread.is_alive():
                 self.root.after(100, self._process_queue)

if __name__ == "__main__":
    if sys.platform == "win32":
        from ctypes import windll
        try:
            windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError): 
            pass # Older Windows versions

    root = tk.Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use('vista')

    app = FantiadlApp(root)
    root.mainloop()