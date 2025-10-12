#!/usr/bin/env python
# -*- coding: utf-8 -*-
import csv
from datetime import datetime
import os
import io
import sys
from dotenv import load_dotenv # type: ignore
import argparse
from tqdm import tqdm # type: ignore
from dateutil.relativedelta import relativedelta # type: ignore

from models import FantiaDownloader, FantiaClub

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# .envファイルから環境変数を読み込む
load_dotenv()

# 環境変数から設定を読み込む (見つからない場合はデフォルト値を使用)
tsv_file = os.getenv('TSV_FILE', 'id_list.txt')
# os.path.expanduser('~') を使ってホームディレクトリを取得し、Downloadsを追加する
default_dl_dir = os.path.join(os.path.expanduser('~'), 'Downloads')
dl_dir = os.path.expandvars(os.getenv('DL_DIR', default_dl_dir))
skip_file = os.getenv('SKIP_FILE', 'skip_list.txt')
cookie_file = os.getenv('COOKIE_FILE', 'cookies.txt')
options = os.getenv('OPTIONS', '')

# コマンドライン引数の設定
parser = argparse.ArgumentParser(description='Fantiaのファンクラブから指定した月の投稿をダウンロードします。')
parser.add_argument(
    '--month',
    type=str,
    default='current',
    help="ダウンロード対象月を指定します。'current' (今月・デフォルト), 'last' (先月), または 'YYYY-MM' 形式で指定します。"
)
parser.add_argument(
    '--skip',
    nargs='+',
    metavar='ID',
    default=[],
    help='一時的にスキップするファンクラブIDをスペース区切りで指定します。'
)
args = parser.parse_args()

# 引数に基づいて対象月を決定
today = datetime.today()
if args.month == 'current':
    target_date_str = today.strftime("%Y-%m")
elif args.month == 'last':
    target_date_str = (today + relativedelta(months=-1)).strftime("%Y-%m")
else:
    try:
        # YYYY-MM形式の妥当性チェック
        datetime.strptime(args.month, '%Y-%m')
        target_date_str = args.month
    except ValueError:
        print(f"エラー: 月の形式が不正です。'YYYY-MM' 形式で指定してください。 (入力: {args.month})", file=sys.stderr)
        sys.exit(1)

print(f"対象月: {target_date_str}")

# スキップリストを読み込む
try:
    skip_ids = set()
    with open(skip_file, 'r', encoding='UTF-8') as f:
        # ファイルからIDを読み込み、前後の空白を削除してセットに追加
        skip_ids = {line.strip() for line in f if line.strip()}
except FileNotFoundError:
    # --skipが指定されている場合はこのメッセージは不要なので、後で判定する
    if not args.skip:
        print(f"\n情報: スキップリストファイル '{skip_file}' は見つかりませんでした。スキップ処理は行われません。")

# コマンドラインからのスキップIDを追加
skip_ids.update(args.skip) # type: ignore

# スキップ対象の表示 (IDが1つ以上ある場合のみ)
if skip_ids: # type: ignore
    print(f"\n--- スキップ対象 ({len(skip_ids)}件) ---")
    for skip_id in sorted(list(skip_ids)):
        print(f"  - ID: {skip_id}")
    print("------------------------")

try:
    with open(tsv_file, 'r', encoding='UTF-8') as f:
        reader = csv.reader(f, delimiter=',')
        next(reader)  # ヘッダー行をスキップ
        # 各フィールドから前後の空白（タブを含む）を削除してリストに読み込む
        rows_to_process = [[field.strip() for field in row] for row in reader]
    # ダウンロード処理の前にリストの内容を表示
    print("\n--- ダウンロード対象 ---")
    for row in rows_to_process:
        print(f"  - {row[1]} (ID: {row[0]})")
    print("------------------------\n")

    # 実行確認
    confirm = input("ダウンロードを開始しますか？ (y/N): ").lower()
    if confirm not in ['y', 'yes']:
        print("処理を中断しました。")
        sys.exit(0)

    # カウンターを初期化
    success_count = 0
    failure_count = 0
    skipped_count = 0

    downloader = FantiaDownloader(
        session_arg=cookie_file,
        directory=dl_dir,
        month_limit=target_date_str,
        quiet=False,
        continue_on_error=True # Always continue on error in list mode
    )

    # tqdmを使用してリスト全体の進捗をグラフィカルに表示
    with tqdm(rows_to_process, unit="件", desc="ファンクラブ") as pbar:
        for row in pbar:
            fan_id, name = row[0], row[1]
            pbar.set_description(f"処理中: {name}")

            # スキップリストに含まれているかチェック
            if fan_id in skip_ids: # type: ignore
                tqdm.write(f"スキップ: {name} (ID: {fan_id}) はスキップ対象のため処理をスキップします。")
                skipped_count += 1
                continue

            try:
                fanclub = FantiaClub(fan_id)
                downloader.download_fanclub(fanclub)
                success_count += 1
            except Exception as e:
                tqdm.write(f"\nエラー: {name} (id={fan_id}) のダウンロード中にエラーが発生しました。")
                tqdm.write(f"--- stderr ---\n{e}\n--------------")
                failure_count += 1
                continue

    # 処理完了後にサマリーを表示
    print("\n\n--- 処理結果サマリー ---")
    print(f"  成功: {success_count}件")
    print(f"  失敗: {failure_count}件")
    print(f"  スキップ: {skipped_count}件")
    print(f"  合計: {len(rows_to_process)}件")
    print("--------------------------")

except FileNotFoundError:
    print(f"エラー: TSVファイルが見つかりません: {tsv_file}")
except Exception as e:
    print(f"エラーが発生しました: {e}")