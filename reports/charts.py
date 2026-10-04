"""Gráficos do relatório PDF no visual da central VIA / landing page: cartões
azul-marinho, gradientes na paleta da marca e destaque do pico. Todos os
valores vêm de ``assistant.deep_analytics.compute_deep`` (dados reais) -
nada é estimado aqui.
"""

import matplotlib

matplotlib.use("Agg")

import textwrap
from datetime import datetime

import matplotlib.dates as mdates
import matplotlib.ticker
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap, to_rgb
from matplotlib.patches import FancyBboxPatch
from PIL import Image, ImageDraw

for _candidate in ("Segoe UI", "Arial", "DejaVu Sans"):
    if any(f.name == _candidate for f in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = _candidate
        break

C = {
    "card": "#08091d",
    "card2": "#10134a",
    "grid": "#23286b",
    "text": "#ffffff",
    "soft": "#e8f4ff",
    "muted": "#a7cbed",
    "accent": "#4eaff7",
    "accent2": "#8ac8ff",
    "green": "#59d4a6",
    "detect": "#2fef8f",
    "amber": "#f0b74a",
    "red": "#ff6b73",
    "violet": "#c792ea",
}

CLASS_COLORS = {
    "carro": C["accent"],
    "moto": C["amber"],
    "onibus": C["green"],
    "caminhao": C["red"],
    "pessoa": C["violet"],
    "placa": C["accent2"],
}
_FALLBACK = [C["accent"], C["amber"], C["green"], C["red"], C["violet"], C["accent2"]]

CLASS_LABELS = {"carro": "Carro", "moto": "Moto", "onibus": "Ônibus", "caminhao": "Caminhão", "pessoa": "Pessoa", "placa": "Placa"}


def class_color(name, index=0):
    return CLASS_COLORS.get(name, _FALLBACK[index % len(_FALLBACK)])


def class_label(name):
    return CLASS_LABELS.get(name, str(name).capitalize())


HEAT_CMAP = LinearSegmentedColormap.from_list("via_heat", ["#10134a", "#2f6fd0", "#4eaff7", "#f0b74a", "#ff6b73"])


def _fig(width, height):
    fig, ax = plt.subplots(figsize=(width, height), dpi=200)
    fig.set_facecolor(C["card"])
    ax.set_facecolor(C["card"])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(colors=C["muted"], labelsize=7, length=0)
    return fig, ax


def _title(fig, title, subtitle=None):
    fig.text(0.035, 0.955, title, color=C["text"], fontsize=10.5, fontweight="bold", va="top")
    if subtitle:
        fig.text(0.035, 0.885, subtitle, color=C["muted"], fontsize=7, va="top")


def _save(fig, out_path, radius=26):
    fig.savefig(out_path, facecolor=C["card"])
    plt.close(fig)
    with Image.open(out_path).convert("RGBA") as image:
        mask = Image.new("L", image.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, image.size[0] - 1, image.size[1] - 1), radius=radius, fill=255)
        image.putalpha(mask)
        image.save(out_path)
    return out_path


def _empty(fig, ax, message="Sem dados no período"):
    ax.text(0.5, 0.45, message, color=C["muted"], ha="center", va="center", transform=ax.transAxes, fontsize=9)
    ax.set_xticks([])
    ax.set_yticks([])


def _horizontal_grid(ax):
    ax.yaxis.grid(True, color=C["grid"], linewidth=0.6, alpha=0.8)
    ax.set_axisbelow(True)


def _rounded_bar(ax, x, width, height, color, y0=0, radius=None, alpha=1.0, zorder=3):
    radius = radius if radius is not None else width * 0.28
    if height <= 0:
        return
    radius = min(radius, height / 2)
    ax.add_patch(FancyBboxPatch(
        (x - width / 2, y0), width, height,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        linewidth=0, facecolor=color, alpha=alpha, zorder=zorder, mutation_aspect=1,
    ))


def _gradient_area(ax, xs, ys, color, top_alpha=0.55):
    rgb = to_rgb(color)
    cmap = LinearSegmentedColormap.from_list("g", [rgb + (0.0,), rgb + (top_alpha,)])
    poly = ax.fill_between(xs, ys, 0, color="none", linewidth=0)
    ymax = max(max(ys), 1)
    image = ax.imshow(
        np.linspace(0, 1, 128).reshape(-1, 1), extent=[min(xs), max(xs), 0, ymax],
        origin="lower", aspect="auto", cmap=cmap, zorder=2,
    )
    image.set_clip_path(poly.get_paths()[0], ax.transData)


