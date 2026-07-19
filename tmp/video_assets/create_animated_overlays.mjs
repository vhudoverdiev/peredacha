import fs from 'node:fs/promises';
import path from 'node:path';
import sharp from 'file:///C:/Users/18EE~1/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/.pnpm/sharp@0.34.5/node_modules/sharp/lib/index.js';

const pack = String.raw`C:\Users\Владимир\Desktop\Презентация CRM\Раб.файлы для видео\CRM_Peredacha_montage_pack`;
const sourceDir = path.join(pack, '05_titles_and_overlays');
const animationDir = path.join(pack, '11_animated_overlays');
const previewsDir = path.join(pack, '09_previews');
const tempPreviewDir = path.join(animationDir, '._preview_tmp');
const progressPath = path.join(animationDir, 'generation_progress.json');
const fps = 24;
const introFrames = 24;
const loopFrames = 48;
const openerFrames = 96;
const width = 1920;
const height = 1080;
const cornerLogoSvg = await fs.readFile(path.join(sourceDir, 'corner_logo_overlay.svg'), 'utf8');
const logoDataMatch = cornerLogoSvg.match(/href="(data:image\/png;base64,[^"]+)"/);
if (!logoDataMatch) throw new Error('Исходный фирменный логотип не найден');
const originalLogoDataUri = logoDataMatch[1];

const colors = {
  ink: '#121B2B',
  gray: '#575D62',
  gray2: '#777E83',
  green: '#7EE600',
  greenDark: '#348F0E',
  pale: '#EAF4DF',
  pale2: '#DDEBCF',
  white: '#FCFDF9',
};

const clamp = (x, min = 0, max = 1) => Math.max(min, Math.min(max, x));
const easeOutCubic = (x) => 1 - Math.pow(1 - clamp(x), 3);
const easeOutBack = (x) => {
  const t = clamp(x);
  const c1 = 1.70158;
  const c3 = c1 + 1;
  return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
};
const enter = (time, start, duration) => easeOutCubic((time - start) / duration);
const fmt = (n) => Number(n).toFixed(2);
const frameName = (prefix, i) => `${prefix}_${String(i + 1).padStart(3, '0')}.png`;

async function ensureDir(dir) {
  await fs.mkdir(dir, { recursive: true });
}

async function setProgress(stage, completed, total) {
  await ensureDir(animationDir);
  await fs.writeFile(progressPath, JSON.stringify({ stage, completed, total, updatedAt: new Date().toISOString() }, null, 2) + '\n');
}

