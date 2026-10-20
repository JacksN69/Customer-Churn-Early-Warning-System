"""Build the 6-page German IBCS Power BI report definition (PBIR format)
inside `powerbi/Customer Churn Early-Warning System.pbix`.

Follows the IBCS 2.0 / ISO 24896:2026-inspired blueprint:
  01 Management-Übersicht
  02 Frühwarnsystem
  03 Kundenprofil 360° (Drillthrough on DimCustomer[customer_id])
  04 Risikotreiber
  05 Modellgüte
  06 Datenqualität
"""
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PBIX_PATH = ROOT / "powerbi" / "Customer Churn Early-Warning System.pbix"
BACKUP_DIR = ROOT / "powerbi" / "backups"

# IBCS Corporate Palette from Blueprint
COLOR_CANVAS = "#F7F8FA"
COLOR_VISUAL_BG = "#FFFFFF"
COLOR_TEXT = "#1F2937"
COLOR_MUTED = "#4B5563"
COLOR_ACCENT = "#285780"
COLOR_COMPARISON = "#A6B0BA"
COLOR_RISK = "#C64747"
COLOR_FAVORABLE = "#247C68"
COLOR_BORDER = "#E2E6EB"


def lit(val: str):
    return {"expr": {"Literal": {"Value": val}}}


def solid_color(hex_color: str):
    return {"solid": {"color": lit(f"'{hex_color}'")}}


def col_field(entity: str, prop: str):
    return {
        "Column": {
            "Expression": {"SourceRef": {"Entity": entity}},
            "Property": prop,
        }
    }


def measure_field(entity: str, prop: str):
    return {
        "Measure": {
            "Expression": {"SourceRef": {"Entity": entity}},
            "Property": prop,
        }
    }


def proj_col(entity: str, prop: str, display_name: str = None, active: bool = True):
    p = {
        "field": col_field(entity, prop),
        "queryRef": f"{entity}.{prop}",
        "nativeQueryRef": prop,
    }
    if active is not None:
        p["active"] = active
    if display_name:
        p["displayName"] = display_name
    return p


def proj_measure(entity: str, prop: str, display_name: str = None, active: bool = None):
    p = {
        "field": measure_field(entity, prop),
        "queryRef": f"{entity}.{prop}",
        "nativeQueryRef": prop,
    }
    if active is not None:
        p["active"] = active
    if display_name:
        p["displayName"] = display_name
    return p


def cat_filter(name: str, entity: str, prop: str, str_value: str, hidden: bool = True):
    return {
        "name": name,
        "field": col_field(entity, prop),
        "type": "Categorical",
        "filter": {
            "Version": 2,
            "From": [{"Name": "t", "Entity": entity, "Type": 0}],
            "Where": [
                {
                    "Condition": {
                        "In": {
                            "Expressions": [
                                {
                                    "Column": {
                                        "Expression": {"SourceRef": {"Source": "t"}},
                                        "Property": prop,
                                    }
                                }
                            ],
                            "Values": [[{"Literal": {"Value": f"'{str_value}'"}}]],
                        }
                    }
                }
            ],
        },
        "howCreated": "User",
        "isHiddenInViewMode": hidden,
    }


def container_formatting(title: str = None, subtitle: str = None, bg_color: str = COLOR_VISUAL_BG, border: bool = True):
    objs = {
        "background": [
            {
                "properties": {
                    "show": lit("true"),
                    "color": solid_color(bg_color),
                    "transparency": lit("0D"),
                }
            }
        ],
        "border": [
            {
                "properties": {
                    "show": lit("true" if border else "false"),
                    "color": solid_color(COLOR_BORDER),
                    "radius": lit("2D"),
                    "width": lit("1D"),
                }
            }
        ],
        "dropShadow": [{"properties": {"show": lit("false")}}],
    }
    if title:
        objs["title"] = [
            {
                "properties": {
                    "show": lit("true"),
                    "text": lit(f"'{title}'"),
                    "fontColor": solid_color(COLOR_TEXT),
                    "fontSize": lit("11D"),
                    "fontFamily": lit("'Segoe UI Semibold'"),
                    "bold": lit("true"),
                }
            }
        ]
    else:
        objs["title"] = [{"properties": {"show": lit("false")}}]

    if subtitle:
        objs["subTitle"] = [
            {
                "properties": {
                    "show": lit("true"),
                    "text": lit(f"'{subtitle}'"),
                    "fontColor": solid_color(COLOR_MUTED),
                    "fontSize": lit("9D"),
                    "fontFamily": lit("'Segoe UI'"),
                }
            }
        ]
    return objs


def make_visual_container(name: str, x: int, y: int, w: int, h: int, z: int, visual_dict: dict, filters: list = None):
    vc = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.5.0/schema.json",
        "name": name,
        "position": {
            "x": x,
            "y": y,
            "z": z,
            "width": w,
            "height": h,
            "tabOrder": z,
        },
        "visual": visual_dict,
    }
    if filters:
        vc["filterConfig"] = {"filters": filters}
    return vc


def make_textbox(name: str, x: int, y: int, w: int, h: int, z: int, lines: list, bg_color: str = COLOR_VISUAL_BG, border: bool = True):
    """lines is a list of dicts: {'text': str, 'size': str, 'bold': bool, 'color': str}"""
    paragraphs = []
    for ln in lines:
        run = {
            "value": ln["text"],
            "textStyle": {
                "fontFamily": "Segoe UI Semibold" if ln.get("bold") else "Segoe UI",
                "fontSize": ln.get("size", "10pt"),
                "color": ln.get("color", COLOR_TEXT),
            },
        }
        if ln.get("bold"):
            run["textStyle"]["fontWeight"] = "bold"
        paragraphs.append({"textRuns": [run]})

    visual = {
        "visualType": "textbox",
        "objects": {
            "general": [{"properties": {"paragraphs": paragraphs}}],
        },
        "visualContainerObjects": container_formatting(title=None, bg_color=bg_color, border=border),
        "drillFilterOtherVisuals": True,
    }
    return make_visual_container(name, x, y, w, h, z, visual)


def make_header(page_prefix: str, title_text: str, subtitle_text: str, active_tab: int):
    tabs = [
        "01 Übersicht",
        "02 Frühwarnsystem",
        "03 Kundenprofil 360°",
        "04 Risikotreiber",
        "05 Modellgüte",
        "06 Datenqualität",
    ]
    nav_parts = []
    for idx, t in enumerate(tabs, start=1):
        if idx == active_tab:
            nav_parts.append(f"[{t.upper()}]")
        else:
            nav_parts.append(t)
    nav_str = "   ·   ".join(nav_parts)

    return make_textbox(
        f"{page_prefix}_header",
        x=16, y=10, w=1408, h=54, z=10,
        lines=[
            {"text": f"{title_text}    |    {nav_str}", "size": "13pt", "bold": True, "color": COLOR_TEXT},
            {"text": subtitle_text, "size": "9pt", "bold": False, "color": COLOR_MUTED},
        ],
        bg_color=COLOR_VISUAL_BG,
        border=True,
    )


def make_footer(page_prefix: str, note_text: str):
    return make_textbox(
        f"{page_prefix}_footer",
        x=16, y=772, w=1408, h=28, z=20,
        lines=[
            {"text": note_text, "size": "8.5pt", "bold": False, "color": COLOR_MUTED},
        ],
        bg_color=COLOR_CANVAS,
        border=False,
    )


