const {remark} = require('remark');
const remarkHtml = require('remark-html').default;
const remarkGfm = require('remark-gfm').default;

let data = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => data += chunk);
process.stdin.on('end', async () => {
  try {
    const file = await remark()
      .use(remarkGfm)
      .use(remarkHtml, { allowDangerousHtml: true })
      .process(data);
    process.stdout.write(String(file));
  } catch (err) {
    console.error(err);
    process.exit(1);
  }
});