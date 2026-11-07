from pathlib import Path
p=Path('.deck-build/build.mjs')
s=p.read_text().replace("Автоматизация за две минуты.pptx","Автоматизация за две минуты — дизайн Передачи.pptx")
s=s.replace('function footer(','''function rounded(s,x,y,w,h,fill,r=24){
 return s.shapes.add({geometry:'roundRect',borderRadius:r,position:{left:x,top:y,width:w,height:h},fill,line:none});
}
async function brand(s,x,y){
 await img(s,path.join(root,'landing/assets/brand-logo.png'),x,y,49,49);
 t(s,'Передача',x+60,y,280,27,23,C.ink,true);
 t(s,'crm.akvilon.tech',x+61,y+27,260,20,14,C.muted);
}
function facade(s,x,y){
 rounded(s,x,y,468,510,C.navy,28);
 const faint='#253944', strong='#46616C';
 for(let i=0;i<21;i++)box(s,x+24+i*21,y+24,1,460,faint);
 for(let i=0;i<22;i++)box(s,x+24,y+24+i*21,420,1,faint);
 t(s,'ОБЪЕКТ  /  СХЕМА ФАСАДА',x+34,y+30,380,25,14,'#B8C9CA',true);
 for(const [bx,by,cols,rows] of [[59,184,3,5],[182,101,3,7],[305,142,2,6]]){
  const h=rows*41+15,w=cols*41;
  box(s,x+bx,y+by,w,2,strong);box(s,x+bx,y+by,2,h,strong);box(s,x+bx+w-2,y+by,2,h,strong);
  for(let r=0;r<rows;r++)for(let c=0;c<cols;c++){
   const wx=x+bx+10+c*41,wy=y+by+12+r*41;
   box(s,wx,wy,22,23,(bx===182&&r===3&&c===1)?C.green:strong);
   box(s,wx+2,wy+2,18,19,(bx===182&&r===3&&c===1)?'#BDF278':C.navy);
  }
 }
 box(s,x+39,y+404,390,2,strong);
 box(s,x+34,y+447,23,5,C.green);
 t(s,'КВАРТИРА № 42',x+68,y+432,320,34,17,C.green,true);
}
function footer(''')
a=s.index('{\nconst s=p.slides.add();s.background.fill=C.navy;')
b=s.index('for(let i=0;',a)
s=s[:a]+'''{
const s=p.slides.add();s.background.fill=C.paper;
await brand(s,64,49);
facade(s,748,110);
rounded(s,64,154,299,36,C.soft,16);
t(s,'CRM ДЛЯ ПЕРЕДАЧИ ОБЪЕКТОВ',78,154,275,36,14,'#365313',true);
t(s,'Автоматизация\\nза две минуты',64,205,660,177,73,C.ink,true);
t(s,'От записи на осмотр до выдачи задач\\nи подготовки документов',66,404,635,82,28,C.muted);
t(s,'Шесть сценариев на примере одного объекта',66,546,638,48,21,C.ink,true);
footer(s,1);note(s,'Две минуты — суммарный ориентир для шести показанных действий в CRM. Время на слайдах приведено для демонстрации и не замерялось. Фасад — условная схема.');
}
'''+s[b:]
a=s.index('t(s,title,64,49'); b=s.index('note(s,',a)
s=s[:a]+'''t(s,'ПЕРЕДАЧА ОБЪЕКТА   /   '+String(i+1).padStart(2,'0'),64,37,700,26,14,'#365313',true);
t(s,title,64,67,1152,73,53,C.ink,true);
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
'''+s[b:]
s=s.replace("t(s,'Сумма ориентиров по всем показанным сценариям'","t(s,'Суммарное время на шесть операций по объекту'").replace("t(s,'Покажем на примере\\nодного объекта',64,160,1120,202,80,C.ink,true);","facade(s,748,110);\nt(s,'Покажем на примере\\nодного объекта',64,160,666,202,59,C.ink,true);").replace("67,393,1110,104,32","67,393,650,104,26").replace("box(s,67,547,445,63,C.green)","rounded(s,67,547,445,63,C.green,20)")
Path('.deck-build/restyled.mjs').write_text(s)