def make_card(name: str, x: int, y: int, w: int, h: int, z: int, entity: str, measure: str, title: str, subtitle: str = None):
    visual = {
        "visualType": "card",
        "query": {
            "queryState": {
                "Values": {
                    "projections": [proj_measure(entity, measure, display_name=title, active=True)]
                }
            }
        },
        "objects": {
            "categoryLabels": [{"properties": {"show": lit("false")}}],
            "labels": [
                {
                    "properties": {
                        "color": solid_color(COLOR_TEXT),
                        "fontSize": lit("20D"),
                        "fontFamily": lit("'Segoe UI Semibold'"),
                        "labelDisplayUnits": lit("1D"),
                    }
                }
            ],
        },
        "visualContainerObjects": container_formatting(title=title, subtitle=subtitle),
        "drillFilterOtherVisuals": True,
    }
    return make_visual_container(name, x, y, w, h, z, visual)


def make_slicer(name: str, x: int, y: int, w: int, h: int, z: int, entity: str, col: str, title: str):
    visual = {
        "visualType": "slicer",
        "query": {
            "queryState": {
                "Values": {
                    "projections": [proj_col(entity, col, display_name=title, active=True)]
                }
            }
        },
        "objects": {
            "data": [{"properties": {"mode": lit("'Dropdown'")}}],
            "header": [{"properties": {"show": lit("false")}}],
        },
        "visualContainerObjects": container_formatting(title=title),
        "drillFilterOtherVisuals": True,
    }
    return make_visual_container(name, x, y, w, h, z, visual)


def make_chart(
    name: str, visual_type: str, x: int, y: int, w: int, h: int, z: int,
    cat_proj: dict, y_projs: list, title: str, subtitle: str = None,
    tooltip_projs: list = None, sort_field: dict = None, sort_dir: str = "Descending",
    filters: list = None, show_labels: bool = True,
):
    q_state = {
        "Category": {"projections": [cat_proj]},
        "Y": {"projections": y_projs},
    }
    if tooltip_projs:
        q_state["Tooltips"] = {"projections": tooltip_projs}

    query = {"queryState": q_state}
    if sort_field:
        query["sortDefinition"] = {
            "sort": [{"field": sort_field, "direction": sort_dir}],
            "isDefaultSort": False,
        }

    visual = {
        "visualType": visual_type,
        "query": query,
        "objects": {
            "labels": [{"properties": {"show": lit("true" if show_labels else "false")}}],
        },
        "visualContainerObjects": container_formatting(title=title, subtitle=subtitle),
        "drillFilterOtherVisuals": True,
    }
    return make_visual_container(name, x, y, w, h, z, visual, filters=filters)


def make_table(
    name: str, x: int, y: int, w: int, h: int, z: int,
    projections: list, title: str, subtitle: str = None,
    sort_field: dict = None, sort_dir: str = "Descending", filters: list = None,
):
    query = {"queryState": {"Values": {"projections": projections}}}
    if sort_field:
        query["sortDefinition"] = {
            "sort": [{"field": sort_field, "direction": sort_dir}],
            "isDefaultSort": False,
        }
    visual = {
        "visualType": "tableEx",
        "query": query,
        "visualContainerObjects": container_formatting(title=title, subtitle=subtitle),
        "drillFilterOtherVisuals": True,
    }
    return make_visual_container(name, x, y, w, h, z, visual, filters=filters)


def make_matrix(
    name: str, x: int, y: int, w: int, h: int, z: int,
    row_proj: dict, col_proj: dict, val_projs: list, title: str, subtitle: str = None,
):
    query = {
        "queryState": {
            "Rows": {"projections": [row_proj]},
            "Columns": {"projections": [col_proj]},
            "Values": {"projections": val_projs},
        }
    }
    visual = {
        "visualType": "pivotTable",
        "query": query,
        "visualContainerObjects": container_formatting(title=title, subtitle=subtitle),
        "drillFilterOtherVisuals": True,
    }
    return make_visual_container(name, x, y, w, h, z, visual)


def make_page_json(name: str, display_name: str, filters: list = None, is_drillthrough: bool = False):
    page = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json",
        "name": name,
        "displayName": display_name,
        "displayOption": "FitToPage",
        "height": 810,
        "width": 1440,
        "objects": {
            "background": [
                {
                    "properties": {
                        "color": solid_color(COLOR_CANVAS),
                        "transparency": lit("0D"),
                    }
                }
            ],
            "outspace": [
                {
                    "properties": {
                        "color": solid_color(COLOR_CANVAS),
                    }
                }
            ],
        },
    }
    if is_drillthrough:
        page["type"] = "Drillthrough"
        page["pageBinding"] = {
            "name": "binding_drill_customer_360",
            "type": "Drillthrough",
            "referenceScope": "Default",
            "acceptsFilterContext": "Default",
            "parameters": [
                {
                    "name": "param_drill_customer_id",
                    "boundFilter": "filter_drill_customer_id",
                    "fieldExpr": col_field("DimCustomer", "customer_id"),
                }
            ],
        }
        page["filterConfig"] = {
            "filters": [
                {
                    "name": "filter_drill_customer_id",
                    "field": col_field("DimCustomer", "customer_id"),
                    "type": "Categorical",
                    "howCreated": "Drillthrough",
                }
            ]
        }
    elif filters:
        page["filterConfig"] = {"filters": filters}
    return page


