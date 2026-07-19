import fs from 'node:fs/promises';
import path from 'node:path';
import sharp from 'file:///C:/Users/18EE~1/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/.pnpm/sharp@0.34.5/node_modules/sharp/lib/index.js';

const pack = String.raw`C:\Users\Владимир\Desktop\Презентация CRM\Раб.файлы для видео\CRM_Peredacha_montage_pack`;
const desktopDir = path.join(pack, '02_desktop_frames');
const combinedDir = path.join(pack, '04_combined_scenes');
const previewsDir = path.join(pack, '09_previews');
const gray = '#575D62';
const outline = '#777E83';
const addressFill = '#E7EAEC';

const targets = [
  path.join(desktopDir, 'desktop_browser_compact_overlay.svg'),
  path.join(desktopDir, 'desktop_browser_fullhd_overlay.svg'),
  path.join(desktopDir, 'desktop_browser_left_overlay.svg'),
  path.join(combinedDir, 'scene_desktop_plus_phone_overlay.svg'),
  path.join(combinedDir, 'scene_split_desktop_phone_overlay.svg'),
];

function updateDesktopSvg(svg, filename) {
  const maskMatch = svg.match(/<mask id="windowBody"><rect x="([^"]+)" y="([^"]+)" width="([^"]+)" height="([^"]+)" rx="([^"]+)" fill="white"\/><rect x="([^"]+)" y="([^"]+)" width="([^"]+)" height="([^"]+)" rx="([^"]+)" fill="black"\/><\/mask>/);
  if (!maskMatch) throw new Error(`windowBody mask not found: ${filename}`);

  const [, outerX, outerY, outerW, outerH, outerRx, innerX, innerY, innerW, innerH, innerRx] = maskMatch;
  svg = svg.replace(
    /<rect x="([^"]+)" y="([^"]+)" width="([^"]+)" height="([^"]+)" rx="([^"]+)" fill="#[A-Fa-f0-9]{6}" mask="url\(#windowBody\)"\/>/,
    `<rect x="${outerX}" y="${outerY}" width="${outerW}" height="${outerH}" rx="${outerRx}" fill="${gray}" mask="url(#windowBody)"/>`,
  );

  svg = svg.replace(/\s*<rect data-logo-gray-desktop-outline="true"[^>]*\/>/g, '');
  const bodyGroup = new RegExp(`(<g filter="url\\(#shadow\\)">\\s*<rect x="${outerX}" y="${outerY}"[\\s\\S]*?<\\/g>)`);
  svg = svg.replace(
    bodyGroup,
    `$1\n  <rect data-logo-gray-desktop-outline="true" x="${outerX}" y="${outerY}" width="${outerW}" height="${outerH}" rx="${outerRx}" fill="none" stroke="${outline}" stroke-width="3"/>`,
  );

  const innerBorder = new RegExp(`<rect x="${innerX}" y="${innerY}" width="${innerW}" height="${innerH}" rx="${innerRx}" fill="none" stroke="#[A-Fa-f0-9]{6}" stroke-width="4"\\/>`);
  svg = svg.replace(
    innerBorder,
    `<rect x="${innerX}" y="${innerY}" width="${innerW}" height="${innerH}" rx="${innerRx}" fill="none" stroke="${outline}" stroke-width="4"/>`,
  );

  svg = svg.replace(/fill="#EEF7E2"/g, `fill="${addressFill}"`);
  svg = svg.replace(/(<text[^>]*>akvilon-peredacha\.ru<\/text>)/g, (text) => text.replace(/fill="#[A-Fa-f0-9]{6}"/, `fill="${gray}"`));
  svg = svg.replace(/\s*<text[^>]*text-anchor="end"[^>]*>CRM [^<]*<\/text>/g, '');

  if (!svg.includes(`fill="${gray}" mask="url(#windowBody)"`)) throw new Error(`gray desktop body missing: ${filename}`);
  if (svg.includes('CRM Передача')) throw new Error(`CRM label remains: ${filename}`);
  return svg;
}

async function renderSvg(svgPath) {
  const pngPath = svgPath.replace(/\.svg$/i, '.png');
  await sharp(svgPath, { density: 144 }).resize(1920, 1080).png().toFile(pngPath);
}

