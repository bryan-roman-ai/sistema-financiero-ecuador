#!/usr/bin/env node
/**
 * Suite de pruebas automatizadas para sistema-financiero-ecuador.
 * Compatible con `node tests.js` y `deno run --allow-read --unstable-detect-cjs tests.js`.
 * Sale con código 1 si alguna verificación falla.
 */
"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");

const ROOT = __dirname;
const DATA = require(path.join(ROOT, "data.js"));
const APP = require(path.join(ROOT, "app.js"));

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    passed += 1;
    console.log("  [PASS] " + name);
  } catch (err) {
    failed += 1;
    console.error("  [FAIL] " + name + "\n         " + (err && err.message ? err.message : String(err)));
  }
}

function readCsvRows(relPath) {
  const txt = fs.readFileSync(path.join(ROOT, relPath), "utf8").trim();
  const lines = txt.split(/\r?\n/);
  const headers = lines[0].split(",");
  return lines.slice(1).map((line) => {
    // Simple CSV split sufficient for our clean numeric/text CSVs (no embedded commas inside values)
    const vals = line.split(",");
    const obj = {};
    headers.forEach((h, i) => {
      obj[h] = vals[i];
    });
    return obj;
  });
}

console.log("Ejecutando pruebas de sistema-financiero-ecuador...\n");

test("1. Archivos estáticos y obligatorios existen (sin CDN ni frameworks externos)", () => {
  const required = [
    "index.html",
    "style.css",
    "app.js",
    "data.js",
    "README.md",
    "LICENSE",
    "etl/clean_and_validate.py",
    "sql/consultas_analisis.sql",
    "data/sources_manifest.json",
    "data/sistema_financiero_ecuador.sqlite",
  ];
  for (const rel of required) {
    assert.ok(fs.existsSync(path.join(ROOT, rel)), "Falta archivo requerido: " + rel);
  }
  const html = fs.readFileSync(path.join(ROOT, "index.html"), "utf8");
  assert.ok(!/cdn\.|unpkg\.|jsdelivr\.|cdnjs\.|fonts\.googleapis/i.test(html), "index.html no debe cargar CDN externos");
  assert.ok(html.includes('lang="es"'), "index.html debe declarar lang=es");
});

test("2. Aviso educativo, pie de autor, accesibilidad y modo claro/oscuro en index.html y style.css", () => {
  const html = fs.readFileSync(path.join(ROOT, "index.html"), "utf8");
  const css = fs.readFileSync(path.join(ROOT, "style.css"), "utf8");
  assert.ok(html.includes("Herramienta educativa. No es asesoría financiera."), "Falta aviso educativo obligatorio");
  assert.ok(html.includes("Hecho por Bryan Román"), "Falta nombre del autor en pie");
  assert.ok(html.includes("linkedin.com/in/bryan-roman-ai"), "Falta enlace LinkedIn en pie");
  assert.ok(html.includes('id="theme-toggle"'), "Falta botón de modo claro/oscuro");
  assert.ok(html.includes("skip-link"), "Falta enlace de salto accesible");
  assert.ok(css.includes('[data-theme="dark"]'), "style.css debe definir modo oscuro");
});

test("3. Funciones puras de app.js coinciden con cálculo independiente sobre CSV limpio (octubre 2026)", () => {
  const carteraRows = readCsvRows("data/clean/cartera_segmentos.csv");
  const depRows = readCsvRows("data/clean/depositos_subsistemas.csv");

  const cOct26 = Number(
    carteraRows.find((r) => r.fecha === "2026-10" && r.segmento === "Total").saldo_mm_usd
  );
  const cOct25 = Number(
    carteraRows.find((r) => r.fecha === "2025-10" && r.segmento === "Total").saldo_mm_usd
  );
  const dOct26 = Number(
    depRows.find((r) => r.fecha === "2026-10" && r.subsistema === "TOTAL").total_mm_usd
  );

  // Verificación independiente de LDR y YoY
  const expectedLDR = Number(((100 * cOct26) / dOct26).toFixed(2));
  const expectedYoY = Number((((cOct26 - cOct25) / cOct25) * 100).toFixed(2));

  assert.strictEqual(APP.computeLDR(cOct26, dOct26), expectedLDR);
  assert.strictEqual(APP.computeLDR(DATA.kpis.cartera_total_mm, DATA.kpis.depositos_total_mm), DATA.kpis.ldr_pct);
  assert.strictEqual(APP.computeYoYPct(cOct26, cOct25), expectedYoY);
  assert.strictEqual(APP.computeLDR(100, 0), null);
  assert.strictEqual(APP.computeYoYPct(100, 0), null);
});

test("4. Spread y holgura legal BCE en app.js coinciden con archivo CSV oficial (noviembre 2026)", () => {
  const tasasRows = readCsvRows("data/clean/tasas_referenciales_bce.csv");
  const novConsumo = tasasRows.find((r) => r.fecha === "2026-11" && r.segmento === "Consumo");
  const novVip = tasasRows.find((r) => r.fecha === "2026-11" && r.segmento === "Vivienda de Interés Público");
  assert.ok(novConsumo && novVip, "Faltan filas de 2026-11 en tasas_referenciales_bce.csv");

  const tarCons = Number(novConsumo.tasa_activa_ref_pct);
  const maxCons = Number(novConsumo.tasa_activa_max_pct);
  const tpr = Number(novConsumo.tasa_pasiva_ref_pct);

  assert.strictEqual(APP.computeSpreadPP(tarCons, tpr), Number(novConsumo.spread_tar_tpr_pp));
  assert.strictEqual(APP.computeHeadroomPP(maxCons, tarCons), Number(novConsumo.holgura_bajo_tope_pp));
  assert.strictEqual(
    APP.computeHeadroomPP(Number(novVip.tasa_activa_max_pct), Number(novVip.tasa_activa_ref_pct)),
    0
  );
});