def build_all_pages():
    pages = []

    # =========================================================================
    # PAGE 1: 01 Management-Übersicht
    # =========================================================================
    p1_id = "page01management0000"
    p1_filters = [cat_filter("f_p1_scoretype", "ChurnPredictions", "ScoreType", "Production (Dec 2023 -> Jan 2024)")]
    p1_visuals = [
        make_header(
            "p1",
            "01 Management-Übersicht — Kunden-Inaktivitätsrisiko & Fokusgruppen",
            "Bewertungsstichtag: Dezember 2023 · Prognosezeitraum: Januar 2024 (Prognose, keine bestätigte Kontoauflösung) · Währung: COP",
            active_tab=1,
        ),
        make_slicer("p1_sl_seg", 16, 70, 346, 54, 100, "DimCustomer", "customer_segment", "Kundensegment"),
        make_slicer("p1_sl_acq", 370, 70, 346, 54, 110, "DimCustomer", "acquisition_channel", "Akquisekanal"),
        make_slicer("p1_sl_loc", 724, 70, 346, 54, 120, "DimCustomer", "location", "Standort (Kolumbien)"),
        make_slicer("p1_sl_coh", 1078, 70, 346, 54, 130, "ChurnPredictions", "ScoreType", "Bewertungskohorte (Standard: Dez 2023)"),

        make_card("p1_kpi1", 16, 132, 275, 88, 200, "ChurnPredictions", "Bewertete aktive Kunden", "Bewertete aktive Kunden", "Aktive Kunden mit >= 6M Historie"),
        make_card("p1_kpi2", 299, 132, 275, 88, 210, "ChurnPredictions", "Kunden mit hohem/kritischem Risiko", "Kunden mit hohem/kritischem Risiko", "Validierter Schwellenwert (12,6 %)"),
        make_card("p1_kpi3", 582, 132, 275, 88, 220, "ChurnPredictions", "Werthaltige Risikokunden", "Werthaltige Risikokunden", "Hoher 3M-Wert + Hohes/Krit. Risiko"),
        make_card("p1_kpi4", 865, 132, 275, 88, 230, "ChurnPredictions", "Durchschnittliches Inaktivitätsrisiko", "Durchschnittliches Inaktivitätsrisiko", "Mittlere Prognose Jan 2024"),
        make_card("p1_kpi5", 1148, 132, 276, 88, 240, "ChurnPredictions", "Transaktionsvolumen 3M Hochrisiko (COP)", "3M-Volumen Hochrisikokunden (COP)", "Gefährdetes 3M-Transaktionsvolumen"),

        make_chart(
            "p1_ch_riskdist", "clusteredBarChart", 16, 228, 696, 262, 300,
            cat_proj=proj_col("ChurnPredictions", "RiskLevel", "Risikostufe"),
            y_projs=[proj_measure("ChurnPredictions", "Bewertete aktive Kunden", "Kundenanzahl")],
            tooltip_projs=[
                proj_measure("ChurnPredictions", "Anteil Risikostufe", "Anteil (%)"),
                proj_measure("ChurnPredictions", "Durchschnittliches Inaktivitätsrisiko", "Ø Inaktivitätsrisiko"),
                proj_measure("ChurnPredictions", "Transaktionsvolumen 3M Gefiltert (COP)", "3M-Volumen (COP)"),
            ],
            title="A. Risikoverteilung der bewerteten Kunden (Critical → Low)",
            subtitle="Anzahl und Anteil aktiver Kunden nach validierter Risikostufe (Prognose Januar 2024)",
            sort_field=col_field("ChurnPredictions", "RiskLevel"),
            sort_dir="Ascending",
        ),
        make_matrix(
            "p1_ch_matrix", 728, 228, 696, 262, 310,
            row_proj=proj_col("ChurnPredictions", "ValueSegment", "3M-Wertsegment"),
            col_proj=proj_col("ChurnPredictions", "RiskGroup2x2", "Risikokategorie"),
            val_projs=[
                proj_measure("ChurnPredictions", "Bewertete aktive Kunden", "Kundenanzahl"),
                proj_measure("ChurnPredictions", "Anteil Risikostufe", "Anteil (%)"),
            ],
            title="B. Risiko-Wert-Matrix (2×2 Priorisierungsmatrix)",
            subtitle="Kundenanzahl je Quadrant (Klick filtert Bericht · Fokus: 1.773 Hoher Wert + Hohes Risiko)",
        ),
        make_chart(
            "p1_ch_trend", "lineChart", 16, 498, 696, 266, 320,
            cat_proj=proj_col("DimDate", "YearMonth", "Beobachtungsmonat (T)"),
            y_projs=[proj_measure("ChurnFeatures", "Beobachtete Inaktivitätsquote (Historisch)", "Beobachtete Inaktivitätsquote (T+1)")],
            tooltip_projs=[proj_measure("ChurnFeatures", "Qualifizierte Aktive Kunden (Historisch)", "Qualifizierte aktive Kunden")],
            title="C. Monatliche Inaktivitätsquote (Beobachtet Jun–Nov 2023)",
            subtitle="Historischer Anteil aktiver Kunden (≥ 6M Historie), die im Folgemonat T+1 keine Transaktion tätigten",
            sort_field=col_field("DimDate", "YearMonth"),
            sort_dir="Ascending",
            filters=[cat_filter("f_p1_elig_months", "DimDate", "EligibleMonthFlag", "Ja")],
        ),
        make_chart(
            "p1_ch_segment", "clusteredBarChart", 728, 498, 696, 266, 330,
            cat_proj=proj_col("DimCustomer", "customer_segment", "Kundensegment"),
            y_projs=[proj_measure("ChurnPredictions", "Anteil Hoch-/Kritisch-Risiko", "Anteil Hoch-/Kritisch-Risiko (%)")],
            tooltip_projs=[
                proj_measure("ChurnPredictions", "Bewertete aktive Kunden", "Bewertete Kunden"),
                proj_measure("ChurnPredictions", "Kunden mit hohem/kritischem Risiko", "Hoch-/Kritisch-Risikokunden"),
                proj_measure("ChurnPredictions", "Transaktionsvolumen 3M Hochrisiko (COP)", "3M-Volumen Hochrisiko (COP)"),
            ],
            title="D. Risiko nach Kundensegment (Anteil High / Critical)",
            subtitle="Prozentualer Anteil von Kunden mit hohem/kritischem Risiko je Kundensegment (Tooltips zeigen Kundenanzahl)",
            sort_field=measure_field("ChurnPredictions", "Anteil Hoch-/Kritisch-Risiko"),
            sort_dir="Descending",
        ),
        make_footer(
            "p1",
            "Methodischer Hinweis: Dezember-Scores sind unbestätigte Prognosen für Januar 2024 (keine Jan-2024-Beobachtungen vorhanden). "
            "4.872 Kunden (12,6 %) überschreiten den validierten Schwellenwert (Okt 2023); das exakte Top-10%-Kapazitätsranking umfasst 3.854 Kunden.",
        ),
    ]
    pages.append((p1_id, make_page_json(p1_id, "01 Management-Übersicht", filters=p1_filters), p1_visuals))

    # =========================================================================
    # PAGE 2: 02 Frühwarnsystem
    # =========================================================================
    p2_id = "page02fruehwarnsys00"
    p2_filters = [cat_filter("f_p2_scoretype", "ChurnPredictions", "ScoreType", "Production (Dec 2023 -> Jan 2024)")]
    p2_visuals = [
        make_header(
            "p2",
            "02 Operatives Frühwarnsystem — Kundenpriorisierung & Retention-Monitor",
            "Operative Prioritätsliste (Standardsortierung: PriorityScore absteigend) · Rechtsklick auf customer_id → Drillthrough zu „03 Kundenprofil 360°“",
            active_tab=2,
        ),
        make_slicer("p2_sl_1", 16, 70, 194, 54, 100, "ChurnPredictions", "RiskLevel", "Risikostufe"),
        make_slicer("p2_sl_2", 218, 70, 214, 54, 110, "ChurnPredictions", "PriorityQuadrant", "Wert-Risiko-Quadrant"),
        make_slicer("p2_sl_3", 440, 70, 184, 54, 120, "DimCustomer", "location", "Standort"),
        make_slicer("p2_sl_4", 632, 70, 184, 54, 130, "DimCustomer", "income_bracket", "Einkommensklasse"),
        make_slicer("p2_sl_5", 824, 70, 184, 54, 140, "DimCustomer", "acquisition_channel", "Akquisekanal"),
        make_slicer("p2_sl_6", 1016, 70, 194, 54, 150, "ChurnPredictions", "PreferredTransactionType", "Transaktionsart"),
        make_slicer("p2_sl_7", 1218, 70, 206, 54, 160, "DimCustomer", "CreditUtilizationStatus", "Kreditkarten-Status"),

        make_card("p2_kpi1", 16, 132, 346, 82, 200, "ChurnPredictions", "Bewertete aktive Kunden", "Gefilterte Kunden", "Aktuelle Auswahl in der Queue"),
        make_card("p2_kpi2", 370, 132, 346, 82, 210, "ChurnPredictions", "Kunden mit hohem/kritischem Risiko", "Hohe Priorität (High/Critical)", "Validierter Schwellenwert ≥ 0,3179"),
        make_card("p2_kpi3", 724, 132, 346, 82, 220, "ChurnPredictions", "Werthaltige Risikokunden", "Hoher Wert + Hohes Risiko", "Primäre Retention-Zielgruppe"),
        make_card("p2_kpi4", 1078, 132, 346, 82, 230, "ChurnPredictions", "Transaktionsvolumen 3M Gefiltert (COP)", "3M-Wertvolumen (COP)", "Transaktionsvolumen der Auswahl"),

        make_table(
            "p2_tbl_queue", 16, 222, 960, 542, 300,
            projections=[
                proj_col("DimCustomer", "customer_id", "Kunde (ID)"),
                proj_col("ChurnPredictions", "RiskRank", "Risiko-Rang"),
                proj_col("ChurnPredictions", "InactiveProbability", "Inaktivitätsrisiko"),
                proj_col("ChurnPredictions", "RiskLevel", "Risikostufe"),
                proj_col("ChurnPredictions", "PriorityQuadrant", "Prioritätsquadrant"),
                proj_col("ChurnPredictions", "PriorityScore", "Priority Score"),
                proj_col("ChurnPredictions", "TransactionCount", "Trans. (Dez)"),
                proj_col("ChurnPredictions", "TransactionCount_Recent3M", "Trans. (3M)"),
                proj_col("ChurnPredictions", "TotalAmount_Recent3M", "Volumen 3M (COP)"),
                proj_col("ChurnPredictions", "DaysSinceLastTransaction", "Tage seit Trans."),
                proj_col("ChurnPredictions", "TopDriver1", "KI-Treiber 1"),
                proj_col("ChurnPredictions", "TopDriver1Impact", "SHAP 1"),
                proj_col("ChurnPredictions", "TopDriver2", "KI-Treiber 2"),
                proj_col("ChurnPredictions", "TopDriver3", "KI-Treiber 3"),
            ],
            title="Operative Kundenpriorisierung (Sortiert nach PriorityScore = Risiko × 3M-Volumen)",
            subtitle="Kundenliste aus LightGBM-Modelloutput · Rechtsklick auf Kunde (ID) → Drillthrough → 03 Kundenprofil 360°",
            sort_field=col_field("ChurnPredictions", "PriorityScore"),
            sort_dir="Descending",
        ),
        make_chart(
            "p2_ch_deciles", "clusteredColumnChart", 984, 222, 440, 266, 310,
            cat_proj=proj_col("ChurnPredictions", "RiskDecile", "Risiko-Dezil (1 = Höchstes)"),
            y_projs=[proj_measure("ChurnPredictions", "Bewertete aktive Kunden", "Kundenanzahl")],
            tooltip_projs=[
                proj_measure("ChurnPredictions", "Durchschnittliches Inaktivitätsrisiko", "Ø Inaktivitätsrisiko"),
                proj_measure("ChurnPredictions", "Transaktionsvolumen 3M Gefiltert (COP)", "3M-Volumen (COP)"),
            ],
            title="Kunden nach Risiko-Dezil (1 = Top 10 % Risiko)",
            subtitle="Klick auf Dezil 1 filtert die exakten Top 10 % (3.854 Kunden)",
            sort_field=col_field("ChurnPredictions", "RiskDecile"),
            sort_dir="Ascending",
        ),
        make_chart(
            "p2_ch_quadvol", "clusteredBarChart", 984, 496, 440, 268, 320,
            cat_proj=proj_col("ChurnPredictions", "PriorityQuadrant", "Prioritätsquadrant"),
            y_projs=[proj_measure("ChurnPredictions", "Transaktionsvolumen 3M Gefiltert (COP)", "3M-Volumen (COP)")],
            tooltip_projs=[
                proj_measure("ChurnPredictions", "Bewertete aktive Kunden", "Kundenanzahl"),
                proj_measure("ChurnPredictions", "Durchschnittliches Inaktivitätsrisiko", "Ø Inaktivitätsrisiko"),
            ],
            title="3M-Transaktionsvolumen (COP) nach Prioritätsquadrant",
            subtitle="Wertvolumen zur Ressourcenallokation im Retention-Team",
            sort_field=col_field("ChurnPredictions", "PriorityQuadrant"),
            sort_dir="Ascending",
        ),
        make_footer(
            "p2",
            "Bedienhinweis: Standardmäßig absteigend nach PriorityScore sortiert (Klick auf Spaltenkopf „Inaktivitätsrisiko“ oder „Risiko-Rang“ wechselt zur reinen Risikoreihung). "
            "Klick auf Dezil 1 im Diagramm rechts oben wählt die exakte 10%-Kapazitätsgrenze (3.854 Kunden).",
        ),
    ]
    pages.append((p2_id, make_page_json(p2_id, "02 Frühwarnsystem", filters=p2_filters), p2_visuals))

    # =========================================================================
    # PAGE 3: 03 Kundenprofil 360° (Drill-through Page)
    # =========================================================================
    p3_id = "page03kundenprofil00"
    p3_visuals = [
        make_header(
            "p3",
            "03 Kundenprofil 360° — Einzelkunden-Analyse & Lokale KI-Erklärung (Drillthrough)",
            "Historisches Transaktionsverhalten (Jan–Dez 2023) vs. Aktiver Kunden-Benchmark · Top-3 lokale SHAP-Treiber in Log-Odds",
            active_tab=3,
        ),
        make_card("p3_kpi1", 16, 72, 275, 84, 100, "ChurnPredictions", "Kunden-ID Auswahl", "Ausgewählter Kunde (ID)", "Drillthrough-Fokus von Seite 2"),
        make_card("p3_kpi2", 299, 72, 275, 84, 110, "ChurnPredictions", "Kunden Inaktivitätsrisiko (Dez 2023)", "Inaktivitätsrisiko (Dez 2023)", "Prognose für Januar 2024"),
        make_card("p3_kpi3", 582, 72, 275, 84, 120, "ChurnPredictions", "Kunden Risiko-Rang (Dez 2023)", "Risiko-Rang (Dez 2023)", "Rang unter 38.531 aktiven Kunden"),
        make_card("p3_kpi4", 865, 72, 275, 84, 130, "ChurnPredictions", "Kunden Prioritätsquadrant (Dez 2023)", "Prioritätsquadrant", "Wert- × Risikoklassifikation"),
        make_card("p3_kpi5", 1148, 72, 276, 84, 140, "ChurnPredictions", "Kunden Tage seit letzter Transaktion (Dez 2023)", "Tage seit letzter Transaktion", "Stand Ende Dezember 2023"),

        make_chart(
            "p3_ch_act_bench", "lineChart", 16, 164, 696, 292, 200,
            cat_proj=proj_col("DimDate", "YearMonth", "Monat (2023)"),
            y_projs=[
                proj_measure("ChurnFeatures", "Kunden Transaktionen (Monat)", "Ausgewählter Kunde (Transaktionen)"),
                proj_measure("ChurnFeatures", "Benchmark Aktive Kunden Transaktionen", "Ø Aktive Kunden (Benchmark)"),
            ],
            title="Monatliche Transaktionsaktivität vs. Benchmark aktiver Kunden (Jan–Dez 2023)",
            subtitle="Zeigt das chronische Aktivitätsniveau des Kunden im Vergleich zum Monatsdurchschnitt aktiver Kunden",
            sort_field=col_field("DimDate", "YearMonth"),
            sort_dir="Ascending",
        ),
        make_chart(
            "p3_ch_shap_bars", "clusteredBarChart", 728, 164, 360, 292, 210,
            cat_proj=proj_col("DriverRankSlot", "DriverSlot", "SHAP-Treiber-Rang"),
            y_projs=[proj_measure("ChurnPredictions", "SHAP Treiber Einfluss (Log-Odds)", "SHAP-Beitrag (Log-Odds)")],
            tooltip_projs=[
                proj_measure("ChurnPredictions", "SHAP Treiber Bezeichnung", "Merkmal & Wert"),
                proj_measure("ChurnPredictions", "SHAP Treiber Wert", "Merkmalswert"),
            ],
            title="KI-Modellerklärung (Divergierende SHAP-Treiber)",
            subtitle="Positiv (+) erhöht Inaktivitätsrisiko · Negativ (-) senkt Risiko",
            sort_field=col_field("DriverRankSlot", "DriverSlot"),
            sort_dir="Ascending",
        ),
        make_table(
            "p3_tbl_shap_detail", 1096, 164, 328, 292, 220,
            projections=[
                proj_col("DriverRankSlot", "DriverSlot", "Rang"),
                proj_measure("ChurnPredictions", "SHAP Treiber Name", "Merkmal (Feature)"),
                proj_measure("ChurnPredictions", "SHAP Treiber Wert", "Kundenwert"),
                proj_measure("ChurnPredictions", "SHAP Treiber Einfluss (Log-Odds)", "SHAP (Log-Odds)"),
            ],
            title="SHAP-Treiber Details (Top 1–3)",
            subtitle="Merkmalsausprägung & Log-Odds-Einfluss",
            sort_field=col_field("DriverRankSlot", "DriverSlot"),
            sort_dir="Ascending",
        ),
        make_chart(
            "p3_ch_vol_cop", "clusteredColumnChart", 16, 464, 696, 300, 230,
            cat_proj=proj_col("DimDate", "YearMonth", "Monat (2023)"),
            y_projs=[proj_measure("ChurnFeatures", "Kunden Transaktionsvolumen (COP)", "Monatsvolumen (COP)")],
            tooltip_projs=[proj_measure("ChurnFeatures", "Kunden Transaktionen (Monat)", "Transaktionsanzahl")],
            title="Monatliches Transaktionsvolumen in COP (Jan–Dez 2023)",
            subtitle="Beobachtetes Transaktionsvolumen ab erstem Beobachtungsmonat (0-Monate explizit im Raster enthalten)",
            sort_field=col_field("DimDate", "YearMonth"),
            sort_dir="Ascending",
        ),
        make_table(
            "p3_tbl_profile", 728, 464, 696, 300, 240,
            projections=[
                proj_col("DimCustomer", "customer_id", "Kunden-ID"),
                proj_col("DimCustomer", "customer_segment", "Segment"),
                proj_col("DimCustomer", "location", "Standort"),
                proj_col("DimCustomer", "income_bracket", "Einkommen"),
                proj_col("DimCustomer", "acquisition_channel", "Akquisekanal"),
                proj_col("DimCustomer", "active_products", "Aktive Produkte"),
                proj_col("DimCustomer", "CreditUtilizationStatus", "Kreditkarten-Auslastung"),
                proj_col("DimCustomer", "satisfaction_score", "Zufriedenheit"),
                proj_col("DimCustomer", "support_tickets_count", "Support-Tickets"),
                proj_col("DimCustomer", "FeatureRequestsDisplay", "Feature-Anfragen"),
                proj_col("DimCustomer", "ComplaintTopicsDisplay", "Beschwerdethemen"),
            ],
            title="Kundenprofil & Service-Kontext (Deskriptive Anzeige — Nicht für ML-Training verwendet)",
            subtitle="Verwendet sichere Anzeigespalten (CreditUtilizationStatus, FeatureRequestsDisplay, ComplaintTopicsDisplay)",
        ),
        make_footer(
            "p3",
            "Methodischer Hinweis: Künftige Inaktivität ist primär mit chronisch geringer Transaktionsfrequenz assoziiert (~1,4 vs. 7,8 Trans./Mon.), "
            "nicht mit einem plötzlichen Rückgang. Fehlende Kreditkartenauslastung bei Nicht-Karteninhabern wird explizit als „No credit card“ dargestellt.",
        ),
    ]
    pages.append((p3_id, make_page_json(p3_id, "03 Kundenprofil 360°", is_drillthrough=True), p3_visuals))

    # =========================================================================
    # PAGE 4: 04 Risikotreiber
    # =========================================================================
    p4_id = "page04risikotreiber0"
    p4_visuals = [
        make_header(
            "p4",
            "04 Risikotreiber & Verhaltensmuster — Explainable AI (SHAP) & Empirische Evidenz",
            "Globale SHAP-Einflussfaktoren (Out-of-Sample Test Nov 2023) & Beobachtete Inaktivitätsraten (Jun–Nov 2023, N = 224.360 Kundenmonate)",
            active_tab=4,
        ),
        make_chart(
            "p4_ch_shap_global", "clusteredBarChart", 16, 72, 696, 340, 100,
            cat_proj=proj_col("FeatureImportance", "feature", "Modellmerkmal (Feature)"),
            y_projs=[proj_measure("FeatureImportance", "Globale SHAP Bedeutung (Test)", "Mittlerer |SHAP|-Wert (Log-Odds, Nov Test)")],
            tooltip_projs=[
                proj_measure("FeatureImportance", "Globale SHAP Bedeutung (Dez Scoring)", "Mittlerer |SHAP|-Wert (Dez Scoring)"),
                proj_measure("FeatureImportance", "SHAP Werte-Korrelation (Test)", "Korrelation Merkmalswert ↔ SHAP"),
            ],
            title="1. Globale Modelleinflussfaktoren — Top 15 nach mittlerem |SHAP|-Beitrag (Log-Odds)",
            subtitle="Dominante Modelltreiber: 6M- & 3M-Transaktionsfrequenz (AvgTransactionCount_6M, TransactionCount_Previous3M, Recent3M)",
            sort_field=measure_field("FeatureImportance", "Globale SHAP Bedeutung (Test)"),
            sort_dir="Descending",
            filters=[cat_filter("f_p4_top15", "FeatureImportance", "IsTop15", "Ja")],
        ),
        make_chart(
            "p4_ch_recency", "clusteredColumnChart", 728, 72, 696, 340, 110,
            cat_proj=proj_col("ChurnFeatures", "RecencyBin", "Tage seit letzter Transaktion (Recency-Gruppen)"),
            y_projs=[proj_measure("ChurnFeatures", "Beobachtete Inaktivitätsquote (Verhalten)", "Beobachtete Inaktivitätsquote (T+1)")],
            tooltip_projs=[proj_measure("ChurnFeatures", "Qualifizierte Aktive Kunden (Historisch)", "Kundenmonate (Nenner)")],
            title="2. Beobachtete Inaktivitätsquote nach Transaktionsabstand (Recency: 8,2 % → 24,9 %)",
            subtitle="Monotoner Anstieg der Inaktivitätsrate von 8,2 % (Transaktion am Monatsende) auf 24,9 % (22–31 Tage Abstand)",
            sort_field=col_field("ChurnFeatures", "RecencyBin"),
            sort_dir="Ascending",
            filters=[cat_filter("f_p4_elig_rec", "ChurnFeatures", "EligibleRowFlag", "Ja")],
        ),
        make_chart(
            "p4_ch_activity", "clusteredColumnChart", 16, 420, 696, 344, 120,
            cat_proj=proj_col("ChurnFeatures", "ActivityBin", "6-Monats-Aktivitätsfrequenz (AvgTransactionCount_6M)"),
            y_projs=[proj_measure("ChurnFeatures", "Beobachtete Inaktivitätsquote (Verhalten)", "Beobachtete Inaktivitätsquote (T+1)")],
            tooltip_projs=[proj_measure("ChurnFeatures", "Qualifizierte Aktive Kunden (Historisch)", "Kundenmonate (Nenner)")],
            title="3. Beobachtete Inaktivitätsquote nach 6-Monats-Aktivitätshäufigkeit",
            subtitle="Kunden mit chronisch niedriger Frequenz (<= 1,5 Trans./Mon.) weisen das höchste Inaktivitätsrisiko auf",
            sort_field=col_field("ChurnFeatures", "ActivityBin"),
            sort_dir="Ascending",
            filters=[cat_filter("f_p4_elig_act", "ChurnFeatures", "EligibleRowFlag", "Ja")],
        ),
        make_chart(
            "p4_ch_txmix", "hundredPercentStackedBarChart", 728, 420, 696, 344, 130,
            cat_proj=proj_col("ChurnPredictions", "RiskLevel", "Risikostufe"),
            y_projs=[
                proj_measure("ChurnPredictions", "Anteil Überweisungen (Transfer %)", "Transfer (%)"),
                proj_measure("ChurnPredictions", "Anteil Zahlungen (Payment %)", "Payment (%)"),
                proj_measure("ChurnPredictions", "Anteil Abhebungen (Withdrawal %)", "Withdrawal (%)"),
                proj_measure("ChurnPredictions", "Anteil Einzahlungen (Deposit %)", "Deposit (%)"),
            ],
            title="4. Gewichteter Transaktionsmix nach Risikostufe (Payment, Transfer, Withdrawal, Deposit)",
            subtitle="Berechnet über reale Transaktionsanzahlen (Transfer ~45 %, Payment ~31 %, Withdrawal ~14 %, Deposit ~10 %)",
            sort_field=col_field("ChurnPredictions", "RiskLevel"),
            sort_dir="Ascending",
            filters=[cat_filter("f_p4_dec_mix", "ChurnPredictions", "ScoreType", "Production (Dec 2023 -> Jan 2024)")],
        ),
        make_footer(
            "p4",
            "Methodische Einordnung: SHAP-Werte repräsentieren Modelltreiber (Erklärung der Modelllogik auf Out-of-Sample-Daten Nov 2023), keine kausalen Effekte. "
            "Beobachtete Raten basieren auf allen 224.360 qualifizierten Kundenmonaten (Jun–Nov 2023).",
        ),
    ]
    pages.append((p4_id, make_page_json(p4_id, "04 Risikotreiber"), p4_visuals))

    # =========================================================================
    # PAGE 5: 05 Modellgüte
    # =========================================================================
    p5_id = "page05modellguete000"
    p5_visuals = [
        make_header(
            "p5",
            "05 Modellgüte & Validierung — Out-of-Sample Bewertung & Kalibrierung (Nov 2023)",
            "Ausgewähltes Modell: lightgbm_leaves31 (61 Features) · Train: Jun–Sep (148.628) | Val: Okt (36.854) | Test: Nov 2023 (38.878, Prävalenz 18,86 %)",
            active_tab=5,
        ),
        make_card("p5_kpi1", 16, 72, 194, 82, 100, "ChurnPredictions", "Test ROC-AUC", "ROC-AUC (Nov Test)", "Out-of-Sample Trennschärfe"),
        make_card("p5_kpi2", 218, 72, 194, 82, 110, "ChurnPredictions", "Test PR-AUC", "PR-AUC (Nov Test)", "Basislinie (Prävalenz): 0,1886"),
        make_card("p5_kpi3", 420, 72, 194, 82, 120, "ChurnPredictions", "Test Precision @ Top 10 %", "Precision @ Top 10 %", "Trefferquote Top-10%-Kapazität"),
        make_card("p5_kpi4", 622, 72, 194, 82, 130, "ChurnPredictions", "Test Recall @ Top 10 %", "Recall @ Top 10 %", "Erfasste Inaktivitätsfälle"),
        make_card("p5_kpi5", 824, 72, 194, 82, 140, "ChurnPredictions", "Test Lift @ Top 10 %", "Lift @ Top 10 %", "Mehrwert ggü. Zufallsauswahl"),
        make_card("p5_kpi6", 1026, 72, 194, 82, 150, "ChurnPredictions", "Test Brier Score", "Brier Score", "Mittlerer quadr. Prognosefehler"),
        make_card("p5_kpi7", 1228, 72, 196, 82, 160, "ChurnPredictions", "Test ECE (Kalibrierungsfehler)", "Expected Calibration Error", "Sehr gute Kalibrierung (1,52 %)"),

        make_chart(
            "p5_ch_calib", "lineChart", 16, 162, 696, 296, 200,
            cat_proj=proj_col("CalibrationDeciles", "DecileLabel", "Risiko-Dezil (Test Nov 2023, 01 = Höchstes Risiko)"),
            y_projs=[
                proj_measure("CalibrationDeciles", "Kalibrierung Prognostiziertes Risiko", "Ø Prognostizierte Wahrscheinlichkeit"),
                proj_measure("CalibrationDeciles", "Kalibrierung Beobachtete Inaktivität", "Beobachtete Inaktivitätsrate (Tatsächlich)"),
            ],
            title="1. Kalibrierungskurve nach Risiko-Dezil (Out-of-Sample Test November 2023)",
            subtitle="Gegenüberstellung von mittlerer prognostizierter Wahrscheinlichkeit und beobachteter Rate je Dezil (ECE = 0,0152)",
            sort_field=col_field("CalibrationDeciles", "DecileLabel"),
            sort_dir="Ascending",
        ),
        make_table(
            "p5_tbl_cm", 728, 162, 696, 296, 210,
            projections=[
                proj_col("ConfusionMatrixTable", "MatrixCell", "Klassifikation"),
                proj_col("ConfusionMatrixTable", "ActualClass", "Tatsächlicher Status (Dez)"),
                proj_col("ConfusionMatrixTable", "PredictedClass", "Modell-Entscheidung"),
                proj_measure("ConfusionMatrixTable", "Konfusionsmatrix Kundenanzahl", "Kundenanzahl"),
                proj_measure("ConfusionMatrixTable", "Konfusionsmatrix Anteil", "Anteil an Testkohorte"),
            ],
            title="2. Konfusionsmatrix am dokumentierten operativen Schwellenwert (p ≥ 0,3179 · Test Nov 2023)",
            subtitle="Markiert 3.514 Kunden (9,0 % der Testkohorte): TN = 29.221 | FP = 2.325 | FN = 6.143 | TP = 1.189",
            sort_field=col_field("ConfusionMatrixTable", "MatrixCell"),
            sort_dir="Ascending",
        ),
        make_table(
            "p5_tbl_models", 16, 466, 696, 298, 220,
            projections=[
                proj_col("ModelExperiments", "Modellvariante", "Modellkandidat"),
                proj_col("ModelExperiments", "feature_set", "Feature-Set"),
                proj_col("ModelExperiments", "n_features", "Features"),
                proj_measure("ModelExperiments", "Validierungs-PR-AUC", "Validierungs-PR-AUC (Okt)"),
                proj_measure("ModelExperiments", "Validierungs-ROC-AUC", "Validierungs-ROC-AUC (Okt)"),
                proj_col("ModelExperiments", "ModellStatus", "Status & Entscheidung"),
            ],
            title="3. Modellvergleich auf dem Oktober-Validierungsfenster (Auswahlkriterium: PR-AUC)",
            subtitle="LightGBM (0,3123) schlägt Logistische Regression (0,2907); statisches Kundenprofil (0,3054) bringt keinen Mehrwert",
            sort_field=measure_field("ModelExperiments", "Validierungs-PR-AUC"),
            sort_dir="Descending",
        ),
        make_table(
            "p5_tbl_policies", 728, 466, 696, 298, 230,
            projections=[
                proj_col("ThresholdPolicyTable", "PolicyName", "Schwellenwert-Politik"),
                proj_col("ThresholdPolicyTable", "RuleDescription", "Definition & Nenner"),
                proj_col("ThresholdPolicyTable", "FlaggedCustomers", "Markierte Kunden"),
                proj_measure("ThresholdPolicyTable", "Schwellenwert Flagged Share", "Markierter Anteil"),
                proj_measure("ThresholdPolicyTable", "Schwellenwert Precision", "Precision"),
                proj_measure("ThresholdPolicyTable", "Schwellenwert Recall", "Recall"),
                proj_measure("ThresholdPolicyTable", "Schwellenwert F1", "F1-Score"),
            ],
            title="4. Precision- / Recall-Vergleich: Kapazitäts-Ranking vs. Fester Schwellenwert",
            subtitle="Unterscheidung zwischen exakter Top-10%-Quote (3.888 Kunden) und festem Validierungs-Cutoff p ≥ 0,3179 (3.514 Kunden)",
            sort_field=col_field("ThresholdPolicyTable", "PolicyName"),
            sort_dir="Ascending",
        ),
        make_footer(
            "p5",
            "Methodische Offenlegung: Im November-Test weisen Critical (34,6 %), High (32,8 %) und Medium (33,2 %) nahezu identische beobachtete Inaktivitätsraten auf "
            "(vs. Low 12,8 %). Das Modell trennt primär eine erhöhte Risikogruppe (Medium+) vom Rest; innerhalb dieser Gruppe dient PriorityScore zur Feinreihung.",
        ),
    ]
    pages.append((p5_id, make_page_json(p5_id, "05 Modellgüte"), p5_visuals))

    # =========================================================================
    # PAGE 6: 06 Datenqualität
    # =========================================================================
    p6_id = "page06datenqualitaet"
    p6_visuals = [
        make_header(
            "p6",
            "06 Datenqualität, Governance & Methodik — ETL-Abstimmung & Leakage-Kontrolle",
            "Vollständige Abstimmung von 3.159.157 Roh-Transaktionen über 48.723 Kunden und 569.706 Kundenmonate · 0 verwaiste Schlüssel",
            active_tab=6,
        ),
        make_card("p6_kpi1", 16, 72, 228, 82, 100, "ChurnFeatures", "Geprüfte Roh-Transaktionen", "Transaktionen (Roh = ETL)", "100 % abgestimmt (3.159.157)"),
        make_card("p6_kpi2", 252, 72, 228, 82, 110, "DimCustomer", "Eindeutige Kunden Gesamt", "Validierte Kunden", "Eindeutige customer_id (48.723)"),
        make_card("p6_kpi3", 488, 72, 228, 82, 120, "ChurnFeatures", "Kundenmonate Gesamt", "Kundenmonate (Jan–Dez)", "Vollständiges Monatsraster"),
        make_card("p6_kpi4", 724, 72, 228, 82, 130, "ChurnFeatures", "Monate ohne Transaktionen", "Monate ohne Transaktionen", "Explizite 0-Monate (17,9 %)"),
        make_card("p6_kpi5", 960, 72, 228, 82, 140, "ChurnFeatures", "Trainingsfähige Beobachtungen", "Trainingsfähige Zeilen", "Jun–Nov, aktiv in T, ≥ 6M Hist."),
        make_card("p6_kpi6", 1196, 72, 228, 82, 150, "ChurnFeatures", "Verwaiste Schlüssel (Orphans)", "Verwaiste Schlüssel", "0 unzugeordnete Transaktionen"),

        make_chart(
            "p6_ch_coverage", "clusteredColumnChart", 16, 162, 696, 296, 200,
            cat_proj=proj_col("DimDate", "YearMonth", "Monat (2023)"),
            y_projs=[
                proj_measure("ChurnFeatures", "Aktive Kundenmonate", "Aktive Kundenmonate (> 0 Trans.)"),
                proj_measure("ChurnFeatures", "Monate ohne Transaktionen", "Monate ohne Transaktionen (0 Trans.)"),
                proj_measure("ChurnFeatures", "Trainingsfähige Beobachtungen", "ML-Qualifiziert (Jun–Nov)"),
            ],
            tooltip_projs=[proj_col("DimDate", "PipelinePhase", "Pipeline-Phase", active=None)],
            title="1. Monatliche Datenabdeckung & Trainings-/Bewertungszeiträume (Jan–Dez 2023)",
            subtitle="Jan–Mai: 6M-Historie-Aufbau | Jun–Sep: Training | Okt: Validierung | Nov: Out-of-Sample Test | Dez: Produktion Scoring",
            sort_field=col_field("DimDate", "YearMonth"),
            sort_dir="Ascending",
        ),
        make_table(
            "p6_tbl_checks", 728, 162, 696, 296, 210,
            projections=[
                proj_col("DataQualityChecks", "CheckOrder", "Nr."),
                proj_col("DataQualityChecks", "Category", "Prüfbereich"),
                proj_col("DataQualityChecks", "CheckName", "Qualitätsprüfung (Gate)"),
                proj_col("DataQualityChecks", "MetricValue", "Validiertes Ergebnis"),
                proj_col("DataQualityChecks", "Status", "Status"),
                proj_col("DataQualityChecks", "MethodologyNote", "Methodische Erläuterung"),
            ],
            title="2. Datenqualitätsprüfung & Reproduzierbare ETL-Gates (DuckDB / Parquet)",
            subtitle="Validierte Prüfergebnisse aus scripts/build_parquet_pipeline.py und src/features/validate_features.py",
            sort_field=col_field("DataQualityChecks", "CheckOrder"),
            sort_dir="Ascending",
        ),
        make_table(
            "p6_tbl_registry", 16, 466, 696, 298, 220,
            projections=[
                proj_col("FeatureRegistry", "table", "Tabelle"),
                proj_col("FeatureRegistry", "column", "Spalte / Feature"),
                proj_col("FeatureRegistry", "historical_ml_policy", "ML-Politik"),
                proj_col("FeatureRegistry", "ml_allowed", "ML Erlaubt"),
                proj_col("FeatureRegistry", "leakage_risk", "Leakage-Risiko"),
                proj_col("FeatureRegistry", "rationale", "Begründung & Zeitliche Verfügbarkeit"),
            ],
            title="3. Feature-Governance & Leakage-Kontrolle (FEATURE_REGISTRY.csv — 112 Spalten)",
            subtitle="Dokumentiert für jedes Attribut die historische Verfügbarkeit zum Zeitpunkt T sowie Ausschlussgründe",
            sort_field=col_field("FeatureRegistry", "table"),
            sort_dir="Ascending",
        ),
        make_textbox(
            "p6_txt_methodology", 728, 466, 696, 298, 230,
            lines=[
                {"text": "4. Datenpipeline, Zeitachsen-Design & Methodische Einschränkungen", "size": "11pt", "bold": True, "color": COLOR_TEXT},
                {"text": "Reproduzierbare Architektur (Python · DuckDB · LightGBM · SHAP · Power BI):", "size": "9.5pt", "bold": True, "color": COLOR_ACCENT},
                {"text": "Roh-CSVs (3.159.157 Trans.)  →  Kunden-Monats-Raster (569.706 Zeilen)  →  61 Verhaltens-Features  →  LightGBM (Chronologisch)  →  SHAP & Scoring  →  Power BI Sternschema", "size": "8.5pt", "bold": False, "color": COLOR_TEXT},
                {"text": "1. Zieldefinition (Keine Kontoauflösung): InactiveNextMonth = 1 bedeutet 0 Transaktionen im Folgemonat T+1 bei aktiven Kunden in T (mit >= 6 Monaten Historie).", "size": "8.5pt", "bold": False, "color": COLOR_TEXT},
                {"text": "2. Transiente Inaktivität (72,6 % Wiederaktivierung): 72,6 % der Kunden mit InactiveNextMonth = 1 transagieren bereits in T+2 wieder; ExtendedInactivityNext3Months liegt bei nur 1,3 %. Das Modell warnt vor Nutzungspausen.", "size": "8.5pt", "bold": False, "color": COLOR_TEXT},
                {"text": "3. Strenge Temporale Leakage-Kontrolle: Der undatierte DimCustomer-Snapshot (Zufriedenheit, NPS, Support, CLV) sowie churn_probability sind für das ML-Training gesperrt und dienen ausschließlich der BI-Ansicht.", "size": "8.5pt", "bold": False, "color": COLOR_TEXT},
                {"text": "4. Ausschluss von ObservedTenureMonths: Da ~80 % der Kunden im Januar 2023 starten, ist die beobachtete Laufzeit ein Kalender-Proxy (Test/Scoring außerhalb des Trainingsbereichs).", "size": "8.5pt", "bold": False, "color": COLOR_TEXT},
                {"text": "5. Interpretierbarkeit vs. Kausalität: SHAP-Werte erklären die Modellvorhersage in Log-Odds, beweisen jedoch keine kausalen Ursachen.", "size": "8.5pt", "bold": False, "color": COLOR_TEXT},
            ],
            bg_color=COLOR_VISUAL_BG,
            border=True,
        ),
        make_footer(
            "p6",
            "Governance-Zusammenfassung: Identische Transaktionen wurden gemäß Datenrichtlinie nicht dedupliziert (keine Transaktions-ID im Quellsystem). "
            "Alle 19 automatisierten Pytest-Tests und sämtliche ETL-Integritätsgates sind bestanden (PASS).",
        ),
    ]
    pages.append((p6_id, make_page_json(p6_id, "06 Datenqualität"), p6_visuals))

    return pages


