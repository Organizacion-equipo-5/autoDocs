import sys
import tempfile
from pathlib import Path
sys.path.insert(0, '.')
from services.exporter import DocumentExporter

sample_docs = {
    'full_markdown': '''# Test

<img src="https://www.planttext.com/plantuml/png/test" alt="Diag">

[🔗 Link](https://planttext.com)

<div style="page-break-inside: avoid; break-inside: avoid;">

#### Model1

> **Desc:** Sample model description

| Prop | Val |
| --- | --- |
| a | 1 |

</div>
'''
}

with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tf:
    tmp_path = tf.name

exp = DocumentExporter({'name': 'T'}, {'documentation': sample_docs})
out = exp._pdf_with_reportlab(tmp_path)
p = Path(out)
print('PDF Path:', out, 'Exists:', p.exists(), 'Size:', p.stat().st_size if p.exists() else 0)
if p.exists():
    p.unlink()
