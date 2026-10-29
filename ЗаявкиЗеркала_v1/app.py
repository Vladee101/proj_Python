import os,sys,json,uuid,datetime,tempfile,shutil,subprocess,atexit,msvcrt
from pathlib import Path
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLineEdit,QComboBox,QDateEdit,QSpinBox,QPushButton,QTableWidget,QTableWidgetItem,QMessageBox,QDialog,QDialogButtonBox,QPlainTextEdit,QLabel,QTabWidget,QHeaderView,QFileDialog)
from PySide6.QtCore import Qt,QDate,QTimer
from PySide6.QtGui import QFont

BASE=Path(sys.executable if getattr(sys,'frozen',False) else __file__).resolve().parent
DATA=BASE/'Заявки.json'; LOCK=BASE/'Заявки.lock'; BACKUP=BASE/'Резервные_копии'
SUPPLIERS=['Толик','СтеклоСтиль','УзорСтекло']
USERS={'Попов Вадим':'Оформитель','Мищенко Андрей':'Приёмщик'}
PILLS={'ok':('✓ Сохранено','#e8f5ec','#1e7e34'),'view':('🔒 Режим просмотра','#efefef','#555555'),'err':('⚠ Ошибка сохранения','#fdeaea','#c0392b')}
NOW=lambda:datetime.datetime.now().isoformat(timespec='seconds')
# Windows SMB byte-range lock held for the entire editing session.
SESSION_LOCK=None
def acquire_session():
 global SESSION_LOCK
 LOCK.parent.mkdir(parents=True,exist_ok=True)
 handle=open(LOCK,'a+b',buffering=0)
 try:
  handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
  SESSION_LOCK=handle
  return True
 except OSError:
  handle.close();return False
def release_session():
 global SESSION_LOCK
 if SESSION_LOCK:
  try:SESSION_LOCK.seek(0);msvcrt.locking(SESSION_LOCK.fileno(),msvcrt.LK_UNLCK,1)
  finally:SESSION_LOCK.close();SESSION_LOCK=None
atexit.register(release_session)
def load():
 if not DATA.exists(): return {'orders':[],'events':[]}
 with DATA.open(encoding='utf-8') as f:return json.load(f)
