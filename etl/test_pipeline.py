#!/usr/bin/env python3
"""Pruebas automatizadas independientes para el pipeline ETL y la base SQLite.

Siguiendo las reglas de verificación, los valores esperados se recalculan
de forma independiente directamente desde los archivos crudos en data/raw/
(sin reutilizar el código de parseo de etl/clean_and_validate.py).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import unittest
from pathlib import Path

import openpyxl
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
CLEAN_DIR = ROOT / "data" / "clean"
DB_PATH = ROOT / "data" / "sistema_financiero_ecuador.sqlite"
MANIFEST_PATH = ROOT / "data" / "sources_manifest.json"
DATA_JS_PATH = ROOT / "data.js"


class TestSistemaFinancieroPipeline(unittest.TestCase):
    def test_clean_csvs_and_sqlite_row_counts_match(self) -> None:
        tables = [
            "cartera_segmentos",
            "depositos_subsistemas",
            "morosidad_segmentos",
            "indicadores_prudenciales",
            "tasas_referenciales_bce",
            "benchmark_morosidad_wb",
        ]
        conn = sqlite3.connect(DB_PATH)
        try:
            for tbl in tables:
                csv_path = CLEAN_DIR / f"{tbl}.csv"
                self.assertTrue(csv_path.exists(), f"Falta CSV limpio: {csv_path}")
                df_csv = pd.read_csv(csv_path)
                sql_count = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                self.assertEqual(
                    len(df_csv),
                    sql_count,
                    f"Conteo distinto en {tbl}: CSV={len(df_csv)} vs SQLite={sql_count}",
                )
                self.assertGreater(sql_count, 0, f"Tabla vacía: {tbl}")
        finally:
            conn.close()

    def test_independent_raw_excel_vs_sqlite_oct_2026(self) -> None:
        """Verifica cifras de octubre 2026 leyendo celdas crudas de Datos.xlsx."""
        wb = openpyxl.load_workbook(
            RAW_DIR / "bce_indicadores_monetarios_financieros.xlsx", data_only=True
        )
        # Cartera Total fila 304 col 8 (2026-10)
        ws_c = wb["3. Cartera"]
        raw_c_date = ws_c.cell(304, 2).value
        self.assertEqual((raw_c_date.year, raw_c_date.month), (2026, 10))
        raw_cartera_total = float(ws_c.cell(304, 8).value)
        raw_cartera_prod = float(ws_c.cell(304, 3).value)
        raw_cartera_cons = float(ws_c.cell(304, 4).value)

        # Depósitos Total fila 303 col 36 (2026-10)
        ws_d = wb["2. Depósitos"]
        raw_d_date = ws_d.cell(303, 2).value
        self.assertEqual((raw_d_date.year, raw_d_date.month), (2026, 10))
        raw_dep_total = float(ws_d.cell(303, 36).value)

        # Morosidad Total fila 303 col 8 y Microcrédito col 5 (2026-10)
        ws_m = wb["3. Morosidad"]
        raw_m_date = ws_m.cell(303, 2).value
        self.assertEqual((raw_m_date.year, raw_m_date.month), (2026, 10))
        raw_mor_total_pct = float(ws_m.cell(303, 8).value) * 100.0
        raw_mor_micro_pct = float(ws_m.cell(303, 5).value) * 100.0
        wb.close()

        conn = sqlite3.connect(DB_PATH)
        try:
            sql_c_tot = conn.execute(
                "SELECT saldo_mm_usd FROM cartera_segmentos WHERE fecha='2026-10' AND segmento='Total'"
            ).fetchone()[0]
            sql_c_prod = conn.execute(
                "SELECT saldo_mm_usd FROM cartera_segmentos WHERE fecha='2026-10' AND segmento='Productivo'"
            ).fetchone()[0]
            sql_c_cons = conn.execute(
                "SELECT saldo_mm_usd FROM cartera_segmentos WHERE fecha='2026-10' AND segmento='Consumo'"
            ).fetchone()[0]
            sql_d_tot = conn.execute(
                "SELECT total_mm_usd FROM depositos_subsistemas WHERE fecha='2026-10' AND subsistema='TOTAL'"
            ).fetchone()[0]
            sql_m_tot = conn.execute(
                "SELECT morosidad_pct FROM morosidad_segmentos WHERE fecha='2026-10' AND segmento='Total'"
            ).fetchone()[0]
            sql_m_micro = conn.execute(
                "SELECT morosidad_pct FROM morosidad_segmentos WHERE fecha='2026-10' AND segmento='Microcrédito'"
            ).fetchone()[0]
        finally:
            conn.close()

        self.assertAlmostEqual(sql_c_tot, raw_cartera_total, places=4)
        self.assertAlmostEqual(sql_c_prod, raw_cartera_prod, places=4)
        self.assertAlmostEqual(sql_c_cons, raw_cartera_cons, places=4)
        self.assertAlmostEqual(sql_d_tot, raw_dep_total, places=4)
        self.assertAlmostEqual(sql_m_tot, raw_mor_total_pct, places=4)
        self.assertAlmostEqual(sql_m_micro, raw_mor_micro_pct, places=4)

        # Ratio LDR independiente
        expected_ldr = round(100.0 * raw_cartera_total / raw_dep_total, 2)
        resumen = json.loads((CLEAN_DIR / "resumen_sql_verificado.json").read_text(encoding="utf-8"))
        q2_2026 = [
            r
            for q in resumen["queries"]
            if q["id"] == "q2_intermediacion_fondeo_anual"
            for r in q["rows"]
            if r["anio"] == "2026"
        ][0]
        self.assertEqual(q2_2026["ratio_cartera_depositos_pct"], expected_ldr)

    def test_independent_worldbank_json_vs_sqlite(self) -> None:
        meta, recs = json.loads(
            (RAW_DIR / "worldbank_FB.AST.NPER.ZS.json").read_text(encoding="utf-8")
        )
        self.assertEqual(meta["sourceid"], "2")
        raw_ecu_2025 = [
            r["value"] for r in recs if r["countryiso3code"] == "ECU" and r["date"] == "2025"
        ][0]
        raw_usa_2025 = [
            r["value"] for r in recs if r["countryiso3code"] == "USA" and r["date"] == "2025"
        ][0]
        raw_per_2024 = [
            r["value"] for r in recs if r["countryiso3code"] == "PER" and r["date"] == "2024"
        ][0]

        conn = sqlite3.connect(DB_PATH)
        try:
            sql_ecu = conn.execute(
                "SELECT morosidad_pct FROM benchmark_morosidad_wb WHERE pais_iso3='ECU' AND anio=2025"
            ).fetchone()[0]
            sql_usa = conn.execute(
                "SELECT morosidad_pct FROM benchmark_morosidad_wb WHERE pais_iso3='USA' AND anio=2025"
            ).fetchone()[0]
            sql_per = conn.execute(
                "SELECT morosidad_pct FROM benchmark_morosidad_wb WHERE pais_iso3='PER' AND anio=2024"
            ).fetchone()[0]
        finally:
            conn.close()

        self.assertAlmostEqual(sql_ecu, raw_ecu_2025, places=4)
        self.assertAlmostEqual(sql_usa, raw_usa_2025, places=4)
        self.assertAlmostEqual(sql_per, raw_per_2024, places=4)

    def test_independent_bce_tasas_nov_2026(self) -> None:
        html_txt = (RAW_DIR / "bce_tasas" / "2026-11.htm").read_bytes().decode("cp1252", "ignore")
        self.assertIn("Noviembre 2026", html_txt)
        self.assertIn("4,83", html_txt)
        self.assertIn("15,69", html_txt)
        self.assertIn("16,77", html_txt)

        df_t = pd.read_csv(CLEAN_DIR / "tasas_referenciales_bce.csv")
        row_cons = df_t[(df_t["fecha"] == "2026-11") & (df_t["segmento"] == "Consumo")].iloc[0]
        self.assertAlmostEqual(row_cons["tasa_pasiva_ref_pct"], 4.83, places=2)
        self.assertAlmostEqual(row_cons["tasa_activa_ref_pct"], 15.69, places=2)
        self.assertAlmostEqual(row_cons["tasa_activa_max_pct"], 16.77, places=2)
        self.assertAlmostEqual(row_cons["spread_tar_tpr_pp"], 15.69 - 4.83, places=2)
        self.assertAlmostEqual(row_cons["holgura_bajo_tope_pp"], 16.77 - 15.69, places=2)

    def test_manifest_sha256_and_metadata(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["fuentes"]), 3)
        for src in manifest["fuentes"]:
            self.assertTrue(src["url_archivo"].startswith("https://"))
            self.assertTrue(len(src["cita_literal"]) > 20)
            self.assertTrue(len(src["fecha_corte"]) >= 4)

        # Verify actual SHA-256 of raw files matches manifest
        h_wb = hashlib.sha256((RAW_DIR / "worldbank_FB.AST.NPER.ZS.json").read_bytes()).hexdigest()
        h_bce = hashlib.sha256(
            (RAW_DIR / "bce_indicadores_monetarios_financieros.xlsx").read_bytes()
        ).hexdigest()
        manifest_by_id = {f["id"]: f for f in manifest["fuentes"]}
        self.assertEqual(manifest_by_id["worldbank_npl"]["sha256"], h_wb)
        self.assertEqual(manifest_by_id["bce_sb_seps_datos"]["sha256"], h_bce)

    def test_data_js_exists_and_nonempty(self) -> None:
        self.assertTrue(DATA_JS_PATH.exists())
        self.assertGreater(DATA_JS_PATH.stat().st_size, 50_000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
