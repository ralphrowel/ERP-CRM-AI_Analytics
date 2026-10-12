"""
Visiq Plotly.js Visualizer (Roadmap §V1.6)
Generates responsive Plotly.js JSON specifications matching data geometry
(bar, line, donut, indicator, grouped bar) with reactive dark/light mode palette synchronization.
"""

from typing import Any, ClassVar


class PlotlyVisualizer:
    """Translates analytical tool outputs into interactive Plotly specifications."""

    COLOR_PALETTE: ClassVar[list[str]] = [
        "#3b82f6",  # Blue
        "#10b981",  # Emerald Green
        "#f59e0b",  # Amber
        "#8b5cf6",  # Purple
        "#ec4899",  # Pink
        "#06b6d4",  # Cyan
        "#ef4444",  # Red
        "#64748b",  # Slate
    ]

    THEMES: ClassVar[dict[str, dict[str, str]]] = {
        "light": {
            "bg_color": "#ffffff",
            "paper_color": "#ffffff",
            "font_color": "#1e293b",
            "grid_color": "#e2e8f0",
            "card_bg": "#f8fafc",
        },
        "dark": {
            "bg_color": "#0f172a",
            "paper_color": "#1e293b",
            "font_color": "#f8fafc",
            "grid_color": "#334155",
            "card_bg": "#1e293b",
        },
    }

    @classmethod
    def generate_spec(
        cls, tool_output: dict[str, Any], theme: str = "light"
    ) -> dict[str, Any]:
        """
        Selects geometry and produces full Plotly spec based on tool output type.
        """
        tool_name = tool_output.get("tool")
        theme_cfg = cls.THEMES.get(theme, cls.THEMES["light"])

        if tool_name == "get_metric":
            return cls._build_indicator_spec(tool_output, theme_cfg)
        elif tool_name == "compare_periods":
            return cls._build_comparison_bar_spec(tool_output, theme_cfg)
        elif tool_name == "top_n":
            return cls._build_top_n_bar_spec(tool_output, theme_cfg)
        elif tool_name == "breakdown":
            dim = tool_output.get("dimension", "")
            if dim in ("month", "date", "year"):
                return cls._build_time_series_line_spec(tool_output, theme_cfg)
            elif tool_output.get("segment_count", 0) <= 5:
                return cls._build_donut_spec(tool_output, theme_cfg)
            else:
                return cls._build_breakdown_bar_spec(tool_output, theme_cfg)
        elif tool_name == "dq_summary":
            return cls._build_dq_score_gauge_spec(tool_output, theme_cfg)

        # Default fallback indicator
        return cls._build_indicator_spec(tool_output, theme_cfg)

    @classmethod
    def _base_layout(cls, title: str, theme_cfg: dict[str, str]) -> dict[str, Any]:
        return {
            "title": {
                "text": title,
                "font": {
                    "size": 16,
                    "color": theme_cfg["font_color"],
                    "family": "Inter, sans-serif",
                },
                "x": 0.05,
            },
            "paper_bgcolor": theme_cfg["paper_color"],
            "plot_bgcolor": theme_cfg["bg_color"],
            "font": {"color": theme_cfg["font_color"], "family": "Inter, sans-serif"},
            "margin": {"l": 50, "r": 30, "t": 50, "b": 50},
            "autosize": True,
        }

    @classmethod
    def _build_indicator_spec(
        cls, output: dict[str, Any], theme_cfg: dict[str, str]
    ) -> dict[str, Any]:
        val = output.get("value", 0)
        unit = output.get("unit", "")
        name = output.get("metric_name", "Metric")
        prefix = "₱" if unit == "PHP" else ""
        suffix = f" {unit}" if unit and unit != "PHP" else ""

        trace = {
            "type": "indicator",
            "mode": "number",
            "value": val,
            "number": {"prefix": prefix, "suffix": suffix, "valueformat": ",.2f"},
            "title": {
                "text": name,
                "font": {"size": 14, "color": theme_cfg["font_color"]},
            },
        }
        layout = cls._base_layout(name, theme_cfg)
        layout["height"] = 240
        return {
            "data": [trace],
            "layout": layout,
            "config": {"responsive": True, "displayModeBar": False},
        }

    @classmethod
    def _build_comparison_bar_spec(
        cls, output: dict[str, Any], theme_cfg: dict[str, str]
    ) -> dict[str, Any]:
        name = output.get("metric_name", "Metric")
        curr = output.get("current_period", {})
        prior = output.get("prior_period", {})

        x = ["Prior Period", "Current Period"]
        y = [prior.get("value", 0), curr.get("value", 0)]
        colors = [
            "#94a3b8",
            "#3b82f6" if output.get("trend") == "increase" else "#ef4444",
        ]

        trace = {
            "type": "bar",
            "x": x,
            "y": y,
            "marker": {"color": colors},
            "text": [f"{v:,.2f}" for v in y],
            "textposition": "auto",
        }
        layout = cls._base_layout(f"{name} Period Comparison", theme_cfg)
        layout["yaxis"] = {"gridcolor": theme_cfg["grid_color"]}
        layout["xaxis"] = {"gridcolor": theme_cfg["grid_color"]}
        layout["height"] = 320
        return {
            "data": [trace],
            "layout": layout,
            "config": {"responsive": True, "displayModeBar": False},
        }

    @classmethod
    def _build_top_n_bar_spec(
        cls, output: dict[str, Any], theme_cfg: dict[str, str]
    ) -> dict[str, Any]:
        items = output.get("items", [])
        names = [it["name"] for it in reversed(items)]
        vals = [it["value"] for it in reversed(items)]
        shares = [f"{it['share_percentage']}%" for it in reversed(items)]

        trace = {
            "type": "bar",
            "orientation": "h",
            "y": names,
            "x": vals,
            "text": shares,
            "textposition": "inside",
            "marker": {"color": cls.COLOR_PALETTE[0]},
        }
        dim = output.get("dimension", "").title()
        title = (
            f"Top {output.get('n', 5)} {dim} by {output.get('metric_name', 'Value')}"
        )
        layout = cls._base_layout(title, theme_cfg)
        layout["xaxis"] = {"gridcolor": theme_cfg["grid_color"]}
        layout["yaxis"] = {"gridcolor": theme_cfg["grid_color"]}
        layout["height"] = max(280, len(items) * 45)
        return {
            "data": [trace],
            "layout": layout,
            "config": {"responsive": True, "displayModeBar": False},
        }

    @classmethod
    def _build_breakdown_bar_spec(
        cls, output: dict[str, Any], theme_cfg: dict[str, str]
    ) -> dict[str, Any]:
        segments = output.get("segments", [])[:15]
        names = [s["name"] for s in segments]
        vals = [s["value"] for s in segments]

        trace = {
            "type": "bar",
            "x": names,
            "y": vals,
            "marker": {"color": cls.COLOR_PALETTE[: len(names)]},
        }
        dim = output.get("dimension", "").title()
        title = f"{output.get('metric_name', 'Metric')} by {dim}"
        layout = cls._base_layout(title, theme_cfg)
        layout["xaxis"] = {"gridcolor": theme_cfg["grid_color"], "tickangle": -25}
        layout["yaxis"] = {"gridcolor": theme_cfg["grid_color"]}
        layout["height"] = 350
        return {
            "data": [trace],
            "layout": layout,
            "config": {"responsive": True, "displayModeBar": False},
        }

    @classmethod
    def _build_donut_spec(
        cls, output: dict[str, Any], theme_cfg: dict[str, str]
    ) -> dict[str, Any]:
        segments = output.get("segments", [])
        labels = [s["name"] for s in segments]
        values = [s["value"] for s in segments]

        trace = {
            "type": "pie",
            "labels": labels,
            "values": values,
            "hole": 0.45,
            "marker": {"colors": cls.COLOR_PALETTE[: len(labels)]},
            "textinfo": "label+percent",
        }
        dim = output.get("dimension", "").title()
        title = f"{output.get('metric_name', 'Metric')} Share by {dim}"
        layout = cls._base_layout(title, theme_cfg)
        layout["height"] = 350
        return {
            "data": [trace],
            "layout": layout,
            "config": {"responsive": True, "displayModeBar": False},
        }

    @classmethod
    def _build_time_series_line_spec(
        cls, output: dict[str, Any], theme_cfg: dict[str, str]
    ) -> dict[str, Any]:
        segments = output.get("segments", [])
        x = [s["name"] for s in segments]
        y = [s["value"] for s in segments]

        trace = {
            "type": "scatter",
            "mode": "lines+markers",
            "x": x,
            "y": y,
            "line": {"color": cls.COLOR_PALETTE[0], "width": 3},
            "marker": {"size": 8, "color": cls.COLOR_PALETTE[1]},
        }
        title = f"{output.get('metric_name', 'Metric')} Trend"
        layout = cls._base_layout(title, theme_cfg)
        layout["xaxis"] = {"gridcolor": theme_cfg["grid_color"]}
        layout["yaxis"] = {"gridcolor": theme_cfg["grid_color"]}
        layout["height"] = 340
        return {
            "data": [trace],
            "layout": layout,
            "config": {"responsive": True, "displayModeBar": False},
        }

    @classmethod
    def _build_dq_score_gauge_spec(
        cls, output: dict[str, Any], theme_cfg: dict[str, str]
    ) -> dict[str, Any]:
        score = output.get("overall_health_score", 98.0)
        trace = {
            "type": "indicator",
            "mode": "gauge+number",
            "value": score,
            "number": {"suffix": "%"},
            "title": {"text": "Overall Data Quality Score", "font": {"size": 14}},
            "gauge": {
                "axis": {"range": [0, 100]},
                "bar": {"color": "#10b981" if score >= 90 else "#f59e0b"},
                "steps": [
                    {"range": [0, 80], "color": "#fee2e2"},
                    {"range": [80, 95], "color": "#fef3c7"},
                    {"range": [95, 100], "color": "#d1fae5"},
                ],
            },
        }
        layout = cls._base_layout("Data Quality Health", theme_cfg)
        layout["height"] = 280
        return {
            "data": [trace],
            "layout": layout,
            "config": {"responsive": True, "displayModeBar": False},
        }
