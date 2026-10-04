"""Monta o relatório em PDF a partir dos MESMOS dados que a Análise
Personalizada e o chatbot usam (assistant/query_engine.py, via
assistant/deep_analytics.py) - os números do PDF batem exatamente com os do
dashboard para o mesmo período.

reportlab foi escolhido por não ter dependências nativas problemáticas no
Windows (ao contrário do WeasyPrint, que precisa de GTK/Cairo/Pango).
"""

import tempfile
from datetime import datetime
from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    NextPageTemplate,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from . import charts
from assistant.deep_analytics import compute_deep
from config.config import BR_TIMEZONE

ASSETS_DIR = Path(__file__).resolve().parent / "assets"

NAVY = colors.HexColor("#010133")
CARD = colors.HexColor("#08091d")
CARD2 = colors.HexColor("#10134a")
ACCENT = colors.HexColor("#4eaff7")
GREEN = colors.HexColor("#59d4a6")
AMBER = colors.HexColor("#f0b74a")
RED = colors.HexColor("#ff6b73")
TEXT = colors.HexColor("#0d1b33")
MUTED = colors.HexColor("#5b7391")
LINE = colors.HexColor("#d7e9fa")
SURFACE = colors.HexColor("#f3f8ff")

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
CONTENT_W = PAGE_W - 2 * MARGIN
HEADER_H = 40 * mm
STRIP_H = 13 * mm


def _styles():
    return {
        "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=13, leading=17, textColor=NAVY, spaceBefore=6, spaceAfter=6),
        "over": ParagraphStyle("over", fontName="Helvetica-Bold", fontSize=7, leading=9, textColor=ACCENT, spaceAfter=1),
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, leading=14.5, textColor=TEXT, alignment=TA_LEFT),
        "bullet": ParagraphStyle("bullet", fontName="Helvetica", fontSize=9.5, leading=14, textColor=TEXT, leftIndent=11, bulletIndent=0),
        "muted": ParagraphStyle("muted", fontName="Helvetica", fontSize=8, leading=11.5, textColor=MUTED),
        "kpi_value": ParagraphStyle("kv", fontName="Helvetica-Bold", fontSize=19, leading=22, textColor=ACCENT),
        "kpi_label": ParagraphStyle("kl", fontName="Helvetica-Bold", fontSize=6.5, leading=9, textColor=colors.HexColor("#a7cbed")),
        "kpi_note": ParagraphStyle("kn", fontName="Helvetica", fontSize=7.5, leading=10, textColor=colors.HexColor("#e8f4ff")),
        "th": ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=colors.white),
        "td": ParagraphStyle("td", fontName="Helvetica", fontSize=8.5, leading=11, textColor=TEXT),
    }


def _period_label(filters):
    if filters.date_from == filters.date_to:
        return filters.date_from.strftime("%d/%m/%Y")
    return f"{filters.date_from.strftime('%d/%m/%Y')} a {filters.date_to.strftime('%d/%m/%Y')}"


def _br(iso, fmt="%d/%m/%Y %H:%M"):
    try:
        return datetime.fromisoformat(iso).astimezone(BR_TIMEZONE).strftime(fmt)
    except (TypeError, ValueError):
        return "-"


def _img(path, width):
    with PILImage.open(path) as image:
        w, h = image.size
    return Image(str(path), width=width, height=width * h / w)


def _asset(name):
    return ASSETS_DIR / name


def _on_first_page(filters, generated_at):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, PAGE_H - HEADER_H, PAGE_W, HEADER_H, stroke=0, fill=1)
        canvas.setFillColor(ACCENT)
        canvas.rect(0, PAGE_H - HEADER_H, PAGE_W, 1.2 * mm, stroke=0, fill=1)

        wordmark = _asset("via-letreiro-claro.png")
        if wordmark.exists():
            canvas.drawImage(str(wordmark), MARGIN, PAGE_H - 7 * mm - 40 * mm * 217 / 900, width=40 * mm, height=40 * mm * 217 / 900,
                             mask="auto", preserveAspectRatio=True)
        mark = _asset("via-assistente-claro.png")
        if mark.exists():
            canvas.drawImage(str(mark), PAGE_W - MARGIN - 19 * mm, PAGE_H - HEADER_H + 7 * mm, width=19 * mm, height=19 * mm,
                             mask="auto", preserveAspectRatio=True)

        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 15)
        canvas.drawString(MARGIN, PAGE_H - 25 * mm, "Relatório de Mobilidade Urbana")
        canvas.setFillColor(colors.HexColor("#a7cbed"))
        canvas.setFont("Helvetica", 8.5)
        canvas.drawString(
            MARGIN, PAGE_H - 31 * mm,
            f"Período: {_period_label(filters)}   ·   Gerado em {generated_at.strftime('%d/%m/%Y às %H:%M')} (Brasília)",
        )
        _footer(canvas, doc)
        canvas.restoreState()

    return draw