function openerSvg(time = 3.2) {
  const logo = enter(time, 0.05, 0.55);
  const brand = enter(time, 0.25, 0.55);
  const title1 = enter(time, 0.42, 0.7);
  const title2 = enter(time, 0.68, 0.7);
  const title3 = enter(time, 0.84, 0.7);
  const sub = enter(time, 1.0, 0.7);
  const url = enter(time, 1.25, 0.55);
  const card = enter(time, 0.38, 0.85);
  const step1 = enter(time, 1.18, 0.48);
  const step2 = enter(time, 1.52, 0.48);
  const step3 = enter(time, 1.86, 0.48);
  const cardX = 18 * (1 - card);
  const bgPhase = time * 0.42;
  const dash = 660 * (1 - enter(time, 0.9, 1.7));
  const pulse = 1 + 0.035 * Math.sin(time * Math.PI * 2 / 2.2);
  const sparkle = (time * 180) % 360;
  const floatY = 5 * Math.sin(bgPhase * Math.PI * 2);
  const pillW = 410 * sub;

  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080">
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#FCFDF9"/><stop offset="1" stop-color="#F4F8EF"/></linearGradient>
  <linearGradient id="lime" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#95F000"/><stop offset="1" stop-color="#64D500"/></linearGradient>
  <linearGradient id="chip" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#FFFFFF"/><stop offset="1" stop-color="#F3F7EF"/></linearGradient>
  <filter id="shadow" x="-30%" y="-30%" width="160%" height="180%"><feDropShadow dx="0" dy="22" stdDeviation="28" flood-color="#121B2B" flood-opacity="0.12"/></filter>
  <filter id="smallShadow" x="-30%" y="-30%" width="160%" height="180%"><feDropShadow dx="0" dy="8" stdDeviation="12" flood-color="#121B2B" flood-opacity="0.10"/></filter>
  <filter id="glow" x="-80%" y="-80%" width="260%" height="260%"><feGaussianBlur stdDeviation="10"/></filter>
  <clipPath id="titleReveal"><rect x="86" y="250" width="1010" height="340" rx="20"/></clipPath>
  <clipPath id="openerLogoClip"><rect x="90" y="70" width="110" height="110" rx="31"/></clipPath>
</defs>
<rect width="1920" height="1080" fill="url(#bg)"/>
<circle cx="70" cy="70" r="215" fill="#EAF4DF" opacity="0.74" transform="translate(${fmt(8 * Math.sin(bgPhase))} ${fmt(floatY)})"/>
<circle cx="1845" cy="1020" r="340" fill="#EAF4DF" opacity="0.72" transform="translate(${fmt(-10 * Math.sin(bgPhase))} ${fmt(-floatY)})"/>
<path d="M-80 835 C360 690 560 1090 1070 900 S1570 500 2010 610" fill="none" stroke="#7EE600" stroke-opacity="0.32" stroke-width="3" stroke-dasharray="10 20" stroke-dashoffset="${fmt(-time * 38)}"/>
<path d="M-40 886 C380 724 585 1118 1092 938 S1590 540 1990 650" fill="none" stroke="#D3E7BD" stroke-width="36" stroke-linecap="round" opacity="0.48"/>

<g opacity="${fmt(logo)}" transform="translate(${fmt(20 * (1 - logo))} 0)">
  <circle cx="145" cy="125" r="74.8" fill="none" stroke="#D8ECC1" stroke-width="3"/>
  <circle cx="212" cy="87" r="7" fill="#86E210"/>
  <rect x="93" y="75" width="110" height="110" rx="31" fill="#DCEBCF"/>
  <image href="${originalLogoDataUri}" x="90" y="70" width="110" height="110" clip-path="url(#openerLogoClip)"/>
  <rect x="90" y="70" width="110" height="110" rx="31" fill="none" stroke="#75C914" stroke-width="2"/>
</g>
<g opacity="${fmt(brand)}" transform="translate(${fmt(240 + 26 * (1 - brand))} 96)">
  <text x="0" y="27" font-family="Montserrat, Arial" font-size="18" font-weight="800" letter-spacing="2.6" fill="#348F0E">CRM «ПЕРЕДАЧА»</text>
  <text x="0" y="57" font-family="Montserrat, Arial" font-size="18" font-weight="600" fill="#777E83">Единая среда передачи объектов</text>
</g>

<g clip-path="url(#titleReveal)">
  <text x="92" y="335" font-family="Bounded, Montserrat, Arial" font-size="76" font-weight="800" fill="#121B2B" opacity="${fmt(title1)}" transform="translate(0 ${fmt(32 * (1 - title1))})">Весь процесс</text>
  <text x="92" y="425" font-family="Bounded, Montserrat, Arial" font-size="76" font-weight="800" fill="#121B2B" opacity="${fmt(title2)}" transform="translate(0 ${fmt(32 * (1 - title2))})">передачи —</text>
  <text x="92" y="515" font-family="Bounded, Montserrat, Arial" font-size="76" font-weight="800" fill="#121B2B" opacity="${fmt(title3)}" transform="translate(0 ${fmt(32 * (1 - title3))})">в одной системе</text>
</g>
<g opacity="${fmt(sub)}" transform="translate(92 ${fmt(575 + 20 * (1 - sub))})">
  <rect width="${fmt(Math.max(18, pillW))}" height="58" rx="29" fill="url(#lime)"/>
  <text x="30" y="38" font-family="Montserrat, Arial" font-size="23" font-weight="800" fill="#121B2B">ОТ АКТА ДО ГОТОВОГО АВР</text>
</g>
<g opacity="${fmt(sub)}" transform="translate(92 ${fmt(675 + 18 * (1 - sub))})">
  <text font-family="Montserrat, Arial" font-size="26" font-weight="600" fill="#687585">Квартиры · замечания · задачи · подрядчики</text>
  <text y="44" font-family="Montserrat, Arial" font-size="26" font-weight="600" fill="#687585">Материалы · документы · отчёты</text>
</g>
<g opacity="${fmt(url)}" transform="translate(${fmt(92 + 18 * (1 - url))} 920)">
  <circle cx="11" cy="11" r="11" fill="#7EE600"/><circle cx="11" cy="11" r="5" fill="#FFFFFF"/>
  <text x="34" y="20" font-family="Montserrat, Arial" font-size="26" font-weight="800" fill="#348F0E">akvilon-peredacha.ru</text>
</g>

<g opacity="${fmt(card)}" transform="translate(${fmt(1160 + cardX)} ${fmt(170 + 8 * (1 - card) + floatY * 0.35)})" filter="url(#shadow)">
  <rect width="650" height="730" rx="50" fill="#FFFFFF" stroke="#DDE6D6" stroke-width="2"/>
  <rect x="32" y="28" width="586" height="88" rx="28" fill="#F1F6EC"/>
  <rect x="56" y="50" width="44" height="44" rx="14" fill="#7EE600"/>
  <path d="M70 72 l9 9 18 -21" fill="none" stroke="#121B2B" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
  <text x="120" y="67" font-family="Montserrat, Arial" font-size="16" font-weight="800" letter-spacing="1.8" fill="#348F0E">ПЕРЕДАЧА ОБЪЕКТА</text>
  <text x="120" y="94" font-family="Montserrat, Arial" font-size="22" font-weight="700" fill="#121B2B">Всё под контролем</text>
  <path d="M87 190 V520" fill="none" stroke="#7EE600" stroke-width="5" stroke-linecap="round" stroke-dasharray="660" stroke-dashoffset="${fmt(dash)}"/>

  <g opacity="${fmt(step1)}" transform="translate(${fmt(0 + 22 * (1 - step1))} 0)">
    <circle cx="87" cy="200" r="29" fill="#7EE600"/><text x="87" y="208" text-anchor="middle" font-family="Montserrat, Arial" font-size="20" font-weight="900" fill="#121B2B">01</text>
    <text x="142" y="194" font-family="Bounded, Montserrat, Arial" font-size="25" font-weight="800" fill="#121B2B">Акт распознан</text>
    <text x="142" y="225" font-family="Montserrat, Arial" font-size="18" font-weight="600" fill="#777E83">Данные появляются в системе автоматически</text>
  </g>
  <g opacity="${fmt(step2)}" transform="translate(${fmt(0 + 22 * (1 - step2))} 0)">
    <circle cx="87" cy="350" r="29" fill="#EAF4DF" stroke="#7EE600" stroke-width="3"/><text x="87" y="358" text-anchor="middle" font-family="Montserrat, Arial" font-size="20" font-weight="900" fill="#348F0E">02</text>
    <text x="142" y="344" font-family="Bounded, Montserrat, Arial" font-size="25" font-weight="800" fill="#121B2B">Задачи распределены</text>
    <text x="142" y="375" font-family="Montserrat, Arial" font-size="18" font-weight="600" fill="#777E83">Видно исполнителя, срок и статус</text>
  </g>
  <g opacity="${fmt(step3)}" transform="translate(${fmt(0 + 22 * (1 - step3))} 0)">
    <circle cx="87" cy="500" r="29" fill="#575D62"/><text x="87" y="508" text-anchor="middle" font-family="Montserrat, Arial" font-size="20" font-weight="900" fill="#FFFFFF">03</text>
    <text x="142" y="494" font-family="Bounded, Montserrat, Arial" font-size="25" font-weight="800" fill="#121B2B">АВР сформирован</text>
    <text x="142" y="525" font-family="Montserrat, Arial" font-size="18" font-weight="600" fill="#777E83">Готовый документ — за 1 секунду</text>
  </g>
  <g opacity="${fmt(step3)}" transform="translate(40 596)">
    <rect width="170" height="60" rx="22" fill="url(#chip)" stroke="#E0E7DA"/><text x="85" y="38" text-anchor="middle" font-family="Montserrat, Arial" font-size="17" font-weight="800" fill="#575D62">ПОДРЯДЧИКИ</text>
    <rect x="188" width="170" height="60" rx="22" fill="url(#chip)" stroke="#E0E7DA"/><text x="273" y="38" text-anchor="middle" font-family="Montserrat, Arial" font-size="17" font-weight="800" fill="#575D62">МАТЕРИАЛЫ</text>
    <rect x="376" width="170" height="60" rx="22" fill="#575D62"/><text x="461" y="38" text-anchor="middle" font-family="Montserrat, Arial" font-size="17" font-weight="800" fill="#FFFFFF">ОТЧЁТЫ</text>
  </g>
  <circle cx="87" cy="500" r="42" fill="none" stroke="#7EE600" stroke-width="3" opacity="0.24" transform="translate(${fmt(87 * (1 - pulse))} ${fmt(500 * (1 - pulse))}) scale(${fmt(pulse)})"/>
</g>
</svg>`;
}

async function renderSvgToPng(svg, out, outWidth = width, outHeight = height) {
  await sharp(Buffer.from(svg)).resize(outWidth, outHeight).png().toFile(out);
}

async function animatedWebp(files, out, { previewWidth = 960, previewHeight = 540, loop = 0 } = {}) {
  const delay = files.map(() => Math.round(1000 / fps));
  await sharp(files, { join: { animated: true } })
    .resize(previewWidth, previewHeight)
    .webp({ quality: 82, alphaQuality: 100, effort: 4, loop, delay })
    .toFile(out);
}

async function makeOpener() {
  const outDir = path.join(animationDir, 'opener', 'png_24fps');
  const previewTemp = path.join(tempPreviewDir, 'opener');
  await ensureDir(outDir);
  await ensureDir(previewTemp);
  const previewFiles = [];
  for (let i = 0; i < openerFrames; i++) {
    const time = i / fps;
    const svg = openerSvg(time);
    const out = path.join(outDir, frameName('opener', i));
    const preview = path.join(previewTemp, frameName('p', i));
    await renderSvgToPng(svg, out);
    await renderSvgToPng(svg, preview, 960, 540);
    previewFiles.push(preview);
  }
  const finalSvg = openerSvg(3.2);
  await fs.writeFile(path.join(sourceDir, 'opener_title_card.svg'), finalSvg, 'utf8');
  await renderSvgToPng(finalSvg, path.join(sourceDir, 'opener_title_card.png'));
  await fs.writeFile(path.join(animationDir, 'opener', 'opener_redesigned_master.svg'), finalSvg, 'utf8');
  await renderSvgToPng(finalSvg, path.join(animationDir, 'opener', 'opener_redesigned_static.png'));
  await animatedWebp(previewFiles, path.join(animationDir, 'opener', 'opener_preview_4s.webp'), { loop: 0 });
  await fs.copyFile(path.join(sourceDir, 'opener_title_card.png'), path.join(previewsDir, 'preview_opener_redesigned.png'));
}

const overlayConfigs = [
  ...Array.from({ length: 8 }, (_, i) => ({
    id: `feature_${String(i + 1).padStart(2, '0')}`,
    source: `feature_${String(i + 1).padStart(2, '0')}_lowerthird.png`,
    crop: { left: 44, top: 822, width: 1600, height: 216 },
    target: { left: 44, top: 822 },
    center: { x: 121, y: 108 },
    orbit: 61,
    introX: -330,
  })),
  {
    id: 'developer',
    source: 'lowerthird_developer.png',
    crop: { left: 44, top: 810, width: 1000, height: 228 },
    target: { left: 44, top: 810 },
    center: { x: 118, y: 115 },
    orbit: 76,
    introX: -280,
  },
  {
    id: 'corner_logo',
    source: 'corner_logo_overlay.png',
    crop: { left: 36, top: 24, width: 430, height: 138 },
    target: { left: 36, top: 24 },
    center: { x: 68, y: 66 },
    orbit: 66,
    introX: -120,
  },
];

async function croppedAsset(config) {
  return sharp(path.join(sourceDir, config.source)).extract(config.crop).png().toBuffer();
}

function motionSvg(cx, cy, config, phase, opacity = 1) {
  const angle = phase * Math.PI * 2;
  const pulse = Math.sin(angle);
  const radius = config.orbit + 4 * pulse;
  const dotX = cx + radius * Math.cos(angle);
  const dotY = cy + radius * Math.sin(angle);
  const ringOpacity = 0.19 + 0.1 * (pulse + 1) / 2;
  const sparkleScale = 0.8 + 0.3 * (Math.sin(angle * 2) + 1) / 2;
  const sparkleX = cx + config.orbit * 0.72;
  const sparkleY = cy - config.orbit * 0.72;
  return Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080">
  <defs><filter id="g" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="12"/></filter></defs>
  <circle cx="${fmt(cx)}" cy="${fmt(cy)}" r="${fmt(config.orbit + 16)}" fill="#7EE600" opacity="${fmt(0.08 * opacity)}" filter="url(#g)"/>
  <circle cx="${fmt(cx)}" cy="${fmt(cy)}" r="${fmt(radius)}" fill="none" stroke="#7EE600" stroke-width="3" opacity="${fmt(ringOpacity * opacity)}"/>
  <circle cx="${fmt(dotX)}" cy="${fmt(dotY)}" r="5" fill="#7EE600" opacity="${fmt(opacity)}"/>
  <g transform="translate(${fmt(sparkleX)} ${fmt(sparkleY)}) scale(${fmt(sparkleScale)})" opacity="${fmt(0.72 * opacity)}"><path d="M0 -8 L3 -3 L8 0 L3 3 L0 8 L-3 3 L-8 0 L-3 -3 Z" fill="#FFFFFF" stroke="#7EE600" stroke-width="1"/></g>
  </svg>`);
}

