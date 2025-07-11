#!/usr/bin/env python
# -*- coding: utf-8 -*-
import csv
import subprocess
from datetime import datetime
import os
import sys
from dotenv import load_dotenv
import argparse
from dateutil.relativedelta import relativedelta

# .envファイルから環境変数を読み込む
load_dotenv()

# 環境変数から設定を読み込む (見つからない場合はデフォルト値を使用)
tsv_file = os.getenv('TSV_FILE', 'id_list.txt')
# os.path.expanduser('~') を使ってホームディレクトリを取得し、Downloadsを追加する
default_dl_dir = os.path.join(os.path.expanduser('~'), 'Downloads')
dl_dir = os.path.expandvars(os.getenv('DL_DIR', default_dl_dir))
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

try:
    with open(tsv_file, 'r', encoding='UTF-8') as f:
        reader = csv.reader(f, delimiter='\t')
        next(reader)  # ヘッダー行をスキップ
        for row in reader:
            fan_id, name = row[0], row[1]

            print(f"id= {fan_id} {name}")
            url = f"https://fantia.jp/fanclubs/{fan_id}"
            command = f"python fantiadl.py {options} -c {cookie_file} -o \"{dl_dir}\" {url} -d {target_date_str}"
            print(command)
            try:
                subprocess.run(command, shell=True, check=True)
            except subprocess.CalledProcessError as e:
                print(f"エラー: id= {fan_id} のダウンロード中にエラーが発生しました。スキップします。(エラーコード: {e.returncode})", file=sys.stderr)
                continue
except FileNotFoundError:
    print(f"エラー: TSVファイルが見つかりません: {tsv_file}")
except Exception as e:
    print(f"エラーが発生しました: {e}")