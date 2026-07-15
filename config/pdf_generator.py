#!/usr/bin/env python3
"""
Professional PDF report generator for compact TradingAgents summaries.
"""

import os
import re
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from fpdf import FPDF
from fpdf.enums import MethodReturnValue

from tradingagents.agents.utils.report_text import sanitize_agent_report_text

DISPLAY_REPLACEMENTS = {
    "INSUFFICIENT_EVIDENCE": "Insufficient Evidence",
    "NO_CURRENT_TRANSACTION": "No current transaction",
    "RESEARCH_OUTPUT": "Research Output",
    "research_only": "Research Only",
    "verified_with_warnings": "Verified with Warnings",
    "close_10_ema": "10-day EMA",
    "close_50_sma": "50-day SMA",
    "close_200_sma": "200-day SMA",
    "macdh": "MACD histogram",
    "macds": "MACD signal line",
    "macd": "MACD",
    "boll_ub": "Bollinger upper band",
    "boll_lb": "Bollinger lower band",
    "boll": "Bollinger middle band",
    "vwma": "VWMA",
    "rsi": "RSI",
    "atr": "ATR",
    "ema": "EMA",
    "sma": "SMA",
    "ohlcv": "OHLCV",
    "get_stock_data": "stock price data lookup",
    "get_indicators": "technical indicator lookup",
    "get_fundamentals": "fundamentals lookup",
    "get_balance_sheet": "balance sheet lookup",
    "get_cashflow": "cash flow lookup",
    "get_income_statement": "income statement lookup",
    "get_news": "news data lookup",
    "get_global_news": "global news lookup",
    "get_insider_transactions": "insider transaction lookup",
    "dynamic S/R": "dynamic support/resistance",
}


def display_text(text):
    if not text:
        return ""
    text = str(text)
    text = text.replace("`", "")
    text = text.replace("//", ":")
    for source, replacement in DISPLAY_REPLACEMENTS.items():
        text = re.sub(rf"(?<![A-Za-z0-9_]){re.escape(source)}(?![A-Za-z0-9_])", replacement, text)
    text = re.sub(r"\b([a-z]+(?:_[a-z0-9]+)+)\b", _humanize_identifier_match, text)
    text = re.sub(r"\b([A-Z]+(?:_[A-Z0-9]+)+)\b", _humanize_constant_match, text)
    text = re.sub(r"\s+:\s+", ": ", text)
    return text


def _humanize_identifier_match(match):
    value = match.group(1)
    if value in DISPLAY_REPLACEMENTS:
        return DISPLAY_REPLACEMENTS[value]
    return value.replace("_", " ")


def _humanize_constant_match(match):
    value = match.group(1)
    if value in DISPLAY_REPLACEMENTS:
        return DISPLAY_REPLACEMENTS[value]
    return value.replace("_", " ").title()


