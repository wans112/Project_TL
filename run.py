import xml.etree.ElementTree as ET
from googletrans import Translator
from tqdm import tqdm
import re

# Fungsi untuk deteksi apakah harus dilewati
def should_skip_translation(text):
    return bool(
        re.search(r"\[[^\]]+\]", text) or       # Tag seperti [FANE]
        re.search(r"&[a-z]+;", text)            # Entity XML seperti &apos;, &lt;
    )

# Inisialisasi translator dan parsing XML
translator = Translator()
tree = ET.parse('english.xml')
root = tree.getroot()
contents = root.findall('content')

# Terjemahkan satu per satu dengan progres
for content in tqdm(contents, desc="Menerjemahkan"):
    original_text = content.text
    if original_text and original_text.strip():
        if should_skip_translation(original_text):
            continue  # Lewati jika ada tag atau entitas XML
        try:
            translated = translator.translate(original_text, src='en', dest='id')
            content.text = translated.text
        except Exception as e:
            print(f"Error:\n{original_text}\n{e}")
            # Biarkan isi tetap

# Simpan ke file baru
tree.write('translated_id.xml', encoding='utf-8', xml_declaration=True)
print("✅ Selesai! Hasil disimpan di 'translated_id.xml'")