async function transformAsset(asset, scale, opacity) {
  const meta = await sharp(asset).metadata();
  const w = Math.max(1, Math.round(meta.width * scale));
  const h = Math.max(1, Math.round(meta.height * scale));
  return {
    buffer: await sharp(asset)
      .resize(w, h)
      .ensureAlpha()
      .linear([1, 1, 1, opacity], [0, 0, 0, 0])
      .png()
      .toBuffer(),
    width: w,
    height: h,
  };
}

async function renderOverlayFrame(asset, config, mode, i, out) {
  let progress;
  let phase;
  let scale;
  let opacity;
  let left;
  let top;
  if (mode === 'intro') {
    progress = i / (introFrames - 1);
    const move = easeOutBack(progress);
    phase = 0;
    scale = 0.96 + 0.04 * move;
    opacity = easeOutCubic(progress / 0.68);
    left = config.target.left + config.introX * (1 - move);
    top = config.target.top + 18 * (1 - easeOutCubic(progress));
  } else {
    phase = i / loopFrames;
    const wave = Math.sin(phase * Math.PI * 2);
    scale = 1 + 0.0025 * wave;
    opacity = 1;
    left = config.target.left;
    top = config.target.top + 2.2 * wave;
  }

  const transformed = await transformAsset(asset, scale, opacity);
  const cx = left + config.center.x * scale;
  const cy = top + config.center.y * scale;
  const base = sharp({ create: { width, height, channels: 4, background: { r: 0, g: 0, b: 0, alpha: 0 } } });
  await base
    .composite([
      { input: motionSvg(cx, cy, config, phase, opacity), left: 0, top: 0 },
      { input: transformed.buffer, left: Math.round(left), top: Math.round(top) },
    ])
    .png()
    .toFile(out);
}