class VeinReportPDF(FPDF):
    def __init__(self, orientation="P", unit="mm", format="A4"):
        super().__init__(orientation, unit, format)
        self.colors = {
            "white": (255, 255, 255),
            "ink": (17, 24, 39),
            "muted": (100, 116, 139),
            "border": (226, 232, 240),
            "surface": (248, 250, 252),
            "surface_alt": (241, 245, 249),
            "navy": (24, 54, 96),
            "navy_dark": (15, 35, 68),
            "blue": (37, 99, 235),
            "teal": (13, 148, 136),
            "amber": (217, 119, 6),
            "red": (190, 18, 60),
        }
        self.l_margin_val = 17
        self.r_margin_val = 17
        self.set_margins(self.l_margin_val, 22, self.r_margin_val)
        self.content_width = self.w - self.l_margin_val - self.r_margin_val

    def header(self):
        if self.page_no() == 1:
            return

        self.set_fill_color(*self.colors["navy_dark"])
        self.rect(0, 0, self.w, 24, "F")
        self.set_fill_color(*self.colors["teal"])
        self.rect(0, 24, self.w, 1.2, "F")

        self.set_xy(self.l_margin_val, 7.5)
        self.set_text_color(*self.colors["white"])
        self.set_font("helvetica", "B", 10)
        self.cell(self.content_width, 5, "TRADING INTELLIGENCE REPORT", ln=True)
        self.set_font("helvetica", "", 7.5)
        self.set_x(self.l_margin_val)
        self.cell(self.content_width, 4, "Evidence-based market summary", ln=False)

        self.set_xy(self.w - 43, 8)
        self.set_font("helvetica", "B", 8)
        self.cell(26, 7, f"PAGE {self.page_no()}", align="R")
        self.set_y(34)

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-15)
        self.set_draw_color(*self.colors["border"])
        self.line(self.l_margin_val, self.get_y(), self.w - self.r_margin_val, self.get_y())
        self.set_font("helvetica", "", 7.5)
        self.set_text_color(*self.colors["muted"])
        self.cell(self.content_width / 2, 9, f"Generated {datetime.now().strftime('%Y-%m-%d')}", align="L")
        self.cell(self.content_width / 2, 9, "Vein Reports report package", align="R")

    def add_title_page(self, ticker, date_str):
        self.add_page()
        self.set_fill_color(*self.colors["navy_dark"])
        self.rect(0, 0, self.w, 28, "F")
        self.set_fill_color(*self.colors["teal"])
        self.rect(0, 28, self.w, 2, "F")
        self.set_fill_color(*self.colors["navy_dark"])
        self.rect(0, self.h - 18, self.w, 18, "F")

        self.set_y(88)
        self.set_text_color(*self.colors["ink"])
        self.set_font("helvetica", "B", 29)
        self.multi_cell(self.content_width, 12, "TRADING\nINTELLIGENCE REPORT", align="C")

        self.ln(8)
        self.set_font("helvetica", "B", 18)
        self.set_text_color(*self.colors["navy"])
        self.cell(self.content_width, 11, str(ticker), ln=True, align="C")

        self.set_font("helvetica", "", 10)
        self.set_text_color(*self.colors["muted"])
        self.cell(self.content_width, 7, f"Analysis date: {date_str}", ln=True, align="C")
        self.cell(self.content_width, 7, "Compiled by Vein Reports", ln=True, align="C")

    def clean_text(self, text):
        if not isinstance(text, str):
            text = str(text)
        text = sanitize_agent_report_text(text)
        text = "".join(c for c in text if ord(c) < 256)
        return display_text(text).strip()

    def status_color(self, value):
        text = str(value).upper()
        if any(word in text for word in ("BUY", "BULLISH", "OVERWEIGHT", "POSITIVE", "LOW")):
            return self.colors["teal"]
        if any(word in text for word in ("SELL", "BEARISH", "UNDERWEIGHT", "HIGH", "DANGER")):
            return self.colors["red"]
        return self.colors["amber"]

    def section_title(self, title, color_name="navy"):
        self.ln(5)
        y = self.get_y()
        self.set_draw_color(*self.colors[color_name])
        self.set_line_width(0.7)
        self.line(self.l_margin_val, y, self.l_margin_val + 22, y)
        self.ln(3)
        self.set_font("helvetica", "B", 13)
        self.set_text_color(*self.colors[color_name])
        self.multi_cell(self.content_width, 7, self.clean_text(title).upper())
        self.ln(1)

    def draw_dashboard_card(self, x, y, width, height, label, value):
        self.set_fill_color(*self.colors["surface"])
        self.rect(x, y, width, height, "F")
        self.set_draw_color(*self.colors["border"])
        self.set_line_width(0.35)
        self.rect(x, y, width, height, "D")

        self.set_xy(x + 5, y + 5)
        self.set_font("helvetica", "B", 7.5)
        self.set_text_color(*self.colors["muted"])
        self.cell(width - 10, 4, self.clean_text(label).upper(), ln=True)

        clean_value = self.clean_text(value)
        self.set_xy(x + 5, y + 14)
        self.set_font("helvetica", "B", 11 if len(clean_value) <= 34 else 9)
        self.set_text_color(*self.status_color(clean_value))
        self.multi_cell(width - 10, 5.4, clean_value)

    def draw_dynamic_table(self, rows: Sequence[Sequence[Any]]):
        rows = self._normalize_table_rows(rows)
        if not rows:
            return

        self.ln(2)
        widths = self._table_column_widths(rows)
        self._draw_table_row(rows[0], widths, is_header=True, fill=True)
        for i, row in enumerate(rows[1:], start=1):
            self._draw_table_row(row, widths, is_header=False, fill=i % 2 == 1)
        self.ln(4)

    def _normalize_table_rows(self, rows):
        cleaned = [
            [self.clean_text(cell) for cell in row]
            for row in rows
            if row is not None
        ]
        cleaned = [row for row in cleaned if any(cell for cell in row)]
        if not cleaned:
            return []
        col_count = max(len(row) for row in cleaned)
        return [row + [""] * (col_count - len(row)) for row in cleaned]

    def _table_column_widths(self, rows):
        col_count = len(rows[0])
        total_width = self.content_width
        padding = 4

        body_rows = rows[1:] or rows
        min_widths = []
        max_widths = []
        content_widths = []

        for col_idx in range(col_count):
            header = rows[0][col_idx]
            cells = [row[col_idx] for row in body_rows]
            all_cells = [header] + cells

            self.set_font("helvetica", "B", 8.0)
            self.get_string_width(header) + padding
            self.set_font("helvetica", "", 8.0)

            # Calculate max width needed for any cell in this column
            max_cell_width = max([self.get_string_width(cell) for cell in all_cells] or [0]) + padding

            # Calculate average content length for this column
            sum(len(str(cell)) for cell in all_cells) / max(1, len(all_cells))

            # Set minimum width based on content
            min_width = max(12, min(20, max_cell_width * 0.3))  # Minimum 12pt, max 20pt, scaled to content

            # Set maximum width based on content
            max_width = min(total_width * 0.6, max(30, max_cell_width))  # Max 60% of total width or max cell width, minimum 30pt

            min_widths.append(min_width)
            max_widths.append(max_width)
            content_widths.append(max_cell_width)

        # Calculate proportional widths based on content
        total_content_width = sum(content_widths)
        if total_content_width > 0:
            # Proportional allocation based on content width
            proportional_widths = [
                max(min_widths[i], min(max_widths[i], (content_widths[i] / total_content_width) * total_width * 0.9))
                for i in range(col_count)
            ]

            # Adjust to fit exactly within total_width
            current_total = sum(proportional_widths)
            if current_total > 0:
                scale_factor = total_width / current_total
                scaled_widths = [width * scale_factor for width in proportional_widths]

                # Ensure widths stay within min/max bounds
                final_widths = []
                for i in range(col_count):
                    width = max(min_widths[i], min(max_widths[i], scaled_widths[i]))
                    final_widths.append(width)

                return final_widths

        # Fallback to equal distribution if content-based calculation fails
        return [total_width / col_count for _ in range(col_count)]

    def _draw_table_row(self, row, widths, *, is_header, fill):
        font_style = "B" if is_header else ""
        font_size = 8.0 if is_header else 7.8
        line_height = 4.5 if is_header else 4.8
        x0 = self.l_margin_val
        y0 = self.get_y()
        row_height = self._table_row_height(row, widths, font_style, font_size, line_height)

        if y0 + row_height > self.page_break_trigger:
            self.add_page()
            y0 = self.get_y()

        fill_color = self.colors["surface_alt"] if is_header else self.colors["surface"]
        self.set_fill_color(*fill_color)
        self.set_draw_color(*(self.colors["teal"] if is_header else self.colors["border"]))
        self.set_line_width(0.35 if is_header else 0.2)

        x = x0
        for width in widths:
            if fill:
                self.rect(x, y0, width, row_height, "F")
            x += width

        self.line(x0, y0, x0 + sum(widths), y0)
        self.line(x0, y0 + row_height, x0 + sum(widths), y0 + row_height)

        x = x0
        self.set_font("helvetica", font_style, font_size)
        self.set_text_color(*(self.colors["navy"] if is_header else self.colors["ink"]))
        for cell, width in zip(row, widths, strict=False):
            self.set_xy(x + 2, y0 + 2)
            self.multi_cell(
                max(1, width - 4),
                line_height,
                self.clean_text(cell),
                border=0,
                align="L",
                new_x="RIGHT",
                new_y="TOP",
            )
            x += width

        self.set_y(y0 + row_height)

    def _table_row_height(self, row, widths, font_style, font_size, line_height):
        self.set_font("helvetica", font_style, font_size)
        max_lines = 1
        for cell, width in zip(row, widths, strict=False):
            lines = self.multi_cell(
                max(1, width - 4),
                line_height,
                self.clean_text(cell),
                dry_run=True,
                output=MethodReturnValue.LINES,
            )
            max_lines = max(max_lines, len(lines) if lines else 1)
        return max_lines * line_height + 4


