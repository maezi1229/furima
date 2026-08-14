#!/usr/bin/env python3
"""仕入れ先/客先から届いたPDFの中身を確認するための補助スクリプト。

digital PDF(選択可能なテキストを含むPDF)であれば、ページごとの
テキストと、表として認識できる部分を表示する。手書きスキャンのFAXなど
文字を含まないPDFの場合は「テキストなし」と表示されるので、その場合は
中身を目視で items.json に書き写す。

使い方:
  python3 extract_pdf_text.py 見積回答.pdf
"""

import sys

import pdfplumber


def main():
    if len(sys.argv) != 2:
        print("使い方: python3 extract_pdf_text.py <PDFファイル>")
        sys.exit(1)

    path = sys.argv[1]
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            print(f"\n===== ページ {i} =====")
            text = page.extract_text()
            if text:
                print("--- テキスト ---")
                print(text)
            else:
                print("(テキストなし。手書き/スキャンの可能性があります。目視で確認してください)")

            tables = page.extract_tables()
            if tables:
                print("--- 表として抽出された内容 ---")
                for t_idx, table in enumerate(tables, start=1):
                    print(f"[表 {t_idx}]")
                    for row in table:
                        print(row)


if __name__ == "__main__":
    main()
