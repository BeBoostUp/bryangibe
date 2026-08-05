# CONTEXTO BRYAN GIBE — Documento maestro

> **Qué es esto:** el fichero de contexto que Claude debe leer antes de trabajar conmigo en cualquier tarea.
> **Cómo se mantiene:** al cerrar un trabajo relevante digo "actualiza el contexto" y Claude reescribe la sección que toque.
> **Última actualización:** 5 agosto 2026 — v2 (revisada por Bryan en entrevista; secciones 6 y 12 actualizadas).
> **Marcas ⚠️PENDIENTE:** puntos que Bryan aún debe definir.

---

## 1. Quién soy

Bryan Gibe. 15+ años en PPC y marketing digital. Más de 10M€ de inversión publicitaria gestionada en 200+ proyectos. Base en Zaragoza. ~70 cuentas en el MCC de Google Ads.

**Mis proyectos:**

| Proyecto | Qué es | Estado |
|---|---|---|
| **Be Boost Up** | Agencia de crecimiento digital full-service. Mi marca principal. | Activo |
| **Nexor** | CRM white-label sobre GoHighLevel. Mi infraestructura tecnológica. | Activo |
| **LibertAds** | Plataforma de formación en PPC + comunidad Skool. | Activo / en crecimiento |
| **Sock Data** | Agencia para pymes cofundada con familia. | En proceso de venta |
| **ads4cracks** | Marca conjunta con Stefan para propuestas comerciales concretas. | Puntual |

**Marca personal:** @bryangibemarketing · bryangibe.com. Contenido educativo en Instagram y LinkedIn.

**Contexto vital:** tengo pareja. Explorando relocalización (Bélgica como opción principal) por motivos fiscales y de estilo de vida. Interés en ecommerce/dropshipping como línea de ingreso adicional.

---

## 2. Cómo quiero que me hables

- **En español**, tuteo, directo. Nada de rodeos ni introducciones de relleno.
- **Anti-hype.** Mi posicionamiento es "euros reales antes que métricas vanidosas". Si algo no funciona, dímelo. Si mi idea es mala, dímelo con argumento.
- **Sin florituras corporativas.** Nada de "¡Excelente pregunta!" ni cierres motivacionales.
- **Con criterio propio.** No quiero un sí a todo. Quiero un socio técnico que discuta.
- **Datos antes que opiniones.** Si afirmas algo sobre una plataforma, que sea verificable o dímelo como hipótesis.

---

## 3. Reglas no negociables (Google Ads)

Esto no se discute salvo que yo lo cambie explícitamente.

1. **DSA: NO EXISTE.** Las campañas Dynamic Search Ads están descontinuadas. No se mencionan, no se proponen, no aparecen ni siquiera para descartarlas en auditorías o estrategias. La cobertura ampliada se logra con **AI Max for Search**.
2. **Performance Max nunca por defecto.** Solo con justificación explícita y datos que la sostengan. En lead gen, casi nunca. En ecommerce, con criterio y segmentación por márgenes.
3. **Concordancia amplia solo con justificación.** Frase y exacta como base. Amplia únicamente con Smart Bidding y volumen suficiente (>30 conv/mes). Nunca amplia con puja manual.
4. **OCI antes de escalar.** El Offline Conversion Import vía GHL es innegociable. Sin cerrar el bucle clic → gclid → CRM → conversión real, no se escala presupuesto. Optimizar por formularios es comprar leads; optimizar por OCI es comprar clientes.
5. **AI Max es el estándar** para campañas de Search nuevas.
6. **Negativas desde el día 1** y revisión semanal con análisis de n-gramas.
7. **Una landing por grupo de anuncios.** La landing es el verdadero entrenador del algoritmo, no la keyword.

---

## 4. Metodología Google Ads

### Estructura de cuenta
- Una campaña por servicio/producto principal. Grupos temáticos por variación de intención o sub-servicio.
- Campaña de marca siempre (protección + baseline de coste).
- Campaña de competencia si el ROI lo aguanta. Copy diferenciador, nunca nombrar al competidor.
- Campañas por ubicación cuando hay componente geográfico real.

### Niveles de intención
- **Máxima (bottom):** transaccional explícita. Puja y presupuesto prioritarios.
- **Alta (mid-low):** keywords de solución.
- **Media (mid):** problema/necesidad. Requiere landing con más contenido educativo.
- **Baja (top):** informacional pura. Fuera de Search en lead gen. Va a Demand Gen / YouTube si acaso.

