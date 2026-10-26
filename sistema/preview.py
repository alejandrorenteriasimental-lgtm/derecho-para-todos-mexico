import json, sys
from pathlib import Path
sys.path.insert(0,'sistema')
import narracion, render
from PIL import Image, ImageDraw
c=Path('piezas/T073'); g=json.loads((c/'guion.json').read_text()); out=c/'salida'
lt=out/'linea_tiempo.json'
linea=json.loads(lt.read_text()) if lt.exists() else narracion.sintetizar(g,out)
print(linea['duracion'], [ (s['inicio'],s['fin']) for s in linea['segmentos']])
base=render.fondo(); segs=linea['segmentos']; T=linea['duracion']+0.6
bls=render.bloques([w for s in segs for w in render.tiempos_palabras(s)])
thumbs=[]
for k,s in enumerate(segs):
    t=s['inicio']+0.75*(s['fin']-s['inicio'])
    off=int(600*t/T); fr=base.crop((0,off,1080,off+1920)).copy()
    capa=Image.new('RGBA',(1080,1920),(0,0,0,0)); d=ImageDraw.Draw(capa)
    ini=s['inicio']-0.2; fin=segs[k+1]['inicio']-0.2 if k+1<len(segs) else T
    render.escena(d,g['escenas'][k],(t-ini)/(fin-ini),t-ini,g['fuentes'])
    render.dibujar_subtitulos(d,t,bls)
    fr=Image.alpha_composite(fr,capa).convert('RGB'); thumbs.append(fr.resize((360,640)))
sheet=Image.new('RGB',(360*5,640*2),(0,0,0))
for i,tm in enumerate(thumbs): sheet.paste(tm,((i%5)*360,(i//5)*640))
sheet.save(out/'contacto.png'); print('ok')