async function makeOverlay(config, index, total) {
  const asset = await croppedAsset(config);
  const root = path.join(animationDir, config.id);
  const introDir = path.join(root, 'intro_png_24fps');
  const loopDir = path.join(root, 'loop_png_24fps');
  const previewTemp = path.join(tempPreviewDir, config.id);
  await ensureDir(introDir);
  await ensureDir(loopDir);
  await ensureDir(previewTemp);
  const previewFiles = [];

  for (let i = 0; i < introFrames; i++) {
    const out = path.join(introDir, frameName('intro', i));
    await renderOverlayFrame(asset, config, 'intro', i, out);
    const preview = path.join(previewTemp, frameName('intro', i));
    await sharp(out).resize(960, 540).png().toFile(preview);
    previewFiles.push(preview);
  }
  for (let i = 0; i < loopFrames; i++) {
    const out = path.join(loopDir, frameName('loop', i));
    await renderOverlayFrame(asset, config, 'loop', i, out);
    const preview = path.join(previewTemp, frameName('loop', i));
    await sharp(out).resize(960, 540).png().toFile(preview);
    previewFiles.push(preview);
  }
  await animatedWebp(previewFiles, path.join(root, `${config.id}_preview.webp`), { loop: 0 });
  await setProgress(`Готово: ${config.id}`, index, total);
}