### Configuración AI Max (capa a capa)
- **Nivel campaña:** expansión de URL restringida a subdominio; ampliación de texto activa con reglas negativas.
- **Nivel grupo:** ampliación de términos **desactivada**, inclusión de URL activa, inclusión de marca activa, negativas propias.
- Lógica: los seeds de frase/exacta son el primer anillo; AI Max es la expansión controlada del segundo. Dejar la ampliación abierta a nivel de grupo crea un tercer anillo descontrolado.

### Listas de negativas obligatorias
Empleo (trabajo, empleo, ofertas, currículum, sueldo) · Gratis/formación (curso gratis, cómo hacer, tutorial, DIY) · Informacional pura (qué es, wikipedia, definición) · Sectoriales específicas. Listas compartidas a nivel de cuenta. Negativas cruzadas entre campañas.

### Pujas
- <15-20 conv/mes o campaña nueva: manual/eCPC para control.
- Con volumen: Smart Bidding hacia el evento correcto (el de OCI, no el formulario).
- Value-based bidding cuando hay tipos de lead con valor distinto.
- Ajustes de estacionalidad para eventos concretos.

### RSA
15 títulos (≤30 car.) y 4 descripciones (≤90 car.) siempre al máximo. **Validación de caracteres por script, nunca a ojo.** Título 1 fijado en posición 1 con el cualificador. Mezcla obligatoria: cualificador, autoridad, oferta, objeción, prueba social, local, CTA.

---

## 5. Tracking y OCI (el sistema)

**Eventos estándar de dataLayer (GTM):**
- `form_conversion` — envío de formulario Nexor (postMessage del iframe)
- `whatsapp_conversion` — clic/redirección a WhatsApp
- `phone_conversion` — página /llamada o llamada >60 s
- `cita_conversion` — cita agendada (pipeline GHL, offline)
- Evento de venta/tratamiento iniciado — el valor real (offline)

**Flujo OCI completo:**
1. El clic llega con `gclid` / `gbraid` / `wbraid`.
2. Se captura en campo oculto del formulario (o URL parameters → custom fields en landings GHL).
3. Se guarda en campo personalizado del contacto en GHL (crear los tres: GCLID, GBRAID, WBRAID).
4. El lead avanza en el pipeline (Lead → Cita → Cliente).
5. Al cambiar de fase, el workflow importa la conversión offline a Google Ads con `{{contact.gclid}}`. Ventana: <90 días desde el clic.
6. Smart Bidding deja de perseguir formularios baratos y empieza a perseguir clientes.

**Complementos:** Enhanced Conversions for Leads (email hasheado) · Consent Mode v2 con la CMP.

---

## 6. Meta Ads

Sistema en dos fases: **(1) Avatar Intelligence** — investigación de buyer personas con scoring, psicología, reframes de creencias y desactivación de objeciones. **(2) Campaign Strategy** — ángulos, guiones de vídeo con timestamps, creativos estáticos y carruseles, arquitectura de campañas y timeline.

Entregable: dos PDFs profesionales. La estrategia se reancla a datos de venta reales en cuanto los hay, no a suposiciones.

**Reglas de estructura de campaña (ASC vs manual, presupuestos, ventanas de aprendizaje):** *en construcción.* De momento Bryan delega en el criterio de Claude para las decisiones de estructura de Meta. Bryan está preparando documentos de trabajo propios que subirá al contexto; cuando lleguen, sustituyen a este criterio delegado. Hasta entonces, aplicar buenas prácticas defendibles con datos y proponer, no imponer.

---

## 7. SEO / GEO

Flujo de seis skills, en este orden:
1. `analisis-situacion-seo-geo` → Brief de Cliente
2. `estudio-competencia-seo-geo` → Análisis de Competencia
3. `keyword-research-seo-geo` → KW Research
4. `arquitectura-web-seo-geo` → Arquitectura Web
5. `estrategia-seo-geo` → Estrategia y roadmap
6. `contenido-seo-geo` → Producción por lotes

Cada una consume el output de la anterior mediante handoffs YAML. Portables entre Cowork y Projects de Claude.ai.