def _on_later_pages(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, PAGE_H - STRIP_H, PAGE_W, STRIP_H, stroke=0, fill=1)
    canvas.setFillColor(ACCENT)
    canvas.rect(0, PAGE_H - STRIP_H, PAGE_W, 0.7 * mm, stroke=0, fill=1)
    wordmark = _asset("via-letreiro-claro.png")
    if wordmark.exists():
        canvas.drawImage(str(wordmark), MARGIN, PAGE_H - STRIP_H + 3.2 * mm, width=22 * mm, height=22 * mm * 217 / 900,
                         mask="auto", preserveAspectRatio=True)
    canvas.setFillColor(colors.HexColor("#a7cbed"))
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(PAGE_W - MARGIN, PAGE_H - STRIP_H + 4.6 * mm, "Relatório de Mobilidade Urbana")
    _footer(canvas, doc)
    canvas.restoreState()


def _footer(canvas, doc):
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.6)
    canvas.line(MARGIN, 13 * mm, PAGE_W - MARGIN, 13 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(MARGIN, 8.5 * mm, "VIA · Inteligência para Mobilidade Urbana")
    canvas.drawRightString(PAGE_W - MARGIN, 8.5 * mm, f"Página {doc.page}")


KPI_HEIGHT = 25 * mm  # todos os cartões têm a mesma altura (nota de até 2 linhas)


def _kpi(value, label, note, styles, width):
    cell = [Paragraph(label, styles["kpi_label"]), Spacer(1, 1.5 * mm), Paragraph(str(value), styles["kpi_value"]), Paragraph(note or "&nbsp;", styles["kpi_note"])]
    table = Table([[cell]], colWidths=[width], rowHeights=[KPI_HEIGHT])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, -1), CARD2),
        ("ROUNDEDCORNERS", [7, 7, 7, 7]),
        ("LINEBEFORE", (0, 0), (0, -1), 2.2, ACCENT),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def _delta_note(kpis):
    if kpis["delta_pct"] is None:
        return "sem período anterior"
    arrow = "▲" if kpis["delta_pct"] >= 0 else "▼"
    color = "#59d4a6" if kpis["delta_pct"] >= 0 else "#ff6b73"
    return f'<font color="{color}">{arrow} {abs(kpis["delta_pct"]):.1f}%</font> vs período anterior'


def _kpi_grid(story, styles, deep):
    k = deep["kpis"]
    gap = 3 * mm
    width = (CONTENT_W - 3 * gap) / 4
    weekday = k["busiest_weekday"] or "-"
    row1 = [
        _kpi(k["total"], "FLUXO TOTAL", _delta_note(k), styles, width),
        _kpi(k["average"], "MÉDIA POR JANELA", f"só janelas com movimento · mediana {k['median']} · desvio {k['std']}", styles, width),
        _kpi(k["peak"], "PICO DE MOVIMENTO", _br(k["peak_at"], "%d/%m às %H:%M"), styles, width),
        _kpi(f"{k['busiest_hour']:02d}h", "HORA MAIS MOVIMENTADA", f"{k['busiest_hour_total']} veículos · {weekday} lidera", styles, width),
    ]
    row2 = [
        _kpi(f"{k['peak_ratio']}×", "ÍNDICE DE PICO", "pico ÷ média das janelas com movimento", styles, width),
        _kpi(f"{k['per_hour_rate']}", "VEÍCULOS POR HORA", f"só nas {k['monitored_hours']} h com movimento registrado", styles, width),
        _kpi(f"{k['heavy_pct']}%", "PESADOS", "ônibus e caminhões", styles, width),
        _kpi(k["cameras"], "CÂMERAS COM LEITURA", f"{k['days']} de {k['period_days']} dia(s) com leituras", styles, width),
    ]
    for row in (row1, row2):
        cells = []
        for index, card in enumerate(row):
            if index:
                cells.append("")  # coluna de respiro entre os cartões
            cells.append(card)
        table = Table([cells], colWidths=[width, gap, width, gap, width, gap, width], hAlign="LEFT")
        table.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(table)
        story.append(Spacer(1, gap))


def _section(styles, overline, title, *flowables):
    return KeepTogether([Paragraph(overline.upper(), styles["over"]), Paragraph(title, styles["h2"]), *flowables, Spacer(1, 4 * mm)])


