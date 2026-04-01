# Vercel + Python/Flask - REGLAS CRITICAS

## Lo que Vercel empaqueta en serverless (Flask preset)
- SOLO el archivo .py principal en `api/` (ej: `api/index.py`)
- Las dependencias de `requirements.txt` (instaladas en `_vendor/`)
- **NO empaqueta**: otros .py en api/, carpeta public/, subdirectorios de api/, ningun archivo estatico

## Solucion para servir HTML/CSS/JS
- **SIEMPRE** embeber el HTML/CSS/JS como strings Python directamente en `api/index.py`
- **NO** usar `send_from_directory` — los archivos no existen en el runtime
- **NO** crear archivos .py separados (ej: `static_content.py`) — tampoco se empaquetan
- **NO** poner archivos en `api/public/` — no se incluyen
- Usar `Response(HTML_STRING, content_type='text/html')` para servir paginas
- CSS y JS van inline dentro del HTML (tags `<style>` y `<script>`)

## Configuracion vercel.json correcta

```json
{
  "rewrites": [
    { "source": "/(.*)", "destination": "/api/index.py" }
  ]
}
```

- Catch-all rewrite: **TODO** pasa por Flask
- **NO** usar `cleanUrls` — no funciona con Flask preset
- **NO** usar `functions.includeFiles` — no funciona con Flask preset
- **NO** necesitar `"framework"` en vercel.json — se configura en el dashboard

## Framework Preset en Vercel Dashboard
- Usar **Flask** (Build and Deployment > Framework Settings)
- Con Flask preset, **TODAS** las requests van al serverless function
- Flask maneja tanto las rutas `/api/*` como las paginas estaticas (`/`, `/login`)
- **IMPORTANTE**: Si el Framework Preset no esta en Flask, el deploy saldra con 404 aunque el codigo este bien

## Auth middleware (before_request)

```python
@app.before_request
def check_auth():
    if request.path in ('/', '/login', '/favicon.ico'):
        return None  # No bloquear paginas estaticas
    if request.path == '/api/login':
        return None  # No bloquear la ruta de login
    if request.path.startswith('/api/'):
        if not session.get('authenticated'):
            return jsonify({'error': 'Not authenticated'}), 401
    return None
```

## Estructura del archivo api/index.py
1. Imports
2. Flask app + config
3. Helper functions (api_get, api_post, etc.)
4. `@app.before_request` — auth middleware (solo para `/api/`)
5. Rutas de paginas estaticas (`/`, `/login`) — devuelven `Response` con HTML embebido
6. Rutas API (`/api/*`)
7. Constants: `LOGIN_HTML` y `INDEX_HTML` (strings con HTML+CSS+JS inline)

## Ruta del archivo en Vercel runtime
- El archivo esta en `/var/task/api/index.py`
- Working directory: `/var/task/`
- Solo `index.py` existe en `/var/task/api/`

## ERRORES COMETIDOS Y LECCIONES APRENDIDAS

### Error 1: Desarrollar en rama feature sin mergear a main
- **Que paso**: Se desarrollo todo en la rama `claude/google-ads-dashboard-ogpgf` pero Vercel despliega produccion desde `main`. La URL de produccion (`dashboardgads.vercel.app`) mostraba 404 porque `main` solo tenia el README.md
- **Solucion**: Mergear la rama feature a `main` con `git merge` y hacer push a `main`
- **REGLA**: Vercel despliega PRODUCCION desde la rama `main`. Las ramas feature solo generan Preview deployments con URLs temporales. Si quieres que la URL de produccion funcione, el codigo DEBE estar en `main`
- **REGLA**: Despues de desarrollar en una rama feature, SIEMPRE mergear a `main` y hacer push para que el deploy de produccion se actualice

### Error 2: No configurar el Framework Preset antes del primer deploy
- **Que paso**: Se hizo deploy sin verificar que el Framework Preset estuviera en Flask, causando que Vercel no supiera como ejecutar el archivo Python
- **REGLA**: ANTES de hacer el primer push, verificar que en Vercel Dashboard > Settings > General > Framework Preset esta seleccionado **Flask**
- **REGLA**: Si se cambia el Framework Preset despues de un deploy, hay que hacer un Redeploy manual para que tome efecto

### Error 3: No configurar Environment Variables antes del deploy
- **Que paso**: Las variables de entorno no estaban configuradas al hacer deploy
- **REGLA**: ANTES del primer deploy, configurar TODAS las Environment Variables necesarias en Vercel Dashboard > Settings > Environment Variables
- **REGLA**: Si se anaden o modifican variables despues del deploy, hay que hacer Redeploy para que tomen efecto

## Errores comunes a EVITAR
- `api/index.py` + `public/index.html` + `cleanUrls` = conflicto de rutas (Vercel sirve el function en vez del HTML)
- Framework "Other" = los rewrites `/api/(.*)` no funcionan consistentemente para Python
- Archivos separados (`.py` o estaticos) = NO se empaquetan, causa 500 o 404
- `send_from_directory` = falla porque `public/` no existe en runtime
- `from static_content import ...` = falla porque el archivo no se empaqueta
- Deploy en rama feature pensando que es produccion = 404 en la URL de produccion
- Olvidar mergear a `main` = la URL de produccion no se actualiza

## Checklist para nuevo proyecto Vercel + Flask

### Paso 1: Configuracion en Vercel Dashboard (ANTES de codear)
- [ ] Crear proyecto en Vercel y conectar repositorio de GitHub
- [ ] Framework Preset = **Flask** (Settings > General)
- [ ] Configurar TODAS las Environment Variables necesarias
- [ ] Verificar que la Production Branch es `main`

### Paso 2: Desarrollo
- [ ] Crear `api/index.py` con Flask app (todo en un archivo)
- [ ] Embeber HTML/CSS/JS como strings Python en el mismo archivo
- [ ] Crear `requirements.txt` con flask y requests (y las dependencias necesarias)
- [ ] Crear `vercel.json` con catch-all rewrite a `api/index.py`

### Paso 3: Deploy
- [ ] Commit y push a `main` (NO a una rama feature si quieres produccion)
- [ ] Si desarrollas en rama feature: mergear a `main` y push
- [ ] Verificar que el deploy se completa en Vercel Dashboard
- [ ] Probar la URL de produccion

### Paso 4: Verificacion post-deploy
- [ ] La URL de produccion carga sin 404
- [ ] El login funciona con el password configurado
- [ ] Las llamadas a la API externa funcionan (tokens correctos)
- [ ] La sesion se mantiene entre paginas
