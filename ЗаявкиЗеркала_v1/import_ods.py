# Импорт исторических заявок из ODS-файла (LibreOffice Calc) в Заявки.json.
# Использование: py import_ods.py [файл.ods] [--force]
# Ожидаемые колонки: код поставщика, артикул, ожидаемая дата (ДД.ММ), наименование,
# характеристики, длина, ширина, количество, кто оформил, принят ('да'/пусто), кто принял.
# Последовательные строки с одинаковыми (поставщик, дата, оформил) образуют одну заявку.
# Скрипт отказывается перезаписывать существующий Заявки.json без ключа --force
# (существующий файл предварительно копируется в бэкап).
import json,uuid,sys,zipfile,datetime
from pathlib import Path
import xml.etree.ElementTree as ET

T='urn:oasis:names:tc:opendocument:xmlns:table:1.0'
X='urn:oasis:names:tc:opendocument:xmlns:text:1.0'
O='urn:oasis:names:tc:opendocument:xmlns:office:1.0'
YEAR='2025'
SUP={'Т':'Толик','С':'СтеклоСтиль'}
WHO={'В':'Попов Вадим','ам':'Мищенко Андрей'}
OK='Принято'
WAIT='Ожидаем'
BASE=Path(__file__).resolve().parent
DATA=BASE/'Заявки.json'

def cell_text(tc):
    ps=[''.join(p.itertext()).strip() for p in tc.findall('{%s}p'%X)]
    ps=[p for p in ps if p]
    if ps:return ' / '.join(ps)
    return tc.get('{%s}value'%O) or tc.get('{%s}date-value'%O) or ''

def stamp(d):
    dd,mm=d.split('.')[:2]
    return '%s-%s-%sT12:00:00'%(YEAR,mm.zfill(2),dd.zfill(2))

def parse_rows(path):
    root=ET.fromstring(zipfile.ZipFile(path).read('content.xml'))
    tbl=list(root.iter('{%s}table'%T))[0]
    rows=[]
    for tr in tbl.iter('{%s}table-row'%T):
        rrep=min(int(tr.get('{%s}number-rows-repeated'%T,'1')),200)
        cells=[]
        for tc in tr.findall('{%s}table-cell'%T):
            rep=min(int(tc.get('{%s}number-columns-repeated'%T,'1')),30)
            cells.extend([cell_text(tc)]*rep)
        while cells and not cells[-1].strip():cells.pop()
        if cells:rows.extend([list(cells)]*rrep)
    return rows

def main():
    args=sys.argv[1:]
    force='--force' in args
    files=[a for a in args if not a.startswith('--')]
    src=Path(files[0]) if files else (sorted(BASE.parent.glob('*.ods')) or [None])[0]
    if not src or not Path(src).exists():
        print('ODS file not found');return 1
    if DATA.exists() and not force:
        print('REFUSED: %s already exists, use --force'%DATA.name);return 1
    data=parse_rows(src)[1:]
    orders=[];prev=None
    for r in data:
        if len(r)<9:continue
        g=[(r[i].strip() if i<len(r) else '') for i in range(11)]
        sup,art,nm,feat=g[0],g[1],g[3],g[4]
        dl,dw,dq,cr,acc,who=g[5],g[6],g[7],g[8],g[9],g[10]
        key=(sup,cr,g[2])
        dt=stamp(g[2])
        if key!=prev:
            orders.append({'id':uuid.uuid4().hex,'number':len(orders)+1,'supplier':SUP.get(sup,sup),'created_at':dt,'created_by':WHO.get(cr,cr),'items':[]})
            prev=key
        status=OK if acc.lower().startswith('да') else WAIT
        orders[-1]['items'].append({'id':uuid.uuid4().hex,'article':art,'name':nm,'features':feat,'length':int(dl or 0),'width':int(dw or 0),'quantity':int(dq or 0),'expected':dt[:10],'status':status,'received_at':dt if status==OK else None,'received_by':WHO.get(who,who) if status==OK else None,'returned_at':None,'returned_by':None})
    if DATA.exists() and force:
        bak=BASE/('Zayavki.backup_%s.json'%datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
        bak.write_text(DATA.read_text(encoding='utf-8'),encoding='utf-8')
        print('backup ->',bak.name)
    out={'orders':orders,'events':[{'time':datetime.datetime.now().isoformat(timespec='seconds'),'user':'Импорт','action':'Импорт из ODS','detail':'%s: %d заявок, %d позиций'%(Path(src).name,len(orders),sum(len(o['items']) for o in orders))}]}
    DATA.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    it=[i for o in orders for i in o['items']]
    print('OK %s -> %s'%(Path(src).name,DATA.name))
    print('orders=%d items=%d accepted=%d waiting=%d'%(len(orders),len(it),sum(1 for i in it if i['status']==OK),sum(1 for i in it if i['status']==WAIT)))
    print('suppliers:',', '.join(sorted({o['supplier'] for o in orders})))
    return 0

if __name__=='__main__':
    sys.exit(main())