def _time_axis(ax, span_days, dense=False):
    if span_days <= 1.5:
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=4 if dense else 8))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    else:
        interval = max(1, int(span_days // (4 if dense else 8)))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=interval))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))


def _segments(timeline):
    segments, current = [], []
    for item in timeline:
        if item["gap_before"] and current:
            segments.append(current)
            current = []
        current.append(item)
    if current:
        segments.append(current)
    return segments


def timeline_png(timeline, out_path):
    fig, ax = _fig(6.7, 2.4)
    _title(fig, "Evolução do fluxo", "Veículos por janela de 15 min · linha tracejada = média móvel (1 h)")
    if not timeline:
        _empty(fig, ax)
        return _save(fig, out_path)

    peak = max(timeline, key=lambda item: item["total"])
    ymax = max(item["total"] for item in timeline)
    _horizontal_grid(ax)

    all_x = []
    for segment in _segments(timeline):
        xs = [mdates.date2num(datetime.fromisoformat(item["t"])) for item in segment]
        ys = [item["total"] for item in segment]
        ma = [item["ma"] for item in segment]
        all_x.extend(xs)
        if len(xs) == 1:
            _rounded_bar(ax, xs[0], 0.006, ys[0], C["accent"], radius=0.002)
            continue
        _gradient_area(ax, xs, ys, C["accent"])
        ax.plot(xs, ys, color=C["accent"], linewidth=1.8, zorder=4, solid_capstyle="round")
        ax.plot(xs, ma, color=C["soft"], linewidth=1, linestyle=(0, (3, 2)), alpha=0.85, zorder=4)

    px = mdates.date2num(datetime.fromisoformat(peak["t"]))
    ax.scatter([px], [peak["total"]], s=90, color=C["amber"], alpha=0.25, zorder=5)
    ax.scatter([px], [peak["total"]], s=26, color=C["amber"], edgecolor=C["card"], linewidth=1, zorder=6)
    ax.annotate(
        f"Pico · {peak['total']} · {peak['label']}", (px, peak["total"]), xytext=(0, 12),
        textcoords="offset points", ha="center", color=C["amber"], fontsize=7.5, fontweight="bold", zorder=7,
    )

    span_days = (max(all_x) - min(all_x)) if len(all_x) > 1 else 0
    ax.xaxis_date()
    _time_axis(ax, span_days)
    if span_days == 0:
        ax.set_xlim(min(all_x) - 0.02, max(all_x) + 0.02)
    ax.set_ylim(0, ymax * 1.28)
    ax.margins(x=0.02)
    fig.subplots_adjust(left=0.07, right=0.975, top=0.76, bottom=0.14)
    return _save(fig, out_path)


def hourly_png(hourly, out_path):
    fig, ax = _fig(6.7, 2.05)
    _title(fig, "Perfil por horário do dia", "Total de veículos em cada hora (horário de Brasília)")
    totals = [item["total"] for item in hourly]
    if not any(totals):
        _empty(fig, ax)
        return _save(fig, out_path)

    peak = max(range(24), key=lambda i: totals[i])
    top = max(totals)
    _horizontal_grid(ax)
    for hour, value in enumerate(totals):
        t = value / top if top else 0
        color = C["amber"] if hour == peak else HEAT_CMAP(0.25 + 0.5 * t)
        _rounded_bar(ax, hour, 0.62, value, color, radius=0.24)
        if hour == peak:
            ax.text(hour, value + top * 0.04, str(value), color=C["amber"], ha="center", fontsize=7.5, fontweight="bold")
    ax.set_xticks(range(0, 24, 2))
    ax.set_xticklabels([f"{h:02d}h" for h in range(0, 24, 2)])
    ax.set_xlim(-0.8, 23.8)
    ax.set_ylim(0, top * 1.2)
    fig.subplots_adjust(left=0.07, right=0.975, top=0.76, bottom=0.13)
    return _save(fig, out_path)


def donut_png(classes, out_path):
    fig, ax = _fig(3.3, 2.6)
    _title(fig, "Tipos de veículo", "Participação no total")
    if not classes:
        _empty(fig, ax)
        return _save(fig, out_path)

    values = [item["total"] for item in classes]
    colors = [class_color(item["name"], i) for i, item in enumerate(classes)]
    ax.pie(
        values, colors=colors, startangle=90, counterclock=False,
        wedgeprops={"width": 0.34, "edgecolor": C["card"], "linewidth": 2},
        center=(-0.55, 0), radius=0.95,
    )
    total = sum(values)
    ax.text(-0.55, 0.06, f"{total}", color=C["text"], fontsize=15, fontweight="bold", ha="center", va="center")
    ax.text(-0.55, -0.2, "veículos", color=C["muted"], fontsize=7, ha="center", va="center")
    for index, item in enumerate(classes[:6]):
        y = 0.62 - index * 0.29
        ax.add_patch(FancyBboxPatch((0.55, y - 0.045), 0.09, 0.09, boxstyle="round,pad=0,rounding_size=0.03", facecolor=colors[index], linewidth=0))
        ax.text(0.72, y + 0.035, class_label(item["name"]), color=C["soft"], fontsize=7.5, va="center")
        ax.text(0.72, y - 0.075, f"{item['total']} · {item['pct']:.1f}%", color=C["muted"], fontsize=6.5, va="center")
    ax.set_xlim(-1.6, 1.7)
    ax.set_ylim(-1.1, 1.1)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.subplots_adjust(left=0.02, right=0.98, top=0.82, bottom=0.03)
    return _save(fig, out_path)


def weekday_hour_png(weekday_hour, out_path):
    fig, ax = _fig(6.7, 2.6)
    _title(fig, "Mapa de calor · dia da semana × hora", "Quanto mais quente a cor, maior o fluxo acumulado naquele horário")
    matrix = np.array(weekday_hour["matrix"], dtype=float)
    if not matrix.any():
        _empty(fig, ax)
        return _save(fig, out_path)

    image = ax.imshow(matrix, aspect="auto", cmap=HEAT_CMAP, vmin=0, vmax=matrix.max(), interpolation="nearest")
    ax.set_xticks(np.arange(-0.5, 24, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, 7, 1), minor=True)
    ax.grid(which="minor", color=C["card"], linewidth=1.6)
    ax.tick_params(which="minor", length=0)
    ax.set_xticks(range(0, 24, 2))
    ax.set_xticklabels([f"{h:02d}h" for h in range(0, 24, 2)])
    ax.set_yticks(range(7))
    ax.set_yticklabels(weekday_hour["labels"])
    ax.tick_params(colors=C["muted"], labelsize=7, length=0)
    cbar = fig.colorbar(image, ax=ax, fraction=0.025, pad=0.015)
    cbar.outline.set_visible(False)
    cbar.ax.tick_params(colors=C["muted"], labelsize=6.5, length=0)
    fig.subplots_adjust(left=0.07, right=0.96, top=0.76, bottom=0.12)
    return _save(fig, out_path)


def daily_png(daily, out_path):
    fig, ax = _fig(6.7, 2.55)
    _title(fig, "Fluxo por dia", "Empilhado por tipo de veículo · selo = variação sobre o dia anterior")
    if not daily:
        _empty(fig, ax)
        return _save(fig, out_path)

    names = []
    for item in daily:
        for name in item["by_class"]:
            if name not in names:
                names.append(name)
    names.sort(key=lambda n: -sum(d["by_class"].get(n, 0) for d in daily))
    top = max(d["total"] for d in daily)
    _horizontal_grid(ax)
    width = min(0.62, 6.0 / max(len(daily), 6))
    for x, item in enumerate(daily):
        base = 0
        for index, name in enumerate(names):
            value = item["by_class"].get(name, 0)
            if value:
                _rounded_bar(ax, x, width, value, class_color(name, index), y0=base, radius=width * 0.12)
                base += value
        ax.text(x, base + top * 0.03, str(item["total"]), color=C["soft"], ha="center", fontsize=7.5, fontweight="bold")
        if item["delta_pct"] is not None:
            up = item["delta_pct"] >= 0
            ax.text(
                x, base + top * 0.14, f"{'▲' if up else '▼'} {abs(item['delta_pct']):.0f}%",
                color=C["green"] if up else C["red"], ha="center", fontsize=6.5,
            )
    labels = [datetime.fromisoformat(item["date"]).strftime("%d/%m") for item in daily]
    step = max(1, len(labels) // 14)
    ax.set_xticks(range(0, len(labels), step))
    ax.set_xticklabels(labels[::step])
    ax.set_xlim(-0.7, len(daily) - 0.3)
    ax.set_ylim(0, top * 1.35)
    for index, name in enumerate(names[:5]):
        x0 = 0.60 + index * 0.085
        fig.add_artist(FancyBboxPatch(
            (x0, 0.905), 0.012, 0.03, boxstyle="round,pad=0,rounding_size=0.004",
            transform=fig.transFigure, facecolor=class_color(name, index), linewidth=0,
        ))
        fig.text(x0 + 0.017, 0.92, class_label(name), color=C["muted"], fontsize=6.5, va="center")
    fig.subplots_adjust(left=0.07, right=0.975, top=0.76, bottom=0.14)
    return _save(fig, out_path)


def cameras_png(cameras, out_path):
    rows = cameras[:8]
    height = max(1.7, 0.36 * len(rows) + 0.95)
    fig, ax = _fig(6.7, height)
    _title(fig, "Fluxo por câmera", "Composição por tipo de veículo · % do total do período")
    if not rows:
        _empty(fig, ax)
        return _save(fig, out_path)

    top = max(row["total"] for row in rows)
    names = []
    for row in rows:
        for name in row["by_class"]:
            if name not in names:
                names.append(name)
    names.sort(key=lambda n: -sum(r["by_class"].get(n, 0) for r in rows))
    for y, row in enumerate(reversed(rows)):
        left = 0
        for index, name in enumerate(names):
            value = row["by_class"].get(name, 0)
            if value:
                ax.barh(y, value, left=left, height=0.5, color=class_color(name, index), edgecolor=C["card"], linewidth=1.2)
                left += value
        if left == 0 and row["total"] > 0:
            ax.barh(y, top * 0.012, height=0.5, color=C["accent"])
            left = top * 0.012
        ax.text(left + top * 0.015, y, f"{row['total']} · {row['pct']:.1f}%", color=C["soft"], va="center", fontsize=7.5, fontweight="bold")
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([row["name"] for row in reversed(rows)], color=C["soft"], fontsize=8)
    ax.set_xlim(0, top * 1.22)
    ax.set_xticks([])
    fig.subplots_adjust(left=0.2, right=0.975, top=0.78, bottom=0.05)
    return _save(fig, out_path)


def cumulative_png(cumulative, out_path):
    fig, ax = _fig(3.3, 2.3)
    _title(fig, "Acumulado no período", "Total de veículos ao longo do tempo")
    if len(cumulative) < 2:
        _empty(fig, ax)
        return _save(fig, out_path)
    xs = [mdates.date2num(datetime.fromisoformat(p["t"])) for p in cumulative]
    ys = [p["value"] for p in cumulative]
    _horizontal_grid(ax)
    _gradient_area(ax, xs, ys, C["green"], top_alpha=0.5)
    ax.plot(xs, ys, color=C["green"], linewidth=1.8, zorder=4)
    ax.scatter([xs[-1]], [ys[-1]], s=22, color=C["green"], edgecolor=C["card"], zorder=5)
    ax.annotate(str(ys[-1]), (xs[-1], ys[-1]), xytext=(-4, 8), textcoords="offset points", ha="right", color=C["green"], fontsize=8, fontweight="bold")
    span = xs[-1] - xs[0]
    ax.xaxis_date()
    _time_axis(ax, span, dense=True)
    ax.set_ylim(0, ys[-1] * 1.18)
    fig.subplots_adjust(left=0.13, right=0.96, top=0.76, bottom=0.14)
    return _save(fig, out_path)


def histogram_png(histogram, median, out_path):
    fig, ax = _fig(3.3, 2.3)
    _title(fig, "Distribuição das janelas", "Quantas janelas de 15 min tiveram cada volume")
    if not histogram:
        _empty(fig, ax)
        return _save(fig, out_path)
    counts = [b["count"] for b in histogram]
    top = max(counts) or 1
    _horizontal_grid(ax)
    for x, bucket in enumerate(histogram):
        _rounded_bar(ax, x, 0.7, bucket["count"], C["accent"], radius=0.2, alpha=0.55 + 0.45 * bucket["count"] / top)
        if bucket["count"]:
            ax.text(x, bucket["count"] + top * 0.04, str(bucket["count"]), color=C["soft"], ha="center", fontsize=6.5)
    ax.set_xticks(range(len(histogram)))
    ax.set_xticklabels([f"{b['from']}–{b['to']}" for b in histogram], rotation=35, ha="right", fontsize=6)
    ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
    ax.set_ylim(0, top * 1.25)
    ax.set_xlim(-0.7, len(histogram) - 0.3)
    ax.text(0.985, 0.94, f"mediana {median}", transform=ax.transAxes, ha="right", color=C["amber"], fontsize=7)
    fig.subplots_adjust(left=0.1, right=0.97, top=0.76, bottom=0.25)
    return _save(fig, out_path)


def occurrences_png(occurrences, out_path):
    fig, ax = _fig(3.3, 2.3)
    _title(fig, "Ocorrências", "Registros por tipo no período")
    items = sorted((occurrences or {}).get("by_type", {}).items(), key=lambda kv: kv[1])
    if not items:
        _empty(fig, ax, "Nenhuma ocorrência")
        return _save(fig, out_path)
    top = max(v for _, v in items)
    palette = [C["red"], C["amber"], C["accent"], C["violet"]]
    for y, (label, value) in enumerate(items):
        ax.barh(y, value, height=0.5, color=palette[y % len(palette)])
        ax.text(value + top * 0.02, y, str(value), color=C["soft"], va="center", fontsize=7.5, fontweight="bold")
    ax.set_yticks(range(len(items)))
    ax.set_yticklabels([textwrap.fill(label, 16) for label, _ in items], color=C["soft"], fontsize=6.8, linespacing=1.05)
    ax.set_xlim(0, top * 1.2)
    ax.set_xticks([])
    fig.subplots_adjust(left=0.34, right=0.95, top=0.76, bottom=0.06)
    return _save(fig, out_path)
