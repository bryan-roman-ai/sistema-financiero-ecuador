#!/usr/bin/env python3
"""Pipeline ETL de limpieza, validación, carga a SQLite y verificación cruzada.

Fuentes públicas oficiales descargadas en data/raw/:
1. Banco Central del Ecuador (BCE) — Monitoreo de los Principales Instrumentos de
   Política Monetaria e Indicadores Financieros (Datos.xlsx; compilado con datos
   de Superintendencia de Bancos [SB] y SEPS).
2. Banco Central del Ecuador (BCE) — Tasas de Interés Activas y Pasivas Efectivas
   Referenciales y Máximas (TasasVigentesMMYYYY.htm e Indice.htm, 2022-01..2026-11).
3. Banco Mundial (API v2) — Bank nonperforming loans to total gross loans (%)
   indicador FB.AST.NPER.ZS para ECU, COL, PER, MEX, CHL y USA.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import openpyxl
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
CLEAN_DIR = ROOT / "data" / "clean"
SQL_PATH = ROOT / "sql" / "consultas_analisis.sql"
DB_PATH = ROOT / "data" / "sistema_financiero_ecuador.sqlite"
MANIFEST_PATH = ROOT / "data" / "sources_manifest.json"
DATA_JS_PATH = ROOT / "data.js"

DOWNLOAD_DATE = "2026-11-26"

BCE_DATOS_URL = "https://contenido.bce.fin.ec/documentos/PublicacionesNotas/Datos.xlsx"
BCE_DATOS_LANDING_URL = (
    "https://contenido.bce.fin.ec/series-de-datos-indicadores-monetarios-y-financieros/"
)
SB_PORTAL_URL = (
    "https://www.superbancos.gob.ec/estadisticas/portalestudios/"
    "sistema-financiero-publico-y-privado/"
)
BCE_TASAS_INDICE_URL = (
    "https://contenido.bce.fin.ec/documentos/Estadisticas/SectorMonFin/"
    "TasasInteres/Indice.htm"
)
BCE_TASAS_HIST_URL = (
    "https://contenido.bce.fin.ec/informacion-historica-de-tasas-maximas-y-referenciales/"
)
WB_API_URL = (
    "https://api.worldbank.org/v2/country/ECU;COL;PER;MEX;CHL;USA/"
    "indicator/FB.AST.NPER.ZS?format=json&per_page=1000"
)
WB_INDICATOR_WEB_URL = "https://data.worldbank.org/indicator/FB.AST.NPER.ZS"

COUNTRY_NAMES_ES = {
    "ECU": "Ecuador",
    "COL": "Colombia",
    "PER": "Perú",
    "MEX": "México",
    "CHL": "Chile",
    "USA": "Estados Unidos",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class SimpleTableParser(HTMLParser):
    """Minimal stdlib HTML table parser (avoids third-party bs4 dependency)."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._in_tr = False
        self._in_cell = False
        self._cur_row: list[str] = []
        self._cur_cell: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t == "tr":
            self._in_tr = True
            self._cur_row = []
        elif t in ("td", "th") and self._in_tr:
            self._in_cell = True
            self._cur_cell = []

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in ("td", "th") and self._in_cell:
            txt = " ".join("".join(self._cur_cell).split())
            self._cur_row.append(txt)
            self._in_cell = False
        elif t == "tr" and self._in_tr:
            non_empty = [c for c in self._cur_row if c != ""]
            if non_empty:
                self.rows.append(non_empty)
            self._in_tr = False

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cur_cell.append(data)


def parse_float_es(s: str) -> float | None:
    cleaned = s.strip().replace("%", "").replace("\xa0", "").replace(" ", "")
    if not cleaned:
        return None
    cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def normalize_segment_label(lbl: str) -> str:
    cleaned = re.sub(r"[\*\d]+$", "", lbl).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    # Unify minor spelling variants across years
    aliases = {
        "Productivo Corporativo": "Productivo Corporativo",
        "Productivo Empresarial": "Productivo Empresarial",
        "Productivo PYMES": "Productivo PYMES",
        "Consumo": "Consumo",
        "Educativo": "Educativo",
        "Educativo Social": "Educativo Social",
        "Vivienda de Interés Público": "Vivienda de Interés Público",
        "Vivienda de Interés Social": "Vivienda de Interés Social",
        "Inmobiliario": "Inmobiliario",
        "Microcrédito Minorista": "Microcrédito Minorista",
        "Microcrédito de Acumulación Simple": "Microcrédito de Acumulación Simple",
        "Microcrédito de Acumulación Ampliada": "Microcrédito de Acumulación Ampliada",
        "Inversión Pública": "Inversión Pública",
    }
    return aliases.get(cleaned, cleaned)


