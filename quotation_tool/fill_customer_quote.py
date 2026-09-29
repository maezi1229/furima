#!/usr/bin/env python3
"""items.json(仕入単価入り)から提出単価・金額を計算し、客先からの見積り依頼
FAXと同じ用紙レイアウトに単価・金額を書き込んだ回答PDFを作成する。

これまで手作業で「客先の元FAXに単価・数量・合計金額を手書きして返送」して
いた工程を自動化するもの。仕入単価(unit_cost)は read_request.py が作った
items.json 雛形に手入力しておくこと(手書きの仕入回答をOCRするのは精度が
低いため非対応)。

処理:
  1. 仕入単価に対して上乗せ率(既定10%)を掛け、100円単位で繰り上げて提出単価とする
  2. 提出単価 × 数量 で金額を算出する
  3. 計算結果をプレビュー表示し、確認を求める
  4. 確認後、客先FAXの単価欄・金額欄に値を書き込み、あわせて宛先(会社名・宛名)を
     依頼元(客先)宛てに書き換えたPDFを出力する。客先の手書き備考(納期質問等)は
     元のFAX画像をそのまま使うため、書き換え対象外の場所であれば自動的に残る。

使い方:
  python3 fill_customer_quote.py \
    --pdf 客先FAX.pdf --template templates/minami_kogyo_v1.json \
    --items items.json --output 回答.pdf
"""

import argparse
import io
import json
import sys
import tempfile
from decimal import ROUND_CEILING, Decimal

import pdfplumber
import pypdf
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

FONT_NAME = "HeiseiKakuGo-W5"
pdfmetrics.registerFont(UnicodeCIDFont(FONT_NAME))

DEFAULT_MARKUP = 0.10
DEFAULT_ROUND_UNIT = 100


def normalize_rotation(pdf_path):
    """スキャンされたFAXの中には、ページの実体は横向きのまま /Rotate で縦表示
    しているものがある。pdfplumberが返す width/height は表示上の(回転後の)
    寸法だが、reportlabのオーバーレイやpypdfのmerge_pageはページ本来の
    (回転前の)座標系で扱うため、/Rotateがあると単価・備考の書き込み位置が
    ずれたり回転して表示されるバグになる。/Rotateが立っているページは
    transfer_rotation_to_content() で回転をコンテンツ自体に焼き込み、
    以降はどのページも /Rotate=0 の状態で統一して扱えるようにする。
    """
    reader = pypdf.PdfReader(pdf_path)
    if all(page.rotation == 0 for page in reader.pages):
        return pdf_path

    writer = pypdf.PdfWriter()
    for page in reader.pages:
        if page.rotation != 0:
            page.transfer_rotation_to_content()
        writer.add_page(page)

    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    writer.write(tmp.name)
    return tmp.name


def compute_unit_price(unit_cost, markup, round_unit):
    """仕入単価に上乗せ率を掛け、round_unit単位で繰り上げる。
    浮動小数点誤差(例: 42000*1.1が46200.00000000001になる)で正しい金額の
    ちょうど倍数が誤って一段階切り上がらないよう、Decimalで厳密に計算する。
    """
    d_cost = Decimal(str(unit_cost))
    d_markup = Decimal(str(markup))
    d_unit = Decimal(str(round_unit))
    marked_up = d_cost * (Decimal(1) + d_markup)
    rounded = (marked_up / d_unit).to_integral_value(rounding=ROUND_CEILING) * d_unit
    return int(rounded)


def compute_items(items, markup, round_unit):
    """unit_costは単一の数値、または材質別の複数単価(例: 国内材/ポスコ材)を
    表す {ラベル: 仕入単価} の辞書のどちらでもよい。辞書の場合は提出単価・
    金額もラベルごとの辞書になる。
    """
    computed = []
    for it in items:
        if it.get("unit_cost") is None:
            raise ValueError(f"row{it.get('row')} ({it.get('name')}) の unit_cost が未入力です")
        qty = it["qty"]
        unit_cost = it["unit_cost"]
        if isinstance(unit_cost, dict):
            unit_price = {label: compute_unit_price(cost, markup, round_unit) for label, cost in unit_cost.items()}
            amount = {label: price * qty for label, price in unit_price.items()}
        else:
            unit_price = compute_unit_price(unit_cost, markup, round_unit)
            amount = unit_price * qty
        computed.append({**it, "unit_price": unit_price, "amount": amount})
    return computed


