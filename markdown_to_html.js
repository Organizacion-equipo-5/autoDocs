const {remark} = require('remark');
const remarkHtml = require('remark-html').default;
const remarkGfm = require('remark-gfm').default;

// remark-html sanitiza la salida: por defecto solo deja pasar imágenes http/https, y los diagramas
// de AutoDocs viajan como imágenes incrustadas (data:image/...). Se permite el esquema `data`
// únicamente en el `src` de las imágenes; el resto del HTML sigue sanitizado.
let sanitizeSchema;
try {
  const {defaultSchema} = require('hast-util-sanitize');
  sanitizeSchema = {
    ...defaultSchema,
    protocols: {
      ...defaultSchema.protocols,
      src: [...((defaultSchema.protocols && defaultSchema.protocols.src) || []), 'data'],
    },
  };
} catch (err) {
  sanitizeSchema = undefined; // sin el esquema personalizado se mantiene el comportamiento anterior
}

let data = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => data += chunk);
process.stdin.on('end', async () => {
  try {
    const file = await remark()
      .use(remarkGfm)
      .use(remarkHtml, sanitizeSchema ? { sanitize: sanitizeSchema } : {})
      .process(data);
    process.stdout.write(String(file));
  } catch (err) {
    console.error(err);
    process.exit(1);
  }
});