def _pair(left, right):
    table = Table([[left, right]], colWidths=[CONTENT_W / 2, CONTENT_W / 2])
    table.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (0, 0), 0), ("RIGHTPADDING", (0, 0), (0, 0), 1.5 * mm),
        ("LEFTPADDING", (1, 0), (1, 0), 1.5 * mm), ("RIGHTPADDING", (1, 0), (1, 0), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return table


def _summary_text(deep):
    k = deep["kpis"]
    parts = [
        f"No período foram registrados <b>{k['total']} veículos</b> em {k['windows']} janelas de 15 minutos "
        f"com movimento ({k['monitored_hours']} h), em {k['days']} de {k['period_days']} dia(s) com leituras; "
        f"média de {k['average']} por janela com movimento. Horários sem leitura não entram nas contas.",
        f"O pico foi de <b>{k['peak']} veículos</b> em {_br(k['peak_at'], '%d/%m às %H:%M')}, "
        f"{k['peak_ratio']}× a média. A hora mais movimentada do dia foi <b>{k['busiest_hour']:02d}h</b>.",
    ]
    if k["top_class"]:
        parts.append(f"O tipo predominante foi <b>{charts.class_label(k['top_class']).lower()}</b> ({k['top_class_pct']}% do total).")
    if k["delta_pct"] is not None:
        direction = "acima" if k["delta_pct"] >= 0 else "abaixo"
        parts.append(f"Em relação ao período anterior de mesma duração, o fluxo ficou {abs(k['delta_pct']):.1f}% {direction}.")
    return " ".join(parts)


def _peaks_table(styles, deep):
    rows = [[Paragraph(h, styles["th"]) for h in ("#", "Janela de 15 min", "Veículos", "Tipo predominante")]]
    for index, item in enumerate(deep["top_windows"][:6], start=1):
        main = max(item["by_class"], key=item["by_class"].get) if item["by_class"] else "-"
        rows.append([Paragraph(str(index), styles["td"]), Paragraph(item["label"], styles["td"]),
                     Paragraph(f"<b>{item['total']}</b>", styles["td"]), Paragraph(charts.class_label(main), styles["td"])])
    table = Table(rows, colWidths=[10 * mm, 60 * mm, 30 * mm, CONTENT_W - 100 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SURFACE]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("ROUNDEDCORNERS", [5, 5, 5, 5]),
    ]))
    return table


def _classes_table(styles, deep):
    rows = [[Paragraph(h, styles["th"]) for h in ("Tipo de veículo", "Quantidade", "% do total", "")]]
    top = max((c["total"] for c in deep["classes"]), default=1)
    bar_w = CONTENT_W - 110 * mm
    for index, item in enumerate(deep["classes"]):
        color = colors.HexColor(charts.class_color(item["name"], index))
        bar = Table([[""]], colWidths=[max(1.5 * mm, bar_w * item["total"] / top)], rowHeights=[3 * mm])
        bar.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), color), ("ROUNDEDCORNERS", [2, 2, 2, 2])]))
        rows.append([Paragraph(charts.class_label(item["name"]), styles["td"]), Paragraph(f"<b>{item['total']}</b>", styles["td"]),
                     Paragraph(f"{item['pct']:.1f}%", styles["td"]), bar])
    table = Table(rows, colWidths=[45 * mm, 30 * mm, 30 * mm, bar_w + 5 * mm], repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SURFACE]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("ROUNDEDCORNERS", [5, 5, 5, 5]),
    ]))
    return table


def _insights(deep):
    k = deep["kpis"]
    points = [
        f"Maior concentração às <b>{_br(k['peak_at'], '%d/%m %H:%M')}</b>, com {k['peak']} veículos na janela ({k['peak_ratio']}× a média do período).",
        f"A hora do dia com mais fluxo acumulado foi <b>{k['busiest_hour']:02d}h</b> ({k['busiest_hour_total']} veículos)"
        + (f", e o dia da semana mais movimentado foi <b>{k['busiest_weekday']}</b>." if k["busiest_weekday"] else "."),
    ]
    variability = (k["std"] / k["average"]) if k["average"] else 0
    points.append(
        f"O fluxo foi <b>{'muito variável' if variability > 0.8 else 'moderadamente variável' if variability > 0.4 else 'estável'}</b> "
        f"(desvio-padrão de {k['std']} para média de {k['average']} por janela)."
    )
    if k["top_class"]:
        points.append(f"Predominância de <b>{charts.class_label(k['top_class']).lower()}</b> ({k['top_class_pct']}%); veículos pesados somam {k['heavy_pct']}% do total.")
    if deep["cameras"]:
        leader = deep["cameras"][0]
        points.append(f"A câmera de maior fluxo foi <b>{leader['name']}</b> ({leader['total']} veículos, {leader['pct']:.1f}% do total).")
    if deep["daily"] and len(deep["daily"]) > 1:
        best = max(deep["daily"], key=lambda d: d["total"])
        points.append(f"O dia de maior movimento foi <b>{datetime.fromisoformat(best['date']).strftime('%d/%m')}</b>, com {best['total']} veículos.")
    by_type = deep["occurrences"]["by_type"]
    if by_type:
        detail = ", ".join(f"{count} {label.lower()}" for label, count in sorted(by_type.items(), key=lambda kv: -kv[1])[:3])
        points.append(f"Ocorrências registradas no período: {detail}.")
    return points


