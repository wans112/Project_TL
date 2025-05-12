import xml.etree.ElementTree as ET
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM, T5Tokenizer
import torch
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm  # Untuk progress bar (opsional)

# Muat tokenizer dan model
model_name = "acul3/mt5-translate-en-id"
tokenizer = T5Tokenizer.from_pretrained(model_name, use_fast=False, legacy=False)
model = AutoModelForSeq2SeqLM.from_pretrained(model_name)

def translate_on_device(batch_texts, device):
    input_texts = [f"translate English to Indonesian: {text}" for text in batch_texts]
    inputs = tokenizer(input_texts, return_tensors="pt", padding=True, truncation=True, max_length=500).to(device)
    with torch.no_grad():
        outputs = model.generate(**inputs, max_length=500, num_beams=4, early_stopping=True)
    return tokenizer.batch_decode(outputs, skip_special_tokens=True)

def translate_batch(texts, batch_size=5):
    translations = []

    devices = []
    if torch.cuda.is_available():
        devices.append(torch.device("cuda"))
    devices.append(torch.device("cpu"))  # Gunakan CPU juga

    model.to(torch.device("cpu"))  # Pastikan model ada di CPU dulu (default)
    model.eval()

    def worker(batch_texts, device):
        model_local = AutoModelForSeq2SeqLM.from_pretrained(model_name).to(device)
        model_local.eval()
        return translate_on_device(batch_texts, device)

    with ThreadPoolExecutor(max_workers=len(devices)) as executor:
        futures = []
        for i in tqdm(range(0, len(texts), batch_size * len(devices)), desc="Translating"):
            chunk = texts[i:i + batch_size * len(devices)]
            for j, device in enumerate(devices):
                sub_batch = chunk[j * batch_size:(j + 1) * batch_size]
                if sub_batch:
                    futures.append(executor.submit(worker, sub_batch, device))
        for future in futures:
            translations.extend(future.result())

    return translations

# Baca file XML
tree = ET.parse("english_sample.xml")
root = tree.getroot()

# Ambil semua teks
contents = root.findall(".//content")
english_texts = [content.text or "" for content in contents]

# Terjemahkan
translated_texts = translate_batch(english_texts, batch_size=8)

# Tampilkan hasil
for original, translated in zip(english_texts, translated_texts):
    print("EN :", original)
    print("ID :", translated)
    print("-" * 40)