function checkerboardSvg(width, height, cell = 40) {
  return Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><defs><pattern id="c" width="${cell * 2}" height="${cell * 2}" patternUnits="userSpaceOnUse"><rect width="${cell * 2}" height="${cell * 2}" fill="#F3F4F5"/><rect width="${cell}" height="${cell}" fill="#DDE1E4"/><rect x="${cell}" y="${cell}" width="${cell}" height="${cell}" fill="#DDE1E4"/></pattern></defs><rect width="100%" height="100%" fill="url(#c)"/></svg>`);
}

async function compositePreview(base, overlays, output) {
  await sharp(base).resize(1920, 1080).composite(overlays.map((input) => ({ input }))).png().toFile(output);
}

async function alphaAt(file, x, y) {
  const { data, info } = await sharp(file).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  return data[(y * info.width + x) * info.channels + 3];
}

async function rgbaAt(file, x, y) {
  const { data, info } = await sharp(file).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  const i = (y * info.width + x) * info.channels;
  return Array.from(data.subarray(i, i + 4));
}

for (const svgPath of targets) {
  const current = await fs.readFile(svgPath, 'utf8');
  const updated = updateDesktopSvg(current, path.basename(svgPath));
  await fs.writeFile(svgPath, updated, 'utf8');
  await renderSvg(svgPath);
}

const bg = path.join(pack, '01_backgrounds', 'background_presentation_style_ai_16x9.png');
const desktopFull = path.join(desktopDir, 'desktop_browser_fullhd_overlay.png');
const combined = path.join(combinedDir, 'scene_desktop_plus_phone_overlay.png');
const lowerThird = path.join(pack, '05_titles_and_overlays', 'feature_01_lowerthird.png');

await compositePreview(checkerboardSvg(1920, 1080), [desktopFull], path.join(previewsDir, 'preview_desktop_transparency.png'));
await compositePreview(bg, [desktopFull], path.join(previewsDir, 'preview_presentation_background_gray_desktop.png'));
await compositePreview(bg, [combined], path.join(previewsDir, 'preview_combined_scene_gray_phone.png'));
await compositePreview(bg, [combined], path.join(previewsDir, 'preview_gray_desktop_and_phone.png'));
await compositePreview(bg, [desktopFull, lowerThird], path.join(previewsDir, 'quick_scene_example.png'));

const readmePath = path.join(pack, '00_README_RU.txt');
let readme = await fs.readFile(readmePath, 'utf8');
const updateSection = `\n\nОБНОВЛЕНИЕ — СЕРАЯ ДЕСКТОПНАЯ РАМКА\n- Все десктопные рамки в 02_desktop_frames и 04_combined_scenes переведены в серый цвет ${gray} — оттенок буквы A в логотипе.\n- Надпись «CRM Передача» с верхней панели удалена. Адрес akvilon-peredacha.ru сохранён.\n- Координаты вставки, размеры и прозрачные области экранов не изменились.\n`;
readme = readme.replace(/\n\nОБНОВЛЕНИЕ — СЕРАЯ ДЕСКТОПНАЯ РАМКА[\s\S]*?(?=\n\n[A-ZА-ЯЁ][A-ZА-ЯЁ ]+|$)/, '');
readme = readme.trimEnd() + updateSection;
await fs.writeFile(readmePath, readme, 'utf8');

const manifestPath = path.join(pack, 'manifest.csv');
let manifest = await fs.readFile(manifestPath, 'utf8');
manifest = manifest
  .replace('"desktop frame"', '"logo-gray desktop frame without CRM label"')
  .replace('"compact desktop frame"', '"compact logo-gray desktop frame without CRM label"')
  .replace('"desktop left, text right"', '"logo-gray desktop left, text right, without CRM label"')
  .replace('"combined scene"', '"combined gray desktop and phone scene without CRM label"');
await fs.writeFile(manifestPath, manifest, 'utf8');

const oldQa = JSON.parse(await fs.readFile(path.join(pack, 'qa_report.json'), 'utf8'));
const alphaChecks = [
  { label: 'desktop fullHD', file: '02_desktop_frames/desktop_browser_fullhd_overlay.png', x: 960, y: 600 },
  { label: 'combined desktop', file: '04_combined_scenes/scene_desktop_plus_phone_overlay.png', x: 600, y: 600 },
  { label: 'combined phone', file: '04_combined_scenes/scene_desktop_plus_phone_overlay.png', x: 1600, y: 500 },
  { label: 'search frame corner', file: '10_search_bar_animation/png_sequence_1920x1080/search_bar_048.png', x: 4, y: 4 },
];
for (const check of alphaChecks) {
  check.alpha = await alphaAt(path.join(pack, check.file), check.x, check.y);
  check.pass = check.alpha === 0;
}
const frameSample = await rgbaAt(desktopFull, 140, 100);
const svgAudits = [];
for (const svgPath of targets) {
  const svg = await fs.readFile(svgPath, 'utf8');
  svgAudits.push({
    file: path.relative(pack, svgPath).replaceAll('\\', '/'),
    grayBody: svg.includes(`fill="${gray}" mask="url(#windowBody)"`),
    crmLabelRemoved: !svg.includes('CRM Передача'),
    desktopOutline: svg.includes('data-logo-gray-desktop-outline="true"'),
  });
}
const qa = {
  ...oldQa,
  updatedAt: new Date().toISOString(),
  desktopFrameColor: gray,
  desktopAddressBarColor: addressFill,
  desktopLabelRemoved: true,
  previousBackgroundPreserved: true,
  changedPhoneSvgCount: oldQa.changedSvgCount ?? 6,
  changedDesktopSvgCount: targets.length,
  changedSvgCount: (oldQa.changedSvgCount ?? 6) + targets.length,
  desktopFrameSample: { x: 140, y: 100, rgba: frameSample, expected: [87, 93, 98, 255], pass: frameSample.join(',') === '87,93,98,255' },
  alphaChecks,
  desktopSvgAudits: svgAudits,
};
qa.pass = qa.desktopFrameSample.pass && alphaChecks.every((x) => x.pass) && svgAudits.every((x) => x.grayBody && x.crmLabelRemoved && x.desktopOutline);
await fs.writeFile(path.join(pack, 'qa_report.json'), JSON.stringify(qa, null, 2) + '\n', 'utf8');

console.log(JSON.stringify({ targets: targets.length, qa }, null, 2));
