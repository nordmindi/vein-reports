import os
import re
import sys
from datetime import datetime
from pathlib import Path

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
    def __init__(self, orientation="P", unit="mm", format="A4", status_label="RESEARCH_OUTPUT"):
        super().__init__(orientation, unit, format)
        self.status_label = display_text(status_label)
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
        self.content_width = 210 - self.l_margin_val - self.r_margin_val
        # Try to find the assets folder in different possible locations
        # 1. In the current working directory (development)
        # 2. In the package installation directory (production)
        possible_paths = [
            os.path.join(os.getcwd(), "assets", "vein-logo-text.webp"),
            os.path.join(os.path.dirname(__file__), "..", "assets", "vein-logo-text.webp"),
            os.path.join(sys.prefix, "assets", "vein-logo-text.webp"),
            os.path.join(getattr(sys, '_MEIPASS', ''), "assets", "vein-logo-text.webp"),
        ]

        self.logo_path = None
        for path in possible_paths:
            if os.path.exists(path):
                self.logo_path = path
                break

        # If still not found, try to find it relative to the package
        if self.logo_path is None:
            # Try to find the package root
            package_root = Path(__file__).parent.parent
            asset_path = package_root / "assets" / "vein-logo-text.webp"
            if asset_path.exists():
                self.logo_path = str(asset_path)

    def header(self):
        if self.page_no() == 1:
            return

        self.set_fill_color(*self.colors["navy_dark"])
        self.rect(0, 0, self.w, 25, "F")
        self.set_fill_color(*self.colors["teal"])
        self.rect(0, 25, self.w, 1.2, "F")

        if self.logo_path and os.path.exists(self.logo_path):
            self.image(self.logo_path, x=17, y=8, w=29)

        self.set_xy(52, 8)
        self.set_text_color(*self.colors["white"])
        self.set_font("helvetica", "B", 9.5)
        self.cell(0, 5, "TRADING INTELLIGENCE REPORT", ln=True)
        self.set_x(52)
        self.set_font("helvetica", "", 7.5)
        self.cell(0, 4, f"VALIDATION STATUS: {self.status_label}", ln=False)

        self.set_xy(self.w - 43, 9)
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
        self.cell(self.content_width / 2, 9, "For research workflow review", align="R")

    def add_title_page(self, ticker, date_str):
        self.add_page()

        self.set_fill_color(*self.colors["navy_dark"])
        self.rect(0, 0, self.w, 28, "F")
        self.set_fill_color(*self.colors["teal"])
        self.rect(0, 28, self.w, 2, "F")

        if self.logo_path and os.path.exists(self.logo_path):
            self.image(self.logo_path, x=(self.w / 2) - 37, y=52, w=74)

        self.set_y(105)
        self.set_font("helvetica", "B", 29)
        self.set_text_color(*self.colors["ink"])
        self.multi_cell(self.content_width, 12, "TRADING\nINTELLIGENCE REPORT", align="C")

        self.ln(8)
        self.set_font("helvetica", "B", 18)
        self.set_text_color(*self.colors["navy"])
        self.cell(self.content_width, 11, f"{ticker}", ln=True, align="C")

        self.set_font("helvetica", "", 10)
        self.set_text_color(*self.colors["muted"])
        self.cell(self.content_width, 7, f"Analysis timestamp: {date_str}", ln=True, align="C")
        self.cell(self.content_width, 7, f"Publication status: {self.status_label}", ln=True, align="C")

        self.set_fill_color(*self.colors["navy_dark"])
        self.rect(0, self.h - 18, self.w, 18, "F")


