import json, sys, time
from pathlib import Path
sys.path.insert(0, 'sistema')
import numpy as np, soundfile as sf, voces
FRAG = ("¿Te pueden meter a la cárcel por deber dinero? El artículo 17 de la Constitución lo responde: "
        "«Nadie puede ser aprisionado por deudas de carácter puramente civil». "
        "Pero ojo: el Código Penal Federal, en su artículo 336, prevé de 1 mes a 5 años de prisión por abandonar a tus hijos sin sustento. "
        "Si un despacho de cobranza te amenaza, puedes acudir a la Condusef o a la Profeco. "
        "Y recuerda: lo que aplica en la Ciudad de México puede cambiar en Jalisco o en Nuevo León.")
FRAG2 = ("La Suprema Corte de Justicia de la Nación resolvió un amparo directo en revisión y fijó jurisprudencia. "
         "En la chamba, la Ley Federal del Trabajo, en su artículo 87, te da derecho a un aguinaldo de al menos 15 días de salario, "
         "y si te corren, te deben tu finiquito. Esto aplica igual en Oaxaca, en Xochimilco, en Texcoco o en Michoacán. "
         "¿Neta? Sí: así lo dice la ley desde 1970.")
FRAGS = [FRAG, FRAG2]
VOCES = {
 "A_kokoro_alex_v01": {"motor":"kokoro","id":"em_alex","lang":"es","velocidad":1.0},
 "B_kokoro_alex_latam": {"motor":"kokoro","id":"em_alex","lang":"es-419","velocidad":0.95},
 "C_kokoro_dora_latam": {"motor":"kokoro","id":"ef_dora","lang":"es-419","velocidad":0.95},
 "D_piper_mx_claude": {"motor":"piper","id":"es_MX-claude-high","velocidad":1.0},
 "E_piper_mx_ald": {"motor":"piper","id":"es_MX-ald-medium","velocidad":1.0},
 "G_kokoro_santa_latam": {"motor":"kokoro","id":"em_santa","lang":"es-419","velocidad":0.95},
 "F_piper_mx_claude_ajustada": {"motor":"piper","id":"es_MX-claude-high","velocidad":0.93,"noise_scale":0.75,"noise_w":0.9},
}
RONDA2 = {
 "R2_B_kokoro_alex": {"motor":"kokoro","id":"em_alex","lang":"es-419","velocidad":0.95},
 "R2_G_kokoro_santa": {"motor":"kokoro","id":"em_santa","lang":"es-419","velocidad":0.95},
 "R2_H_kokoro_mezcla_alex_santa": {"motor":"kokoro","id":"mezcla","mezcla":{"em_alex":0.5,"em_santa":0.5},"lang":"es-419","velocidad":0.95},
 "R2_D_piper_mx_claude": {"motor":"piper","id":"es_MX-claude-high","velocidad":0.97},
}
ronda = sys.argv[1] if len(sys.argv) > 1 else "1"
if ronda == "2": VOCES = RONDA2
out = Path('voz_pruebas') / ('ronda2' if ronda == "2" else ''); out.mkdir(parents=True, exist_ok=True); res = {}
for nombre, v in VOCES.items():
    t0 = time.time(); partes = []
    for fr in FRAGS:
        x, sr = voces.sintetizar(fr, v, pausa=0.0 if nombre.startswith('A_') else 0.42); partes += [x, np.zeros(int(0.8*sr), np.float32)]
    a = np.concatenate(partes); dt = time.time()-t0
    crudo = out/f'{nombre}_crudo.wav'; sf.write(crudo, a, sr)
    final = out/f'{nombre}.wav'; voces.postproceso(crudo, final); crudo.unlink()
    dur = len(a)/sr; hyp = voces.transcribir(final)
    r = {"duracion_s": round(dur,1), "rtf": round(dt/dur,2), "wer": round(voces.wer(" ".join(FRAGS), hyp),3), "transcripcion": hyp, **voces.prosodia(final)}
    r["palabras_por_min"] = round(len(voces._toks(" ".join(FRAGS)))/dur*60)
    res[nombre] = r; print(nombre, {k:v for k,v in r.items() if k!='transcripcion'}, flush=True)
(out/'resultados.json').write_text(json.dumps({"fragmentos": FRAGS, "voces": VOCES, "resultados": res}, ensure_ascii=False, indent=2))