def save(data):
 BACKUP.mkdir(exist_ok=True)
 if DATA.exists():
  shutil.copy2(DATA,BACKUP/('backup_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.json'))
  for old in sorted(BACKUP.glob('backup_*.json'))[:-100]:old.unlink(missing_ok=True)
 fd,tmp=tempfile.mkstemp(dir=BASE,prefix='.orders_',suffix='.tmp')
 try:
  with os.fdopen(fd,'w',encoding='utf-8') as f:
   json.dump(data,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
  os.replace(tmp,DATA)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
def event(data,user,action,detail):data['events'].append({'time':NOW(),'user':user,'action':action,'detail':detail})
class ItemDialog(QDialog):
 def __init__(self,parent=None,item=None):
  super().__init__(parent);self.setWindowTitle('Товар');self.resize(490,430);form=QFormLayout(self)
  self.art=QLineEdit();self.name=QLineEdit();self.features=QPlainTextEdit();self.features.setMaximumHeight(90)
  self.length=QSpinBox();self.width=QSpinBox();self.qty=QSpinBox()
  for w in (self.length,self.width):w.setRange(1,100000);w.setSuffix(' мм')
  self.qty.setRange(1,100000)
  self.date=QDateEdit();self.date.setCalendarPopup(True);self.date.setDisplayFormat('dd.MM.yyyy');self.date.setDate(QDate.currentDate())
  for label,w in [('Артикул',self.art),('Наименование',self.name),('Характеристики',self.features),('Длина',self.length),('Ширина',self.width),('Количество',self.qty),('Ожидаемая дата',self.date)]:form.addRow(label,w)
  if item:
   self.art.setText(item['article']);self.name.setText(item['name']);self.features.setPlainText(item.get('features',''));self.length.setValue(item['length']);self.width.setValue(item['width']);self.qty.setValue(item['quantity']);self.date.setDate(QDate.fromString(item['expected'],'yyyy-MM-dd'))
  buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(self.validate);buttons.rejected.connect(self.reject);form.addRow(buttons)
 def validate(self):
  if not self.art.text().strip() or not self.name.text().strip():QMessageBox.warning(self,'Проверка','Укажите артикул и наименование');return
  self.accept()
 def value(self):return {'article':self.art.text().strip(),'name':self.name.text().strip(),'features':self.features.toPlainText().strip(),'length':self.length.value(),'width':self.width.value(),'quantity':self.qty.value(),'expected':self.date.date().toString('yyyy-MM-dd')}
class OrderDialog(QDialog):
 def __init__(self,parent=None,order=None):
  super().__init__(parent);self.setWindowTitle('Редактирование заявки' if order else 'Новая заявка');self.resize(850,520);self.items=[dict(i) for i in order['items']] if order else []
  root=QVBoxLayout(self);row=QHBoxLayout();self.supplier=QComboBox();self.supplier.addItems(SUPPLIERS)
  if order:self.supplier.setCurrentText(order['supplier'])
  row.addWidget(QLabel('Поставщик:'));row.addWidget(self.supplier);row.addStretch();root.addLayout(row)
  self.table=QTableWidget(0,6);self.table.setHorizontalHeaderLabels(['Артикул','Наименование','Характеристики','Размер, мм','Кол-во','Ожидается']);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);root.addWidget(self.table)
  bar=QHBoxLayout()
  for label,fn in [('Добавить товар',self.add),('Изменить товар',self.edit),('Удалить товар',self.delete)]:
   b=QPushButton(label);b.clicked.connect(fn);bar.addWidget(b)
  root.addLayout(bar)
  buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);buttons.accepted.connect(self.validate);buttons.rejected.connect(self.reject);root.addWidget(buttons);self.refresh()
 def refresh(self):
  self.table.setRowCount(len(self.items))
  for r,i in enumerate(self.items):
   for c,v in enumerate([i['article'],i['name'],i.get('features',''),f"{i['length']} × {i['width']}",str(i['quantity']),i['expected']]):self.table.setItem(r,c,QTableWidgetItem(v))
 def add(self):
  d=ItemDialog(self)
  if d.exec():self.items.append(dict(d.value(),id=uuid.uuid4().hex,status='Ожидаем',received_at=None,received_by=None));self.refresh()
 def edit(self):
  r=self.table.currentRow()
  if r<0:return
  d=ItemDialog(self,self.items[r])
  if d.exec():self.items[r].update(d.value());self.refresh()
 def delete(self):
  r=self.table.currentRow()
  if r>=0 and QMessageBox.question(self,'Удаление','Удалить выбранный товар?')==QMessageBox.Yes:self.items.pop(r);self.refresh()
 def validate(self):
  if not self.items:QMessageBox.warning(self,'Проверка','Добавьте хотя бы один товар');return
  articles=[x['article'].casefold() for x in self.items]
  if len(articles)!=len(set(articles)) and QMessageBox.question(self,'Проверка','В заявке есть дубликаты артикулов. Продолжить?')!=QMessageBox.Yes:return
  self.accept()