test("5. Benchmark Banco Mundial en data.js coincide con JSON crudo descargado de api.worldbank.org", () => {
  const rawWb = JSON.parse(
    fs.readFileSync(path.join(ROOT, "data/raw/worldbank_FB.AST.NPER.ZS.json"), "utf8")
  );
  const records = rawWb[1];
  const expectedCountries = ["CHL", "COL", "ECU", "MEX", "PER", "USA"];
  assert.deepStrictEqual(Object.keys(DATA.wb_series).sort(), expectedCountries);

  for (const iso of expectedCountries) {
    const rawCountry = records
      .filter((r) => r.countryiso3code === iso && r.value !== null)
      .sort((a, b) => Number(a.date) - Number(b.date));
    const lastRaw = rawCountry[rawCountry.length - 1];
    const lastDataJs = DATA.wb_series[iso][DATA.wb_series[iso].length - 1];
    assert.strictEqual(lastDataJs.anio, Number(lastRaw.date), "Último año distinto para " + iso);
    assert.strictEqual(
      lastDataJs.valor,
      Number(Number(lastRaw.value).toFixed(2)),
      "Último valor distinto para " + iso
    );
  }
});

test("6. Consultas SQLite exportadas en data.js coinciden con resumen_sql_verificado.json", () => {
  const sqlJson = JSON.parse(
    fs.readFileSync(path.join(ROOT, "data/clean/resumen_sql_verificado.json"), "utf8")
  );
  assert.strictEqual(sqlJson.verified_equivalent, true);
  assert.strictEqual(DATA.sql_consultas.length, 6);
  assert.deepStrictEqual(DATA.sql_consultas, sqlJson.queries);
});

test("7. Trazabilidad de fuentes: toda fuente tiene URL https, fecha de corte y cita literal", () => {
  assert.strictEqual(DATA.manifest.fuentes.length, 3);
  for (const f of DATA.manifest.fuentes) {
    assert.ok(f.url_archivo.startsWith("https://"), "URL inválida en " + f.id);
    assert.ok(f.fecha_corte && f.fecha_corte.length >= 4, "Falta fecha_corte en " + f.id);
    assert.ok(f.cita_literal && f.cita_literal.length > 20, "Falta cita_literal en " + f.id);
  }
});

test("8. Generadores SVG hechos a mano producen marcado válido y accesible", () => {
  const lineSvg = APP.renderMultiLineSVG({
    title: "Prueba línea",
    desc: "Descripción prueba",
    labels: ["2024-01", "2024-02", "2024-03"],
    seriesList: [{ name: "Serie A", color: "#0f4c81", values: [1.5, 2.5, 2.0] }],
    yUnit: "%",
    activeIndex: 1,
  });
  assert.ok(lineSvg.startsWith("<svg") && lineSvg.endsWith("</svg>"));
  assert.ok(lineSvg.includes('role="img"'));
  assert.ok(lineSvg.includes("<path d=\"M"));
  assert.ok(lineSvg.includes("<title"));

  const barSvg = APP.renderHorizontalBarsSVG({
    title: "Prueba barras",
    desc: "Barras prueba",
    items: [
      { label: "Consumo", value: 15.69, marker: 16.77 },
      { label: "Corporativo", value: 6.88, marker: 7.74 },
    ],
    showMarker: true,
    baseRefLine: { value: 4.83, label: "TPR 4,83%" },
  });
  assert.ok(barSvg.startsWith("<svg") && barSvg.endsWith("</svg>"));
  assert.ok(barSvg.includes("<rect"));

  const prudSvg = APP.renderGroupedPrudencialSVG(DATA.prudenciales_ultimo);
  assert.ok(prudSvg.startsWith("<svg") && prudSvg.endsWith("</svg>"));
});

test("9. Formateadores deterministas y filtros temporales en app.js", () => {
  assert.strictEqual(APP.fmtNum(76357.06, 2), "76.357,06");
  assert.strictEqual(APP.fmtPct(4.83), "4,83 %");
  assert.strictEqual(APP.fmtSignedPP(-0.29), "-0,29 pp");
  assert.strictEqual(APP.fmtSignedPP(1.27), "+1,27 pp");
  assert.strictEqual(APP.fmtNum(null), "N/D");

  const filtered = APP.filterByStartMonth(DATA.cartera_depositos_mensual, "2026-01");
  assert.strictEqual(filtered.length, 10, "Debe haber 10 meses en 2026 (ene-oct)");
  assert.strictEqual(filtered[0].fecha, "2026-01");
  assert.strictEqual(filtered[filtered.length - 1].fecha, "2026-10");

  const peakTpr = APP.getPeakEntry(DATA.tasas_mensual, "tpr");
  assert.strictEqual(peakTpr.fecha, "2024-07");
  assert.strictEqual(peakTpr.valor, 8.45);
});

console.log(`\nResumen: ${passed} aprobadas, ${failed} fallidas.`);
if (failed > 0) {
  process.exit(1);
}