class PDFGenerator:
    def __init__(self, output_dir: str = "reports"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def generate_report(self, data: dict) -> str:
        ticker = data.get("entity", "Unknown")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        filename = f"TradingAgents_Report_{ticker}_{timestamp}.pdf"
        filepath = os.path.join(self.output_dir, filename)
        date_str = datetime.now().strftime("%B %d, %Y")

        pdf = VeinReportPDF()
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.add_title_page(ticker, date_str)
        self._add_highlights_page(pdf, data)
        self._add_content_page(pdf, data)
        pdf.output(filepath)
        return filepath

    def _add_highlights_page(self, pdf, data):
        pdf.add_page()
        pdf.set_font("helvetica", "B", 20)
        pdf.set_text_color(*pdf.colors["ink"])
        pdf.cell(pdf.content_width, 10, "Executive Dashboard", ln=True)
        pdf.set_font("helvetica", "", 8.5)
        pdf.set_text_color(*pdf.colors["muted"])
        pdf.multi_cell(pdf.content_width, 5, "Compact summary of signal, sentiment, confidence, and risk.")
        pdf.ln(4)

        metrics = {
            "Signal": data.get("signal", "N/A"),
            "Sentiment": f"{data.get('sentiment', 0.0):+.2f}",
            "Confidence": f"{int(data.get('confidence', 0) * 100)}%",
            "Risk Level": data.get("risk_level", "N/A"),
        }

        start_y = pdf.get_y()
        card_width = (pdf.content_width - 8) / 2
        card_height = 31
        col_gap = 8
        row_gap = 7

        for i, (label, val) in enumerate(metrics.items()):
            x = pdf.l_margin_val if i % 2 == 0 else pdf.l_margin_val + card_width + col_gap
            y = start_y + (i // 2) * (card_height + row_gap)
            pdf.draw_dashboard_card(x, y, card_width, card_height, label, val)

        rows = (len(metrics) + 1) // 2
        pdf.set_y(start_y + rows * (card_height + row_gap) + 5)

    def _add_content_page(self, pdf, data):
        pdf.add_page()

        pdf.section_title("Executive Summary", "navy")
        pdf.set_font("helvetica", "", 10)
        pdf.set_text_color(*pdf.colors["ink"])
        pdf.multi_cell(pdf.content_width, 5.8, pdf.clean_text(data.get("summary", "No summary available.")))
        pdf.ln(5)

        pdf.section_title("Bullish Vectors", "teal")
        self._render_factor_list(pdf, data.get("bull_factors", []))

        pdf.section_title("Bearish Vectors", "red")
        self._render_factor_list(pdf, data.get("bear_factors", []))

        for table in data.get("tables", []):
            title = table.get("title") if isinstance(table, dict) else None
            rows = self._table_rows_from_payload(table)
            if not rows:
                continue
            if title:
                pdf.section_title(title, "navy")
            pdf.draw_dynamic_table(rows)

    def _render_factor_list(self, pdf, factors):
        if not factors:
            pdf.set_font("helvetica", "", 9.5)
            pdf.set_text_color(*pdf.colors["muted"])
            pdf.multi_cell(pdf.content_width, 5.5, "No supported factors provided.")
            pdf.ln(2)
            return

        for factor in factors:
            pdf.set_x(pdf.l_margin_val + 3)
            pdf.set_font("helvetica", "B", 9.5)
            pdf.set_text_color(*pdf.colors["teal"])
            pdf.cell(4, 5.5, "-")
            pdf.set_font("helvetica", "", 9.5)
            pdf.set_text_color(*pdf.colors["ink"])
            pdf.multi_cell(pdf.content_width - 7, 5.5, pdf.clean_text(factor))
            pdf.ln(0.5)

    def _table_rows_from_payload(self, table):
        if isinstance(table, dict):
            rows = table.get("rows") or []
            columns = table.get("columns")
            if columns:
                return [columns] + rows
            return rows
        return table


if __name__ == "__main__":
    gen = PDFGenerator()
    test_data = {
        "entity": "NVDA",
        "summary": (
            "NVIDIA is in a medium-term correction within a still-intact long-term "
            "uptrend. Momentum is deteriorating, while oversold conditions are "
            "building near major moving-average support."
        ),
        "sentiment": -0.45,
        "signal": "SELL",
        "confidence": 0.82,
        "risk_level": "HIGH",
        "bull_factors": ["CUDA ecosystem moat", "Data center demand", "AI secular trend"],
        "bear_factors": ["Momentum deterioration", "Valuation compression risk", "Event-risk sensitivity"],
    }
    path = gen.generate_report(test_data)
    print(f"Report generated at: {path}")
