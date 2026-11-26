# Sistema Financiero del Ecuador — Análisis de Crédito, Tasas y Morosidad

> **Herramienta educativa. No es asesoría financiera.**

Proyecto de portafolio de **análisis de datos financieros y riesgo de crédito** enfocado en el sistema financiero ecuatoriano (**Superintendencia de Bancos**, **SEPS** y **Banco Central del Ecuador**) con benchmark internacional de morosidad bancaria vía API del **Banco Mundial** (`FB.AST.NPER.ZS`) comparando **Ecuador** frente a **Colombia, Perú, México, Chile y Estados Unidos**.

Incluye un pipeline reproducible en **Python (`pandas`)** con 16 validaciones de calidad de datos y pruebas unitarias independientes, **6 consultas SQL equivalentes en SQLite** verificadas numéricamente contra `pandas`, y un **tablero web estático** (`index.html`, `style.css`, `app.js`, `data.js`) sin frameworks, sin CDN y con gráficos **SVG hechos a mano**, modo claro/oscuro y diseño responsive y accesible.

---

## Preguntas de negocio que responde el proyecto

1. **Composición y motor del crédito:** ¿Qué segmentos concentran la cartera bruta del sistema financiero ecuatoriano al corte más reciente (`2026-10`) y cuáles impulsan el crecimiento interanual?
2. **Intermediación y estructura de fondeo:** ¿Cómo evolucionaron los depósitos (vista vs. plazo), la cuota de los Bancos Privados y el ratio Cartera/Depósitos (LDR) entre 2015 y 2026?
3. **Concentración de riesgo crediticio:** ¿Qué segmentos presentan mayor morosidad a octubre 2026, cómo se comparan frente a su promedio móvil de 12 meses y qué tan lejos están de sus picos 2015–2026?
4. **Ciclo de tasas y topes legales:** ¿Cómo respondió el spread entre las Tasas Activas Efectivas Referenciales (TAR) y la Tasa Pasiva Referencial (TPR) entre enero 2022 y noviembre 2026, y qué segmentos operan pegados al tope máximo legal de la JPRFM?
5. **Posicionamiento internacional:** ¿Dónde se ubica la morosidad bancaria total de Ecuador (`FB.AST.NPER.ZS`, Banco Mundial) frente a Colombia, Perú, México, Chile y EE. UU.?
6. **Contraste prudencial por subsistema:** ¿Cómo difieren Solvencia, Liquidez y ROE entre Bancos Privados, Cooperativas (Segmento 1 y 2) y Mutualistas?

---

## Fuentes públicas oficiales (descargadas y auditadas el 2026-11-26)

Todos los archivos crudos descargados en esta sesión se conservan en `data/raw/` con trazabilidad completa (URL, fecha de descarga, fecha de corte, cita literal y hash SHA-256) en `data/sources_manifest.json`.