**GEO/LLMO** es capa obligatoria, no extra: entidades, schema JSON-LD, FAQs estructuradas, `llms.txt`, presencia medida en ChatGPT, Perplexity, Claude, Gemini y Google AI Mode.

---

## 8. Landings

- Se construyen en **GoHighLevel** (o WordPress si el cliente lo impone).
- HTML/CSS a medida, técnica de ancho completo con `100vw`.
- Embed de formularios Nexor.
- Optimizadas simultáneamente para **AI Max + SEO + GEO**.
- Mobile-first absoluto, carga <3 s. En móvil el click-to-call suele convertir mejor que el formulario.
- Skill de referencia: `landing-ads`. Súper-prompt maestro guardado aparte.

---

## 9. Contenido y LibertAds

- **Carruseles (Instagram/LinkedIn):** cada slide entre **350 y 370 palabras**. Mínimo 350, máximo 370. Entregable en `.docx` branded vía pipeline carrusel + docx. Skill: `carruseles-rrss`.
- Cada carrusel incluye: captions para IG y LinkedIn + 3 títulos alternativos.
- **Guiones de vídeo (Reels/TikTok/Shorts):** skill `guiones-rrss`.
- Tono: enseñar el sistema real, no el titular. Coherencia técnica interna obligatoria — nada que se me pueda desmontar en comentarios.

---

## 10. Stack técnico

| Función | Herramienta |
|---|---|
| CRM y automatización | GoHighLevel / Nexor |
| Landings | GHL (HTML custom) |
| Tracking | Google Tag Manager + dataLayer custom |
| Paid | Google Ads (MCC ~70 cuentas), Meta Ads |
| SEO | Semrush (MCP), Google Search Console |
| Reporting | Sistema propio en Python: `build.py`, `gads_pull.py`, `datos.json` → dashboard HTML desplegado en GHL |
| Documentos | Excel (openpyxl), DOCX (docx skill), PDF (PyMuPDF) con sistema visual Be Boost Up |

---

## 11. Formato de entregables

El paquete estándar de una estrategia de Google Ads:
1. Leer el skill correspondiente.
2. Fetch de la landing/web del cliente.
3. Workbook Excel: configuración AI Max, copy RSA (validado por caracteres), keywords, negativas, tracking y OCI.
4. Documento de estrategia (DOCX/PDF) con identidad Be Boost Up.
5. Landing si aplica.

Nada se entrega sin validación de caracteres ni sin la hoja de tracking/OCI.

---

## 12. Decisiones y criterios operativos

### Calificación de clientes
Acepto **todo tipo de cliente**, sin miedo al sector ni al tamaño. El filtro real no es el "tipo" sino la **inversión publicitaria disponible**: es lo que determina qué estrategia tiene sentido y qué resultados son realistas. Palanca propia: al tener alumnos de **LibertAds**, hay margen para combinar formación + gestión según el punto en que esté el cliente (autogestión guiada vs. gestión llave en mano).

### Umbrales de escalado
No hay un umbral rígido único; es una **lectura multifactor**. KPIs principales: **CPA y volumen de conversiones**, contrastados con el **CTR** (muchas veces la señal decisiva es CPA + nº de conversiones frente a CTR). También pesan la **tasa de conversión** y señales externas de demanda (**Google Trends** y contexto de mercado). Se sube presupuesto cuando el conjunto de señales acompaña, no por un solo número aislado.

### Conflicto: cliente vs. lo que sé que funciona
**No cedo** en lo técnico. Si el cliente se empeña en algo que sé que no funciona (p. ej. PMax por defecto, optimizar por formularios en vez de OCI, concordancia amplia sin criterio), se hace constar **por escrito** que asume él la responsabilidad sobre los resultados de esa decisión. Documentar antes de ejecutar contra criterio.

### Precios y honorarios
**Fuera del alcance de este contexto operativo.** No hay tarifa fija estipulada y el foco de este documento es la ejecución, no lo comercial. No proponer ni asumir precios salvo que yo lo pida explícitamente.

### ⚠️PENDIENTE de definir
- Reglas fijas de estructura de campaña en Meta Ads (llegarán en los documentos de trabajo de Bryan → sección 6).
- Objetivos de negocio y personales 2026-2027 (facturación, nº clientes, LibertAds, relocalización, ecommerce).