class MarkdownPDFGenerator:
    def __init__(self, ticker="UNKNOWN", date_str="", status_label="RESEARCH_OUTPUT"):
        self.pdf = VeinReportPDF(status_label=status_label)
        self.pdf.set_auto_page_break(auto=True, margin=20)
        self.pdf.add_title_page(ticker, date_str)
        self.colors = self.pdf.colors

    def _clean_line(self, text):
        if not text:
            return ""
        text = sanitize_agent_report_text(text)
        text = "".join(c for c in str(text) if ord(c) < 256)
        text = text.replace("**", "")
        # Strip leftover markdown heading markers if a line fell through as body text.
        text = re.sub(r"^#{1,6}\s+", "", text)
        text = display_text(text)
        return re.sub(r"\s{3,}", " ", text).strip()

    def add_highlights_page(self, md_text, dashboard_metrics=None):
        metrics = dashboard_metrics or self._metrics_from_markdown(md_text)

        self.pdf.add_page()
        self.pdf.set_font("helvetica", "B", 20)
        self.pdf.set_text_color(*self.colors["ink"])
        self.pdf.cell(self.pdf.content_width, 10, "Executive Dashboard", ln=True)

        self.pdf.set_font("helvetica", "", 8.5)
        self.pdf.set_text_color(*self.colors["muted"])
        self.pdf.multi_cell(
            self.pdf.content_width,
            5,
            "Canonical report summary generated from validation and final portfolio decision data.",
        )
        self.pdf.ln(4)

        start_y = self.pdf.get_y()
        card_w = (self.pdf.content_width - 8) / 2
        card_h = 31
        row_gap = 7
        col_gap = 8

        for i, (label, val) in enumerate(metrics.items()):
            x = self.pdf.l_margin_val if i % 2 == 0 else self.pdf.l_margin_val + card_w + col_gap
            y = start_y + (i // 2) * (card_h + row_gap)
            self._dashboard_card(x, y, card_w, card_h, label, val)

        rows = (len(metrics) + 1) // 2
        self.pdf.set_y(start_y + rows * (card_h + row_gap) + 5)

    def _dashboard_card(self, x, y, width, height, label, value):
        self.pdf.set_fill_color(*self.colors["surface"])
        self.pdf.rect(x, y, width, height, "F")
        self.pdf.set_draw_color(*self.colors["border"])
        self.pdf.set_line_width(0.35)
        self.pdf.rect(x, y, width, height, "D")

        self.pdf.set_xy(x + 5, y + 5)
        self.pdf.set_font("helvetica", "B", 7.5)
        self.pdf.set_text_color(*self.colors["muted"])
        self.pdf.cell(width - 10, 4, self._clean_line(label).upper(), ln=True)

        clean_value = self._clean_line(value)
        font_size = 11 if len(clean_value) <= 38 else 9
        self.pdf.set_xy(x + 5, y + 14)
        self.pdf.set_font("helvetica", "B", font_size)
        self.pdf.set_text_color(*self._value_color(label, clean_value))
        self.pdf.multi_cell(width - 10, 5.4, clean_value)

    def _value_color(self, label, value):
        text = f"{label} {value}".upper()
        if any(word in text for word in ("BLOCKED", "SELL", "UNDERWEIGHT", "HIGH RISK")):
            return self.colors["red"]
        if any(word in text for word in ("BUY", "OVERWEIGHT", "VERIFIED")):
            return self.colors["teal"]
        if any(word in text for word in ("WARNING", "RESEARCH", "HOLD")):
            return self.colors["amber"]
        return self.colors["ink"]

    def _metrics_from_markdown(self, md_text):
        metrics = {"Status": self.pdf.status_label, "Recommendation": "N/A", "Action": "N/A", "Target": "N/A"}
        for line in md_text.split("\n"):
            if "Rating:" in line:
                metrics["Recommendation"] = line.split(":", 1)[1].strip().replace("**", "")
            if "Price Target:" in line:
                metrics["Target"] = line.split(":", 1)[1].strip().replace("**", "")
            if "Target Price:" in line:
                metrics["Target"] = line.split(":", 1)[1].strip().replace("**", "")
        if metrics["Recommendation"] != "N/A":
            metrics["Action"] = f"Use final Portfolio Manager rating: {metrics['Recommendation']}"
        return metrics

    def add_markdown_content(self, md_text):
        md_text = sanitize_agent_report_text(md_text)
        lines = md_text.split("\n")
        table_rows = []

        for raw in lines:
            raw_line = raw.strip()
            line = self._clean_line(raw_line)

            if not raw_line or raw_line == "---":
                if table_rows:
                    self._render_table(table_rows)
                    table_rows = []
                continue

            if "|" in raw_line and "---" in raw_line:
                continue
            if "|" in raw_line:
                table_rows.append(self._parse_table_row(raw_line))
                continue
            if table_rows:
                self._render_table(table_rows)
                table_rows = []

            self.pdf.set_x(self.pdf.l_margin_val)
            heading = re.match(r"^(#{1,6})\s+(.*)$", raw_line)
            if heading:
                level = len(heading.group(1))
                title = self._clean_line(heading.group(2))
                if level == 1:
                    self._render_h1(title)
                elif level == 2:
                    self._render_h2(title)
                else:
                    # ### and deeper (incl. supply-chain #### subsections)
                    self._render_h3(title)
            elif raw_line.startswith("- ") or raw_line.startswith("* "):
                self._render_bullet(line[2:])
            else:
                self._render_paragraph(line)

        if table_rows:
            self._render_table(table_rows)

    def _render_h1(self, text):
        self.pdf.ln(5)
        self.pdf.set_font("helvetica", "B", 17)
        self.pdf.set_text_color(*self.colors["ink"])
        self.pdf.multi_cell(self.pdf.content_width, 8, self._clean_line(text))
        self.pdf.ln(2)

    def _render_h2(self, text):
        self.pdf.ln(7)
        y = self.pdf.get_y()
        self.pdf.set_draw_color(*self.colors["teal"])
        self.pdf.set_line_width(0.7)
        self.pdf.line(self.pdf.l_margin_val, y, self.pdf.l_margin_val + 22, y)
        self.pdf.ln(3)
        self.pdf.set_font("helvetica", "B", 13)
        self.pdf.set_text_color(*self.colors["navy"])
        self.pdf.multi_cell(self.pdf.content_width, 7, self._clean_line(text).upper())
        self.pdf.ln(1)

    def _render_h3(self, text):
        self.pdf.ln(3)
        self.pdf.set_font("helvetica", "B", 10.5)
        self.pdf.set_text_color(*self.colors["navy"])
        self.pdf.multi_cell(self.pdf.content_width, 6, self._clean_line(text))

    def _render_bullet(self, text):
        self.pdf.set_x(self.pdf.l_margin_val + 3)
        self.pdf.set_font("helvetica", "B", 9.5)
        self.pdf.set_text_color(*self.colors["teal"])
        self.pdf.cell(4, 5.5, "-")
        self.pdf.set_font("helvetica", "", 9.5)
        self.pdf.set_text_color(*self.colors["ink"])
        self.pdf.multi_cell(self.pdf.content_width - 7, 5.5, self._clean_line(text))
        self.pdf.ln(0.5)

    def _render_paragraph(self, text):
        if not text:
            return
        self.pdf.set_font("helvetica", "", 9.5)
        self.pdf.set_text_color(*self.colors["ink"])
        self.pdf.multi_cell(self.pdf.content_width, 5.6, self._clean_line(text))
        self.pdf.ln(1.2)

    def _render_table(self, rows):
        if not rows:
            return
        rows = self._normalize_table_rows(rows)
        if not rows:
            return

        self.pdf.ln(2)
        widths = self._table_column_widths(rows)
        self._draw_table_header(rows[0], widths)
        for i, row in enumerate(rows[1:], start=1):
            self._draw_table_row(row, widths, is_header=False, fill=i % 2 == 1)
        self.pdf.ln(4)

    def _parse_table_row(self, raw_line):
        parts = raw_line.split("|")
        if raw_line.startswith("|"):
            parts = parts[1:]
        if raw_line.endswith("|"):
            parts = parts[:-1]
        return [self._clean_line(part) for part in parts]

    def _normalize_table_rows(self, rows):
        cleaned = [[self._clean_line(cell) for cell in row] for row in rows]
        cleaned = [row for row in cleaned if any(cell for cell in row)]
        if not cleaned:
            return []
        col_count = max(len(row) for row in cleaned)
        return [row + [""] * (col_count - len(row)) for row in cleaned]

    def _table_column_widths(self, rows):
        col_count = len(rows[0])
        total_width = self.pdf.content_width
        padding = 4

        body_rows = rows[1:] or rows
        min_widths = []
        max_widths = []
        content_widths = []

        for col_idx in range(col_count):
            header = rows[0][col_idx]
            cells = [row[col_idx] for row in body_rows]
            all_cells = [header] + cells

            self.pdf.set_font("helvetica", "B", 8.0)
            self.pdf.get_string_width(header) + padding
            self.pdf.set_font("helvetica", "", 8.0)

            # Calculate max width needed for any cell in this column
            max_cell_width = max([self.pdf.get_string_width(cell) for cell in all_cells] or [0]) + padding

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

    def _draw_table_header(self, row, widths):
        self._draw_table_row(row, widths, is_header=True, fill=True)

    def _draw_table_row(self, row, widths, *, is_header, fill):
        font_style = "B" if is_header else ""
        font_size = 8.0 if is_header else 7.8
        line_height = 4.5 if is_header else 4.8
        x0 = self.pdf.l_margin_val
        y0 = self.pdf.get_y()
        row_height = self._table_row_height(row, widths, font_style, font_size, line_height)

        if y0 + row_height > self.pdf.page_break_trigger:
            self.pdf.add_page()
            y0 = self.pdf.get_y()

        fill_color = self.colors["surface_alt"] if is_header else self.colors["surface"]
        self.pdf.set_fill_color(*fill_color)
        self.pdf.set_draw_color(*(self.colors["teal"] if is_header else self.colors["border"]))
        self.pdf.set_line_width(0.35 if is_header else 0.2)

        x = x0
        for width in widths:
            if fill:
                self.pdf.rect(x, y0, width, row_height, "F")
            x += width

        self.pdf.line(x0, y0, x0 + sum(widths), y0)
        self.pdf.line(x0, y0 + row_height, x0 + sum(widths), y0 + row_height)

        x = x0
        self.pdf.set_font("helvetica", font_style, font_size)
        self.pdf.set_text_color(*(self.colors["navy"] if is_header else self.colors["ink"]))
        for cell, width in zip(row, widths, strict=False):
            self.pdf.set_xy(x + 2, y0 + 2)
            self.pdf.multi_cell(
                max(1, width - 4),
                line_height,
                self._clean_line(cell),
                border=0,
                align="L",
                new_x="RIGHT",
                new_y="TOP",
            )
            x += width

        self.pdf.set_y(y0 + row_height)

    def _table_row_height(self, row, widths, font_style, font_size, line_height):
        self.pdf.set_font("helvetica", font_style, font_size)
        max_lines = 1
        for cell, width in zip(row, widths, strict=False):
            lines = self.pdf.multi_cell(
                max(1, width - 4),
                line_height,
                self._clean_line(cell),
                dry_run=True,
                output=MethodReturnValue.LINES,
            )
            max_lines = max(max_lines, len(lines) if lines else 1)
        return max_lines * line_height + 4

    def save(self, output_path):
        self.pdf.output(output_path)
        print(f"REPORT_SYNC_COMPLETE: {output_path}")
