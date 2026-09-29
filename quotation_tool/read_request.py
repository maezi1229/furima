#!/usr/bin/env python3
"""客先からの見積り依頼FAX(PDF)から、品目(材質・寸法・数量)を自動読み取り、
仕入単価を手入力するための items.json の雛形を作る。

材質・寸法・数量は用紙にあらかじめ印字/タイプされている前提なのでOCR精度は
高いが、仕入単価は仕入れ先が手書きで書き込んで返してくるため、このスクリプト
では読み取らない(手書きOCRは誤読が多く実用に耐えないため)。生成される
items.json の unit_cost は null になっているので、仕入れ先からの回答(PDF画像
またはメール本文)を見ながら金額を手で入力してから fill_customer_quote.py に
渡すこと。

対応しているのは templates/ 以下にレイアウト定義がある帳票のみ。新しい客先の
FAX用紙を扱う場合は、まず新しいテンプレート定義(罫線の座標)を用意する必要が
ある。

使い方:
  python3 read_request.py --pdf 客先FAX.pdf --template templates/minami_kogyo_v1.json --out items_skeleton.json
"""

import argparse
import json
import re

import pdfplumber
import pytesseract
from pytesseract import Output

NOISE_CHARS = re.compile(r"[_\\|ー\-\s.:;,、。]")
MIN_CONFIDENCE = 50


def clean_ocr_text(raw):
    return raw.strip()


def pt_to_px(value_pt, resolution):
    return round(value_pt * resolution / 72)


def crop_cell(image, x_range_pt, y_range_pt, resolution, padding_px=5):
    x0 = pt_to_px(x_range_pt[0], resolution) + padding_px
    x1 = pt_to_px(x_range_pt[1], resolution) - padding_px
    y0 = pt_to_px(y_range_pt[0], resolution) + padding_px
    y1 = pt_to_px(y_range_pt[1], resolution) - padding_px
    return image.crop((x0, y0, x1, y1))


def ocr_cell(image, x_range_pt, y_range_pt, resolution, lang="jpn+eng"):
    """セルをOCRし、(テキスト, 最大信頼度) を返す。
    罫線のかすれ等をOCRが誤認識した「ノイズ」は信頼度が低く出る傾向があるため、
    行が実際に記入済みかどうかの判定に使う。
    """
    crop = crop_cell(image, x_range_pt, y_range_pt, resolution)
    data = pytesseract.image_to_data(crop, lang=lang, config="--psm 7", output_type=Output.DICT)
    words = [(t.strip(), c) for t, c in zip(data["text"], data["conf"]) if t.strip()]
    text = " ".join(w for w, _ in words)
    max_conf = max((c for _, c in words), default=-1)
    return text.strip(), max_conf


def is_meaningful(raw, max_conf):
    stripped = NOISE_CHARS.sub("", raw)
    return len(stripped) >= 2 and max_conf >= MIN_CONFIDENCE


def parse_qty(raw):
    digits = re.sub(r"[^0-9]", "", raw)
    return int(digits) if digits else None


def main():
    parser = argparse.ArgumentParser(description="客先FAXから品目を自動読取してitems.jsonの雛形を作る")
    parser.add_argument("--pdf", required=True, help="客先からの見積り依頼PDF")
    parser.add_argument("--template", required=True, help="帳票レイアウト定義(templates/*.json)")
    parser.add_argument("--out", required=True, help="出力するitems.jsonのパス")
    parser.add_argument("--page", type=int, default=0, help="対象ページ番号(0始まり、既定0)")
    args = parser.parse_args()

    with open(args.template, encoding="utf-8") as f:
        tpl = json.load(f)

    resolution = tpl["render_resolution"]
    cols = tpl["columns_pt"]

    with pdfplumber.open(args.pdf) as pdf:
        page = pdf.pages[args.page]
        image = page.to_image(resolution=resolution).original

    items = []
    for row_idx, row_band in enumerate(tpl["row_bands_pt"], start=1):
        material_raw, material_conf = ocr_cell(image, cols["material"], row_band, resolution)
        if not is_meaningful(material_raw, material_conf):
            continue

        dimension_raw, _ = ocr_cell(image, cols["dimension"], row_band, resolution)
        qty_raw, _ = ocr_cell(image, cols["qty"], row_band, resolution)
        qty = parse_qty(qty_raw)

        items.append(
            {
                "row": row_idx,
                "name": clean_ocr_text(material_raw),
                "spec": clean_ocr_text(dimension_raw),
                "qty": qty if qty is not None else qty_raw,
                "unit_cost": None,
                "_ocr_note": "material/dimension/qtyはOCR自動読取。誤読がないか元PDFと照合すること。unit_costは仕入れ先の回答を見て手入力する。",
            }
        )

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    print(f"{len(items)} 件の品目を検出しました: {args.out}")
    for it in items:
        print(f"  row{it['row']}: {it['name']} / {it['spec']} / 数量{it['qty']}")
    print("unit_cost (仕入単価) を手入力してから fill_customer_quote.py を実行してください。")


if __name__ == "__main__":
    main()