def parse_bce_datos_workbook(xlsx_path: Path) -> dict[str, pd.DataFrame]:
    """Extract cartera, depósitos, morosidad and prudential indicators from BCE Datos.xlsx."""
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)

    # 1. Cartera bruta por segmento (sheet '3. Cartera')
    ws_c = wb["3. Cartera"]
    seg_cols = [
        (3, "Productivo"),
        (4, "Consumo"),
        (5, "Microcrédito"),
        (6, "Vivienda"),
        (7, "Educativa"),
        (8, "Total"),
    ]
    cartera_rows = []
    for r in range(13, ws_c.max_row + 1):
        d = ws_c.cell(r, 2).value
        if not isinstance(d, (dt.datetime, dt.date)):
            continue
        ym = f"{d.year:04d}-{d.month:02d}"
        for col_idx, seg_name in seg_cols:
            val = ws_c.cell(r, col_idx).value
            if val is not None:
                cartera_rows.append(
                    {
                        "fecha": ym,
                        "segmento": seg_name,
                        "saldo_mm_usd": round(float(val), 6),
                        "fuente": "SB y SEPS vía BCE (Datos.xlsx - 3. Cartera)",
                        "url_fuente": BCE_DATOS_URL,
                    }
                )
    df_cartera = pd.DataFrame(cartera_rows)

    # 2. Depósitos por subsistema (sheet '2. Depósitos')
    ws_d = wb["2. Depósitos"]
    # Columns verified in Datos.xlsx:
    # Vista: BP=3, CO1=5, CO2=6, MU=7, TOTAL=8
    # Plazo: BP=17, CO1=19, CO2=20, MU=21, TOTAL=22
    # Total: BP=31, CO1=33, CO2=34, MU=35, TOTAL=36
    sub_map = [
        ("BP", "Bancos Privados", 3, 17, 31),
        ("CO1", "Cooperativas Seg. 1", 5, 19, 33),
        ("CO2", "Cooperativas Seg. 2", 6, 20, 34),
        ("MU", "Mutualistas", 7, 21, 35),
        ("TOTAL", "Total SFPr y SFPS", 8, 22, 36),
    ]
    dep_rows = []
    for r in range(12, ws_d.max_row + 1):
        d = ws_d.cell(r, 2).value
        if not isinstance(d, (dt.datetime, dt.date)):
            continue
        ym = f"{d.year:04d}-{d.month:02d}"
        for code, label, c_v, c_p, c_t in sub_map:
            v = ws_d.cell(r, c_v).value
            p = ws_d.cell(r, c_p).value
            t = ws_d.cell(r, c_t).value
            if t is None and v is None and p is None:
                continue
            v_num = float(v) if v is not None else 0.0
            p_num = float(p) if p is not None else 0.0
            t_num = float(t) if t is not None else v_num + p_num
            dep_rows.append(
                {
                    "fecha": ym,
                    "subsistema": code,
                    "subsistema_nombre": label,
                    "vista_mm_usd": round(v_num, 6),
                    "plazo_mm_usd": round(p_num, 6),
                    "total_mm_usd": round(t_num, 6),
                    "fuente": "SB y SEPS vía BCE (Datos.xlsx - 2. Depósitos)",
                    "url_fuente": BCE_DATOS_URL,
                }
            )
    df_depositos = pd.DataFrame(dep_rows)

    # 3. Morosidad por segmento (sheet '3. Morosidad')
    ws_m = wb["3. Morosidad"]
    mor_cols = [
        (3, "Productivo"),
        (4, "Consumo"),
        (5, "Microcrédito"),
        (6, "Vivienda"),
        (7, "Educativo"),
        (8, "Total"),
    ]
    mor_rows = []
    for r in range(12, ws_m.max_row + 1):
        d = ws_m.cell(r, 2).value
        if not isinstance(d, (dt.datetime, dt.date)):
            continue
        ym = f"{d.year:04d}-{d.month:02d}"
        for col_idx, seg_name in mor_cols:
            val = ws_m.cell(r, col_idx).value
            if val is not None:
                mor_rows.append(
                    {
                        "fecha": ym,
                        "segmento": seg_name,
                        "morosidad_pct": round(float(val) * 100.0, 6),
                        "fuente": "SB y SEPS vía BCE (Datos.xlsx - 3. Morosidad)",
                        "url_fuente": BCE_DATOS_URL,
                    }
                )
    df_morosidad = pd.DataFrame(mor_rows)

    # 4. Indicadores prudenciales: Solvencia, Liquidez, ROE
    prud_subs = [
        ("Bancos Privados", 3),
        ("Coop. Seg. 1", 5),
        ("Coop. Seg. 2", 6),
        ("Mutualistas", 7),
        ("Total SFPr y SFPS", 8),
    ]

    def read_prud_sheet(sheet_name: str, start_row: int, col_name: str) -> pd.DataFrame:
        ws = wb[sheet_name]
        recs = []
        for r in range(start_row, ws.max_row + 1):
            d = ws.cell(r, 2).value
            if not isinstance(d, (dt.datetime, dt.date)):
                continue
            ym = f"{d.year:04d}-{d.month:02d}"
            for sub_label, c_idx in prud_subs:
                val = ws.cell(r, c_idx).value
                recs.append(
                    {
                        "fecha": ym,
                        "subsistema": sub_label,
                        col_name: round(float(val) * 100.0, 6) if val is not None else None,
                    }
                )
        return pd.DataFrame(recs)

    df_sol = read_prud_sheet("4. Índices_solvencia", 12, "solvencia_pct")
    df_liq = read_prud_sheet("4. Índices_liquidez", 12, "liquidez_pct")
    df_roe = read_prud_sheet("4. Índices_ROE", 13, "roe_pct")
    df_prud = (
        df_sol.merge(df_liq, on=["fecha", "subsistema"], how="outer")
        .merge(df_roe, on=["fecha", "subsistema"], how="outer")
        .sort_values(["fecha", "subsistema"])
        .reset_index(drop=True)
    )
    df_prud["fuente"] = "SB y SEPS vía BCE (Datos.xlsx - Solvencia/Liquidez/ROE)"
    df_prud["url_fuente"] = BCE_DATOS_URL

    # 5. Cartera refinanciada y reestructurada (for context/audit)
    ws_rr = wb["3. Cartera_ref_reestr"]
    rr_rows = []
    for r in range(12, ws_rr.max_row + 1):
        d = ws_rr.cell(r, 2).value
        if not isinstance(d, (dt.datetime, dt.date)):
            continue
        ym = f"{d.year:04d}-{d.month:02d}"
        ref_v = ws_rr.cell(r, 3).value
        ree_v = ws_rr.cell(r, 4).value
        rr_rows.append(
            {
                "fecha": ym,
                "refinanciada_mm_usd": round(float(ref_v), 6) if ref_v is not None else None,
                "reestructurada_mm_usd": round(float(ree_v), 6) if ree_v is not None else None,
            }
        )
    df_ref_reestr = pd.DataFrame(rr_rows)

    wb.close()
    return {
        "cartera": df_cartera,
        "depositos": df_depositos,
        "morosidad": df_morosidad,
        "prudenciales": df_prud,
        "ref_reestr": df_ref_reestr,
    }


