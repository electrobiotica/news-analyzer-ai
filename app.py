from flask import Flask, request, jsonify, render_template, abort
from newspaper import Article
import openai
from dotenv import load_dotenv
import os, json, re
from datetime import datetime

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

app = Flask(__name__, template_folder="templates")

@app.after_request
def add_cors_headers(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return resp

@app.route('/')
def index():
    return render_template('index_full.html')

# === Rutas adicionales para servir auditoria, legal, politica ===
@app.route('/auditoria')
@app.route('/auditoria.html')
def auditoria():
    return render_template('auditoria.html')

@app.route('/legal')
@app.route('/legal.html')
def legal():
    return render_template('legal.html')

@app.route('/politica')
@app.route('/politica.html')
def politica():
    return render_template('politica.html')

@app.route('/analizar', methods=['POST', 'OPTIONS'])
def analizar():
    if request.method == 'OPTIONS':
        return ('', 204)

    data = request.get_json() or {}
    url = data.get('url')
    if not url:
        return jsonify({'error': 'URL no proporcionada'}), 400

    try:
        article = Article(url)
        article.download()
        article.parse()
        texto = article.text[:6000].replace('"', "'")

        fecha = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        base_prompt = f'''Analiza el texto periodístico y responde ÚNICAMENTE con JSON válido (sin texto extra).
Formato EXACTO:
{{
  "alineacion": {{"izquierda": <0-100>, "derecha": <0-100>}},
  "justificacion": {{"es":"...", "en":"..."}},
  "keywords": {{"es":["..."], "en":["..."]}},
  "frases_sesgadas": {{"es":["..."], "en":["..."]}}
}}

Reglas:
- Claves en minúsculas.
- Los porcentajes deben sumar 100.
- Nada fuera del JSON.

TEXTO:
""" {texto} """ 
'''

        def pedir_json(prompt_text):
            resp = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt_text}],
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            return resp.choices[0].message.content.strip()

        def parsear_json(seguro):
            try:
                return json.loads(seguro), None
            except json.JSONDecodeError as err:
                m = re.search(r"\{[\s\S]*\}", seguro)
                if m:
                    try:
                        return json.loads(m.group(0)), None
                    except Exception as e2:
                        return None, f"Regex found but still invalid: {e2}"
                return None, str(err)

        salida = pedir_json(base_prompt)
        datos, error_parseo = parsear_json(salida)

        if datos is None:
            reparador_prompt = (
                "Convierte lo siguiente en JSON válido estrictamente (sin texto extra):\n"
                f"{salida}"
            )
            salida2 = pedir_json(reparador_prompt)
            datos, error_parseo = parsear_json(salida2)
            if datos is None:
                return jsonify({"error": "❌ Error al decodificar JSON de OpenAI."}), 500

        izq = int(datos.get("alineacion", {}).get("izquierda", 50))
        der = int(datos.get("alineacion", {}).get("derecha", 50))
        izq = max(0, izq); der = max(0, der)
        total = izq + der
        if total == 0:
            izq = der = 50
        elif total != 100:
            izq = round(izq * 100 / total)
            der = 100 - izq

        resultado = {
            "alineacion": {"izquierda": izq, "derecha": der},
            "justificacion": datos.get("justificacion", {}) or {},
            "keywords": datos.get("keywords", {}) or {},
            "frases_sesgadas": datos.get("frases_sesgadas", {}) or {},
            "url": url,
            "fecha_analisis": fecha
        }

        return jsonify(resultado)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)
