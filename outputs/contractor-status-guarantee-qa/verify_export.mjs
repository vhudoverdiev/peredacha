import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const sourcePath = "contractor_export_qa_2026-07-18.xlsx";
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(sourcePath));

const sheets = await workbook.inspect({
  kind: "sheet",
  include: "id,name",
  maxChars: 2000,
});
console.log(sheets.ndjson);

const completed = await workbook.inspect({
  kind: "table",
  range: "Выполненные!A1:D5",
  include: "values,formulas",
  tableMaxRows: 5,
  tableMaxCols: 4,
  maxChars: 4000,
});
console.log(completed.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 50 },
  summary: "final formula error scan",
});
console.log(errors.ndjson);

for (const sheetName of ["Не выполненные", "Выполненные"]) {
  const preview = await workbook.render({
    sheetName,
    autoCrop: "all",
    scale: 1.5,
    format: "png",
  });
  const safeName = sheetName === "Выполненные" ? "completed" : "open";
  await fs.writeFile(`${safeName}.png`, new Uint8Array(await preview.arrayBuffer()));
}