async function alphaAt(file, x, y) {
  const { data, info } = await sharp(file).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  return data[(y * info.width + x) * info.channels + 3];
}

await fs.rm(animationDir, { recursive: true, force: true });
await ensureDir(animationDir);
await ensureDir(tempPreviewDir);
await setProgress('Перерисовка заставки', 0, overlayConfigs.length + 1);
await makeOpener();
await setProgress('Заставка готова', 1, overlayConfigs.length + 1);

for (let i = 0; i < overlayConfigs.length; i++) {
  await makeOverlay(overlayConfigs[i], i + 2, overlayConfigs.length + 1);
}

const animationReadme = `CRM «Передача» — анимированные титры и оверлеи
====================================================

ФОРМАТ
- 1920x1080, 24 fps.
- Заставка opener: 96 PNG-кадров, 4 секунды, полный кадр.
- Каждый feature_01–08, developer и corner_logo: INTRO 24 кадра с появлением + LOOP 48 кадров с бесшовной непрерывной анимацией.
- У оверлеев сохранён прозрачный фон. Размещайте их на верхней видеодорожке.
- Файлы preview.webp нужны только для быстрого просмотра.

КАК ИМПОРТИРОВАТЬ
1. Импортируйте первый PNG нужной папки как image sequence.
2. Установите частоту 24 fps.
3. Сначала поставьте intro_png_24fps один раз.
4. Затем повторяйте loop_png_24fps нужное количество раз — начало и конец цикла совпадают.

ЧТО АНИМИРОВАНО
- Появление: мягкий выезд, проявление и лёгкий акцент масштаба.
- Непрерывный цикл: спокойное микродвижение, световое кольцо, орбитальная точка и блик.
- Новая заставка: поэтапное появление логотипа, заголовка и процесса «Акт → Задачи → АВР», затем живой фон.
`;
await fs.writeFile(path.join(animationDir, '00_README_RU.txt'), animationReadme, 'utf8');

