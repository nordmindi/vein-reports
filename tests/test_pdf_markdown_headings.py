"""PDF markdown rendering cleans heading markers used by supply-chain reports."""

from scripts.generate_full_report_pdf import MarkdownPDFGenerator


def test_pdf_renders_h4_headings_without_hash_markers(tmp_path):
    md = "\n".join(
        [
            "# Trading Analysis Report: NVDA",
            "",
            "### Supply Chain Analyst",
            "### Supply Chain & Chokepoint Analysis",
            "Per Vein Graph structural analysis.",
            "#### Anchor Products",
            "- High-End GPUs/Accelerators",
            "#### Downstream Dependencies",
            "| Dependency | Category | Hops | Chokepoint |",
            "| --- | --- | --- | --- |",
            "| Logic Die | Component | 1 | No |",
            "###### Nested Detail",
            "Extra context.",
        ]
    )
    out = tmp_path / "report.pdf"
    generator = MarkdownPDFGenerator(ticker="NVDA", date_str="July 25, 2026")
    generator.add_highlights_page(md)
    generator.add_markdown_content(md)
    generator.save(str(out))
    assert out.exists()
    assert out.stat().st_size > 500


def test_clean_line_strips_heading_hashes():
    generator = MarkdownPDFGenerator(ticker="NVDA", date_str="July 25, 2026")
    assert generator._clean_line("#### Anchor Products") == "Anchor Products"
    assert generator._clean_line("###### Nested Detail") == "Nested Detail"
    assert generator._clean_line("Plain body text") == "Plain body text"