class Main(QMainWindow):
 def __init__(self):
  super().__init__();self.setWindowTitle('Заявки на зеркала и стекло');self.resize(1260,750)
  self.can_edit=acquire_session();self.user=QComboBox();self.user.addItems(USERS);self.user.currentTextChanged.connect(self.refresh)
  central=QWidget();self.setCentralWidget(central);root=QVBoxLayout(central);top=QHBoxLayout();top.addWidget(QLabel('Сотрудник:'));top.addWidget(self.user);top.addStretch();self.pill=QLabel();self.pill.hide();top.addWidget(self.pill);root.addLayout(top)
  self._pill_timer=QTimer(self);self._pill_timer.setSingleShot(True);self._pill_timer.timeout.connect(lambda:self.pill.hide() if self.can_edit else self.set_pill('view'))
  self.metrics=QLabel();root.addWidget(self.metrics)
  if not self.can_edit:self.set_pill('view')
  controls=QHBoxLayout();self.search=QLineEdit();self.search.setPlaceholderText('Поиск: артикул, название, характеристики, номер заявки, размер');self.search.textChanged.connect(self.refresh);controls.addWidget(self.search)
  self.supplier=QComboBox();self.supplier.addItems(['Все поставщики']+SUPPLIERS);self.supplier.currentTextChanged.connect(self.refresh);controls.addWidget(self.supplier)
  self.status=QComboBox();self.status.addItems(['Все статусы','Ожидаем','Принято','Возврат','Просрочено']);self.status.currentTextChanged.connect(self.refresh);controls.addWidget(self.status)
  self.date=QDateEdit();self.date.setCalendarPopup(True);self.date.setDisplayFormat('dd.MM.yyyy');self.date.setDate(QDate.currentDate());controls.addWidget(self.date)
  self.date_enabled=QComboBox();self.date_enabled.addItems(['Все даты','Ожидается на дату','Создано на дату','Принято на дату']);self.date_enabled.currentTextChanged.connect(self.refresh);controls.addWidget(self.date_enabled);root.addLayout(controls)
  self.table=QTableWidget(0,12);self.table.setHorizontalHeaderLabels(['Заявка','Поставщик','Артикул','Наименование','Характеристики','Размеры, мм','Кол-во','Ожидается','Статус','Факт. дата','Принял','Оформил']);self.table.setSelectionBehavior(QTableWidget.SelectRows);self.table.setEditTriggers(QTableWidget.NoEditTriggers);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive);self.table.setColumnWidth(4,260);root.addWidget(self.table)
  bar=QHBoxLayout()
  for label,fn in [('Новая заявка',self.create),('Редактировать заявку',self.edit),('Принял',lambda:self.transition('Принято')),('Возврат',lambda:self.transition('Возврат')),('Снова ожидаем',self.reset),('PDF заявки',self.pdf),('Обновить',self.refresh),('История',self.history)]:
   b=QPushButton(label);b.clicked.connect(fn);bar.addWidget(b)
  root.addLayout(bar);self.refresh()
 def selected(self):
  r=self.table.currentRow()
  if r<0:QMessageBox.information(self,'Выбор','Выберите товар в таблице');return None,None
  order_id=self.table.item(r,0).data(Qt.UserRole);item_id=self.table.item(r,2).data(Qt.UserRole)
  data=self._load_or_warn()
  if data is None:return None,None
  for order in data['orders']:
   if order['id']==order_id:
    for item in order['items']:
     if item['id']==item_id:return order,item
  return None,None
 def refresh(self,*_):
  if not hasattr(self,'table'):return
  try:data=load()
  except Exception as ex:QMessageBox.critical(self,'Ошибка данных',str(ex));return
  rows=[];q=self.search.text().strip().casefold();today=datetime.date.today().isoformat();dt=self.date.date().toString('yyyy-MM-dd')
  for order in data['orders']:
   for item in order['items']:
    if self.supplier.currentIndex()>0 and order['supplier']!=self.supplier.currentText():continue
    st=self.status.currentText()
    if st=='Просрочено' and not (item['status']=='Ожидаем' and item['expected']<today):continue
    if st not in ('Все статусы','Просрочено') and item['status']!=st:continue
    date_filter=self.date_enabled.currentText()
    if date_filter=='Ожидается на дату' and item['expected']!=dt:continue
    if date_filter=='Создано на дату' and order['created_at'][:10]!=dt:continue
    if date_filter=='Принято на дату' and (item.get('received_at') or '')[:10]!=dt:continue
    vals=[str(order['number']),order['supplier'],item['article'],item['name'],item.get('features',''),f"{item['length']} × {item['width']}",str(item['quantity']),item['expected'],item['status'],item.get('received_at') or '',item.get('received_by') or '',order['created_by']]
    if q and q not in ' '.join(vals).casefold():continue
    rows.append((order,item,vals))
  self.table.setRowCount(len(rows))
  for r,(order,item,vals) in enumerate(rows):
   for c,v in enumerate(vals):self.table.setItem(r,c,QTableWidgetItem(v))
   self.table.item(r,0).setData(Qt.UserRole,order['id']);self.table.item(r,2).setData(Qt.UserRole,item['id'])
  all_items=[i for o in data['orders'] for i in o['items']]
  wait=[i for i in all_items if i['status']=='Ожидаем']
  accepted=[i for i in all_items if i['status']=='Принято' and (i.get('received_at') or '')[:10]==today]
  self.metrics.setText(f'ОЖИДАЕМ ВСЕГО: {len(wait)}     ОЖИДАЕМ СЕГОДНЯ: {sum(i["expected"]==today for i in wait)}     ПРОСРОЧЕНО: {sum(i["expected"]<today for i in wait)}     ПРИНЯТО СЕГОДНЯ: {len(accepted)}')
  self.statusBar().showMessage(f'Показано товаров: {len(rows)} | '+('Редактирование разрешено' if self.can_edit else 'Только просмотр'))
 def writable(self,role):
  if not self.can_edit:QMessageBox.warning(self,'Занято','Другой пользователь уже работает с файлом. Доступен только просмотр.');return False
  if USERS[self.user.currentText()]!=role:QMessageBox.warning(self,'Доступ',f'Действие доступно роли «{role}»');return False
  return True
 def set_pill(self,kind,sticky=True,text=None):
  label,bg,fg=PILLS[kind];self.pill.setText(text or label);self.pill.setStyleSheet(f'padding:3px 10px;border-radius:10px;background:{bg};color:{fg};font-weight:600;');self.pill.setToolTip('Другой сотрудник редактирует данные. Для получения доступа закройте и снова откройте программу после освобождения.' if kind=='view' else '');self.pill.show()
  if not sticky:self._pill_timer.start(5000)
 def _save(self,data):
  try:save(data)
  except Exception as ex:self.set_pill('err');QMessageBox.critical(self,'Ошибка сохранения',f'Не удалось записать данные: {ex}');return False
  self.set_pill('ok',sticky=False);return True
 def _load_or_warn(self):
  try:return load()
  except Exception as ex:self.set_pill('err',text='⚠ Ошибка чтения данных');QMessageBox.warning(self,'Ошибка данных',f'Не удалось прочитать данные: {ex}');return None
 def create(self):
  if not self.writable('Оформитель'):return
  d=OrderDialog(self)
  if d.exec():
   data=self._load_or_warn()
   if data is None:return
   existing={i['article'].casefold() for o in data['orders'] for i in o['items']}
   dup=[i['article'] for i in d.items if i['article'].casefold() in existing]
   if dup and QMessageBox.question(self,'Артикул','Такой артикул уже существует: '+', '.join(dup[:5])+'. Продолжить?')!=QMessageBox.Yes:return
   number=max([o['number'] for o in data['orders']],default=0)+1
   order={'id':uuid.uuid4().hex,'number':number,'supplier':d.supplier.currentText(),'created_at':NOW(),'created_by':self.user.currentText(),'items':d.items}
   data['orders'].append(order);event(data,self.user.currentText(),'Создание заявки',f'№{number}')
   if self._save(data):self.refresh()
 def edit(self):
  if not self.writable('Оформитель'):return
  order,item=self.selected()
  if not order:return
  d=OrderDialog(self,order)
  if d.exec():
   data=self._load_or_warn()
   if data is None:return
   existing={i['article'].casefold() for o in data['orders'] if o['id']!=order['id'] for i in o['items']}
   dup=[i['article'] for i in d.items if i['article'].casefold() in existing]
   if dup and QMessageBox.question(self,'Артикул','Такой артикул уже существует: '+', '.join(dup[:5])+'. Продолжить?')!=QMessageBox.Yes:return
   for o in data['orders']:
    if o['id']==order['id']:
     before=json.dumps(o,ensure_ascii=False);o['supplier']=d.supplier.currentText();o['items']=d.items
     event(data,self.user.currentText(),'Редактирование заявки',f"№{o['number']}; до: {before}; после: {json.dumps(o,ensure_ascii=False)}");break
   if self._save(data):self.refresh()
 def transition(self,status):
  if not self.writable('Приёмщик'):return
  order,item=self.selected()
  if not item:return
  if item['status']!='Ожидаем':QMessageBox.warning(self,'Статус','Можно обработать только товар со статусом «Ожидаем»');return
  if QMessageBox.question(self,'Подтверждение',f"{status}: {item['article']} ({item['quantity']} шт.)?")!=QMessageBox.Yes:return
  data=self._load_or_warn()
  if data is None:return
  for o in data['orders']:
   for i in o['items']:
    if i['id']==item['id']:
     i['status']=status;i['received_at']=NOW() if status=='Принято' else None;i['received_by']=self.user.currentText() if status=='Принято' else None;i['returned_at']=NOW() if status=='Возврат' else None;i['returned_by']=self.user.currentText() if status=='Возврат' else None
  event(data,self.user.currentText(),status,item['article'])
  if self._save(data):self.refresh()
 def reset(self):
  if not self.writable('Оформитель'):return
  order,item=self.selected()
  if not item or item['status']!='Возврат':QMessageBox.warning(self,'Статус','Выберите возвращённый товар');return
  d=ItemDialog(self,item)
  if d.exec():
   data=self._load_or_warn()
   if data is None:return
   for o in data['orders']:
    for i in o['items']:
     if i['id']==item['id']:
      i.update(d.value());i['status']='Ожидаем';i['received_at']=None;i['received_by']=None
   event(data,self.user.currentText(),'Повторное ожидание',f"{item['article']}; новая дата {d.value()['expected']}")
   if self._save(data):self.refresh()
 def history(self):
  data=load();dialog=QDialog(self);dialog.setWindowTitle('История действий');dialog.resize(900,450);layout=QVBoxLayout(dialog);table=QTableWidget(0,4);table.setHorizontalHeaderLabels(['Дата','Сотрудник','Действие','Подробности']);table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);layout.addWidget(table)
  for e in reversed(data['events']):
   r=table.rowCount();table.insertRow(r)
   for c,v in enumerate([e['time'],e['user'],e['action'],e['detail']]):table.setItem(r,c,QTableWidgetItem(v))
  dialog.exec()
 def pdf(self):
  order,item=self.selected()
  if not order:return
  path,_=QFileDialog.getSaveFileName(self,'Сохранить PDF',f"Заявка_{order['number']}.pdf",'PDF (*.pdf)')
  if not path:return
  from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,Spacer
  from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
  from reportlab.lib import colors
  from reportlab.lib.pagesizes import landscape,A4
  from reportlab.pdfbase import pdfmetrics
  from reportlab.pdfbase.ttfonts import TTFont
  fonts=[r'C:\Windows\Fonts\arial.ttf',r'C:\Windows\Fonts\DejaVuSans.ttf','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
  font=next((x for x in fonts if Path(x).exists()),None)
  if not font:QMessageBox.warning(self,'PDF','Не найден шрифт с поддержкой кириллицы');return
  pdfmetrics.registerFont(TTFont('RU',font));style=ParagraphStyle('ru',fontName='RU',fontSize=9,leading=13)
  p=lambda v:Paragraph(str(v).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('\n','<br/>'),style)
  story=[p('ЗАЯВКА НА ИЗГОТОВЛЕНИЕ И ПОСТАВКУ'),Spacer(1,9),p(f"Заявка №{order['number']}"),p(f"Поставщик: {order['supplier']}"),p(f"Дата: {order['created_at'][:10]}"),Spacer(1,16)]
  rows=[[p(x) for x in ['Артикул','Наименование','Характеристики','Длина, мм','Ширина, мм','Кол-во','Ожидаемая дата']]]
  for i in order['items']:rows.append([p(i['article']),p(i['name']),p(i.get('features','')),p(i['length']),p(i['width']),p(i['quantity']),p(i['expected'])])
  t=Table(rows,colWidths=[80,95,260,65,65,50,100],repeatRows=1);t.setStyle(TableStyle([('GRID',(0,0),(-1,-1),0.3,colors.grey),('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4)]));story.append(t)
  SimpleDocTemplate(path,pagesize=landscape(A4),leftMargin=32,rightMargin=32).build(story);QMessageBox.information(self,'PDF','PDF сохранён')
if __name__=='__main__':
 app=QApplication(sys.argv);app.setStyle('Fusion');w=Main();w.show();sys.exit(app.exec())
