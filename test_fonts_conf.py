import os, tempfile
from pathlib import Path

cache_dir = Path(tempfile.gettempdir()) / 'fontconfig_cache'
cache_dir.mkdir(parents=True, exist_ok=True)

clean_fonts_conf = f'''<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
    <dir>C:\\Windows\\Fonts</dir>
    <cachedir>{cache_dir}</cachedir>
</fontconfig>
'''

conf_path = Path(tempfile.gettempdir()) / 'autodocs_clean_fonts.conf'
conf_path.write_text(clean_fonts_conf, encoding='utf-8')

os.add_dll_directory(r'C:\msys64\ucrt64\bin')
os.environ['FONTCONFIG_FILE'] = str(conf_path)
os.environ['FONTCONFIG_PATH'] = str(conf_path.parent)

from weasyprint import HTML
pdf = HTML(string='<h1>Documento con Fuentes de Windows Limpias</h1><p>Texto sin warnings ni errores.</p>').write_pdf()
print('PDF generated successfully! Size:', len(pdf))