def parse_single_bce_tasa_html(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    text = ""
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    parser = SimpleTableParser()
    parser.feed(text)

    section: str | None = None
    side_by_side = False
    maximas: dict[str, float] = {}
    referenciales: dict[str, float] = {}
    pasivas: dict[str, float] = {}
    otras: dict[str, float] = {}

    for cells in parser.rows:
        joined = " | ".join(cells)
        low = joined.lower()

        if "tasa activa efectiva referencial para el segmento" in low and "máxima" in low:
            section = "both"
            side_by_side = True
            continue
        if "tasas de interés activas máximas" in low or "tasa activa efectiva máxima" in low:
            section = "maximas"
            side_by_side = False
            continue
        if (
            "tasas de interés activas efectivas referenciales" in low
            or "tasas de interés activas referenciales" in low
        ):
            section = "referenciales"
            side_by_side = False
            continue
        if "tasas de interés pasivas efectivas promedio por instrumento" in low:
            section = "pasivas_inst"
            side_by_side = False
            continue
        if "tasas de interés pasivas efectivas referenciales por plazo" in low:
            section = "pasivas_plazo"
            side_by_side = False
            continue
        if "otras tasas referenciales" in low:
            section = "otras"
            side_by_side = False
            continue

        if section == "both" and side_by_side and len(cells) >= 4:
            v_ref = parse_float_es(cells[1])
            v_max = parse_float_es(cells[3])
            if v_ref is not None and v_max is not None:
                referenciales[normalize_segment_label(cells[0])] = v_ref
                maximas[normalize_segment_label(cells[2])] = v_max
            continue

        i = 0
        while i + 1 < len(cells):
            val = parse_float_es(cells[i + 1])
            if val is not None:
                lbl = normalize_segment_label(cells[i])
                if section == "maximas":
                    maximas[lbl] = val
                elif section == "referenciales":
                    referenciales[lbl] = val
                elif section in ("pasivas_inst", "pasivas_plazo"):
                    pasivas[lbl] = val
                elif section == "otras":
                    otras[lbl] = val
                i += 2
            else:
                i += 1

    return {
        "maximas": maximas,
        "referenciales": referenciales,
        "pasivas": pasivas,
        "otras": otras,
    }


def parse_bce_tasas_series(tasas_dir: Path) -> pd.DataFrame:
    manifest_file = tasas_dir / "manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))

    target_segments = [
        "Productivo Corporativo",
        "Productivo Empresarial",
        "Productivo PYMES",
        "Consumo",
        "Educativo",
        "Educativo Social",
        "Vivienda de Interés Público",
        "Vivienda de Interés Social",
        "Inmobiliario",
        "Microcrédito Minorista",
        "Microcrédito de Acumulación Simple",
        "Microcrédito de Acumulación Ampliada",
        "Inversión Pública",
    ]

    rows = []
    for ym in sorted(manifest.keys()):
        html_path = tasas_dir / f"{ym}.htm"
        parsed = parse_single_bce_tasa_html(html_path)
        tpr = parsed["otras"].get("Tasa Pasiva Referencial")
        tar_gral = parsed["otras"].get("Tasa Activa Referencial")
        ahorro = parsed["pasivas"].get("Depósitos de Ahorro")
        plazo361 = parsed["pasivas"].get("Plazo 361 y más")
        url = manifest[ym]["url"]

        if tpr is None or tar_gral is None:
            raise ValueError(f"Faltan TPR/TAR en {ym} ({html_path})")

        for seg in target_segments:
            t_ref = parsed["referenciales"].get(seg)
            t_max = parsed["maximas"].get(seg)
            if t_ref is None or t_max is None:
                raise ValueError(f"Falta segmento '{seg}' en {ym}: ref={t_ref}, max={t_max}")
            rows.append(
                {
                    "fecha": ym,
                    "segmento": seg,
                    "tipo_tasa": "Efectiva anual (%)",
                    "tasa_activa_ref_pct": round(t_ref, 4),
                    "tasa_activa_max_pct": round(t_max, 4),
                    "tasa_pasiva_ref_pct": round(tpr, 4),
                    "tasa_activa_ref_general_pct": round(tar_gral, 4),
                    "tasa_ahorro_pct": round(ahorro, 4) if ahorro is not None else None,
                    "tasa_plazo_361_pct": round(plazo361, 4) if plazo361 is not None else None,
                    "spread_tar_tpr_pp": round(t_ref - tpr, 4),
                    "holgura_bajo_tope_pp": round(t_max - t_ref, 4),
                    "fuente": "Banco Central del Ecuador (BCE - Tasas Efectivas Vigentes)",
                    "url_fuente": url,
                }
            )
    return pd.DataFrame(rows)


def parse_worldbank_npl(json_path: Path) -> tuple[pd.DataFrame, str]:
    meta, records = json.loads(json_path.read_text(encoding="utf-8"))
    last_updated = meta.get("lastupdated", "")
    rows = []
    for rec in records:
        val = rec.get("value")
        iso = rec.get("countryiso3code")
        if val is None or iso not in COUNTRY_NAMES_ES:
            continue
        rows.append(
            {
                "pais_iso3": iso,
                "pais_nombre": COUNTRY_NAMES_ES[iso],
                "anio": int(rec["date"]),
                "morosidad_pct": round(float(val), 6),
                "indicador": rec["indicator"]["id"],
                "indicador_nombre": rec["indicator"]["value"],
                "ultima_actualizacion_api": last_updated,
                "fuente": "Banco Mundial (WDI / FMI FSI - FB.AST.NPER.ZS)",
                "url_fuente": WB_API_URL,
            }
        )
    df = pd.DataFrame(rows).sort_values(["pais_iso3", "anio"]).reset_index(drop=True)
    return df, last_updated


def validate_datasets(
    df_cartera: pd.DataFrame,
    df_depositos: pd.DataFrame,
    df_morosidad: pd.DataFrame,
    df_prud: pd.DataFrame,
    df_tasas: pd.DataFrame,
    df_wb: pd.DataFrame,
) -> dict[str, Any]:
    """Run strict data-quality assertions across all 6 cleaned datasets."""
    checks: list[dict[str, Any]] = []

    def check(name: str, cond: bool, detail: str) -> None:
        if not cond:
            raise AssertionError(f"Validación fallida [{name}]: {detail}")
        checks.append({"check": name, "ok": True, "detail": detail})

    # 1. Cartera: sin nulos, fechas sin duplicados, suma de segmentos == Total
    check(
        "cartera_no_nulos",
        not df_cartera[["fecha", "segmento", "saldo_mm_usd"]].isna().any().any(),
        f"{len(df_cartera)} filas verificadas sin nulos",
    )
    check(
        "cartera_claves_unicas",
        not df_cartera.duplicated(["fecha", "segmento"]).any(),
        "Sin claves (fecha, segmento) duplicadas",
    )
    piv_c = df_cartera.pivot(index="fecha", columns="segmento", values="saldo_mm_usd")
    seg_sum = piv_c[["Productivo", "Consumo", "Microcrédito", "Vivienda", "Educativa"]].sum(axis=1)
    max_diff_c = float((seg_sum - piv_c["Total"]).abs().max())
    check(
        "cartera_suma_segmentos_igual_total",
        max_diff_c <= 0.05,
        f"Diferencia máxima |suma(segmentos) - Total| = {max_diff_c:.6f} MM USD (umbral <= 0.05)",
    )
    check(
        "cartera_saldos_no_negativos",
        bool((df_cartera["saldo_mm_usd"] >= 0).all()),
        "Todos los saldos de cartera >= 0",
    )

    # 2. Depósitos: vista + plazo == total y valores >= 0
    check(
        "depositos_no_nulos",
        not df_depositos[["fecha", "subsistema", "vista_mm_usd", "plazo_mm_usd", "total_mm_usd"]]
        .isna()
        .any()
        .any(),
        f"{len(df_depositos)} filas verificadas sin nulos",
    )
    dep_diff = (
        df_depositos["vista_mm_usd"] + df_depositos["plazo_mm_usd"] - df_depositos["total_mm_usd"]
    ).abs().max()
    check(
        "depositos_vista_mas_plazo_igual_total",
        float(dep_diff) <= 0.05,
        f"Diferencia máxima |vista + plazo - total| = {float(dep_diff):.6f} MM USD",
    )

    # 3. Morosidad: rango plausible [0, 40]% y cobertura temporal igual a cartera
    check(
        "morosidad_rango_valido",
        bool(((df_morosidad["morosidad_pct"] >= 0) & (df_morosidad["morosidad_pct"] <= 40)).all()),
        f"Rango observado: {df_morosidad['morosidad_pct'].min():.2f}% .. {df_morosidad['morosidad_pct'].max():.2f}%",
    )
    check(
        "morosidad_alineada_con_cartera",
        set(df_morosidad["fecha"].unique()) == set(df_cartera["fecha"].unique()),
        f"Mismos {df_morosidad['fecha'].nunique()} meses que cartera ({df_morosidad['fecha'].min()}..{df_morosidad['fecha'].max()})",
    )

    # 4. Prudenciales: claves únicas y solvencia/liquidez positivas donde no son nulas
    check(
        "prudenciales_claves_unicas",
        not df_prud.duplicated(["fecha", "subsistema"]).any(),
        f"{len(df_prud)} filas sin duplicados",
    )
    sol_nonnull = df_prud["solvencia_pct"].dropna()
    check(
        "prudenciales_solvencia_positiva",
        bool(((sol_nonnull > 0) & (sol_nonnull < 100)).all()),
        f"Solvencia entre {sol_nonnull.min():.2f}% y {sol_nonnull.max():.2f}%",
    )

    # 5. Tasas BCE: 59 meses continuos (2022-01..2026-11), TAR <= Tasa Máxima legal
    meses_tasas = sorted(df_tasas["fecha"].unique())
    check(
        "tasas_bce_cobertura_continua",
        len(meses_tasas) == 59 and meses_tasas[0] == "2022-01" and meses_tasas[-1] == "2026-11",
        f"59 meses continuos verificados ({meses_tasas[0]}..{meses_tasas[-1]})",
    )
    check(
        "tasas_bce_tar_menor_o_igual_maxima",
        bool((df_tasas["tasa_activa_ref_pct"] <= df_tasas["tasa_activa_max_pct"] + 1e-6).all()),
        "En 100% de meses y segmentos, TAR <= Tasa Activa Efectiva Máxima legal",
    )
    check(
        "tasas_bce_rango_valido",
        bool(
            ((df_tasas["tasa_activa_ref_pct"] > 0) & (df_tasas["tasa_activa_max_pct"] <= 40)).all()
            and ((df_tasas["tasa_pasiva_ref_pct"] > 0) & (df_tasas["tasa_pasiva_ref_pct"] < 20)).all()
        ),
        "Tasas activas y pasivas en rangos válidos",
    )

    # 6. Banco Mundial: 6 países esperados, indicador único FB.AST.NPER.ZS
    check(
        "wb_seis_paises_objetivo",
        set(df_wb["pais_iso3"].unique()) == set(COUNTRY_NAMES_ES.keys()),
        f"Países presentes: {sorted(df_wb['pais_iso3'].unique())}",
    )
    check(
        "wb_indicador_exacto",
        set(df_wb["indicador"].unique()) == {"FB.AST.NPER.ZS"},
        "Indicador único FB.AST.NPER.ZS",
    )
    check(
        "wb_rango_morosidad",
        bool(((df_wb["morosidad_pct"] > 0) & (df_wb["morosidad_pct"] < 30)).all()),
        f"Rango WB observado: {df_wb['morosidad_pct'].min():.2f}% .. {df_wb['morosidad_pct'].max():.2f}%",
    )

    return {"passed": len(checks), "checks": checks}


def build_sqlite(
    db_path: Path,
    df_cartera: pd.DataFrame,
    df_depositos: pd.DataFrame,
    df_morosidad: pd.DataFrame,
    df_prud: pd.DataFrame,
    df_tasas: pd.DataFrame,
    df_wb: pd.DataFrame,
) -> None:
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    try:
        df_cartera.to_sql("cartera_segmentos", conn, index=False)
        df_depositos.to_sql("depositos_subsistemas", conn, index=False)
        df_morosidad.to_sql("morosidad_segmentos", conn, index=False)
        df_prud.to_sql("indicadores_prudenciales", conn, index=False)
        df_tasas.to_sql("tasas_referenciales_bce", conn, index=False)
        df_wb.to_sql("benchmark_morosidad_wb", conn, index=False)

        conn.executescript(
            """
            CREATE INDEX idx_cartera_fecha_seg ON cartera_segmentos(fecha, segmento);
            CREATE INDEX idx_dep_fecha_sub ON depositos_subsistemas(fecha, subsistema);
            CREATE INDEX idx_mor_fecha_seg ON morosidad_segmentos(fecha, segmento);
            CREATE INDEX idx_prud_fecha_sub ON indicadores_prudenciales(fecha, subsistema);
            CREATE INDEX idx_tasas_fecha_seg ON tasas_referenciales_bce(fecha, segmento);
            CREATE INDEX idx_wb_pais_anio ON benchmark_morosidad_wb(pais_iso3, anio);
            """
        )
        conn.commit()
    finally:
        conn.close()


def parse_named_sql_queries(sql_path: Path) -> list[dict[str, str]]:
    text = sql_path.read_text(encoding="utf-8")
    blocks = re.split(r"(?=^-- @query:\s*)", text, flags=re.MULTILINE)
    queries = []
    for blk in blocks:
        m = re.match(r"^-- @query:\s*(\S+)\s*\n(.*)", blk.strip(), flags=re.DOTALL)
        if not m:
            continue
        name = m.group(1)
        body = m.group(2).strip()
        # Extract leading comment lines as title/description
        desc_lines = []
        sql_lines = []
        in_header = True
        for line in body.splitlines():
            if in_header and line.strip().startswith("--"):
                desc_lines.append(line.strip().lstrip("-").strip())
            else:
                in_header = False
                sql_lines.append(line)
        queries.append(
            {
                "id": name,
                "descripcion": " ".join(desc_lines),
                "sql": "\n".join(sql_lines).strip(),
            }
        )
    return queries


def cross_check_pandas_vs_sqlite(
    db_path: Path,
    sql_path: Path,
    df_cartera: pd.DataFrame,
    df_depositos: pd.DataFrame,
    df_morosidad: pd.DataFrame,
    df_prud: pd.DataFrame,
    df_tasas: pd.DataFrame,
    df_wb: pd.DataFrame,
) -> dict[str, Any]:
    """Execute all 6 SQLite queries and cross-check every single number against pandas."""
    queries = parse_named_sql_queries(sql_path)
    conn = sqlite3.connect(db_path)
    sql_results: dict[str, pd.DataFrame] = {}
    try:
        for q in queries:
            sql_results[q["id"]] = pd.read_sql_query(q["sql"], conn)
    finally:
        conn.close()

    # Independent pandas calculations for each of the 6 queries
    # Q1: Cartera último corte
    max_f = df_cartera["fecha"].max()
    yoy_f = f"{int(max_f[:4]) - 1:04d}{max_f[4:]}"
    c_now = df_cartera[(df_cartera["fecha"] == max_f) & (df_cartera["segmento"] != "Total")].copy()
    c_tot = float(
        df_cartera[(df_cartera["fecha"] == max_f) & (df_cartera["segmento"] == "Total")][
            "saldo_mm_usd"
        ].iloc[0]
    )
    c_prev = df_cartera[df_cartera["fecha"] == yoy_f].set_index("segmento")["saldo_mm_usd"]
    c_now["participacion_pct"] = (100.0 * c_now["saldo_mm_usd"] / c_tot).round(2)
    c_now["var_interanual_pct"] = (
        100.0 * (c_now["saldo_mm_usd"] - c_now["segmento"].map(c_prev)) / c_now["segmento"].map(c_prev)
    ).round(2)
    c_now["saldo_mm_usd"] = c_now["saldo_mm_usd"].round(2)
    pd_q1 = c_now.sort_values("saldo_mm_usd", ascending=False).reset_index(drop=True)

    # Q2: Intermediación y fondeo anual 2015-2026
    dep15 = df_depositos[df_depositos["fecha"] >= "2015-01"].copy()
    dep15["anio"] = dep15["fecha"].str[:4]
    cierres = dep15.groupby("anio")["fecha"].max().reset_index()
    q2_rows = []
    for _, row in cierres.iterrows():
        fc = row["fecha"]
        d_tot = df_depositos[(df_depositos["fecha"] == fc) & (df_depositos["subsistema"] == "TOTAL")].iloc[0]
        d_bp = df_depositos[(df_depositos["fecha"] == fc) & (df_depositos["subsistema"] == "BP")].iloc[0]
        c_t = float(
            df_cartera[(df_cartera["fecha"] == fc) & (df_cartera["segmento"] == "Total")][
                "saldo_mm_usd"
            ].iloc[0]
        )
        q2_rows.append(
            {
                "anio": row["anio"],
                "fecha_cierre": fc,
                "depositos_total_mm": round(float(d_tot["total_mm_usd"]), 2),
                "cartera_total_mm": round(c_t, 2),
                "ratio_cartera_depositos_pct": round(100.0 * c_t / float(d_tot["total_mm_usd"]), 2),
                "share_plazo_pct": round(
                    100.0 * float(d_tot["plazo_mm_usd"]) / float(d_tot["total_mm_usd"]), 2
                ),
                "share_bancos_privados_pct": round(
                    100.0 * float(d_bp["total_mm_usd"]) / float(d_tot["total_mm_usd"]), 2
                ),
            }
        )
    pd_q2 = pd.DataFrame(q2_rows)

    # Q3: Riesgo morosidad por segmento
    m_max_f = df_morosidad["fecha"].max()
    ult12 = sorted(df_morosidad["fecha"].unique())[-12:]
    m_now = df_morosidad[df_morosidad["fecha"] == m_max_f].set_index("segmento")["morosidad_pct"]
    m_12 = df_morosidad[df_morosidad["fecha"].isin(ult12)].groupby("segmento")["morosidad_pct"].mean()
    m_pico = df_morosidad[df_morosidad["fecha"] >= "2015-01"].groupby("segmento")["morosidad_pct"].max()
    pd_q3 = (
        pd.DataFrame(
            {
                "fecha_corte": m_max_f,
                "segmento": m_now.index,
                "morosidad_actual_pct": m_now.round(2).values,
                "promedio_12m_pct": m_12.reindex(m_now.index).round(2).values,
                "pico_2015_2026_pct": m_pico.reindex(m_now.index).round(2).values,
                "desv_vs_12m_pp": (m_now - m_12.reindex(m_now.index)).round(2).values,
            }
        )
        .sort_values("morosidad_actual_pct", ascending=False)
        .reset_index(drop=True)
    )

    # Q4: Spread tasas BCE último corte
    t_max_f = df_tasas["fecha"].max()
    pd_q4 = (
        df_tasas[df_tasas["fecha"] == t_max_f][
            [
                "fecha",
                "segmento",
                "tasa_activa_ref_pct",
                "tasa_activa_max_pct",
                "tasa_pasiva_ref_pct",
                "spread_tar_tpr_pp",
                "holgura_bajo_tope_pp",
            ]
        ]
        .rename(
            columns={
                "fecha": "fecha_corte",
                "tasa_activa_ref_pct": "tar_pct",
                "tasa_activa_max_pct": "tasa_max_legal_pct",
                "tasa_pasiva_ref_pct": "tpr_pct",
            }
        )
        .sort_values("spread_tar_tpr_pp", ascending=False)
        .reset_index(drop=True)
    )
    for col in ["tar_pct", "tasa_max_legal_pct", "tpr_pct", "spread_tar_tpr_pp", "holgura_bajo_tope_pp"]:
        pd_q4[col] = pd_q4[col].round(2)

    # Q5: Benchmark morosidad WB
    wb_latest = df_wb.sort_values("anio").groupby("pais_iso3", as_index=False).last()
    wb_2019 = df_wb[df_wb["anio"] == 2019].set_index("pais_iso3")["morosidad_pct"]
    ecu_val = float(wb_latest[wb_latest["pais_iso3"] == "ECU"]["morosidad_pct"].iloc[0])
    wb_latest["morosidad_2019_pct"] = wb_latest["pais_iso3"].map(wb_2019)
    wb_latest["cambio_vs_2019_pp"] = (wb_latest["morosidad_pct"] - wb_latest["morosidad_2019_pct"]).round(2)
    wb_latest["brecha_vs_ecuador_pp"] = (wb_latest["morosidad_pct"] - ecu_val).round(2)
    wb_latest["morosidad_actual_pct"] = wb_latest["morosidad_pct"].round(2)
    wb_latest["morosidad_2019_pct"] = wb_latest["morosidad_2019_pct"].round(2)
    pd_q5 = wb_latest.sort_values("morosidad_actual_pct", ascending=False).reset_index(drop=True)

    # Q6: Salud prudencial último corte
    p_max_f = df_prud["fecha"].max()
    pd_q6 = (
        df_prud[(df_prud["fecha"] == p_max_f) & (df_prud["solvencia_pct"].notna())][
            ["fecha", "subsistema", "solvencia_pct", "liquidez_pct", "roe_pct"]
        ]
        .rename(columns={"fecha": "fecha_corte"})
        .sort_values("roe_pct", ascending=False)
        .reset_index(drop=True)
    )
    for col in ["solvencia_pct", "liquidez_pct", "roe_pct"]:
        pd_q6[col] = pd_q6[col].round(2)

    pairs = [
        ("q1_cartera_ultimo_corte", pd_q1, ["saldo_mm_usd", "participacion_pct", "var_interanual_pct"]),
        (
            "q2_intermediacion_fondeo_anual",
            pd_q2,
            [
                "depositos_total_mm",
                "cartera_total_mm",
                "ratio_cartera_depositos_pct",
                "share_plazo_pct",
                "share_bancos_privados_pct",
            ],
        ),
        (
            "q3_riesgo_morosidad_segmento",
            pd_q3,
            ["morosidad_actual_pct", "promedio_12m_pct", "pico_2015_2026_pct", "desv_vs_12m_pp"],
        ),
        (
            "q4_spread_tasas_bce_ultimo",
            pd_q4,
            ["tar_pct", "tasa_max_legal_pct", "tpr_pct", "spread_tar_tpr_pp", "holgura_bajo_tope_pp"],
        ),
        (
            "q5_benchmark_morosidad_latam_usa",
            pd_q5,
            ["morosidad_actual_pct", "morosidad_2019_pct", "cambio_vs_2019_pp", "brecha_vs_ecuador_pp"],
        ),
        ("q6_salud_prudencial_subsistemas", pd_q6, ["solvencia_pct", "liquidez_pct", "roe_pct"]),
    ]

    for qid, pd_df, num_cols in pairs:
        sq_df = sql_results[qid]
        assert len(sq_df) == len(pd_df), f"Filas distintas en {qid}: SQL={len(sq_df)} vs pandas={len(pd_df)}"
        for col in num_cols:
            diff = (sq_df[col].astype(float) - pd_df[col].astype(float)).abs().max()
            assert diff <= 0.011, f"Discrepancia pandas vs SQLite en {qid}.{col}: max_diff={diff}"

    out = []
    for q in queries:
        df_res = sql_results[q["id"]]
        out.append(
            {
                "id": q["id"],
                "descripcion": q["descripcion"],
                "sql": q["sql"],
                "columns": list(df_res.columns),
                "rows": df_res.to_dict(orient="records"),
            }
        )
    return {"verified_equivalent": True, "queries": out}


def build_sources_manifest(
    df_cartera: pd.DataFrame,
    df_depositos: pd.DataFrame,
    df_morosidad: pd.DataFrame,
    df_tasas: pd.DataFrame,
    df_wb: pd.DataFrame,
    wb_last_updated: str,
) -> dict[str, Any]:
    """Build exact traceability manifest with URL, cut-off date, SHA-256 and short literal quotes."""
    c_max = df_cartera["fecha"].max()
    c_tot = float(
        df_cartera[(df_cartera["fecha"] == c_max) & (df_cartera["segmento"] == "Total")][
            "saldo_mm_usd"
        ].iloc[0]
    )
    d_tot = float(
        df_depositos[(df_depositos["fecha"] == c_max) & (df_depositos["subsistema"] == "TOTAL")][
            "total_mm_usd"
        ].iloc[0]
    )
    m_tot = float(
        df_morosidad[(df_morosidad["fecha"] == c_max) & (df_morosidad["segmento"] == "Total")][
            "morosidad_pct"
        ].iloc[0]
    )
    m_micro = float(
        df_morosidad[(df_morosidad["fecha"] == c_max) & (df_morosidad["segmento"] == "Microcrédito")][
            "morosidad_pct"
        ].iloc[0]
    )

    t_max = df_tasas["fecha"].max()
    t_row_corp = df_tasas[
        (df_tasas["fecha"] == t_max) & (df_tasas["segmento"] == "Productivo Corporativo")
    ].iloc[0]
    t_row_cons = df_tasas[(df_tasas["fecha"] == t_max) & (df_tasas["segmento"] == "Consumo")].iloc[0]

    wb_ecu_2025 = float(
        df_wb[(df_wb["pais_iso3"] == "ECU") & (df_wb["anio"] == 2025)]["morosidad_pct"].iloc[0]
    )
    wb_per_2024 = float(
        df_wb[(df_wb["pais_iso3"] == "PER") & (df_wb["anio"] == 2024)]["morosidad_pct"].iloc[0]
    )

    return {
        "fecha_descarga": DOWNLOAD_DATE,
        "alcance_geografico": "Ecuador (BCE, SB, SEPS) y benchmark internacional (Colombia, Perú, México, Chile, EE. UU.)",
        "fuentes": [
            {
                "id": "bce_sb_seps_datos",
                "institucion": "Superintendencia de Bancos (SB) y SEPS — compilado y publicado por el Banco Central del Ecuador (BCE)",
                "titulo": "Monitoreo de los Principales Instrumentos de Política Monetaria e Indicadores Financieros (Datos.xlsx)",
                "url_archivo": BCE_DATOS_URL,
                "url_portal": BCE_DATOS_LANDING_URL,
                "url_superbancos": SB_PORTAL_URL,
                "fecha_descarga": DOWNLOAD_DATE,
                "fecha_corte": c_max,
                "cobertura_temporal": f"{df_cartera['fecha'].min()} a {c_max} (mensual, {df_cartera['fecha'].nunique()} meses)",
                "moneda_y_unidad": "Millones de dólares estadounidenses (MM USD) para saldos; porcentaje (%) para morosidad, solvencia, liquidez y ROE",
                "nota_metodologica": (
                    "Sector Financiero Privado (Bancos Privados y Mutualistas) y Sector Financiero "
                    "Popular y Solidario (Cooperativas Seg. 1 y Seg. 2 desde ene-2015). Considera "
                    "entidades operativas al último corte (omite entidades en liquidación forzosa: "
                    "Coop. Cámara de Comercio de Ambato dic-2024, Amibank mar-2025, Coop. Crea jul-2025)."
                ),
                "cita_literal": (
                    f"Hoja '3. Cartera' y '3. Morosidad' (Fuente: SB y SEPS), corte 2026-10-01: "
                    f"Cartera de crédito bruta Total = {c_tot:,.2f} millones USD; "
                    f"Depósitos Totales = {d_tot:,.2f} millones USD; "
                    f"Índice de morosidad Total = {m_tot:.2f}% (Microcrédito = {m_micro:.2f}%)."
                ),
                "sha256": sha256_file(RAW_DIR / "bce_indicadores_monetarios_financieros.xlsx"),
            },
            {
                "id": "bce_tasas_referenciales",
                "institucion": "Banco Central del Ecuador (BCE) / Junta de Política y Regulación Financiera y Monetaria (JPRFM)",
                "titulo": "Tasas de Interés Activas y Pasivas Efectivas Referenciales y Máximas Vigentes",
                "url_archivo": BCE_TASAS_INDICE_URL,
                "url_portal": BCE_TASAS_HIST_URL,
                "fecha_descarga": DOWNLOAD_DATE,
                "fecha_corte": t_max,
                "cobertura_temporal": f"{df_tasas['fecha'].min()} a {t_max} (mensual, {df_tasas['fecha'].nunique()} meses)",
                "tipo_tasa": "Tasa efectiva anual (%): promedio ponderado por monto (TAR y TPR) y topes máximos legales vigentes (JPRFM)",
                "nota_metodologica": (
                    "Para noviembre 2026 las tasas activas y pasivas efectivas referenciales se calculan "
                    "con operaciones de las semanas del 17 de septiembre al 14 de octubre de 2026 con "
                    "cobertura de 371 entidades financieras."
                ),
                "cita_literal": (
                    f"BCE Indice.htm (Noviembre 2026): Tasa Pasiva Referencial = {t_row_corp['tasa_pasiva_ref_pct']:.2f}% anual; "
                    f"Productivo Corporativo TAR = {t_row_corp['tasa_activa_ref_pct']:.2f}% (Máxima = {t_row_corp['tasa_activa_max_pct']:.2f}%); "
                    f"Consumo TAR = {t_row_cons['tasa_activa_ref_pct']:.2f}% (Máxima = {t_row_cons['tasa_activa_max_pct']:.2f}%)."
                ),
                "sha256_ultimo_mes": sha256_file(RAW_DIR / "bce_tasas" / "2026-11.htm"),
            },
            {
                "id": "worldbank_npl",
                "institucion": "Banco Mundial (World Development Indicators / FMI Financial Soundness Indicators)",
                "titulo": "Bank nonperforming loans to total gross loans (%) — Indicador FB.AST.NPER.ZS",
                "url_archivo": WB_API_URL,
                "url_portal": WB_INDICATOR_WEB_URL,
                "fecha_descarga": DOWNLOAD_DATE,
                "fecha_corte": f"2025 (ECU, COL, MEX, CHL, USA) / 2024 (PER); API lastupdated={wb_last_updated}",
                "cobertura_temporal": f"{int(df_wb['anio'].min())} a {int(df_wb['anio'].max())} (anual)",
                "tipo_indicador": "Porcentaje (%) de préstamos bancarios improductivos sobre cartera bruta total",
                "nota_metodologica": (
                    "Indicador armonizado FMI-FSI reportado vía API v2 del Banco Mundial. "
                    "Al corte de descarga (2026-11-26), Perú registra último dato en 2024."
                ),
                "cita_literal": (
                    f"World Bank API v2 (lastupdated {wb_last_updated}, FB.AST.NPER.ZS): "
                    f"Ecuador 2025 = {wb_ecu_2025:.2f}%; Perú 2024 = {wb_per_2024:.2f}%."
                ),
                "sha256": sha256_file(RAW_DIR / "worldbank_FB.AST.NPER.ZS.json"),
            },
        ],
    }


def export_web_data_js(
    df_cartera: pd.DataFrame,
    df_depositos: pd.DataFrame,
    df_morosidad: pd.DataFrame,
    df_prud: pd.DataFrame,
    df_tasas: pd.DataFrame,
    df_wb: pd.DataFrame,
    df_ref_reestr: pd.DataFrame,
    sql_summary: dict[str, Any],
    manifest: dict[str, Any],
    validation_report: dict[str, Any],
) -> None:
    """Export compact structured dataset to data.js for static zero-dependency web dashboard."""
    # Monthly Cartera + Depósitos + Ratio LDR (full history 2002-07..2026-10)
    piv_c = df_cartera.pivot(index="fecha", columns="segmento", values="saldo_mm_usd").sort_index()
    dep_tot = df_depositos[df_depositos["subsistema"] == "TOTAL"].set_index("fecha").sort_index()
    dep_bp = df_depositos[df_depositos["subsistema"] == "BP"].set_index("fecha").sort_index()
    dep_co1 = df_depositos[df_depositos["subsistema"] == "CO1"].set_index("fecha").sort_index()
    dep_co2 = df_depositos[df_depositos["subsistema"] == "CO2"].set_index("fecha").sort_index()
    dep_mu = df_depositos[df_depositos["subsistema"] == "MU"].set_index("fecha").sort_index()

    fechas_ec = list(piv_c.index)
    cartera_depositos_mensual = []
    for f in fechas_ec:
        ct = float(piv_c.loc[f, "Total"])
        dtot = float(dep_tot.loc[f, "total_mm_usd"])
        cartera_depositos_mensual.append(
            {
                "fecha": f,
                "cartera_total": round(ct, 2),
                "productivo": round(float(piv_c.loc[f, "Productivo"]), 2),
                "consumo": round(float(piv_c.loc[f, "Consumo"]), 2),
                "microcredito": round(float(piv_c.loc[f, "Microcrédito"]), 2),
                "vivienda": round(float(piv_c.loc[f, "Vivienda"]), 2),
                "educativa": round(float(piv_c.loc[f, "Educativa"]), 2),
                "depositos_total": round(dtot, 2),
                "depositos_vista": round(float(dep_tot.loc[f, "vista_mm_usd"]), 2),
                "depositos_plazo": round(float(dep_tot.loc[f, "plazo_mm_usd"]), 2),
                "depositos_bp": round(float(dep_bp.loc[f, "total_mm_usd"]), 2),
                "depositos_co1": round(float(dep_co1.loc[f, "total_mm_usd"]), 2),
                "depositos_co2": round(float(dep_co2.loc[f, "total_mm_usd"]), 2) if f in dep_co2.index else 0.0,
                "depositos_mu": round(float(dep_mu.loc[f, "total_mm_usd"]), 2) if f in dep_mu.index else 0.0,
                "ldr_pct": round(100.0 * ct / dtot, 2),
            }
        )

    # Monthly Morosidad por segmento
    piv_m = df_morosidad.pivot(index="fecha", columns="segmento", values="morosidad_pct").sort_index()
    morosidad_mensual = []
    for f in piv_m.index:
        morosidad_mensual.append(
            {
                "fecha": f,
                "Total": round(float(piv_m.loc[f, "Total"]), 2),
                "Productivo": round(float(piv_m.loc[f, "Productivo"]), 2),
                "Consumo": round(float(piv_m.loc[f, "Consumo"]), 2),
                "Microcrédito": round(float(piv_m.loc[f, "Microcrédito"]), 2),
                "Vivienda": round(float(piv_m.loc[f, "Vivienda"]), 2),
                "Educativo": round(float(piv_m.loc[f, "Educativo"]), 2),
            }
        )

    # Monthly Tasas BCE (key segments for time-series chart + all 13 segments for latest cutoff)
    key_rate_segs = [
        "Productivo Corporativo",
        "Productivo PYMES",
        "Consumo",
        "Inmobiliario",
        "Microcrédito Minorista",
    ]
    tasas_mensual = []
    for f, grp in df_tasas.groupby("fecha", sort=True):
        first = grp.iloc[0]
        rec = {
            "fecha": f,
            "tpr": round(float(first["tasa_pasiva_ref_pct"]), 2),
            "ahorro": round(float(first["tasa_ahorro_pct"]), 2) if pd.notna(first["tasa_ahorro_pct"]) else None,
            "plazo361": round(float(first["tasa_plazo_361_pct"]), 2) if pd.notna(first["tasa_plazo_361_pct"]) else None,
            "url": first["url_fuente"],
        }
        seg_map = grp.set_index("segmento")
        for s in key_rate_segs:
            rec[s] = round(float(seg_map.loc[s, "tasa_activa_ref_pct"]), 2)
        tasas_mensual.append(rec)

    t_last = df_tasas["fecha"].max()
    tasas_ultimo_corte = (
        df_tasas[df_tasas["fecha"] == t_last][
            [
                "fecha",
                "segmento",
                "tasa_activa_ref_pct",
                "tasa_activa_max_pct",
                "tasa_pasiva_ref_pct",
                "spread_tar_tpr_pp",
                "holgura_bajo_tope_pp",
                "url_fuente",
            ]
        ]
        .sort_values("tasa_activa_ref_pct", ascending=False)
        .to_dict(orient="records")
    )

    # World Bank benchmark (2010..2025)
    wb_recent = df_wb[df_wb["anio"] >= 2010].copy()
    wb_series: dict[str, list[dict[str, Any]]] = {}
    for iso, grp in wb_recent.groupby("pais_iso3", sort=True):
        wb_series[iso] = [
            {"anio": int(r["anio"]), "valor": round(float(r["morosidad_pct"]), 2)}
            for _, r in grp.sort_values("anio").iterrows()
        ]

    # Prudenciales último corte + serie anual 2015-2026 de Bancos Privados vs Coop Seg 1
    p_last = df_prud["fecha"].max()
    prud_ultimo = (
        df_prud[(df_prud["fecha"] == p_last) & (df_prud["solvencia_pct"].notna())][
            ["fecha", "subsistema", "solvencia_pct", "liquidez_pct", "roe_pct"]
        ]
        .round(2)
        .to_dict(orient="records")
    )

    rr_last = df_ref_reestr.dropna().iloc[-1]

    payload = {
        "generado_en": DOWNLOAD_DATE,
        "manifest": manifest,
        "validaciones": validation_report,
        "kpis": {
            "fecha_corte_sistema": fechas_ec[-1],
            "fecha_corte_tasas": t_last,
            "cartera_total_mm": cartera_depositos_mensual[-1]["cartera_total"],
            "depositos_total_mm": cartera_depositos_mensual[-1]["depositos_total"],
            "ldr_pct": cartera_depositos_mensual[-1]["ldr_pct"],
            "morosidad_total_pct": morosidad_mensual[-1]["Total"],
            "morosidad_micro_pct": morosidad_mensual[-1]["Microcrédito"],
            "morosidad_productivo_pct": morosidad_mensual[-1]["Productivo"],
            "tpr_pct": tasas_mensual[-1]["tpr"],
            "tar_corporativo_pct": tasas_mensual[-1]["Productivo Corporativo"],
            "tar_consumo_pct": tasas_mensual[-1]["Consumo"],
            "cartera_refinanciada_mm": round(float(rr_last["refinanciada_mm_usd"]), 2),
            "cartera_reestructurada_mm": round(float(rr_last["reestructurada_mm_usd"]), 2),
            "wb_ecu_2025_pct": wb_series["ECU"][-1]["valor"],
            "wb_ecu_anio": wb_series["ECU"][-1]["anio"],
        },
        "cartera_depositos_mensual": cartera_depositos_mensual,
        "morosidad_mensual": morosidad_mensual,
        "tasas_mensual": tasas_mensual,
        "tasas_ultimo_corte": tasas_ultimo_corte,
        "wb_series": wb_series,
        "wb_paises": COUNTRY_NAMES_ES,
        "prudenciales_ultimo": prud_ultimo,
        "sql_consultas": sql_summary["queries"],
    }

    js_text = (
        "// Archivo generado automáticamente por etl/clean_and_validate.py\n"
        "// Contiene únicamente datos públicos oficiales descargados y verificados.\n"
        "const SFE_DATA = "
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + ";\n"
        "if (typeof window !== 'undefined') { window.SFE_DATA = SFE_DATA; }\n"
        "if (typeof module !== 'undefined' && module.exports) { module.exports = SFE_DATA; }\n"
    )
    DATA_JS_PATH.write_text(js_text, encoding="utf-8")


def main() -> None:
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)

    bce_dfs = parse_bce_datos_workbook(RAW_DIR / "bce_indicadores_monetarios_financieros.xlsx")
    df_cartera = bce_dfs["cartera"]
    df_depositos = bce_dfs["depositos"]
    df_morosidad = bce_dfs["morosidad"]
    df_prud = bce_dfs["prudenciales"]
    df_ref_reestr = bce_dfs["ref_reestr"]

    df_tasas = parse_bce_tasas_series(RAW_DIR / "bce_tasas")
    df_wb, wb_last_updated = parse_worldbank_npl(RAW_DIR / "worldbank_FB.AST.NPER.ZS.json")

    validation_report = validate_datasets(
        df_cartera, df_depositos, df_morosidad, df_prud, df_tasas, df_wb
    )

    # Save cleaned CSVs
    df_cartera.to_csv(CLEAN_DIR / "cartera_segmentos.csv", index=False)
    df_depositos.to_csv(CLEAN_DIR / "depositos_subsistemas.csv", index=False)
    df_morosidad.to_csv(CLEAN_DIR / "morosidad_segmentos.csv", index=False)
    df_prud.to_csv(CLEAN_DIR / "indicadores_prudenciales.csv", index=False)
    df_tasas.to_csv(CLEAN_DIR / "tasas_referenciales_bce.csv", index=False)
    df_wb.to_csv(CLEAN_DIR / "benchmark_morosidad_wb.csv", index=False)

    # Build SQLite DB and cross-check every SQL query against independent pandas math
    build_sqlite(DB_PATH, df_cartera, df_depositos, df_morosidad, df_prud, df_tasas, df_wb)
    sql_summary = cross_check_pandas_vs_sqlite(
        DB_PATH, SQL_PATH, df_cartera, df_depositos, df_morosidad, df_prud, df_tasas, df_wb
    )
    (CLEAN_DIR / "resumen_sql_verificado.json").write_text(
        json.dumps(sql_summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    manifest = build_sources_manifest(
        df_cartera, df_depositos, df_morosidad, df_tasas, df_wb, wb_last_updated
    )
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    export_web_data_js(
        df_cartera,
        df_depositos,
        df_morosidad,
        df_prud,
        df_tasas,
        df_wb,
        df_ref_reestr,
        sql_summary,
        manifest,
        validation_report,
    )

    print("ETL completado y validado con éxito:")
    print(f"  - Validaciones aprobadas: {validation_report['passed']}/{validation_report['passed']}")
    for chk in validation_report["checks"]:
        print(f"    [OK] {chk['check']}: {chk['detail']}")
    print(f"  - Equivalencia pandas == SQLite verificada en {len(sql_summary['queries'])} consultas.")
    print(f"  - SQLite generado: {DB_PATH} ({DB_PATH.stat().st_size:,} bytes)")
    print(f"  - data.js generado: {DATA_JS_PATH} ({DATA_JS_PATH.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