def print_preview(computed, reply_to_lines, notes, reply_notes):
    scalar_amounts = [c["amount"] for c in computed if not isinstance(c["amount"], dict)]
    subtotal = sum(scalar_amounts)
    has_dict_items = any(isinstance(c["amount"], dict) for c in computed)
    print("=" * 72)
    print("宛先を次の内容に書き換えます:")
    for line in reply_to_lines:
        print(f"  {line}")
    if notes:
        print("材質欄付近の備考として次を記載します:")
        for note in notes:
            print(f"  {note}")
    if reply_notes:
        print("文末に回答コメントとして次を記載します:")
        for note in reply_notes:
            print(f"  {note}")
    print("-" * 72)
    print(f"{'行':<5}{'品名':<14}{'規格':<16}{'数量':>5}{'仕入単価':>11}{'提出単価':>11}{'金額':>11}")
    for c in computed:
        if isinstance(c["unit_cost"], dict):
            print(f"row{c['row']:<2}{c['name'][:14]:<14}{c['spec'][:16]:<16}{c['qty']:>5}")
            for label, cost in c["unit_cost"].items():
                price = c["unit_price"][label]
                amt = c["amount"][label]
                print(f"    - {label:<10}{'':<16}{'':<5}{cost:>11,}{price:>11,}{amt:>11,}")
        else:
            print(
                f"row{c['row']:<2}{c['name'][:14]:<14}{c['spec'][:16]:<16}{c['qty']:>5}"
                f"{c['unit_cost']:>11,}{c['unit_price']:>11,}{c['amount']:>11,}"
            )
    print("-" * 72)
    if has_dict_items:
        print(f"合計(単一単価の行のみ): {subtotal:,} 円 ※材質別単価の行は客先が選ぶため合計に含めていません")
    else:
        print(f"合計: {subtotal:,} 円")
    print("=" * 72)
    return subtotal


def confirm(prompt="この内容で回答PDFに書き込みますか? [y/N]: "):
    ans = input(prompt).strip().lower()
    return ans in ("y", "yes")


def draw_note_block(c, area, texts, page_height, fontsize=11):
    if not texts or not area:
        return
    x0, y0_top, x1, y1_bottom = area
    c.setFillColorRGB(0, 0, 0)
    c.setFont(FONT_NAME, fontsize)
    line_gap = (y1_bottom - y0_top) / max(len(texts), 1)
    for i, text in enumerate(texts):
        baseline_from_top = y0_top + line_gap * (i + 1) - line_gap * 0.25
        c.drawString(x0, page_height - baseline_from_top, text)


def build_overlay(computed, tpl, page_width, page_height, reply_to_lines, notes, reply_notes, row_notes, x_offset=0.0, y_offset=0.0):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_width, page_height))
    if x_offset or y_offset:
        # 同じ客先・同じ帳票でも、FAX送信のたびに用紙が数ポイント単位で
        # ずれて読み込まれることがある(テンプレート較正時の基準とのズレ)。
        # 一つずつ座標を補正する代わりに、キャンバス全体を平行移動して
        # まとめて補正する。
        c.translate(x_offset, y_offset)

    redact = tpl.get("header_redact_pt")
    if redact:
        x0, y0_top, x1, y1_bottom = redact
        rect_y = page_height - y1_bottom
        rect_h = y1_bottom - y0_top
        c.setFillColorRGB(1, 1, 1)
        c.rect(x0, rect_y, x1 - x0, rect_h, fill=1, stroke=0)

        c.setFillColorRGB(0, 0, 0)
        c.setFont(FONT_NAME, 15)
        line_gap = rect_h / max(len(reply_to_lines), 1)
        for i, line in enumerate(reply_to_lines):
            baseline_from_top = y0_top + line_gap * (i + 1) - line_gap * 0.35
            c.drawString(x0 + 6, page_height - baseline_from_top, line)

    draw_note_block(c, tpl.get("note_area_pt"), notes, page_height, fontsize=11)
    draw_note_block(c, tpl.get("reply_note_area_pt"), reply_notes, page_height, fontsize=11)

    cols = tpl["columns_pt"]
    padding = 4

    if row_notes:
        row_note_x0 = cols["material"][0]
        row_note_x1 = cols["dimension"][1]
        c.setFillColorRGB(0, 0, 0)
        c.setFont(FONT_NAME, 8)
        for row_num, text in row_notes.items():
            row_top, row_bottom = tpl["row_bands_pt"][row_num - 1]
            y_center = page_height - (row_top + row_bottom) / 2 - 3
            c.drawString(row_note_x0 + 2, y_center, text)

    for item in computed:
        row_band = tpl["row_bands_pt"][item["row"] - 1]
        row_top, row_bottom = row_band
        row_height = row_bottom - row_top
        unit_price_x = cols["unit_price"][1] - padding

        # 客先/仕入先が単価欄に既に手書きの数字(仕入原価の合計等)を書き込んで
        # いる場合、隣接列(金額列や備考欄)にまではみ出ていることがあるため、
        # 単価欄より右側の列も含めて白塗りしてから新しい単価を書く
        # (でないと仕入原価が客先に見えてしまう/数字が重なって読めなくなる)。
        c.setFillColorRGB(1, 1, 1)
        wipe_x0 = cols["unit_price"][0]
        wipe_x1 = max(x1 for x0, x1 in cols.values() if x0 >= cols["unit_price"][0])
        wipe_top = row_top - row_height * 0.15
        wipe_bottom = row_bottom + row_height * 0.85
        c.rect(
            wipe_x0,
            page_height - wipe_bottom,
            wipe_x1 - wipe_x0,
            wipe_bottom - wipe_top,
            fill=1,
            stroke=0,
        )
        c.setFillColorRGB(0, 0, 0)

        if isinstance(item["unit_price"], dict):
            labels = list(item["unit_price"].keys())
            c.setFont(FONT_NAME, 7.5)
            line_gap = (row_bottom - row_top) / max(len(labels), 1)
            for i, label in enumerate(labels):
                price = item["unit_price"][label]
                baseline_from_top = row_top + line_gap * (i + 1) - line_gap * 0.3
                c.drawRightString(unit_price_x, page_height - baseline_from_top, f"{label}@{price:,}")
        else:
            c.setFont(FONT_NAME, 10)
            y_center = page_height - (row_top + row_bottom) / 2 - 3.5
            c.drawRightString(unit_price_x, y_center, f"@{item['unit_price']:,}")

        if "amount" in cols and not isinstance(item["amount"], dict):
            y_center = page_height - (row_top + row_bottom) / 2 - 3.5
            amount_x = cols["amount"][1] - padding
            c.drawRightString(amount_x, y_center, f"¥{item['amount']:,}")

    c.save()
    buf.seek(0)
    return buf


