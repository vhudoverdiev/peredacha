import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "C:/Users/Владимир/Desktop/100 Квартал 7 очередь .xlsx";
const outputDir = "C:/Users/Владимир/Desktop/Сайты/Peredacha/outputs/019faff4-cleaned-workbook";
const outputPath = `${outputDir}/100 Квартал 7 очередь - проверка.xlsx`;

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const sheetInfo = JSON.parse(`[${(await workbook.inspect({ kind: "sheet", include: "name", maxChars: 10000 })).ndjson.trim().split("\n").join(",")}]`);

for (const info of sheetInfo) {
  const sheet = workbook.worksheets.getItem(info.name);

  if (info.name === "Таблица") {
    // Keep rows 1-6 as the table header and keep apartment/building numbers in A:B.
    sheet.getRange("E7:AG289").clear({ applyTo: "contents" });

    const idValues = sheet.getRange("A7:B289").values;
    const replacement = idValues.map(([apt, build]) => {
      const hasRow = apt !== null && apt !== "" || build !== null && build !== "";
      return hasRow ? ["Проверка", "Проверка"] : [null, null];
    });
    sheet.getRange("C7:D289").values = replacement;
  } else {
    // Keep the first three header rows plus visible apartment/building-number columns.
    for (const range of ["C4:D75", "H4:I75", "M4:N75", "R4:S75", "W4:X75"]) {
      sheet.getRange(range).clear({ applyTo: "contents" });
    }
  }
}

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
  maxChars: 4000,
});
console.log("ERROR_SCAN");
console.log(errors.ndjson);

await fs.mkdir(outputDir, { recursive: true });

for (const info of sheetInfo) {
  const previewRange = info.name === "Таблица" ? "A1:AG35" : "A1:X25";
  const preview = await workbook.render({
    sheetName: info.name,
    range: previewRange,
    scale: 1,
    format: "png",
  });
  await fs.writeFile(`${outputDir}/preview-${info.name.replace(/[\\/:*?"<>|]/g, "_")}.png`, new Uint8Array(await preview.arrayBuffer()));
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(outputPath);
