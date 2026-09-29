#!/usr/bin/env python3
"""仕入れ先/客先から届いたPDFの中身を確認するための補助スクリプト。

digital PDF(選択可能なテキストを含むPDF)であれば、ページごとの
テキストと、表として認識できる部分を表示する。手書きスキャンのFAXなど
文字を含まない(=画像だけの)PDFの場合は、ページを画像化してOCR
(Tesseract, 日本語+英語)を実行し、読み取れた文字を表示する。

OCRは手書き文字の完全な読み取りを保証するものではない。誤読の可能性が
あるため、OCR結果は必ず元のPDFと見比べたうえで items.json に転記する
こと(generate_quote.py 側でも最終確認プロンプトがあるため、誤りは
そこでも気づける)。

使い方:
  python3 extract_pdf_text.py 見積回答.pdf
  python3 extract_pdf_text.py 見積回答.pdf --ocr        # 文字層があってもOCRも実行する
  python3 extract_pdf_text.py 見積回答.pdf --lang eng   # OCR言語を変更(既定 jpn+eng)
  python3 extract_pdf_text.py 見積回答.pdf --resolution 400  # OCR画質を変更(既定 300)
"""

import argparse

import pdfplumber
import pytesseract


def ocr_page(page, lang, resolution):
    image = page.to_image(resolution=resolution).original
    return pytesseract.image_to_string(image, lang=lang)


def main():
    parser = argparse.ArgumentParser(description="PDFのテキスト/表を確認する(必要ならOCRも行う)")
    parser.add_argument("pdf", help="確認するPDFファイル")
    parser.add_argument("--ocr", action="store_true", help="文字層があってもOCRを強制実行する")
    parser.add_argument("--lang", default="jpn+eng", help="OCR言語(既定 jpn+eng)")
    parser.add_argument("--resolution", type=int, default=300, help="OCR時の画像解像度(既定 300)")
    args = parser.parse_args()

    with pdfplumber.open(args.pdf) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            print(f"\n===== ページ {i} =====")
            text = page.extract_text()

            if text:
                print("--- テキスト(PDF内の文字層) ---")
                print(text)
            else:
                print("(文字層なし。手書き/スキャンの可能性があります)")

            tables = page.extract_tables()
            if tables:
                print("--- 表として抽出された内容 ---")
                for t_idx, table in enumerate(tables, start=1):
                    print(f"[表 {t_idx}]")
                    for row in table:
                        print(row)

            if not text or args.ocr:
                print(f"--- OCR結果(lang={args.lang}, 誤読の可能性あり。原本と要照合) ---")
                ocr_text = ocr_page(page, args.lang, args.resolution)
                print(ocr_text.strip() if ocr_text.strip() else "(OCRでも文字を検出できませんでした)")


if __name__ == "__main__":
    main()
