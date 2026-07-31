import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const outputPath = "C:/Users/Владимир/Desktop/Сайты/Peredacha/outputs/019faff4-cleaned-workbook/100 Квартал 7 очередь - проверка.xlsx";
const input = await FileBlob.load(outputPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const main = workbook.worksheets.getItem("Таблица");
console.log("MAIN_SAMPLE");
console.log((await workbook.inspect({
  kind: "table",
  sheetId: "Таблица",
  range: "A4:H12",
  tableMaxRows: 12,
  tableMaxCols: 8,
  maxChars: 6000,
})).ndjson);

console.log("OLD_NAME_SEARCH");
console.log((await workbook.inspect({
  kind: "match",
  searchTerm: "Глебова|Шайхутдинова|Рогозин|Голубева|Шерягин|Ханталин|\\b7\\s?9\\d{2}",
  options: { useRegex: true, maxResults: 20 },
  maxChars: 4000,
})).ndjson);

let nonEmptyUnexpected = 0;
for (const info of JSON.parse(`[${(await workbook.inspect({ kind: "sheet", include: "name", maxChars: 10000 })).ndjson.trim().split("\n").join(",")}]`)) {
  const sheet = workbook.worksheets.getItem(info.name);
  if (info.name === "Таблица") {
    const values = sheet.getRange("E7:AG289").values;
    nonEmptyUnexpected += values.flat().filter((value) => value !== null && value !== "").length;
  } else {
    for (const range of ["C4:D75", "H4:I75", "M4:N75", "R4:S75", "W4:X75"]) {
      const values = sheet.getRange(range).values;
      nonEmptyUnexpected += values.flat().filter((value) => value !== null && value !== "").length;
    }
  }
}

const replacements = main.getRange("C7:D289").values.flat().filter((value) => value === "Проверка").length;
console.log(JSON.stringify({ nonEmptyUnexpected, replacements }));
