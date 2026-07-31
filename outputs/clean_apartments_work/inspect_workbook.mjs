import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "C:/Users/Владимир/Desktop/100 Квартал 7 очередь .xlsx";
const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);

console.log("SHEETS");
console.log((await workbook.inspect({ kind: "sheet", include: "id,name", maxChars: 4000 })).ndjson);

console.log("SUMMARY");
console.log((await workbook.inspect({
  kind: "workbook,sheet,table",
  tableMaxRows: 12,
  tableMaxCols: 20,
  tableMaxCellChars: 80,
  maxChars: 20000,
})).ndjson);

for (const term of ["ФИО", "тел", "кварт", "строит", "№"]) {
  console.log(`MATCH ${term}`);
  console.log((await workbook.inspect({
    kind: "match",
    searchTerm: term,
    options: { maxResults: 80 },
    maxChars: 12000,
  })).ndjson);
}
