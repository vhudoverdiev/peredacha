import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {Presentation,PresentationFile} from '@oai/artifact-tool';
const root=process.cwd(), dir=path.join(root,'.deck-build'), out=path.join(root,'exports/presentation');
const p=Presentation.create({slideSize:{width:1280,height:720}});
const C={navy:'#151D27',green:'#93D72B',ink:'#101828',muted:'#536173',paper:'#F6F8EF',line:'#D9E2D3',soft:'#EEF9DD',white:'#FFFFFF'};
const none={fill:'none',width:0};
function box(s,x,y,w,h,fill){return s.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill,line:none});}
function t(s,v,x,y,w,h,size,color=C.ink,bold=false){
 const a=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:none});
 a.text=v; a.text.style={typeface:'Aptos',fontSize:size,bold,color,insets:0,verticalAlignment:'middle'};return a;
}
function note(s,content){s.speakerNotes.text=content;}
const scenes=[
 ['records','Запись на осмотр',180,20,'Сверяли календарь, согласовывали время и вручную заносили запись.','Выберите свободное время и помещение. CRM сохранит запись и покажет занятое время в календаре.','Календарь осмотров с записью на квартиру № 42','app/workflows.py'],
 ['ocr','Распознавание актов',480,30,'Открывали PDF и вручную переносили замечания из акта.','Загрузите PDF. CRM извлечёт данные акта и замечания. Проверьте строки перед сохранением.','Загрузка PDF-актов для распознавания','app/templates/task_recognition.html'],
 ['avr','Акт выполненных работ',360,20,'Открывали шаблон Word и заполняли данные по квартире вручную.','Выберите помещение и проверьте подставленные данные. CRM сформирует акт в Word по шаблону.','Поля акта с данными из карточки помещения','app/templates/avr.html'],
 ['claim','Претензия подрядчику',600,20,'Собирали замечания по квартирам и переносили их в письмо подрядчику.','Выберите подрядчика и помещения. CRM соберёт претензию в Word из замечаний по выбранным помещениям.','Выбор помещений и кнопка «Претензия Word»','app/routes.py, app/services/contractor_claim_docx.py'],
 ['tasks','Выдача задач',240,15,'Пересылали замечания исполнителям и отдельно отмечали, кто за что отвечает.','Выберите замечания и назначьте исполнителя. В CRM видны выданные задачи, статусы и комментарии.','Выданные задачи со статусами и комментариями','app/routes.py, раздел «Выдача задач»'],
 ['appeal','Обращение по помещению',180,15,'Сохраняли обращение из переписки и отдельно отслеживали, что по нему сделали.','Создайте обращение по помещению и при необходимости приложите файл. Статус и обсуждение будут в карточке.','Форма обращения с привязкой к помещению','app/workflows.py, app/templates/appeal_form.html'],
];
function rounded(s,x,y,w,h,fill,r=24){
 return s.shapes.add({geometry:'roundRect',borderRadius:r,position:{left:x,top:y,width:w,height:h},fill,line:none});
}
async function brand(s,x,y){
 await img(s,path.join(root,'landing/assets/brand-logo.png'),x,y,49,49);
 t(s,'Передача',x+60,y,280,27,23,C.ink,true);
 t(s,'crm.akvilon.tech',x+61,y+27,260,20,14,C.muted);
}
function coverMetric(s){
 rounded(s,731,127,485,464,C.navy,34);
 t(s,'ШЕСТЬ ДЕЙСТВИЙ В CRM',765,157,415,29,15,'#C8D2D5',true);
 t(s,'120',759,198,428,208,176,C.green,true);
 t(s,'секунд суммарно',767,393,415,49,30,C.white,true);
 box(s,767,463,410,1,'#465562');
 t(s,'Ориентир для демонстрации',767,490,414,42,19,'#C8D2D5');
}
function demoAgenda(s){
 rounded(s,747,140,469,421,C.soft,30);
 t(s,'ЧТО ПОКАЖЕМ В CRM',778,169,405,34,16,'#365313',true);
 const rows=['Запись на осмотр','Распознавание акта и выдача задач','Подготовка документов'];
 for(let i=0;i<rows.length;i++){
  const y=223+i*95;
  box(s,778,y,405,1,'#CEDDBA');
  t(s,'0'+(i+1),778,y+14,62,55,22,'#365313',true);
  t(s,rows[i],838,y+11,337,61,23,C.ink,true);
 }
}
function footer(s,n,dark=false){const col=dark?'#B6C0CB':C.muted;box(s,64,655,1152,1,dark?'#435060':C.line);t(s,'ПЕРЕДАЧА  /  CRM',64,664,330,22,13,col,true);t(s,String(n).padStart(2,'0'),1171,664,50,22,13,col,true);}
async function img(s,file,x,y,w,h){let blob=await fs.readFile(file);const iw=blob.readUInt32BE(16),ih=blob.readUInt32BE(20),scale=Math.min(w/iw,h/ih);s.images.add({blob,contentType:'image/png',position:{left:x+(w-iw*scale)/2,top:y+(h-ih*scale)/2,width:iw*scale,height:ih*scale}});}
{
const s=p.slides.add();s.background.fill=C.paper;
await brand(s,64,49);
coverMetric(s);
rounded(s,64,154,299,36,C.soft,16);
t(s,'CRM ДЛЯ ПЕРЕДАЧИ ОБЪЕКТОВ',78,154,275,36,14,'#365313',true);
t(s,'Автоматизация\nза две минуты',64,205,660,177,73,C.ink,true);
t(s,'От записи на осмотр до выдачи задач\nи подготовки документов',66,404,635,82,28,C.muted);
t(s,'Шесть сценариев на примере одного объекта',66,546,638,48,21,C.ink,true);
footer(s,1);note(s,'Две минуты — суммарный ориентир для шести показанных действий в CRM. Время на слайдах приведено для демонстрации и не замерялось. Референсы оформления: https://linear.app/, https://stripe.com/, https://pitch.com/templates/collections/Product.');
}
for(let i=0;i<scenes.length;i++){
const [key,title,before,after,old,now,caption,source]=scenes[i];
const s=p.slides.add();s.background.fill=C.paper;
t(s,'ПЕРЕДАЧА ОБЪЕКТА   /   '+String(i+1).padStart(2,'0'),64,37,700,26,14,'#365313',true);
t(s,title,64,67,1152,73,51,C.ink,true);
rounded(s,64,153,335,469,'#EBEEE6',22);
rounded(s,420,153,796,469,C.white,22);
rounded(s,89,179,143,31,'#DDE3D9',13);
t(s,'ДО  /  ВРУЧНУЮ',101,179,131,31,13,C.muted,true);
t(s,`${before} сек.`,88,218,284,77,58,C.ink,true);
box(s,89,307,283,1,'#CFD7CA');
t(s,old,89,326,278,158,25,C.ink);
rounded(s,446,179,150,31,C.soft,13);
t(s,'ПОСЛЕ  /  В CRM',457,179,135,31,13,'#365313',true);
t(s,`${after} сек.`,447,219,260,75,60,'#365313',true);
t(s,now,717,177,470,116,21,C.ink);
rounded(s,446,305,744,273,'#E9EFE6',14);
await img(s,path.join(dir,key+'.png'),453,312,730,259);
t(s,caption,447,586,730,26,15,C.muted);
footer(s,i+2);t(s,'Время ориентировочное',486,664,360,22,13,C.muted);
note(s,`Покажите экран CRM. ${now}\nВремя — демонстрационная оценка. Скриншот снят в локальной CRM с тестовыми данными. Источник сценария — ${source}.`);
}
{
const s=p.slides.add();s.background.fill=C.navy;
t(s,'Шесть действий за 120 секунд',64,49,1152,90,59,C.white,true);
t(s,'Суммарное время на шесть операций по объекту',65,145,1140,45,25,'#D8E1E7');
t(s,'ДО  /  ВРУЧНУЮ',64,242,485,32,18,'#B6C0CB',true);
t(s,'2 040 сек.',64,274,540,137,95,C.white,true);
t(s,'ПОСЛЕ  /  В CRM',670,242,500,32,18,C.green,true);
t(s,'120 сек.',670,274,530,137,95,C.green,true);
box(s,65,426,530,10,'#5A6877');box(s,671,426,530,10,'#435060');box(s,671,426,31,10,C.green);
t(s,'34 минуты',66,466,500,50,35,C.white);
t(s,'2 минуты',671,466,520,50,35,C.white);
t(s,'Время приведено для демонстрации. Фактических замеров нет.',64,577,1152,32,18,'#B6C0CB');
footer(s,8,true);
note(s,'Сумма ручных оценок: 180 + 480 + 360 + 600 + 240 + 180 = 2040 секунд. Сумма оценок CRM: 20 + 30 + 20 + 20 + 15 + 15 = 120 секунд. При замене оценок обновите итоговые числа и длину зелёной полосы.');
}
{
const s=p.slides.add();s.background.fill=C.paper;
box(s,64,70,42,7,C.green);t(s,'ДЕМОНСТРАЦИЯ CRM',64,92,680,31,17,'#365313',true);
demoAgenda(s);
t(s,'Покажем на примере\nодного объекта',64,160,666,202,59,C.ink,true);
t(s,'Пройдём рабочий сценарий службы передачи\nот записи до готового документа.',67,393,650,104,25,C.muted);
rounded(s,67,547,445,63,C.green,20);t(s,'Согласовать демонстрацию',88,552,406,50,26,C.ink,true);
footer(s,9);note(s,'Предложите выбрать один объект и согласовать время демонстрации.');
}
const draft=path.join(dir,'draft.pptx');
await (await PresentationFile.exportPptx(p)).save(draft);
const skill=process.env.DECK_SKILL;
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
await finalizePresentation({
 workspaceDir:root,candidatePath:draft,finalPath:path.join(out,'Автоматизация за две минуты — финальный дизайн.pptx'),
 pythonExecutable:process.env.DECK_PYTHON,
 integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit'],
 fontPolicy:{basis:'design',families:['Aptos']}, verifyArtifactToolImport:true,
 receiptPath:path.join(dir,'validation-v4.json')
});
