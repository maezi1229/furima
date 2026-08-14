#!/usr/bin/env python3
"""客先向け見積書PDFを、仕入れ先の価格から自動計算して作成するツール。

想定する業務フロー:
  1. 客先からPDF(またはFAX)で見積依頼が来る
  2. 仕入れ先に転送し、仕入単価入りの回答(PDFへの手書き書き込み・メール等)を受け取る
  3. 仕入単価に対して一定の掛け率(既定10%)を上乗せし、100円未満を切り捨てる
  4. 品目ごとの単価・数量・金額をまとめ、客先に提出する見積書PDFを作成する

このツールは上記の 3, 4 を自動化する。品目データ(品名・数量・仕入単価)は
items.json として用意する。手書きFAXやメール本文などOCRで読み取れない
入力は、目視で items.json に書き写す想定(digital PDFの場合は
extract_pdf_text.py でテキスト/表を抜き出して転記を楽にできる)。

使い方:
  python3 generate_quote.py --items items.json --customer customer.json --output quote.pdf

  # 内容確認をスキップして即出力する場合
  python3 generate_quote.py --items items.json --customer customer.json --output quote.pdf --yes

items.json の書式 (配列):
  [
    {"name": "○○ 新品", "spec": "型番XXX", "qty": 2, "unit_cost": 15000},
    {"name": "△△", "spec": "", "qty": 1, "unit_cost": 8300}
  ]
  - name: 品名
  - spec: 規格/型番(省略可、空文字でよい)
  - qty: 数量
  - unit_cost: 仕入単価(仕入れ先からの回答額)

customer.json の書式:
  {
    "customer_name": "株式会社○○ 御中",
    "subject": "○○一式",
    "quote_no": "2026-0001",
    "note": "納期についてはご相談ください。"
  }
  - customer_name, subject 以外は省略可
"""

import argparse
import json
import math
import sys
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FONT_BOLD = "HeiseiKakuGo-W5"
FONT_REGULAR = "HeiseiMin-W3"
pdfmetrics.registerFont(UnicodeCIDFont(FONT_BOLD))
pdfmetrics.registerFont(UnicodeCIDFont(FONT_REGULAR))

DEFAULT_MARKUP = 0.10
DEFAULT_ROUND_UNIT = 100


def round_down(value, unit):
    if unit <= 0:
        return value
    return math.floor(value / unit) * unit


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def compute_items(items, markup, round_unit):
    computed = []
    for it in items:
        qty = it["qty"]
        unit_cost = it["unit_cost"]
        unit_price = round_down(unit_cost * (1 + markup), round_unit)
        amount = unit_price * qty
        computed.append(
            {
                "name": it.get("name", ""),
                "spec": it.get("spec", ""),
                "qty": qty,
                "unit_cost": unit_cost,
                "unit_price": unit_price,
                "amount": amount,
            }
        )
    return computed


def print_preview(computed, customer, tax_rate):
    subtotal = sum(c["amount"] for c in computed)
    tax = round_down(subtotal * tax_rate, 1) if tax_rate else 0
    total = subtotal + tax

    print("=" * 72)
    print(f"客先: {customer.get('customer_name', '')}")
    print(f"件名: {customer.get('subject', '')}")
    print("-" * 72)
    header = f"{'品名':<22}{'規格':<12}{'数量':>5}{'仕入単価':>11}{'提出単価':>11}{'金額':>11}"
    print(header)
    for c in computed:
        print(
            f"{c['name'][:22]:<22}{c['spec'][:12]:<12}{c['qty']:>5}"
            f"{c['unit_cost']:>11,}{c['unit_price']:>11,}{c['amount']:>11,}"
        )
    print("-" * 72)
    print(f"小計: {subtotal:,} 円")
    if tax_rate:
        print(f"消費税({tax_rate * 100:.0f}%): {tax:,.0f} 円")
    print(f"合計: {total:,.0f} 円")
    print("=" * 72)
    return subtotal, tax, total


def confirm(prompt="この内容で見積書PDFを出力しますか? [y/N]: "):
    ans = input(prompt).strip().lower()
    return ans in ("y", "yes")