| Fuente | Indicadores y tipo | Cobertura y corte | URL oficial | Cita literal verificada |
| :--- | :--- | :--- | :--- | :--- |
| **Superintendencia de Bancos (SB) y SEPS vía BCE** (*Monitoreo de los Principales Instrumentos de Política Monetaria e Indicadores Financieros*, `Datos.xlsx`) | Cartera bruta por segmento (MM USD), Depósitos vista/plazo/totales por subsistema (MM USD), Morosidad ampliada por segmento (%), Cartera refinanciada/reestructurada (MM USD), Solvencia, Liquidez y ROE (%) | Mensual: `2002-07` a **`2026-10`** (292 meses) | [Datos.xlsx (BCE)](https://contenido.bce.fin.ec/documentos/PublicacionesNotas/Datos.xlsx) · [Portal BCE](https://contenido.bce.fin.ec/series-de-datos-indicadores-monetarios-y-financieros/) · [Portal SB](https://www.superbancos.gob.ec/estadisticas/portalestudios/sistema-financiero-publico-y-privado/) | Hoja `3. Cartera` y `3. Morosidad` (`Fuente: SB y SEPS`), corte `2026-10-01`: Cartera Total = `76.357,06` MM USD; Depósitos Totales = `89.116,47` MM USD; Morosidad Total = `4,22 %` (Microcrédito = `8,68 %`). |
| **Banco Central del Ecuador (BCE) / JPRFM** (*Tasas de Interés Activas y Pasivas Efectivas Referenciales y Máximas*) | **Tasa efectiva anual (%)**: Tasa Activa Efectiva Referencial (TAR, promedio ponderado por monto), Tasa Activa Efectiva Máxima (tope legal JPRFM), Tasa Pasiva Efectiva Referencial (TPR), Ahorro y Plazo ≥361 días | Mensual: `2022-01` a **`2026-11`** (59 meses) | [Boletín vigente Indice.htm](https://contenido.bce.fin.ec/documentos/Estadisticas/SectorMonFin/TasasInteres/Indice.htm) · [Histórico mensual BCE](https://contenido.bce.fin.ec/informacion-historica-de-tasas-maximas-y-referenciales/) | `Indice.htm` (Noviembre 2026, cobertura 371 entidades): TPR = `4,83 %` anual; Productivo Corporativo TAR = `6,88 %` (Máxima = `7,74 %`); Consumo TAR = `15,69 %` (Máxima = `16,77 %`). |
| **Banco Mundial — API v2 (WDI / FMI FSI)** | `FB.AST.NPER.ZS`: *Bank nonperforming loans to total gross loans (%)* | Anual: `2001` a **`2025`** (`2024` para Perú); API `lastupdated=2026-11-11` | [API JSON Banco Mundial](https://api.worldbank.org/v2/country/ECU;COL;PER;MEX;CHL;USA/indicator/FB.AST.NPER.ZS?format=json&per_page=1000) · [Ficha WDI](https://data.worldbank.org/indicator/FB.AST.NPER.ZS) | API v2 (`FB.AST.NPER.ZS`): Ecuador 2025 = `4,45 %` (`4,4520 %`); Perú 2024 = `3,99 %` (`3,9903 %`). |

### Notas metodológicas importantes de las fuentes
- **Cobertura del archivo BCE/SB/SEPS (`Datos.xlsx`):** incluye Sector Financiero Privado (Bancos Privados y Mutualistas) y Sector Financiero Popular y Solidario (Cooperativas Segmento 1 y Segmento 2 desde enero 2015). Considera entidades operativas a la última fecha disponible (omite entidades en liquidación forzosa: Coop. Cámara de Comercio de Ambato dic-2024, Amibank mar-2025 y Coop. Crea jul-2025).
- **Diferencia entre morosidad local y Banco Mundial:** la serie mensual de `Datos.xlsx` (`4,22 %` en `2026-10`) agrega SFPr + SFPS con definición regulatoria ecuatoriana, mientras que `FB.AST.NPER.ZS` (`4,45 %` en `2025`) es un indicador anual armonizado del FMI (FSI) para bancos comerciales que permite comparación internacional homogénea.
- **Corte de Perú en Banco Mundial:** al `2026-11-26`, la API del Banco Mundial publica datos hasta `2025` para Ecuador, Colombia, México, Chile y EE. UU., y hasta `2024` para Perú. Esta diferencia de año se muestra explícitamente en todas las tablas y gráficos.

---

## Metodología y fórmulas

1. **Ingesta y normalización (`etl/clean_and_validate.py`):**
   - Extracción de `Datos.xlsx` con `openpyxl` + `pandas` y conversión explícita de razones decimales (`0,042245`) a porcentaje (`4,2245 %`).
   - Parseo de los 59 boletines HTML mensuales del BCE (`2022-01` a `2026-11`), manejando tanto el formato de tabla paralela (ene–jul 2022) como el formato apilado (ago 2022–nov 2026).
   - Validaciones automáticas (16/16): integridad sin nulos, unicidad de claves, suma de segmentos igual al Total (`max |diff| = 0,000002 MM USD`), suma vista + plazo igual a depósitos totales (`max |diff| = 0,000001 MM USD`), `TAR <= Tasa Máxima legal` en el 100 % de los meses y segmentos.
2. **Carga a SQLite y verificación cruzada (`sql/consultas_analisis.sql`):**
   - Construcción de `data/sistema_financiero_ecuador.sqlite` con 6 tablas indexadas.
   - Ejecución de las 6 consultas SQL y verificación automática de equivalencia numérica (`|SQL - pandas| <= 0,01`) contra cálculos independientes en `pandas`.
3. **Fórmulas aplicadas:**
   - **Ratio Cartera / Depósitos (LDR, %):** $\text{LDR} = \frac{\text{Cartera Bruta Total}}{\text{Depósitos Totales}} \times 100$
   - **Variación interanual (YoY, %):** $\text{YoY}_t = \frac{X_t - X_{t-12}}{X_{t-12}} \times 100$
   - **Participación por segmento (%):** $\text{Part.}_i = \frac{\text{Cartera}_i}{\text{Cartera Total}} \times 100$
   - **Spread financiero referencial (pp):** $\text{Spread}_i = \text{TAR}_i - \text{TPR}$ (ambas expresadas en tasa efectiva anual %)
   - **Holgura bajo tope legal (pp):** $\text{Holgura}_i = \text{Tasa Máxima Legal}_i - \text{TAR}_i$
   - **Brecha internacional (pp):** $\text{Brecha}_p = \text{Morosidad}_p - \text{Morosidad}_{\text{ECU}}$

---

## Hallazgos clave (respaldados únicamente por los datos descargados)

1. **Cartera bruta de $76.357,06 MM USD (`2026-10`, +9,91 % YoY) impulsada por crédito Productivo:**
   - **Consumo** mantiene la mayor participación con **$32.747,13 MM** (`42,89 %`, `+8,41 %` YoY).
   - **Productivo** ocupa el segundo lugar con **$27.402,29 MM** (`35,89 %`), pero registra la mayor expansión interanual (**`+14,03 %` YoY**).
   - **Microcrédito** representa `14,83 %` (`$11.324,13 MM`, `+6,59 %` YoY), **Vivienda** `6,22 %` (`$4.751,14 MM`, `+6,96 %` YoY) y **Educativa** `0,17 %` (`$132,38 MM`, `-22,26 %` YoY).
2. **Triplicación del fondeo en una década y normalización del ratio LDR:**
   - Los depósitos totales pasaron de **$29.655,64 MM** (`2015-12`) a **$89.116,47 MM** (`2026-10`).
   - El **ratio Cartera/Depósitos (LDR)** descendió desde **`94,19 %`** (`2023-12`) a **`85,68 %`** (`2026-10`), evidenciando mayor holgura de liquidez de fondeo.
   - Los **depósitos a plazo** subieron de `39,21 %` del total (`2015-12`) a un pico anual de `54,19 %` (`2024-12`) y se moderaron a `51,38 %` (`2026-10`). La participación de **Bancos Privados** en los depósitos totales se ubica en `70,90 %` (`$63.184,07 MM`).
3. **Riesgo crediticio concentrado en Microcrédito y Consumo, aunque debajo de su promedio 12 meses:**
   - A `2026-10`, la morosidad total es **`4,22 %`** (`-0,16 pp` vs. promedio 12m de `4,39 %`; pico 2015–2026: `6,07 %` en `2016-05`).
   - **Microcrédito** registra **`8,68 %`** (`-0,29 pp` vs. promedio 12m de `8,97 %`; pico 2015–2026: `10,69 %` en `2016-05` y pico reciente `10,27 %` en `2024-09`), más de 8 veces la morosidad de **Productivo** (**`1,06 %`**). **Consumo** marca **`5,51 %`** y **Vivienda** **`3,02 %`**.
   - La cartera refinanciada (`$1.180,07 MM`) y reestructurada (`$1.531,54 MM`) suma `$2.711,61 MM` (`3,55 %` de la cartera bruta).
4. **Fuerte descenso de tasas pasivas (2024–2026) y topes legales vinculantes en vivienda social:**
   - La **Tasa Pasiva Referencial (TPR)** cayó **`3,62 pp`** desde su pico de **`8,45 %`** (`2024-07`) hasta **`4,83 %`** (`2026-11`).
   - En `2026-11`, los mayores spreads efectivos sobre la TPR corresponden a **Microcrédito de Acumulación Simple** (`15,68 pp`, TAR `20,51 %`), **Microcrédito Minorista** (`14,64 pp`, TAR `19,47 %`, con `8,76 pp` de holgura bajo el tope de `28,23 %`) y **Consumo** (`10,86 pp`, TAR `15,69 %`, a solo `1,08 pp` del tope de `16,77 %`).
   - **Vivienda de Interés Público** y **Vivienda de Interés Social** operan pegadas al techo legal (`4,99 %` TAR = `4,99 %` Máxima, holgura `0,00 pp`, spread `0,16 pp` sobre la TPR).
5. **Ecuador presenta la morosidad bancaria más alta del grupo benchmark (Banco Mundial):**
   - En `FB.AST.NPER.ZS`, **Ecuador** cerró `2025` en **`4,45 %`** (`+1,27 pp` respecto a `3,18 %` en `2019`, aunque bajando desde `4,82 %` en `2024`).
   - Comparativo al último año disponible: **Perú** `3,99 %` (`2024`, `-0,46 pp` vs. Ecuador), **Colombia** `2,96 %` (`2025`, `-1,49 pp`), **Chile** `2,40 %` (`2025`, `-2,05 pp`), **México** `2,17 %` (`2025`, `-2,28 pp`) y **Estados Unidos** `0,96 %` (`2025`, `-3,49 pp`).
6. **Contraste prudencial Bancos Privados vs. Cooperativas (`2026-10`):**
   - **Bancos Privados** lideran rentabilidad con **ROE de `13,86 %`** (Solvencia `13,31 %`, Liquidez `18,94 %`).
   - **Cooperativas Seg. 1** presentan mayores colchones de **Solvencia (`16,52 %`)** y **Liquidez (`29,02 %`)**, pero un **ROE de `4,36 %`** (`3,50 %` en Coop. Seg. 2).

---

## Estructura del proyecto

```text
sistema-financiero-ecuador/
├── index.html                           # Tablero web estático (español, accesible, claro/oscuro)
├── style.css                            # Estilos responsive sin frameworks ni CDN
├── app.js                               # Lógica analítica y gráficos SVG hechos a mano
├── data.js                              # Dataset estructurado generado por el pipeline Python
├── tests.js                             # Pruebas JS ejecutables con Node o Deno (exit 1 si falla)
├── requirements.txt                     # Dependencias Python (pandas, openpyxl)
├── LICENSE                              # Licencia MIT
├── README.md                            # Documentación, preguntas de negocio y hallazgos
├── etl/
│   ├── clean_and_validate.py            # Limpieza pandas, 16 validaciones, carga SQLite y cruce SQL
│   └── test_pipeline.py                 # Pruebas unitarias independientes en Python
├── sql/
│   └── consultas_analisis.sql           # 6 consultas SQLite documentadas equivalentes a pandas
└── data/
    ├── raw/                             # Archivos oficiales descargados (BCE, SB/SEPS, Banco Mundial)
    ├── clean/                           # CSVs limpios + resumen_sql_verificado.json
    ├── sources_manifest.json            # Metadatos, URLs, fechas de corte, citas literales y SHA-256
    └── sistema_financiero_ecuador.sqlite
```

---

## Cómo reproducir y correr las pruebas

### 1. Ejecutar el pipeline Python (`pandas` + validaciones + SQLite)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python etl/clean_and_validate.py
```

### 2. Ejecutar las pruebas unitarias independientes en Python
```bash
.venv/bin/python etl/test_pipeline.py
```

### 3. Ejecutar las consultas SQL directamente en SQLite
```bash
sqlite3 -header -column data/sistema_financiero_ecuador.sqlite < sql/consultas_analisis.sql
```

### 4. Ejecutar las pruebas JavaScript (`tests.js`)
Con Node.js:
```bash
node tests.js
```
O con Deno (si `node` no está instalado en el sistema):
```bash
deno run --allow-read --unstable-detect-cjs tests.js
```

### 5. Abrir el tablero web estático
Puedes abrir `index.html` directamente en el navegador (`file://`) o levantarlo localmente con:
```bash
python3 -m http.server 8000
# Luego abre http://localhost:8000
```

---

Hecho por Bryan Román · [linkedin.com/in/bryan-roman-ai](https://www.linkedin.com/in/bryan-roman-ai) · Licencia MIT.
