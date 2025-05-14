from googletrans import Translator
import xml.etree.ElementTree as ET
import re
import concurrent.futures
import asyncio
from datetime import datetime
import os
import time
from typing import List, Tuple
from queue import Queue
import threading

MAX_THREADS = 7  # Batasi jumlah thread menjadi 7

class TranslationProgress:
    def __init__(self, total_items):
        self.total_items = total_items
        self.progress = {i: 0 for i in range(MAX_THREADS)}  # Gunakan MAX_THREADS
        self.lock = threading.Lock()
        self.start_time = time.time()
        
    def update(self, thread_id: int, count: int):
        with self.lock:
            self.progress[thread_id] = count
            
    def get_progress(self) -> dict:
        with self.lock:
            total_processed = sum(self.progress.values())
            elapsed_time = time.time() - self.start_time
            
            if total_processed > 0:
                items_per_second = total_processed / elapsed_time
                estimated_remaining = (self.total_items - total_processed) / items_per_second if items_per_second > 0 else 0
            else:
                items_per_second = 0
                estimated_remaining = 0
                
            return {
                'total': self.total_items,
                'processed': total_processed,
                'percent': (total_processed / self.total_items) * 100,
                'thread_progress': dict(self.progress),
                'elapsed_time': elapsed_time,
                'items_per_second': items_per_second,
                'estimated_remaining': estimated_remaining
            }

class XMLTranslator:
    def __init__(self, input_file: str, output_file: str):
        self.input_file = input_file
        self.output_file = output_file
        self.timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        self.username = os.getlogin()
        self.progress = None
        self.error_queue = Queue()
        self.start_time = datetime.utcnow()

    def clean_html_tags(self, text: str) -> str:
        clean = re.compile('<.*?>')
        return re.sub(clean, '', text)

    def format_time(self, seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def print_progress(self):
        while True:
            progress_info = self.progress.get_progress()
            current_time = datetime.utcnow()
            
            os.system('cls' if os.name == 'nt' else 'clear')
            
            # Header dengan informasi detail
            print(f"Translation Progress Report")
            print(f"==========================")
            print(f"Start Time (UTC): {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Current Time (UTC): {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"User: {self.username}")
            print(f"Input File: {self.input_file}")
            print(f"Output File: {self.output_file}")
            print(f"Threads: {MAX_THREADS}")
            print("=" * 50)
            
            # Progress information
            print(f"\nOverall Progress: {progress_info['percent']:.2f}%")
            print(f"Items Processed: {progress_info['processed']}/{progress_info['total']}")
            print(f"Elapsed Time: {self.format_time(progress_info['elapsed_time'])}")
            print(f"Processing Speed: {progress_info['items_per_second']:.2f} items/second")
            print(f"Estimated Time Remaining: {self.format_time(progress_info['estimated_remaining'])}")
            
            # Thread progress dengan visual indicator
            print("\nThread Progress:")
            for thread_id, count in progress_info['thread_progress'].items():
                thread_percent = (count / (progress_info['total'] / MAX_THREADS)) * 100
                bar_length = 30
                filled_length = int(thread_percent / 100 * bar_length)
                bar = '█' * filled_length + '-' * (bar_length - filled_length)
                print(f"Thread {thread_id}: [{bar}] {count} items ({thread_percent:.2f}%)")
            
            # Error display
            print("\nRecent Errors:")
            while not self.error_queue.empty():
                print(self.error_queue.get())
            
            if progress_info['processed'] >= progress_info['total']:
                break
                
            time.sleep(1)

    async def translate_text(self, translator: Translator, text: str) -> str:
        try:
            translation = await translator.translate(text, src='en', dest='id')
            return translation.text
        except Exception as e:
            print(f"Translation error: {str(e)}")
            return text

    async def translate_chunk(self, thread_id: int, chunk: List[Tuple[str, str]]) -> List[Tuple[str, str, str]]:
        translator = Translator()
        results = []
        
        for i, (uid, text) in enumerate(chunk):
            try:
                cleaned_text = self.clean_html_tags(text)
                translated = await self.translate_text(translator, cleaned_text)
                results.append((uid, text, translated))
                
                self.progress.update(thread_id, i + 1)
                await asyncio.sleep(0.5)
                
            except Exception as e:
                error_msg = f"Error in thread {thread_id} translating {uid}: {str(e)}"
                self.error_queue.put(error_msg)
                results.append((uid, text, text))
        
        return results

    async def process_chunks(self, chunks: List[List[Tuple[str, str]]]):
        tasks = []
        for i, chunk in enumerate(chunks):
            task = asyncio.create_task(self.translate_chunk(i, chunk))
            tasks.append(task)
        return await asyncio.gather(*tasks)

    def translate_parallel(self):
        try:
            tree = ET.parse(self.input_file)
            root = tree.getroot()
            
            contents = [(content.get('contentuid'), content.text) 
                       for content in root.findall('content') if content.text]
            
            self.progress = TranslationProgress(len(contents))
            
            progress_thread = threading.Thread(target=self.print_progress)
            progress_thread.daemon = True
            progress_thread.start()
            
            # Split contents into MAX_THREADS chunks
            chunk_size = len(contents) // MAX_THREADS
            chunks = [contents[i:i + chunk_size] for i in range(0, len(contents), chunk_size)]
            
            # Ensure all remaining items are included
            if len(chunks) > MAX_THREADS:
                chunks[MAX_THREADS-1].extend([item for chunk in chunks[MAX_THREADS:] for item in chunk])
                chunks = chunks[:MAX_THREADS]
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            translated_chunks = loop.run_until_complete(self.process_chunks(chunks))
            
            translated_contents = []
            for chunk_result in translated_chunks:
                translated_contents.extend(chunk_result)
            
            translated_contents.sort(key=lambda x: contents.index((x[0], x[1])))
            
            self.save_xml(translated_contents)
            
            progress_thread.join(timeout=1)
            loop.close()
            
            print("\nTranslation completed!")
            
        except Exception as e:
            print(f"Error in parallel translation: {str(e)}")
        finally:
            try:
                loop.close()
            except:
                pass

    def save_xml(self, translated_contents: List[Tuple[str, str, str]]):
        xmlstr = '<?xml version="1.0" encoding="utf-8"?>\n'
        xmlstr += f'<!-- Translated from {self.input_file} - {self.timestamp} by {self.username} -->\n'
        xmlstr += '<contentList>\n'
        
        for uid, _, translated in translated_contents:
            xmlstr += f'\t<content contentuid="{uid}">{translated}</content>\n'

        xmlstr += '</contentList>'

        with open(self.output_file, 'w', encoding='utf-8') as f:
            f.write(xmlstr)

def main():
    translator = XMLTranslator('english-ori.xml', 'indonesia.xml')
    translator.translate_parallel()

if __name__ == "__main__":
    main()
