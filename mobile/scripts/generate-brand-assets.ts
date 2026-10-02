import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import sharp from 'sharp';
import { branding, ThemeMode } from '../src/config/branding';

const destination = path.resolve('assets/branding');
function svg(mode: ThemeMode, scale: number, background?: string, monochrome = false) {
  const colors = branding.themes[mode];
  const mark = branding.mark;
  const accent = monochrome ? '#FFFFFF' : colors.accent;
  const north = monochrome ? '#FFFFFF' : colors.north;
  const south = monochrome ? '#FFFFFF' : colors.south;
  const offset = (1024 - scale * 100) / 2;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">
    ${background ? `<rect width="1024" height="1024" fill="${background}"/>` : ''}
    <g transform="translate(${offset},${offset}) scale(${scale})">
      <path d="${mark.left}" stroke="${accent}" stroke-width="10" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
      <path d="${mark.right}" stroke="${accent}" stroke-width="10" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
      <polygon points="${mark.north}" fill="${north}"/><polygon points="${mark.south}" fill="${south}"/>
    </g></svg>`;
}
async function main() {
  await mkdir(destination, { recursive: true });
  const assets = {
    'icon-dark': svg('dark', 7.2, branding.themes.dark.background),
    'icon-light': svg('light', 7.2, branding.themes.light.background),
    'icon-tinted': svg('dark', 7.2, '#000000', true),
    'adaptive-foreground': svg('dark', 5.8),
    'adaptive-monochrome': svg('dark', 5.8, undefined, true),
    'splash-dark': svg('dark', 9),
    'splash-light': svg('light', 9),
  };
  for (const [name, source] of Object.entries(assets)) {
    await writeFile(path.join(destination, `${name}.svg`), source.split('\n').map(line => line.trimEnd()).join('\n') + '\n');
    await sharp(Buffer.from(source)).png().toFile(path.join(destination, `${name}.png`));
  }
  await sharp({ create: { width: 1024, height: 1024, channels: 4, background: { r: 0, g: 0, b: 0, alpha: 0 } } })
    .png().toFile(path.join(destination, 'splash-empty.png'));
}
void main();