def build_pdf(computed, customer, output_path, subtotal, tax, total, tax_rate, markup):
    styles = {
        "title": ParagraphStyle("title", fontName=FONT_BOLD, fontSize=18, alignment=1, spaceAfter=6 * mm),
        "normal": ParagraphStyle("normal", fontName=FONT_REGULAR, fontSize=10, leading=14),
        "small": ParagraphStyle("small", fontName=FONT_REGULAR, fontSize=8, leading=11),
        "total": ParagraphStyle("total", fontName=FONT_BOLD, fontSize=13),
    }

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
    )

    story = []
    story.append(Paragraph("御見積書", styles["title"]))

    today = date.today().strftime("%Y年%m月%d日")
    meta_lines = [f"発行日: {today}"]
    if customer.get("quote_no"):
        meta_lines.append(f"見積番号: {customer['quote_no']}")
    story.append(Paragraph("　".join(meta_lines), styles["small"]))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph(customer.get("customer_name", ""), styles["normal"]))
    if customer.get("subject"):
        story.append(Paragraph(f"件名: {customer['subject']}", styles["normal"]))
    story.append(Spacer(1, 6 * mm))

    table_data = [["品名", "規格", "数量", "単価", "金額"]]
    for c in computed:
        table_data.append(
            [c["name"], c["spec"], str(c["qty"]), f"¥{c['unit_price']:,}", f"¥{c['amount']:,}"]
        )

    subtotal_row_index = len(table_data)
    table_data.append(["", "", "", "小計", f"¥{subtotal:,}"])
    if tax_rate:
        table_data.append(["", "", "", f"消費税({tax_rate * 100:.0f}%)", f"¥{tax:,.0f}"])
    total_row_index = len(table_data)
    table_data.append(["", "", "", "合計", f"¥{total:,.0f}"])

    col_widths = [70 * mm, 30 * mm, 15 * mm, 25 * mm, 30 * mm]
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    style = [
        ("FONTNAME", (0, 0), (-1, -1), FONT_REGULAR),
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e8e8")),
        ("GRID", (0, 0), (-1, subtotal_row_index - 1), 0.5, colors.grey),
        ("ALIGN", (2, 0), (2, -1), "CENTER"),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (3, total_row_index), (-1, total_row_index), FONT_BOLD),
        ("LINEABOVE", (3, subtotal_row_index), (-1, subtotal_row_index), 0.5, colors.grey),
        ("LINEABOVE", (3, total_row_index), (-1, total_row_index), 1, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    table.setStyle(TableStyle(style))
    story.append(table)
    story.append(Spacer(1, 8 * mm))

    if customer.get("note"):
        story.append(Paragraph(customer["note"], styles["small"]))

    doc.build(story)


def main():
    parser = argparse.ArgumentParser(description="仕入単価から客先向け見積書PDFを作成する")
    parser.add_argument("--items", required=True, help="品目データ(JSON)へのパス")
    parser.add_argument("--customer", required=True, help="客先情報(JSON)へのパス")
    parser.add_argument("--output", required=True, help="出力するPDFのパス")
    parser.add_argument("--markup", type=float, default=DEFAULT_MARKUP, help="上乗せ率(既定 0.10 = 10%%)")
    parser.add_argument("--round-unit", type=int, default=DEFAULT_ROUND_UNIT, help="切り捨て単位(既定 100円)")
    parser.add_argument("--tax-rate", type=float, default=0.0, help="消費税率。既定は0(税抜のみ表示)")
    parser.add_argument("--yes", action="store_true", help="確認プロンプトをスキップして出力する")
    args = parser.parse_args()

    items = load_json(args.items)
    customer = load_json(args.customer)

    computed = compute_items(items, args.markup, args.round_unit)
    subtotal, tax, total = print_preview(computed, customer, args.tax_rate)

    if not args.yes:
        if not confirm():
            print("出力を中止しました。")
            sys.exit(0)

    output_path = Path(args.output)
    build_pdf(computed, customer, output_path, subtotal, tax, total, args.tax_rate, args.markup)
    print(f"見積書PDFを出力しました: {output_path.resolve()}")


if __name__ == "__main__":
    main()
