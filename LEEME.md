# Chispa: noticias que merecen un minuto

## Qué hay en esta carpeta
- `index.html`: la web (un solo archivo, sin dependencias).
- `feeds/`: un JSON por día más `index.json` con la lista de días. Ya incluye el 19 de septiembre.
- `api/prefs.php`: opcional. Recibe tus me gusta, guardados y descartes para personalizar los días siguientes.
- `data/`: donde se guarda `prefs.json`. Protegida con `.htaccess` (Apache).
- `scripts/update_feed.py`: genera el feed del día (RSS + API de Claude).
- `.github/workflows/update.yml`: alternativa si la web vive en GitHub.

## Subirla
Sube todo a una carpeta de tu servidor (por ejemplo `/var/www/chispa`). Ábrela por http(s):
si abres `index.html` con doble clic desde el disco, el navegador bloquea la carga de los JSON.

## Actualización automática diaria (servidor con Python)
1. `pip install feedparser requests`
2. Crea una clave en https://console.anthropic.com (sección API Keys) y prueba a mano:
   `ANTHROPIC_API_KEY=sk-ant-... SITE_DIR=/var/www/chispa python3 /var/www/chispa/scripts/update_feed.py`
3. Programa el cron (`crontab -e`), por ejemplo a las 7:00:
   `0 7 * * * ANTHROPIC_API_KEY=sk-ant-... SITE_DIR=/var/www/chispa /usr/bin/python3 /var/www/chispa/scripts/update_feed.py >> /var/log/chispa.log 2>&1`

Mejor aún: mueve `scripts/` fuera de la carpeta pública y apunta `SITE_DIR` a la web.

Ajustes opcionales por variable de entorno: `CHISPA_TARGET` (historias por día, 50),
`CHISPA_KEEP_DAYS` (días que se conservan, 14), `CHISPA_MODEL` (modelo de Claude).

## Cómo aprende tus gustos
La web guarda tus reacciones en el navegador y, si `api/prefs.php` está disponible, envía un resumen
a `data/prefs.json`. El script lo lee cada mañana y da más peso a los temas y enfoques que te gustan,
sin dejar nunca de incluir un mínimo de cada tema.

## Añadir o quitar fuentes
Edita el diccionario `FEEDS` al principio de `scripts/update_feed.py`.
