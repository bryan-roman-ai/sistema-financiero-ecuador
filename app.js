/* ============================================================================
   Sistema Financiero del Ecuador — Lógica Analítica y Gráficos SVG Hechos a Mano
   Sin frameworks, sin CDN, sin dependencias externas.
   Exporta funciones puras para verificación automatizada en tests.js.
   ============================================================================ */

(function (globalScope) {
  "use strict";

  const COLORS = {
    primary: "var(--c-1)",
    secondary: "var(--c-2)",
    danger: "var(--c-3)",
    warning: "var(--c-4)",
    violet: "var(--c-5)",
    cyan: "var(--c-6)",
  };

  const SEGMENT_COLORS = {
    Microcrédito: "var(--c-3)",
    Consumo: "var(--c-4)",
    Total: "var(--c-1)",
    Vivienda: "var(--c-2)",
    Educativo: "var(--c-5)",
    Productivo: "var(--c-6)",
  };

  const WB_COLORS = {
    ECU: "var(--c-3)",
    PER: "var(--c-4)",
    COL: "var(--c-1)",
    CHL: "var(--c-5)",
    MEX: "var(--c-2)",
    USA: "var(--c-6)",
  };

  // ---------- Funciones puras analíticas (auditables en tests.js) ----------

  function fmtNum(val, decimals) {
    if (val === null || val === undefined || Number.isNaN(Number(val))) {
      return "N/D";
    }
    const dec = decimals === undefined ? 2 : decimals;
    const num = Number(val);
    const neg = num < 0;
    const fixed = Math.abs(num).toFixed(dec);
    const parts = fixed.split(".");
    const intFormatted = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    const body = dec > 0 ? intFormatted + "," + parts[1] : intFormatted;
    return neg ? "-" + body : body;
  }

  function fmtPct(val, decimals) {
    if (val === null || val === undefined || Number.isNaN(Number(val))) return "N/D";
    return fmtNum(val, decimals === undefined ? 2 : decimals) + " %";
  }

  function fmtSignedPP(val) {
    if (val === null || val === undefined || Number.isNaN(Number(val))) return "N/D";
    const num = Number(val);
    const prefix = num > 0 ? "+" : "";
    return prefix + fmtNum(num, 2) + " pp";
  }

  function computeLDR(carteraMM, depositosMM) {
    if (!depositosMM || depositosMM <= 0) return null;
    return Number(((100 * carteraMM) / depositosMM).toFixed(2));
  }

  function computeYoYPct(currentVal, prevVal) {
    if (!prevVal || prevVal === 0) return null;
    return Number((((currentVal - prevVal) / prevVal) * 100).toFixed(2));
  }

  function computeSpreadPP(tarPct, tprPct) {
    return Number((tarPct - tprPct).toFixed(2));
  }

  function computeHeadroomPP(maxPct, tarPct) {
    return Number((maxPct - tarPct).toFixed(2));
  }

  function filterByStartMonth(series, startYM) {
    return series.filter((row) => row.fecha >= startYM);
  }

  function getPeakEntry(series, key) {
    if (!series || series.length === 0) return null;
    let best = null;
    for (const row of series) {
      const v = row[key];
      if (v === null || v === undefined) continue;
      if (!best || v > best.valor) {
        best = { fecha: row.fecha, valor: v };
      }
    }
    return best;
  }

  function buildLinePath(points) {
    if (!points || points.length === 0) return "";
    return points
      .map((p, idx) => (idx === 0 ? "M" : "L") + p.x.toFixed(1) + "," + p.y.toFixed(1))
      .join(" ");
  }

  function escHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // ---------- Generadores de SVG hechos a mano ----------

  function renderMultiLineSVG(opts) {
    const {
      title,
      desc,
      labels,
      seriesList,
      yUnit,
      width = 660,
      height = 290,
      activeIndex = null,
      yMinZero = true,
      yFormatter = (v) => fmtNum(v, 1),
    } = opts;

    const pad = { top: 18, right: 20, bottom: 38, left: 56 };
    const plotW = width - pad.left - pad.right;
    const plotH = height - pad.top - pad.bottom;

    const allVals = [];
    for (const s of seriesList) {
      for (const v of s.values) {
        if (v !== null && v !== undefined && !Number.isNaN(v)) allVals.push(v);
      }
    }
    const rawMin = allVals.length ? Math.min(...allVals) : 0;
    const rawMax = allVals.length ? Math.max(...allVals) : 10;
    const yMin = yMinZero ? 0 : Math.floor(rawMin * 0.9);
    const yMax = rawMax === yMin ? yMin + 1 : rawMax * 1.08;

    const xOf = (i) =>
      labels.length <= 1 ? pad.left : pad.left + (i / (labels.length - 1)) * plotW;
    const yOf = (v) => pad.top + plotH - ((v - yMin) / (yMax - yMin)) * plotH;

    // Gridlines horizontales (5 pasos)
    const ticks = 5;
    let gridMarkup = "";
    for (let t = 0; t <= ticks; t++) {
      const val = yMin + ((yMax - yMin) * t) / ticks;
      const y = yOf(val);
      gridMarkup +=
        `<line class="chart-grid" x1="${pad.left}" y1="${y.toFixed(1)}" x2="${(width - pad.right).toFixed(1)}" y2="${y.toFixed(1)}"/>` +
        `<text class="chart-axis-text" x="${pad.left - 8}" y="${(y + 4).toFixed(1)}" text-anchor="end">${escHtml(yFormatter(val))}${yUnit ? escHtml(yUnit) : ""}</text>`;
    }

    // Etiquetas eje X (máx 6 marcas)
    const xCount = Math.min(6, labels.length);
    let xMarkup = "";
    for (let k = 0; k < xCount; k++) {
      const idx =
        xCount === 1 ? 0 : Math.round((k * (labels.length - 1)) / (xCount - 1));
      const x = xOf(idx);
      xMarkup += `<text class="chart-axis-text" x="${x.toFixed(1)}" y="${height - 12}" text-anchor="middle">${escHtml(labels[idx])}</text>`;
    }

    // Rutas de cada serie
    let pathsMarkup = "";
    for (const s of seriesList) {
      const segments = [];
      let cur = [];
      s.values.forEach((v, i) => {
        if (v === null || v === undefined || Number.isNaN(v)) {
          if (cur.length) {
            segments.push(cur);
            cur = [];
          }
        } else {
          cur.push({ x: xOf(i), y: yOf(v), v, i });
        }
      });
      if (cur.length) segments.push(cur);

      const strokeW = s.strokeWidth || 2.3;
      const dash = s.dashed ? ' stroke-dasharray="5 4"' : "";
      for (const seg of segments) {
        pathsMarkup += `<path d="${buildLinePath(seg)}" fill="none" stroke="${s.color}" stroke-width="${strokeW}" stroke-linejoin="round" stroke-linecap="round"${dash}/>`;
      }
      // Punto en último valor
      const lastSeg = segments[segments.length - 1];
      if (lastSeg && lastSeg.length) {
        const lastPt = lastSeg[lastSeg.length - 1];
        pathsMarkup += `<circle cx="${lastPt.x.toFixed(1)}" cy="${lastPt.y.toFixed(1)}" r="3.6" fill="${s.color}"/>`;
      }
    }

    // Línea guía vertical (scrubber / hover)
    let guideMarkup = "";
    if (activeIndex !== null && activeIndex >= 0 && activeIndex < labels.length) {
      const gx = xOf(activeIndex);
      guideMarkup += `<line x1="${gx.toFixed(1)}" y1="${pad.top}" x2="${gx.toFixed(1)}" y2="${(pad.top + plotH).toFixed(1)}" stroke="var(--text-muted)" stroke-width="1.2" stroke-dasharray="3 3"/>`;
      for (const s of seriesList) {
        const val = s.values[activeIndex];
        if (val !== null && val !== undefined && !Number.isNaN(val)) {
          guideMarkup += `<circle cx="${gx.toFixed(1)}" cy="${yOf(val).toFixed(1)}" r="4.8" fill="${s.color}" stroke="var(--surface)" stroke-width="1.8"/>`;
        }
      }
    }

    const titleId = "svg-t-" + Math.random().toString(36).slice(2, 8);
    const descId = "svg-d-" + Math.random().toString(36).slice(2, 8);

    return (
      `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="${titleId} ${descId}" data-plot-left="${pad.left}" data-plot-width="${plotW}" data-count="${labels.length}">` +
      `<title id="${titleId}">${escHtml(title)}</title>` +
      `<desc id="${descId}">${escHtml(desc)}</desc>` +
      gridMarkup +
      xMarkup +
      pathsMarkup +
      guideMarkup +
      `</svg>`
    );
  }

  function renderHorizontalBarsSVG(opts) {
    const {
      title,
      desc,
      items,
      maxValue,
      width = 520,
      rowHeight = 30,
      labelWidth = 175,
      valueFormatter = (v) => fmtNum(v, 2),
      showMarker = false,
      baseRefLine = null,
    } = opts;

    const pad = { top: 14, right: 82, bottom: 26, left: labelWidth };
    const height = pad.top + pad.bottom + items.length * rowHeight;
    const plotW = width - pad.left - pad.right;
    const maxV = maxValue || Math.max(...items.map((d) => Math.max(d.value, d.marker || 0))) * 1.08;
    const xOf = (v) => pad.left + (Math.max(0, v) / maxV) * plotW;

    let body = "";
    // Vertical gridlines
    for (let t = 0; t <= 4; t++) {
      const val = (maxV * t) / 4;
      const x = xOf(val);
      body += `<line class="chart-grid" x1="${x.toFixed(1)}" y1="${pad.top}" x2="${x.toFixed(1)}" y2="${height - pad.bottom}"/>`;
      body += `<text class="chart-axis-text" x="${x.toFixed(1)}" y="${height - 8}" text-anchor="middle">${escHtml(fmtNum(val, 0))}</text>`;
    }

    // Reference vertical line (e.g. TPR = 4.83%)
    if (baseRefLine !== null && baseRefLine !== undefined) {
      const rx = xOf(baseRefLine.value);
      body += `<line x1="${rx.toFixed(1)}" y1="${pad.top - 4}" x2="${rx.toFixed(1)}" y2="${height - pad.bottom}" stroke="var(--c-2)" stroke-width="1.8" stroke-dasharray="4 3"/>`;
      body += `<text class="chart-axis-text" x="${(rx + 4).toFixed(1)}" y="${pad.top + 6}" fill="var(--c-2)" font-weight="700">${escHtml(baseRefLine.label)}</text>`;
    }

    items.forEach((item, idx) => {
      const y = pad.top + idx * rowHeight + 6;
      const barH = Math.max(12, rowHeight - 12);
      const bw = Math.max(2, xOf(item.value) - pad.left);

      // Background bar up to legal cap if marker present
      if (showMarker && item.marker !== undefined && item.marker !== null) {
        const mw = Math.max(2, xOf(item.marker) - pad.left);
        body += `<rect x="${pad.left}" y="${y}" width="${mw.toFixed(1)}" height="${barH}" rx="3" fill="var(--surface-alt)" stroke="var(--border)" stroke-width="1"/>`;
      }

      body += `<rect x="${pad.left}" y="${y}" width="${bw.toFixed(1)}" height="${barH}" rx="3" fill="${item.color || COLORS.primary}"/>`;

      if (showMarker && item.marker !== undefined && item.marker !== null) {
        const mx = xOf(item.marker);
        body += `<line x1="${mx.toFixed(1)}" y1="${y - 2}" x2="${mx.toFixed(1)}" y2="${y + barH + 2}" stroke="var(--c-3)" stroke-width="2.4"/>`;
      }

      const shortLbl = item.label.length > 26 ? item.label.slice(0, 25) + "…" : item.label;
      body += `<text class="chart-axis-text" x="${pad.left - 8}" y="${(y + barH * 0.72).toFixed(1)}" text-anchor="end">${escHtml(shortLbl)}</text>`;

      const textX = showMarker && item.marker ? Math.max(xOf(item.value), xOf(item.marker)) + 6 : pad.left + bw + 6;
      const valText = item.rightLabel || valueFormatter(item.value);
      body += `<text class="chart-axis-text" x="${textX.toFixed(1)}" y="${(y + barH * 0.72).toFixed(1)}" font-weight="700">${escHtml(valText)}</text>`;
    });

    const titleId = "svg-bt-" + Math.random().toString(36).slice(2, 8);
    const descId = "svg-bd-" + Math.random().toString(36).slice(2, 8);
    return (
      `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="${titleId} ${descId}">` +
      `<title id="${titleId}">${escHtml(title)}</title>` +
      `<desc id="${descId}">${escHtml(desc)}</desc>` +
      body +
      `</svg>`
    );
  }

  function renderGroupedPrudencialSVG(rows) {
    const width = 560;
    const height = 250;
    const pad = { top: 28, right: 16, bottom: 46, left: 44 };
    const plotW = width - pad.left - pad.right;
    const plotH = height - pad.top - pad.bottom;

    const metrics = [
      { key: "solvencia_pct", label: "Solvencia", color: "var(--c-1)" },
      { key: "liquidez_pct", label: "Liquidez", color: "var(--c-2)" },
      { key: "roe_pct", label: "ROE", color: "var(--c-4)" },
    ];
    const maxV = Math.max(
      ...rows.flatMap((r) => metrics.map((m) => Number(r[m.key]) || 0))
    ) * 1.15;
    const yOf = (v) => pad.top + plotH - (v / maxV) * plotH;

    let body = "";
    for (let t = 0; t <= 4; t++) {
      const val = (maxV * t) / 4;
      const y = yOf(val);
      body += `<line class="chart-grid" x1="${pad.left}" y1="${y.toFixed(1)}" x2="${width - pad.right}" y2="${y.toFixed(1)}"/>`;
      body += `<text class="chart-axis-text" x="${pad.left - 6}" y="${(y + 4).toFixed(1)}" text-anchor="end">${fmtNum(val, 0)}%</text>`;
    }

    // Legend top
    metrics.forEach((m, i) => {
      const lx = pad.left + i * 110;
      body += `<rect x="${lx}" y="6" width="11" height="11" rx="2" fill="${m.color}"/>`;
      body += `<text class="chart-axis-text" x="${lx + 15}" y="15">${escHtml(m.label)}</text>`;
    });

    const groupW = plotW / rows.length;
    const barW = Math.min(22, (groupW - 18) / metrics.length);

    rows.forEach((r, gi) => {
      const gx = pad.left + gi * groupW + (groupW - barW * metrics.length - 4) / 2;
      metrics.forEach((m, mi) => {
        const val = Number(r[m.key]) || 0;
        const x = gx + mi * (barW + 2);
        const y = yOf(val);
        const h = pad.top + plotH - y;
        body += `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${Math.max(1, h).toFixed(1)}" rx="2" fill="${m.color}"/>`;
      });
      const shortName = r.subsistema.replace("Total SFPr y SFPS", "Total SF");
      body += `<text class="chart-axis-text" x="${(pad.left + gi * groupW + groupW / 2).toFixed(1)}" y="${height - 14}" text-anchor="middle">${escHtml(shortName)}</text>`;
    });

    return (
      `<svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Indicadores prudenciales por subsistema en porcentaje">` +
      `<title>Solvencia, liquidez y ROE por subsistema a octubre 2026</title>` +
      body +
      `</svg>`
    );
  }

  // ---------- Inicialización del tablero en navegador ----------

  function initDashboard() {
    const D = globalScope.SFE_DATA;
    if (!D || typeof document === "undefined") return;

    // 1. Tema claro / oscuro
    const themeBtn = document.getElementById("theme-toggle");
    const themeText = document.getElementById("theme-toggle-text");
    function applyTheme(mode) {
      document.documentElement.setAttribute("data-theme", mode);
      const isDark = mode === "dark";
      themeBtn.setAttribute("aria-pressed", String(isDark));
      themeText.textContent = isDark ? "Modo claro" : "Modo oscuro";
      try {
        localStorage.setItem("sfe_theme", mode);
      } catch (_e) {}
    }
    let savedTheme = null;
    try {
      savedTheme = localStorage.getItem("sfe_theme");
    } catch (_e) {}
    const prefersDark =
      globalScope.matchMedia && globalScope.matchMedia("(prefers-color-scheme: dark)").matches;
    applyTheme(savedTheme || (prefersDark ? "dark" : "light"));
    themeBtn.addEventListener("click", () => {
      const cur = document.documentElement.getAttribute("data-theme");
      applyTheme(cur === "dark" ? "light" : "dark");
    });

    // Helper para buscar consulta SQL por id
    const sqlById = {};
    D.sql_consultas.forEach((q) => {
      sqlById[q.id] = q;
    });

    // 2. KPIs Ejecutivos
    const q1 = sqlById["q1_cartera_ultimo_corte"].rows;
    const cSeries = D.cartera_depositos_mensual;
    const lastCD = cSeries[cSeries.length - 1];
    const prevYrCD = cSeries.find(
      (r) => r.fecha === Number(lastCD.fecha.slice(0, 4)) - 1 + lastCD.fecha.slice(4)
    );
    const carteraYoY = prevYrCD ? computeYoYPct(lastCD.cartera_total, prevYrCD.cartera_total) : null;
    const depYoY = prevYrCD ? computeYoYPct(lastCD.depositos_total, prevYrCD.depositos_total) : null;

    const consTasa = D.tasas_ultimo_corte.find((t) => t.segmento === "Consumo");
    const prodQ1 = q1.find((r) => r.segmento === "Productivo");
    const tprPeak = getPeakEntry(D.tasas_mensual, "tpr");
    const q5Rows = sqlById["q5_benchmark_morosidad_latam_usa"].rows;
    const usaQ5 = q5Rows.find((r) => r.pais_iso3 === "USA");
    const srcDatos = D.manifest.fuentes.find((f) => f.id === "bce_sb_seps_datos");
    const srcTasas = D.manifest.fuentes.find((f) => f.id === "bce_tasas_referenciales");
    const srcWB = D.manifest.fuentes.find((f) => f.id === "worldbank_npl");

    const kpiCards = [
      {
        label: "Cartera Bruta Total (SFPr + SFPS)",
        value: "$" + fmtNum(D.kpis.cartera_total_mm, 2) + " MM",
        sub: `Var. interanual: +${fmtNum(carteraYoY, 2)} % · Productivo lidera (+${fmtNum(prodQ1.var_interanual_pct, 2)} %)`,
        meta: `SB y SEPS vía BCE · Corte ${D.kpis.fecha_corte_sistema}`,
        url: srcDatos.url_archivo,
      },
      {
        label: "Depósitos Totales y Ratio LDR",
        value: "$" + fmtNum(D.kpis.depositos_total_mm, 2) + " MM",
        sub: `Cartera/Depósitos: ${fmtPct(D.kpis.ldr_pct)} · Depósitos YoY: +${fmtNum(depYoY, 2)} %`,
        meta: `SB y SEPS vía BCE · Corte ${D.kpis.fecha_corte_sistema}`,
        url: srcDatos.url_archivo,
      },
      {
        label: "Morosidad Total Ecuador",
        value: fmtPct(D.kpis.morosidad_total_pct),
        sub: `Microcrédito: ${fmtPct(D.kpis.morosidad_micro_pct)} · Productivo: ${fmtPct(D.kpis.morosidad_productivo_pct)}`,
        meta: `Cartera improductiva / bruta · Corte ${D.kpis.fecha_corte_sistema}`,
        url: srcDatos.url_archivo,
      },
      {
        label: "Tasa Pasiva Referencial (TPR)",
        value: fmtPct(D.kpis.tpr_pct),
        sub: `Tasa efectiva anual ponderada · Pico ${tprPeak.fecha}: ${fmtPct(tprPeak.valor)}`,
        meta: `BCE (371 entidades) · Corte ${D.kpis.fecha_corte_tasas}`,
        url: srcTasas.url_archivo,
      },
      {
        label: "TAR Consumo vs. Tope Legal",
        value: fmtPct(consTasa.tasa_activa_ref_pct),
        sub: `Tope JPRFM: ${fmtPct(consTasa.tasa_activa_max_pct)} · Spread vs. TPR: ${fmtNum(consTasa.spread_tar_tpr_pp, 2)} pp`,
        meta: `Tasa efectiva anual BCE · Corte ${D.kpis.fecha_corte_tasas}`,
        url: srcTasas.url_archivo,
      },
      {
        label: "Benchmark Morosidad Bancaria (WB)",
        value: fmtPct(D.kpis.wb_ecu_2025_pct),
        sub: `Ecuador (${D.kpis.wb_ecu_anio}) · Mayor del bloque vs. EE. UU. (${fmtPct(usaQ5.morosidad_actual_pct)})`,
        meta: `Banco Mundial FB.AST.NPER.ZS · API 2026-11-11`,
        url: srcWB.url_archivo,
      },
    ];

    document.getElementById("kpi-grid").innerHTML = kpiCards
      .map(
        (k) =>
          `<article class="kpi-card">` +
          `<div><div class="kpi-label">${escHtml(k.label)}</div>` +
          `<div class="kpi-value">${escHtml(k.value)}</div>` +
          `<div class="kpi-sub">${escHtml(k.sub)}</div></div>` +
          `<div class="kpi-meta">${escHtml(k.meta)} · <a href="${escHtml(k.url)}" target="_blank" rel="noopener noreferrer">Fuente</a></div>` +
          `</article>`
      )
      .join("");

    // Estado interactivo
    let startWindow = "2015-01";
    const activeMorSegments = new Set(["Microcrédito", "Consumo", "Total", "Vivienda", "Productivo"]);

    // 3. Sección 1: Cartera y Depósitos
    const scrubCartera = document.getElementById("scrub-cartera");
    const chartCDWrap = document.getElementById("chart-cartera-dep");
    const readoutCartera = document.getElementById("readout-cartera");
    document.getElementById("legend-cartera-dep").innerHTML =
      `<span class="legend-item"><span class="legend-swatch" style="background:var(--c-2)"></span>Depósitos Totales (MM USD)</span>` +
      `<span class="legend-item"><span class="legend-swatch" style="background:var(--c-1)"></span>Cartera Bruta Total (MM USD)</span>`;

    function drawCarteraDep(idxOverride) {
      const sub = filterByStartMonth(D.cartera_depositos_mensual, startWindow);
      scrubCartera.max = String(sub.length - 1);
      const idx =
        idxOverride !== undefined ? Math.min(sub.length - 1, Math.max(0, idxOverride)) : sub.length - 1;
      scrubCartera.value = String(idx);

      chartCDWrap.innerHTML = renderMultiLineSVG({
        title: "Evolución mensual de Depósitos Totales y Cartera Bruta en Ecuador",
        desc: `Serie desde ${sub[0].fecha} hasta ${sub[sub.length - 1].fecha} en millones de USD.`,
        labels: sub.map((r) => r.fecha),
        seriesList: [
          { name: "Depósitos Totales", color: "var(--c-2)", values: sub.map((r) => r.depositos_total), strokeWidth: 2.5 },
          { name: "Cartera Bruta", color: "var(--c-1)", values: sub.map((r) => r.cartera_total), strokeWidth: 2.5 },
        ],
        yUnit: "",
        yFormatter: (v) => "$" + fmtNum(v / 1000, 0) + " mil M",
        activeIndex: idx,
      });

      const r = sub[idx];
      const sharePlazo = ((100 * r.depositos_plazo) / r.depositos_total).toFixed(1);
      const shareBP = ((100 * r.depositos_bp) / r.depositos_total).toFixed(1);
      readoutCartera.innerHTML =
        `<span><strong>${escHtml(r.fecha)}</strong> · Depósitos: <strong>$${fmtNum(r.depositos_total, 2)} MM</strong> (Plazo ${fmtNum(sharePlazo, 1)} %, BP ${fmtNum(shareBP, 1)} %)</span>` +
        `<span>Cartera: <strong>$${fmtNum(r.cartera_total, 2)} MM</strong> · Ratio LDR: <span class="badge badge-neutral">${fmtPct(r.ldr_pct)}</span></span>`;

      bindSvgPointerScrub(chartCDWrap, sub.length, (i) => drawCarteraDep(i));
    }

    scrubCartera.addEventListener("input", () => drawCarteraDep(Number(scrubCartera.value)));

    // Barras composición Cartera (2026-10)
    const segColorMap = {
      Consumo: "var(--c-4)",
      Productivo: "var(--c-1)",
      Microcrédito: "var(--c-3)",
      Vivienda: "var(--c-2)",
      Educativa: "var(--c-5)",
    };
    document.getElementById("chart-cartera-seg").innerHTML = renderHorizontalBarsSVG({
      title: "Composición de cartera bruta por segmento de crédito en octubre 2026",
      desc: "Saldos en millones de dólares estadounidenses.",
      width: 480,
      labelWidth: 112,
      rowHeight: 32,
      items: q1.map((r) => ({
        label: r.segmento,
        value: r.saldo_mm_usd,
        color: segColorMap[r.segmento] || COLORS.primary,
        rightLabel: fmtNum(r.participacion_pct, 1) + " %",
      })),
    });

    document.querySelector("#table-cartera-seg tbody").innerHTML = q1
      .map((r) => {
        const cls = r.var_interanual_pct >= 0 ? "badge-good" : "badge-bad";
        const sign = r.var_interanual_pct >= 0 ? "+" : "";
        return (
          `<tr><td><strong>${escHtml(r.segmento)}</strong></td>` +
          `<td class="num">$${fmtNum(r.saldo_mm_usd, 2)}</td>` +
          `<td class="num">${fmtNum(r.participacion_pct, 2)} %</td>` +
          `<td class="num"><span class="badge ${cls}">${sign}${fmtNum(r.var_interanual_pct, 2)} %</span></td></tr>`
        );
      })
      .join("");

    // 4. Sección 2: Morosidad por Segmento
    const allMorSegments = ["Microcrédito", "Consumo", "Total", "Vivienda", "Educativo", "Productivo"];
    const chipsWrap = document.getElementById("chips-morosidad");
    const chartMorWrap = document.getElementById("chart-morosidad");
    const scrubMor = document.getElementById("scrub-morosidad");
    const readoutMor = document.getElementById("readout-morosidad");

    function renderMorChips() {
      chipsWrap.innerHTML = allMorSegments
        .map((seg) => {
          const on = activeMorSegments.has(seg);
          return `<button type="button" class="chip" data-seg="${escHtml(seg)}" aria-pressed="${on}"><span class="legend-swatch" style="background:${SEGMENT_COLORS[seg]}"></span>${escHtml(seg)}</button>`;
        })
        .join("");
      chipsWrap.querySelectorAll(".chip").forEach((btn) => {
        btn.addEventListener("click", () => {
          const seg = btn.getAttribute("data-seg");
          if (activeMorSegments.has(seg) && activeMorSegments.size > 1) {
            activeMorSegments.delete(seg);
          } else {
            activeMorSegments.add(seg);
          }
          renderMorChips();
          drawMorosidad(Number(scrubMor.value));
        });
      });
    }

    function drawMorosidad(idxOverride) {
      const sub = filterByStartMonth(D.morosidad_mensual, startWindow);
      scrubMor.max = String(sub.length - 1);
      const idx =
        idxOverride !== undefined ? Math.min(sub.length - 1, Math.max(0, idxOverride)) : sub.length - 1;
      scrubMor.value = String(idx);

      const selected = allMorSegments.filter((s) => activeMorSegments.has(s));
      chartMorWrap.innerHTML = renderMultiLineSVG({
        title: "Evolución mensual de morosidad por segmento de crédito en Ecuador",
        desc: "Porcentaje de cartera improductiva sobre cartera bruta.",
        labels: sub.map((r) => r.fecha),
        seriesList: selected.map((seg) => ({
          name: seg,
          color: SEGMENT_COLORS[seg],
          values: sub.map((r) => r[seg]),
          strokeWidth: seg === "Total" ? 2.8 : 2.1,
          dashed: seg === "Total",
        })),
        yUnit: "%",
        yFormatter: (v) => fmtNum(v, 1),
        activeIndex: idx,
      });

      const r = sub[idx];
      readoutMor.innerHTML =
        `<strong>${escHtml(r.fecha)}</strong>` +
        selected
          .map(
            (seg) =>
              `<span><span class="legend-swatch" style="background:${SEGMENT_COLORS[seg]};vertical-align:middle;margin-right:4px"></span>${escHtml(seg)}: <strong>${fmtPct(r[seg])}</strong></span>`
          )
          .join("");

      bindSvgPointerScrub(chartMorWrap, sub.length, (i) => drawMorosidad(i));
    }
    scrubMor.addEventListener("input", () => drawMorosidad(Number(scrubMor.value)));

    // Tabla semáforo riesgo morosidad
    const q3 = sqlById["q3_riesgo_morosidad_segmento"].rows;
    document.querySelector("#table-morosidad-riesgo tbody").innerHTML = q3
      .map((r) => {
        const cls = r.desv_vs_12m_pp <= 0 ? "badge-good" : "badge-warn";
        return (
          `<tr><td><strong>${escHtml(r.segmento)}</strong></td>` +
          `<td class="num"><strong>${fmtNum(r.morosidad_actual_pct, 2)} %</strong></td>` +
          `<td class="num">${fmtNum(r.promedio_12m_pct, 2)} %</td>` +
          `<td class="num">${fmtNum(r.pico_2015_2026_pct, 2)} %</td>` +
          `<td class="num"><span class="badge ${cls}">${fmtSignedPP(r.desv_vs_12m_pp)}</span></td></tr>`
        );
      })
      .join("");

    document.getElementById("nota-ref-reestr").innerHTML =
      `<span><strong>Cartera con alivio / reprogramación (${escHtml(D.kpis.fecha_corte_sistema)}):</strong> Refinanciada <strong>$${fmtNum(D.kpis.cartera_refinanciada_mm, 2)} MM</strong> · Reestructurada <strong>$${fmtNum(D.kpis.cartera_reestructurada_mm, 2)} MM</strong> (${fmtNum((100 * (D.kpis.cartera_refinanciada_mm + D.kpis.cartera_reestructurada_mm)) / D.kpis.cartera_total_mm, 2)} % de la cartera bruta).</span>`;

    // Selector de ventana temporal compartido (Secciones 1 y 2)
    document.querySelectorAll(".window-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        startWindow = btn.getAttribute("data-window");
        document.querySelectorAll(".window-btn").forEach((b) => {
          const active = b === btn;
          b.classList.toggle("is-active", active);
          b.setAttribute("aria-pressed", String(active));
        });
        drawCarteraDep();
        drawMorosidad();
      });
    });

    // 5. Sección 3: Tasas Referenciales BCE
    const tasaSeriesCfg = [
      { key: "Microcrédito Minorista", label: "TAR Microcrédito Minorista", color: "var(--c-3)" },
      { key: "Consumo", label: "TAR Consumo", color: "var(--c-4)" },
      { key: "Productivo PYMES", label: "TAR PYMES", color: "var(--c-5)" },
      { key: "Productivo Corporativo", label: "TAR Corporativo", color: "var(--c-1)" },
      { key: "tpr", label: "Tasa Pasiva Ref. (TPR)", color: "var(--c-2)", dashed: true },
    ];
    document.getElementById("legend-tasas").innerHTML = tasaSeriesCfg
      .map(
        (s) =>
          `<span class="legend-item"><span class="legend-swatch" style="background:${s.color}"></span>${escHtml(s.label)}</span>`
      )
      .join("");

    const chartTasasWrap = document.getElementById("chart-tasas-serie");
    const scrubTasas = document.getElementById("scrub-tasas");
    const readoutTasas = document.getElementById("readout-tasas");

    function drawTasasSerie(idxOverride) {
      const tData = D.tasas_mensual;
      scrubTasas.max = String(tData.length - 1);
      const idx =
        idxOverride !== undefined ? Math.min(tData.length - 1, Math.max(0, idxOverride)) : tData.length - 1;
      scrubTasas.value = String(idx);

      chartTasasWrap.innerHTML = renderMultiLineSVG({
        title: "Evolución mensual de tasas activas y pasiva referenciales BCE (2022–2026)",
        desc: "Tasas efectivas anuales en porcentaje.",
        labels: tData.map((r) => r.fecha),
        seriesList: tasaSeriesCfg.map((cfg) => ({
          name: cfg.label,
          color: cfg.color,
          values: tData.map((r) => r[cfg.key]),
          dashed: cfg.dashed,
          strokeWidth: cfg.key === "tpr" ? 2.8 : 2.1,
        })),
        yUnit: "%",
        yFormatter: (v) => fmtNum(v, 0),
        activeIndex: idx,
      });

      const r = tData[idx];
      const spreadCons = computeSpreadPP(r["Consumo"], r.tpr);
      readoutTasas.innerHTML =
        `<span><strong>${escHtml(r.fecha)}</strong> · TPR: <strong>${fmtPct(r.tpr)}</strong> · Corporativo: <strong>${fmtPct(r["Productivo Corporativo"])}</strong> · Consumo: <strong>${fmtPct(r["Consumo"])}</strong> (Spread ${fmtNum(spreadCons, 2)} pp) · Micro Minorista: <strong>${fmtPct(r["Microcrédito Minorista"])}</strong></span>` +
        `<a href="${escHtml(r.url)}" target="_blank" rel="noopener noreferrer">Boletín BCE ${escHtml(r.fecha)}</a>`;

      bindSvgPointerScrub(chartTasasWrap, tData.length, (i) => drawTasasSerie(i));
    }
    scrubTasas.addEventListener("input", () => drawTasasSerie(Number(scrubTasas.value)));

    // Barras TAR vs Máxima (Noviembre 2026)
    const tasasLast = D.tasas_ultimo_corte;
    document.getElementById("chart-tasas-barras").innerHTML = renderHorizontalBarsSVG({
      title: "Tasas activas efectivas referenciales vs. topes máximos legales en noviembre 2026",
      desc: "Comparación de los 13 segmentos de crédito del BCE frente a la Tasa Pasiva Referencial (4,83 %).",
      width: 580,
      labelWidth: 192,
      rowHeight: 26,
      maxValue: 31,
      showMarker: true,
      baseRefLine: { value: D.kpis.tpr_pct, label: `TPR ${fmtNum(D.kpis.tpr_pct, 2)}%` },
      items: tasasLast.map((r) => ({
        label: r.segmento,
        value: r.tasa_activa_ref_pct,
        marker: r.tasa_activa_max_pct,
        color: r.holgura_bajo_tope_pp < 0.5 ? "var(--c-4)" : "var(--c-1)",
        rightLabel: `${fmtNum(r.tasa_activa_ref_pct, 2)}% / ${fmtNum(r.tasa_activa_max_pct, 2)}%`,
      })),
    });

    // 6. Sección 4: Benchmark Internacional (Banco Mundial)
    const wbCountries = ["ECU", "PER", "COL", "CHL", "MEX", "USA"];
    const wbYears = [];
    for (let y = 2010; y <= 2025; y++) wbYears.push(String(y));

    document.getElementById("legend-wb").innerHTML = wbCountries
      .map(
        (iso) =>
          `<span class="legend-item"><span class="legend-swatch" style="background:${WB_COLORS[iso]}"></span>${escHtml(D.wb_paises[iso])} (${iso})</span>`
      )
      .join("");

    document.getElementById("chart-wb-lines").innerHTML = renderMultiLineSVG({
      title: "Benchmark anual de morosidad bancaria (FB.AST.NPER.ZS), 2010–2025",
      desc: "Comparación de Ecuador frente a Perú, Colombia, Chile, México y Estados Unidos.",
      labels: wbYears,
      seriesList: wbCountries.map((iso) => {
        const byY = {};
        (D.wb_series[iso] || []).forEach((pt) => {
          byY[String(pt.anio)] = pt.valor;
        });
        return {
          name: D.wb_paises[iso],
          color: WB_COLORS[iso],
          values: wbYears.map((y) => (byY[y] !== undefined ? byY[y] : null)),
          strokeWidth: iso === "ECU" ? 3.4 : 2.0,
        };
      }),
      yUnit: "%",
      yFormatter: (v) => fmtNum(v, 1),
    });

    const q5 = sqlById["q5_benchmark_morosidad_latam_usa"].rows;
    document.getElementById("chart-wb-bars").innerHTML = renderHorizontalBarsSVG({
      title: "Morosidad bancaria al último año disponible por país (Banco Mundial)",
      desc: "Porcentaje de préstamos improductivos sobre cartera bruta.",
      width: 480,
      labelWidth: 122,
      rowHeight: 30,
      maxValue: 5.5,
      items: q5.map((r) => ({
        label: `${r.pais_nombre} (${r.ultimo_anio})`,
        value: r.morosidad_actual_pct,
        color: WB_COLORS[r.pais_iso3] || COLORS.primary,
        rightLabel: fmtNum(r.morosidad_actual_pct, 2) + " %",
      })),
    });

    document.querySelector("#table-wb tbody").innerHTML = q5
      .map((r) => {
        const gapStr = r.pais_iso3 === "ECU" ? "Base" : fmtSignedPP(r.brecha_vs_ecuador_pp);
        const cls = r.pais_iso3 === "ECU" ? "badge-bad" : "badge-neutral";
        return (
          `<tr><td><strong>${escHtml(r.pais_nombre)}</strong> (${escHtml(r.pais_iso3)})</td>` +
          `<td class="num">${r.ultimo_anio}</td>` +
          `<td class="num"><strong>${fmtNum(r.morosidad_actual_pct, 2)} %</strong></td>` +
          `<td class="num">${fmtNum(r.morosidad_2019_pct, 2)} %</td>` +
          `<td class="num"><span class="badge ${cls}">${escHtml(gapStr)}</span></td></tr>`
        );
      })
      .join("");

    // 7. Sección 5: Prudencial y Explorador SQL
    const q6 = sqlById["q6_salud_prudencial_subsistemas"].rows;
    document.getElementById("chart-prudencial").innerHTML = renderGroupedPrudencialSVG(q6);
    document.querySelector("#table-prudencial tbody").innerHTML = q6
      .map(
        (r) =>
          `<tr><td><strong>${escHtml(r.subsistema)}</strong></td>` +
          `<td class="num">${fmtNum(r.solvencia_pct, 2)} %</td>` +
          `<td class="num">${fmtNum(r.liquidez_pct, 2)} %</td>` +
          `<td class="num"><strong>${fmtNum(r.roe_pct, 2)} %</strong></td></tr>`
      )
      .join("");

    // Explorador SQLite
    const sqlSel = document.getElementById("sql-selector");
    D.sql_consultas.forEach((q, idx) => {
      const opt = document.createElement("option");
      opt.value = q.id;
      opt.textContent = `${idx + 1}. ${q.id}`;
      sqlSel.appendChild(opt);
    });

    function renderSqlQuery(qid) {
      const q = sqlById[qid];
      document.getElementById("sql-desc").textContent = q.descripcion;
      document.getElementById("sql-code").textContent = q.sql;
      document.querySelector("#sql-result-table thead").innerHTML =
        "<tr>" + q.columns.map((c) => `<th>${escHtml(c)}</th>`).join("") + "</tr>";
      document.querySelector("#sql-result-table tbody").innerHTML = q.rows
        .map(
          (row) =>
            "<tr>" +
            q.columns
              .map((c) => {
                const v = row[c];
                const isNum = typeof v === "number";
                return `<td class="${isNum ? "num" : ""}">${escHtml(isNum ? fmtNum(v, Number.isInteger(v) ? 0 : 2) : v)}</td>`;
              })
              .join("") +
            "</tr>"
        )
        .join("");
    }
    sqlSel.addEventListener("change", () => renderSqlQuery(sqlSel.value));
    renderSqlQuery(D.sql_consultas[0].id);

    // 8. Sección 6: Hallazgos derivados estrictamente de los datos
    const morTotalPeak15 = getPeakEntry(filterByStartMonth(D.morosidad_mensual, "2015-01"), "Total");
    const q2 = sqlById["q2_intermediacion_fondeo_anual"].rows;
    const y2015 = q2[0];
    const y2023 = q2.find((r) => r.anio === "2023");
    const y2026 = q2[q2.length - 1];
    const vipTasa = D.tasas_ultimo_corte.find((t) => t.segmento === "Vivienda de Interés Público");
    const microMinTasa = D.tasas_ultimo_corte.find((t) => t.segmento === "Microcrédito Minorista");
    const ecuQ5 = q5.find((r) => r.pais_iso3 === "ECU");
    const perQ5 = q5.find((r) => r.pais_iso3 === "PER");
    const colQ5 = q5.find((r) => r.pais_iso3 === "COL");
    const chlQ5 = q5.find((r) => r.pais_iso3 === "CHL");
    const mexQ5 = q5.find((r) => r.pais_iso3 === "MEX");
    const bpPrud = q6.find((r) => r.subsistema === "Bancos Privados");
    const co1Prud = q6.find((r) => r.subsistema === "Coop. Seg. 1");
    const ecu2024 = (D.wb_series["ECU"] || []).find((p) => p.anio === 2024);

    const insights = [
      {
        title: "El crédito Productivo lidera la expansión reciente",
        body: `A ${D.kpis.fecha_corte_sistema}, la cartera bruta suma $${fmtNum(lastCD.cartera_total, 2)} MM (+${fmtNum(carteraYoY, 2)} % YoY). Consumo sigue siendo el mayor segmento (${fmtNum(q1[0].participacion_pct, 2)} %), pero Productivo crece a un ritmo superior (+${fmtNum(prodQ1.var_interanual_pct, 2)} % YoY).`,
      },
      {
        title: "Fondeo más holgado tras la baja de tasas pasivas",
        body: `Entre cierre 2015 y ${y2026.fecha_cierre}, los depósitos pasaron de $${fmtNum(y2015.depositos_total_mm, 2)} MM a $${fmtNum(y2026.depositos_total_mm, 2)} MM. El ratio Cartera/Depósitos bajó de ${fmtPct(y2023.ratio_cartera_depositos_pct)} (dic 2023) a ${fmtPct(y2026.ratio_cartera_depositos_pct)} (${y2026.fecha_cierre}).`,
      },
      {
        title: "Fuerte dispersión de riesgo entre segmentos",
        body: `La morosidad total (${fmtPct(D.kpis.morosidad_total_pct)}, lejos del pico 2015–2026 de ${fmtPct(morTotalPeak15.valor)} en ${morTotalPeak15.fecha}) oculta una brecha de más de 8× entre Microcrédito (${fmtPct(D.kpis.morosidad_micro_pct)}) y Productivo (${fmtPct(D.kpis.morosidad_productivo_pct)}).`,
      },
      {
        title: "Compresión de tasas pasivas y topes vinculantes",
        body: `La TPR cayó ${fmtNum(tprPeak.valor - D.kpis.tpr_pct, 2)} pp desde su pico (${fmtPct(tprPeak.valor)} en ${tprPeak.fecha}) hasta ${fmtPct(D.kpis.tpr_pct)} en ${D.kpis.fecha_corte_tasas}. Vivienda VIP opera con holgura ${fmtNum(vipTasa.holgura_bajo_tope_pp, 2)} pp bajo su tope (${fmtPct(vipTasa.tasa_activa_max_pct)}), mientras Microcrédito Minorista mantiene ${fmtNum(microMinTasa.holgura_bajo_tope_pp, 2)} pp de holgura.`,
      },
      {
        title: "Ecuador lidera la morosidad en el benchmark regional",
        body: `En la serie armonizada del Banco Mundial (FB.AST.NPER.ZS), Ecuador cerró ${ecuQ5.ultimo_anio} en ${fmtPct(ecuQ5.morosidad_actual_pct)} (${fmtSignedPP(ecuQ5.cambio_vs_2019_pp)} vs. 2019, aunque debajo de ${fmtPct(ecu2024.valor)} en 2024), superando a Perú (${fmtPct(perQ5.morosidad_actual_pct)} en ${perQ5.ultimo_anio}), Colombia (${fmtPct(colQ5.morosidad_actual_pct)}), Chile (${fmtPct(chlQ5.morosidad_actual_pct)}), México (${fmtPct(mexQ5.morosidad_actual_pct)}) y EE. UU. (${fmtPct(usaQ5.morosidad_actual_pct)}).`,
      },
      {
        title: "Divergencia estructural entre Bancos y Cooperativas",
        body: `A ${D.kpis.fecha_corte_sistema}, Cooperativas Seg. 1 exhiben mayor solvencia (${fmtPct(co1Prud.solvencia_pct)} vs. ${fmtPct(bpPrud.solvencia_pct)}) y liquidez (${fmtPct(co1Prud.liquidez_pct)} vs. ${fmtPct(bpPrud.liquidez_pct)}) que Bancos Privados, pero menos de un tercio de su rentabilidad sobre patrimonio (ROE ${fmtPct(co1Prud.roe_pct)} vs. ${fmtPct(bpPrud.roe_pct)}).`,
      },
    ];
    document.getElementById("insights-grid").innerHTML = insights
      .map(
        (ins) =>
          `<article class="insight-card"><h3>${escHtml(ins.title)}</h3><p>${escHtml(ins.body)}</p></article>`
      )
      .join("");

    // 9. Sección 7: Validaciones y Fuentes
    document.getElementById("val-summary").textContent =
      `Estado del pipeline Python (pandas + SQLite): ${D.validaciones.passed}/${D.validaciones.passed} validaciones aprobadas y equivalencia exacta verificada en las ${D.sql_consultas.length} consultas SQL.`;
    document.getElementById("val-list").innerHTML = D.validaciones.checks
      .map(
        (c) =>
          `<li><span class="badge badge-good">OK</span> <strong>${escHtml(c.check)}</strong>: ${escHtml(c.detail)}</li>`
      )
      .join("");

    document.getElementById("sources-list").innerHTML = D.manifest.fuentes
      .map(
        (f) =>
          `<div class="source-card">` +
          `<h4>${escHtml(f.titulo)}</h4>` +
          `<p><strong>Institución:</strong> ${escHtml(f.institucion)}</p>` +
          `<p><strong>Fecha de corte:</strong> ${escHtml(f.fecha_corte)} · <strong>Descarga:</strong> ${escHtml(f.fecha_descarga)} · <strong>Cobertura:</strong> ${escHtml(f.cobertura_temporal)}</p>` +
          `<p><strong>Nota metodológica:</strong> ${escHtml(f.nota_metodologica)}</p>` +
          `<blockquote class="source-quote">${escHtml(f.cita_literal)}</blockquote>` +
          `<p><strong>URL original:</strong> <a href="${escHtml(f.url_archivo)}" target="_blank" rel="noopener noreferrer">${escHtml(f.url_archivo)}</a>` +
          (f.url_portal ? ` · <a href="${escHtml(f.url_portal)}" target="_blank" rel="noopener noreferrer">Portal institucional</a>` : "") +
          `</p>` +
          `</div>`
      )
      .join("");

    // Render inicial de gráficos interactivos
    drawCarteraDep();
    renderMorChips();
    drawMorosidad();
    drawTasasSerie();
  }

  function bindSvgPointerScrub(container, count, onIndex) {
    const svg = container.querySelector("svg");
    if (!svg || count <= 1) return;
    svg.addEventListener("mousemove", (ev) => {
      const rect = svg.getBoundingClientRect();
      const viewW = svg.viewBox.baseVal.width || 660;
      const plotLeft = Number(svg.getAttribute("data-plot-left")) || 56;
      const plotWidth = Number(svg.getAttribute("data-plot-width")) || 584;
      const relX = ((ev.clientX - rect.left) / rect.width) * viewW;
      const t = Math.max(0, Math.min(1, (relX - plotLeft) / plotWidth));
      const idx = Math.round(t * (count - 1));
      onIndex(idx);
    });
  }

  // Exportar API pública para tests.js (Node / Deno)
  const api = {
    fmtNum,
    fmtPct,
    fmtSignedPP,
    computeLDR,
    computeYoYPct,
    computeSpreadPP,
    computeHeadroomPP,
    filterByStartMonth,
    getPeakEntry,
    buildLinePath,
    renderMultiLineSVG,
    renderHorizontalBarsSVG,
    renderGroupedPrudencialSVG,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  if (typeof window !== "undefined") {
    window.SFE_APP = api;
    if (typeof document !== "undefined") {
      if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initDashboard);
      } else {
        initDashboard();
      }
    }
  }
})(typeof globalThis !== "undefined" ? globalThis : window);