def build_report_pdf(filters, out_path):
    """Gera o PDF em `out_path` (Path) e o retorna. `filters` é um
    assistant.query_engine.QueryFilters."""
    styles = _styles()
    generated_at = datetime.now(BR_TIMEZONE)
    deep = compute_deep(filters)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        doc = BaseDocTemplate(
            str(out_path), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
            title="Relatório de Mobilidade Urbana · VIA", author="VIA",
        )
        first = PageTemplate(
            id="first", onPage=_on_first_page(filters, generated_at),
            frames=[Frame(MARGIN, 17 * mm, CONTENT_W, PAGE_H - HEADER_H - 17 * mm - 8 * mm, id="f1", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)],
        )
        later = PageTemplate(
            id="later", onPage=_on_later_pages,
            frames=[Frame(MARGIN, 17 * mm, CONTENT_W, PAGE_H - STRIP_H - 17 * mm - 8 * mm, id="f2", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)],
        )
        doc.addPageTemplates([first, later])

        story = [NextPageTemplate("later")]

        if not deep["has_data"]:
            story += [
                Paragraph("Resumo executivo", styles["h2"]),
                Paragraph(
                    "Não há dados suficientes registrados para o período selecionado. Nenhum número foi estimado ou "
                    "inventado - o relatório ficará completo assim que houver histórico de detecções no banco de dados.",
                    styles["body"],
                ),
            ]
            doc.build(story)
            return out_path

        def png(name):
            return tmp_dir / f"{name}.png"

        full = CONTENT_W
        half = CONTENT_W / 2 - 1.5 * mm

        _kpi_grid(story, styles, deep)
        story.append(_section(styles, "Visão geral", "Resumo executivo", Paragraph(_summary_text(deep), styles["body"])))

        story.append(_section(styles, "Fluxo", "Evolução ao longo do tempo", _img(charts.timeline_png(deep["timeline"], png("timeline")), full)))
        story.append(_section(styles, "Padrão diário", "Perfil por horário", _img(charts.hourly_png(deep["hourly"], png("hourly")), full)))

        story.append(_section(
            styles, "Composição", "Tipos de veículo e acumulado",
            _pair(_img(charts.donut_png(deep["classes"], png("donut")), half),
                  _img(charts.cumulative_png(deep["cumulative"], png("cumulative")), half)),
        ))
        story.append(_section(styles, "Detalhamento", "Veículos por tipo", _classes_table(styles, deep)))

        story.append(_section(styles, "Intensidade", "Mapa de calor semanal", _img(charts.weekday_hour_png(deep["weekday_hour"], png("weekday")), full)))

        if len(deep["daily"]) >= 2:
            story.append(_section(styles, "Comparativo", "Fluxo por dia", _img(charts.daily_png(deep["daily"], png("daily")), full)))

        if deep["cameras"]:
            story.append(_section(styles, "Pontos de monitoramento", "Fluxo por câmera", _img(charts.cameras_png(deep["cameras"], png("cameras")), full)))

        story.append(_section(
            styles, "Estatística", "Distribuição e ocorrências",
            _pair(_img(charts.histogram_png(deep["histogram"], deep["kpis"]["median"], png("hist")), half),
                  _img(charts.occurrences_png(deep["occurrences"], png("occ")), half)),
        ))
        story.append(_section(styles, "Ranking", "Janelas de maior movimento", _peaks_table(styles, deep)))

        bullets = [Paragraph(point, styles["bullet"], bulletText="•") for point in _insights(deep)]
        story.append(_section(styles, "Leitura dos dados", "Insights", *[item for b in bullets for item in (b, Spacer(1, 1.6 * mm))]))
        story.append(Paragraph(
            f"Fonte dos dados: {'banco de dados PostgreSQL' if deep['source'] == 'postgres' else 'histórico local'}. "
            "Contagens de veículos por janela de 15 minutos, em horário de Brasília. Todos os valores são calculados "
            "a partir de detecções reais; nenhum dado é estimado.",
            styles["muted"],
        ))

        doc.build(story)

    return out_path
