import { cp, mkdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const vendor = path.join(root, 'frontend', 'assets', 'vendor');

async function copy(source, target) {
  const destination = path.join(vendor, target);
  await mkdir(path.dirname(destination), { recursive: true });
  await cp(path.join(root, 'node_modules', source), destination, { recursive: true });
}

await Promise.all([
  copy('chart.js/dist/chart.umd.js', 'chart.js'),
  copy('jszip/dist/jszip.min.js', 'jszip.min.js'),
  copy('pdfjs-dist/build/pdf.min.js', 'pdf.min.js'),
  copy('pdfjs-dist/build/pdf.worker.min.js', 'pdf.worker.min.js'),
  copy('xlsx/dist/xlsx.full.min.js', 'xlsx.full.min.js'),
  copy('@fortawesome/fontawesome-free/css/all.min.css', 'fontawesome/css/all.min.css'),
  copy('@fortawesome/fontawesome-free/webfonts/fa-brands-400.woff2', 'fontawesome/webfonts/fa-brands-400.woff2'),
  copy('@fortawesome/fontawesome-free/webfonts/fa-regular-400.woff2', 'fontawesome/webfonts/fa-regular-400.woff2'),
  copy('@fortawesome/fontawesome-free/webfonts/fa-solid-900.woff2', 'fontawesome/webfonts/fa-solid-900.woff2'),
  copy(
    '@fortawesome/fontawesome-free/webfonts/fa-v4compatibility.woff2',
    'fontawesome/webfonts/fa-v4compatibility.woff2'
  )
]);

console.log(`Vendored frontend assets in ${vendor}`);