def inject_pages_into_pbix(pbix_path: Path):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_file = BACKUP_DIR / "Customer Churn Early-Warning System.before-dashboard-20261020.pbix"
    if not backup_file.exists():
        shutil.copy2(pbix_path, backup_file)
        print("Created backup:", backup_file)

    pages = build_all_pages()
    page_order = [p[0] for p in pages]
    pages_metadata = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json",
        "pageOrder": page_order,
        "activePageName": page_order[0],
    }

    # Read existing PBIX entries except old pages and SecurityBindings
    kept_entries = {}
    with zipfile.ZipFile(pbix_path, "r") as zf:
        for item in zf.infolist():
            name = item.filename
            if name == "SecurityBindings":
                continue
            if name.startswith("Report/definition/pages/"):
                continue
            data = zf.read(name)
            if name == "[Content_Types].xml":
                txt = data.decode("utf-8-sig")
                txt = txt.replace('<Override PartName="/SecurityBindings" ContentType="" />', "")
                data = txt.encode("utf-8-sig")
            elif name == "Report/StaticResources/SharedResources/BaseThemes/CY25SU12.json":
                theme_obj = json.loads(data.decode("utf-8"))
                theme_obj["dataColors"] = [
                    COLOR_ACCENT,      # #285780 (Primary Accent)
                    COLOR_COMPARISON,  # #A6B0BA (Comparison / Benchmark)
                    COLOR_RISK,        # #C64747 (Risk / Alert)
                    COLOR_FAVORABLE,   # #247C68 (Favorable)
                    "#4B5563",
                    "#1F2937",
                    "#D97706",
                    "#6B7280",
                ] + theme_obj.get("dataColors", [])[8:]
                theme_obj["foreground"] = COLOR_TEXT
                theme_obj["tableAccent"] = COLOR_ACCENT
                theme_obj["good"] = COLOR_FAVORABLE
                theme_obj["bad"] = COLOR_RISK
                if "textClasses" in theme_obj:
                    theme_obj["textClasses"]["callout"] = {"fontSize": 22, "fontFace": "Segoe UI Semibold", "color": COLOR_TEXT}
                    theme_obj["textClasses"]["title"] = {"fontSize": 11, "fontFace": "Segoe UI Semibold", "color": COLOR_TEXT}
                    theme_obj["textClasses"]["header"] = {"fontSize": 10, "fontFace": "Segoe UI Semibold", "color": COLOR_TEXT}
                    theme_obj["textClasses"]["label"] = {"fontSize": 9, "fontFace": "Segoe UI", "color": COLOR_TEXT}
                data = json.dumps(theme_obj, ensure_ascii=False).encode("utf-8")
            kept_entries[name] = (item, data)

    tmp_path = pbix_path.with_suffix(".pbix.tmp")
    with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for name, (info, data) in kept_entries.items():
            # Preserve original compression type for DataModel etc.
            zout.writestr(info, data)

        zout.writestr(
            "Report/definition/pages/pages.json",
            json.dumps(pages_metadata, indent=2, ensure_ascii=False).encode("utf-8"),
        )
        for page_id, page_json, visuals in pages:
            zout.writestr(
                f"Report/definition/pages/{page_id}/page.json",
                json.dumps(page_json, indent=2, ensure_ascii=False).encode("utf-8"),
            )
            for vis in visuals:
                v_name = vis["name"]
                zout.writestr(
                    f"Report/definition/pages/{page_id}/visuals/{v_name}/visual.json",
                    json.dumps(vis, indent=2, ensure_ascii=False).encode("utf-8"),
                )

    tmp_path.replace(pbix_path)
    total_visuals = sum(len(v) for _, _, v in pages)
    print(f"SUCCESS: Injected {len(pages)} pages and {total_visuals} visuals into {pbix_path}")

    # Ensure scripts/build_powerbi_model.ps1 has a UTF-8 BOM for Windows PowerShell 5.1
    ps1_path = ROOT / "scripts" / "build_powerbi_model.ps1"
    if ps1_path.exists():
        raw_ps1 = ps1_path.read_bytes()
        if not raw_ps1.startswith(b"\xef\xbb\xbf"):
            ps1_path.write_bytes(b"\xef\xbb\xbf" + raw_ps1)
            print("Added UTF-8 BOM to scripts/build_powerbi_model.ps1")


if __name__ == "__main__":
    inject_pages_into_pbix(PBIX_PATH)
