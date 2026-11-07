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
 a.text=v; a.text.style={typeface:'Arial',fontSize:size,bold,color,insets:0,verticalAlignment:'middle'};return a;
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
function footer(s,n,dark=false){const col=dark?'#B6C0CB':C.muted;box(s,64,655,1152,1,dark?'#435060':C.line);t(s,'ПЕРЕДАЧА  /  CRM',64,664,330,22,13,col,true);t(s,String(n).padStart(2,'0'),1171,664,50,22,13,col,true);}
async function img(s,file,x,y,w,h){let blob=await fs.readFile(file);const iw=blob.readUInt32BE(16),ih=blob.readUInt32BE(20),scale=Math.min(w/iw,h/ih);s.images.add({blob,contentType:'image/png',position:{left:x+(w-iw*scale)/2,top:y+(h-ih*scale)/2,width:iw*scale,height:ih*scale}});}
{
const s=p.slides.add();s.background.fill=C.navy;
box(s,64,62,42,7,C.green);t(s,'ПЕРЕДАЧА  /  CRM ДЛЯ ДЕВЕЛОПЕРОВ',64,81,670,30,17,C.green,true);
t(s,'Автоматизация\nза две минуты',64,156,1100,220,90,C.white,true);
t(s,'Как меняется работа с осмотрами,\nзамечаниями и документами в CRM',67,427,900,100,35,'#D8E1E7');
t(s,'Шесть сценариев с ориентировочным временем выполнения',68,585,1080,25,17,'#B6C0CB');
footer(s,1,true);note(s,'Две минуты — суммарный ориентир для шести показанных действий в CRM. Время на слайдах приведено для демонстрации и не замерялось.');
}
for(let i=0;i<scenes.length;i++){
const [key,title,before,after,old,now,caption,source]=scenes[i];
const s=p.slides.add();s.background.fill=C.paper;
t(s,title,64,49,1160,85,57,C.ink,true);
box(s,64,155,366,475,C.white);box(s,448,155,768,475,C.soft);
t(s,'ДО  /  ВРУЧНУЮ',88,175,305,32,16,C.muted,true);
t(s,`${before} сек.`,88,212,312,84,63,C.ink,true);
t(s,old,88,318,303,175,28,C.ink);
t(s,'ПОСЛЕ  /  В CRM',474,175,440,32,16,'#365313',true);
t(s,`${after} сек.`,474,210,260,77,60,C.ink,true);
t(s,now,745,181,442,124,21,C.ink);
box(s,474,311,716,267,C.white);
await img(s,path.join(dir,key+'.png'),481,318,702,253);
t(s,caption,475,584,705,28,15,C.muted);
footer(s,i+2);t(s,'Время ориентировочное',485,664,360,22,13,C.muted);
note(s,`Покажите экран CRM. ${now}\nВремя — демонстрационная оценка. Скриншот снят в локальной CRM с тестовыми данными. Источник сценария — ${source}.`);
}
{
const s=p.slides.add();s.background.fill=C.navy;
t(s,'Шесть действий за 120 секунд',64,49,1152,90,59,C.white,true);
t(s,'Сумма ориентиров по всем показанным сценариям',65,145,1140,45,25,'#D8E1E7');
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
t(s,'Покажем на примере\nодного объекта',64,160,1120,202,80,C.ink,true);
t(s,'Запишем осмотр, загрузим акт и назначим задачу.\nЗатем покажем, как CRM формирует документы.',67,393,1110,104,32,C.muted);
box(s,67,547,445,63,C.green);t(s,'Согласовать демонстрацию',88,552,406,50,26,C.ink,true);
footer(s,9);note(s,'Предложите выбрать один объект и согласовать время демонстрации.');
}
const draft=path.join(dir,'draft.pptx');
await (await PresentationFile.exportPptx(p)).save(draft);
const skill=process.env.DECK_SKILL;
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
await finalizePresentation({
 workspaceDir:root,candidatePath:draft,finalPath:path.join(out,'Автоматизация за две минуты.pptx'),
 pythonExecutable:process.env.DECK_PYTHON,
 integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
 layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit'],
 fontPolicy:{basis:'design',families:['Arial']}, verifyArtifactToolImport:true,
 receiptPath:path.join(dir,'validation.json')
});
