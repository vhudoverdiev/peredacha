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
async function brand(s,x,y,dark=false){
 await img(s,path.join(dir,'rounded-logo.png'),x,y,49,49);
 t(s,'Передача',x+60,y,280,27,23,dark?C.white:C.ink,true);
 t(s,'crm.akvilon.tech',x+61,y+27,260,20,14,dark?'#B6C0CB':C.muted);
}
function coverMetric(s){
 rounded(s,731,127,485,464,'#202D37',34);
 for(let i=0;i<6;i++)rounded(s,768+i*69,555,53,7,i<3?C.green:'#597544',3);
 t(s,'ШЕСТЬ ДЕЙСТВИЙ В CRM',765,157,415,29,15,'#C8D2D5',true);
 t(s,'120',759,198,428,208,176,C.green,true);
 t(s,'секунд суммарно',767,393,415,49,30,C.white,true);
 box(s,767,463,410,1,'#465562');
 t(s,'Ориентир для демонстрации',767,490,414,42,19,'#C8D2D5');
}
function footer(s,n,dark=false){const col=dark?'#B6C0CB':C.muted;box(s,64,655,1152,1,dark?'#435060':C.line);t(s,'ПЕРЕДАЧА  /  CRM',64,664,330,22,13,col,true);t(s,String(n).padStart(2,'0'),1171,664,50,22,13,col,true);}
async function img(s,file,x,y,w,h){let blob=await fs.readFile(file);const iw=blob.readUInt32BE(16),ih=blob.readUInt32BE(20),scale=Math.min(w/iw,h/ih);s.images.add({blob,contentType:'image/png',position:{left:x+(w-iw*scale)/2,top:y+(h-ih*scale)/2,width:iw*scale,height:ih*scale}});}
{
const s=p.slides.add();s.background.fill=C.navy;
await brand(s,64,49,true);
coverMetric(s);
t(s,'CRM ДЛЯ ПЕРЕДАЧИ ОБЪЕКТОВ',65,158,600,30,16,C.green,true);
t(s,'Автоматизация\nза две минуты',64,205,660,177,73,C.white,true);
t(s,'Осмотры, задачи и документы',66,404,635,66,31,'#D8E1E7');
footer(s,1,true);note(s,'120 секунд — демонстрационная оценка для шести операций.');
}
const steps=[
 ['Время','Запись','Календарь'],
 ['PDF','Распознавание','Замечания'],
 ['Помещение','Проверка полей','Акт Word'],
 ['Подрядчик','Замечания','Претензия Word'],
 ['Замечание','Назначение','Задача'],
 ['Сообщение','Карточка','Статус'],
];
const shortBefore=[
 'Сверяли расписание и вносили запись вручную.',
 'Переписывали замечания из PDF.',
 'Заполняли шаблон Word вручную.',
 'Собирали замечания и писали претензию.',
 'Рассылали задачи и сверяли статусы.',
 'Искали обращения и ответы в переписке.',
];
function workflow(s,labels){
 for(let j=0;j<3;j++){
  const x=446+j*252;
  rounded(s,x,291,222,44,j===2?C.soft:'#EDF0EC',14);
  t(s,labels[j],x+15,293,194,38,19,j===2?'#365313':C.ink,true);
  if(j<2)t(s,'›',x+229,294,22,36,24,C.muted,true);
 }
}
for(let i=0;i<scenes.length;i++){
const [key,title,before,after,old,now,caption,source]=scenes[i];
const s=p.slides.add();s.background.fill=C.paper;
t(s,'ПЕРЕДАЧА ОБЪЕКТА   /   '+String(i+1).padStart(2,'0'),64,37,700,26,14,'#365313',true);
t(s,title,64,67,1000,73,51,C.ink,true);
rounded(s,1138,43,78,78,C.soft,22);
await img(s,path.join(dir,`scenario-${i}.png`),1145,50,64,64);
rounded(s,64,153,335,469,'#EBEEE6',22);
rounded(s,420,153,796,469,C.white,22);
rounded(s,89,179,143,31,'#DDE3D9',13);
t(s,'ДО  /  ВРУЧНУЮ',101,179,131,31,13,C.muted,true);
t(s,`${before} сек.`,88,218,284,77,58,C.ink,true);
box(s,89,307,283,1,'#CFD7CA');
t(s,shortBefore[i],89,309,278,99,25,C.ink);
t(s,'ЭКОНОМИЯ ВРЕМЕНИ',89,464,283,28,14,'#365313',true);
t(s,`−${before-after} сек.`,89,492,283,58,40,C.ink,true);
rounded(s,89,563,281,8,'#D4DDD0',4);
rounded(s,89,563,281*(before-after)/before,8,C.green,4);
rounded(s,446,179,150,31,C.soft,13);
t(s,'ПОСЛЕ  /  В CRM',457,179,135,31,13,'#365313',true);
t(s,`${after} сек.`,447,219,260,75,60,'#365313',true);
workflow(s,steps[i]);
rounded(s,446,352,744,227,'#E9EFE6',14);
await img(s,path.join(dir,key+'.png'),453,358,730,215);
t(s,caption,447,586,730,26,15,C.muted);
footer(s,i+2);t(s,'Время ориентировочное',486,664,360,22,13,C.muted);
for(let j=0;j<6;j++)rounded(s,920+j*34,675,25,4,j===i?C.green:'#D7E0D2',2);
note(s,`Покажите экран CRM. ${now}\nВремя — демонстрационная оценка. Скриншот снят в локальной CRM с тестовыми данными. Источник сценария — ${source}.`);
}
{
const s=p.slides.add();s.background.fill=C.navy;
t(s,'ИТОГ  /  ШЕСТЬ ОПЕРАЦИЙ ПО ОБЪЕКТУ',64,54,1130,28,16,C.green,true);
t(s,'С 34 минут до двух',64,90,1152,94,70,C.white,true);
rounded(s,64,216,451,313,'#23313C',30);
rounded(s,545,216,671,313,C.green,30);
t(s,'ДО  /  ВРУЧНУЮ',96,245,387,35,16,'#C9D3DC',true);
t(s,'2 040',91,294,390,145,111,C.white,true);
t(s,'секунд',99,449,385,38,28,'#C9D3DC');
t(s,'ПОСЛЕ  /  В CRM',577,245,600,35,16,'#264014',true);
t(s,'120',569,277,604,174,159,C.navy,true);
t(s,'секунд',579,449,604,38,28,'#264014');
t(s,'Время ориентировочное. Фактических замеров нет.',64,574,1152,35,18,'#B6C0CB');
footer(s,8,true);
note(s,'Сумма оценок: 2040 секунд вручную и 120 секунд в CRM. Референсы оформления: https://pitch.com/templates/collections/Creative и https://www.apple.com/apple-events/.');
}
const draft=path.join(dir,'draft.pptx');
await (await PresentationFile.exportPptx(p)).save(draft);
const skill=process.env.DECK_SKILL;
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
await finalizePresentation({
 explicitTotalSlideCount:8,workspaceDir:root,candidatePath:draft,finalPath:path.join(out,'Автоматизация за две минуты — 8 слайдов.pptx'),
 pythonExecutable:process.env.DECK_PYTHON,
 integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit'],
 fontPolicy:{basis:'design',families:['Aptos']}, verifyArtifactToolImport:true,
 receiptPath:path.join(dir,'validation-v6.json')
});