def main():
    parser = argparse.ArgumentParser(description="客先FAXに単価・金額を書き込んだ回答PDFを作る")
    parser.add_argument("--pdf", required=True, help="客先からの見積り依頼PDF(書き込み先の元帳票)")
    parser.add_argument("--template", required=True, help="帳票レイアウト定義(templates/*.json)")
    parser.add_argument("--items", required=True, help="仕入単価入りのitems.json(read_request.py出力+手入力)")
    parser.add_argument("--output", required=True, help="出力する回答PDFのパス")
    parser.add_argument("--markup", type=float, default=DEFAULT_MARKUP, help="上乗せ率(既定0.10=10%%)")
    parser.add_argument("--round-unit", type=int, default=DEFAULT_ROUND_UNIT, help="繰り上げ単位(既定100円)")
    parser.add_argument("--page", type=int, default=0, help="書き込み対象ページ番号(0始まり、既定0)")
    parser.add_argument("--reply-to", action="append", help="宛先の書き換え文言(1行ずつ指定、複数回指定可)。省略時はテンプレート定義を使用")
    parser.add_argument("--note", action="append", help="材質欄付近(タイトル直下)に書き加える備考(1行ずつ指定、複数回指定可)")
    parser.add_argument("--reply-note", action="append", help="文末に書き加える回答コメント(納期回答等、1行ずつ指定、複数回指定可)")
    parser.add_argument(
        "--row-note",
        action="append",
        help="表内の特定の行(材質・寸法欄)に書き加える備考。'行番号:テキスト' の形式で指定(複数回指定可)。例: --row-note '10:別途 運賃:混載便4,500円 または チャーター便47,000円'",
    )
    parser.add_argument("--yes", action="store_true", help="確認プロンプトをスキップする")
    parser.add_argument(
        "--x-offset",
        type=float,
        default=0.0,
        help="書き込み位置全体の水平補正(pt、既定0)。同じ客先・同じ様式でも送信ごとに用紙が数pt単位でずれて"
        "読み込まれることがあるため、生成結果を見てずれていたら調整する",
    )
    parser.add_argument("--y-offset", type=float, default=0.0, help="書き込み位置全体の垂直補正(pt、既定0)")
    args = parser.parse_args()

    with open(args.template, encoding="utf-8") as f:
        tpl = json.load(f)
    with open(args.items, encoding="utf-8") as f:
        items = json.load(f)

    pdf_path = normalize_rotation(args.pdf)

    reply_to_lines = args.reply_to if args.reply_to else tpl.get("reply_to_lines", [])
    notes = args.note or []
    reply_notes = args.reply_note or []

    row_notes = {}
    for entry in args.row_note or []:
        row_str, _, text = entry.partition(":")
        row_notes[int(row_str)] = text

    try:
        computed = compute_items(items, args.markup, args.round_unit)
    except ValueError as e:
        print(f"エラー: {e}")
        sys.exit(1)

    print_preview(computed, reply_to_lines, notes, reply_notes)
    if row_notes:
        print("表内の特定行に次を記載します:")
        for row_num, text in sorted(row_notes.items()):
            print(f"  row{row_num}: {text}")
        print("=" * 72)

    if not args.yes and not confirm():
        print("出力を中止しました。")
        sys.exit(0)

    with pdfplumber.open(pdf_path) as plumber_pdf:
        page = plumber_pdf.pages[args.page]
        page_width, page_height = page.width, page.height

    overlay_buf = build_overlay(
        computed, tpl, page_width, page_height, reply_to_lines, notes, reply_notes, row_notes,
        x_offset=args.x_offset, y_offset=args.y_offset,
    )
    overlay_reader = pypdf.PdfReader(overlay_buf)

    reader = pypdf.PdfReader(pdf_path)
    writer = pypdf.PdfWriter()
    for i, page in enumerate(reader.pages):
        if i == args.page:
            page.merge_page(overlay_reader.pages[0])
        writer.add_page(page)

    with open(args.output, "wb") as f:
        writer.write(f)

    print(f"回答PDFを出力しました: {args.output}")


if __name__ == "__main__":
    main()