const rootReadmePath = path.join(pack, '00_README_RU.txt');
let rootReadme = await fs.readFile(rootReadmePath, 'utf8');
rootReadme = rootReadme.replace(/\n\nАНИМИРОВАННЫЕ ТИТРЫ И ОВЕРЛЕИ[\s\S]*?(?=\n\n[A-ZА-ЯЁ][A-ZА-ЯЁ ]+|$)/, '');
rootReadme = rootReadme.trimEnd() + `\n\n\nАНИМИРОВАННЫЕ ТИТРЫ И ОВЕРЛЕИ\n- Папка 11_animated_overlays содержит новую 4-секундную заставку и анимации feature_01–08, developer, corner_logo.\n- Все оверлеи: 24 кадра появления + 48 кадров бесшовного цикла, 24 fps, прозрачный фон.\n- Подробная инструкция по импорту находится внутри папки.\n`;
await fs.writeFile(rootReadmePath, rootReadme, 'utf8');

const manifestPath = path.join(pack, 'manifest.csv');
let manifest = await fs.readFile(manifestPath, 'utf8');
manifest = manifest.replace(/\r?\n"opener_animation\/png_24fps[\s\S]*$/m, '');
manifest = manifest.trimEnd() + `\n"opener_animation/png_24fps","1920x1080","no","redesigned 4-second animated opener, 24 fps","full frame"\n"feature_01-08/intro_png_24fps","1920x1080","yes","animated lower-third entrances, 24 fps","overlay"\n"feature_01-08/loop_png_24fps","1920x1080","yes","seamless animated lower-third loops, 24 fps","overlay"\n"developer/intro+loop_png_24fps","1920x1080","yes","animated developer lower third","overlay"\n"corner_logo/intro+loop_png_24fps","1920x1080","yes","animated corner logo","overlay"\n`;
await fs.writeFile(manifestPath, manifest, 'utf8');

const qaPath = path.join(pack, 'qa_report.json');
const qa = JSON.parse(await fs.readFile(qaPath, 'utf8'));
const sampleFeature = path.join(animationDir, 'feature_01', 'loop_png_24fps', 'loop_001.png');
const sampleDeveloper = path.join(animationDir, 'developer', 'loop_png_24fps', 'loop_001.png');
const sampleCorner = path.join(animationDir, 'corner_logo', 'loop_png_24fps', 'loop_001.png');
const animationAlphaChecks = [
  { file: '11_animated_overlays/feature_01/loop_png_24fps/loop_001.png', x: 10, y: 10, alpha: await alphaAt(sampleFeature, 10, 10) },
  { file: '11_animated_overlays/developer/loop_png_24fps/loop_001.png', x: 1800, y: 100, alpha: await alphaAt(sampleDeveloper, 1800, 100) },
  { file: '11_animated_overlays/corner_logo/loop_png_24fps/loop_001.png', x: 1800, y: 1000, alpha: await alphaAt(sampleCorner, 1800, 1000) },
];
for (const check of animationAlphaChecks) check.pass = check.alpha === 0;
qa.updatedAt = new Date().toISOString();
qa.animations = {
  fps,
  openerFrames,
  openerSeconds: openerFrames / fps,
  animatedFeatureCount: 8,
  introFrames,
  loopFrames,
  developerAnimated: true,
  cornerLogoAnimated: true,
  alphaChecks: animationAlphaChecks,
};
const sample = qa.desktopFrameSample?.rgba ?? [];
if (qa.desktopFrameSample) qa.desktopFrameSample.pass = sample.length === 4 && Math.abs(sample[0] - 87) <= 1 && Math.abs(sample[1] - 93) <= 1 && Math.abs(sample[2] - 98) <= 1 && sample[3] === 255;
qa.pass = (qa.desktopFrameSample?.pass ?? true) && (qa.alphaChecks ?? []).every((x) => x.pass) && (qa.desktopSvgAudits ?? []).every((x) => x.grayBody && x.crmLabelRemoved && x.desktopOutline) && animationAlphaChecks.every((x) => x.pass);
await fs.writeFile(qaPath, JSON.stringify(qa, null, 2) + '\n', 'utf8');

const staticPreviews = [
  path.join(sourceDir, 'opener_title_card.png'),
  path.join(animationDir, 'feature_01', 'loop_png_24fps', 'loop_013.png'),
  path.join(animationDir, 'developer', 'loop_png_24fps', 'loop_013.png'),
  path.join(animationDir, 'corner_logo', 'loop_png_24fps', 'loop_013.png'),
];
await sharp(staticPreviews, { join: { across: 2, shim: 8, background: '#EEF1F3' } })
  .resize(1920, 1080, { fit: 'inside' })
  .png()
  .toFile(path.join(previewsDir, 'preview_animated_assets_contact_sheet.png'));

await fs.rm(tempPreviewDir, { recursive: true, force: true });
await setProgress('Готово', overlayConfigs.length + 1, overlayConfigs.length + 1);
console.log(JSON.stringify({ animationDir, openerFrames, overlays: overlayConfigs.length, introFrames, loopFrames, qaPass: qa.pass }, null, 2));
