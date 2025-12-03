import threading
import time
import os
import pandas as pd
from backend.core.ai_service import AIService
from backend.core.glossary_processor import GlossaryProcessor
from backend.config_manager import load_config

class ReviewEngine:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(ReviewEngine, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized: return
        self._initialized = True
        self.is_running = False
        self.stop_event = threading.Event()
        self.progress = {"current": 0, "total": 0, "message": "Idle", "percent": 0}
        self.logs = []
        self.ai_service = AIService()
        self.processor = GlossaryProcessor(self.ai_service)
        self.config = load_config()

    def start_task(self, directory, novel_background):
        if self.is_running:
            return False, "Task is already running"
        
        self.is_running = True
        self.stop_event.clear()
        self.progress = {"current": 0, "total": 0, "message": "Starting...", "percent": 0}
        self.logs = []
        
        # Reload config to ensure latest API key and settings are used
        self.config = load_config()
        self.ai_service.reload_config()
        
        thread = threading.Thread(target=self._run_task, args=(directory, novel_background))
        thread.daemon = True
        thread.start()
        return True, "Task started"

    def stop_task(self):
        if not self.is_running:
            return False, "No task running"
        self.stop_event.set()
        self.is_running = False
        self.progress["message"] = "Stopping..."
        return True, "Task stopping"

    def _run_task(self, directory, novel_background):
        try:
            self.add_log("Task started.")
            glossary_path = None
            reference_path = None
            
            # Find files
            for f in os.listdir(directory):
                if f.endswith('.xlsx') and not f.startswith('~') and 'glossary_output' not in f and 'modified' not in f.lower():
                    glossary_path = os.path.join(directory, f)
                elif f.endswith('.txt'):
                    reference_path = os.path.join(directory, f)
            
            if not glossary_path or not reference_path:
                raise FileNotFoundError("Missing .xlsx or .txt files")

            glossary_df, reference_dict, original_cols = self.processor.load_data(glossary_path, reference_path)
            total_rows = len(glossary_df)
            self.progress["total"] = total_rows
            
            max_workers = self.config.get("MAX_WORKERS", 3)
            batch_size = self.config.get("BATCH_SIZE", 10)
            processed_count = 0
            results = []
            
            import json
            
            # Create batches
            batches = []
            for i in range(0, total_rows, batch_size):
                batches.append(glossary_df.iloc[i:i+batch_size])

            import concurrent.futures

            def process_single_batch(batch_idx, batch_data):
                if self.stop_event.is_set(): return None
                self.add_log(f"Starting batch {batch_idx + 1}...")
                return self.processor.process_batch(batch_data, novel_background, reference_dict, log_callback=self.add_log)

            final_rows = []
            modification_log = []

            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_batch = {executor.submit(process_single_batch, i, batch): i for i, batch in enumerate(batches)}
                
                # We need to process results in order to maintain original order in final output? 
                # Or we can just collect them and sort later if needed. 
                # Actually, appending to final_rows in completion order might scramble the file.
                # Better to collect all results first, then reconstruct? 
                # Or just process as completed and accept reordering? 
                # The user script uses as_completed but then appends to processed_rows. 
                # This effectively scrambles the order if batches finish out of order.
                # However, for a glossary, order might not be strictly critical, but preserving it is better.
                # Let's store results in a dict by batch_index and reconstruct later.
                
                batch_results_map = {}

                for future in concurrent.futures.as_completed(future_to_batch):
                    batch_idx = future_to_batch[future]
                    if self.stop_event.is_set():
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                    
                    try:
                        ai_results = future.result()
                        batch_results_map[batch_idx] = ai_results
                        
                        if ai_results:
                            for res in ai_results:
                                self.add_log(f"Processed: {res.get('korean_term')} -> {res.get('judgment_emoji')}")
                        
                        # Update progress safely
                        processed_count += batch_size 
                        if processed_count > total_rows: processed_count = total_rows
                        
                        self.progress["current"] = processed_count
                        self.progress["percent"] = int((processed_count / total_rows) * 100)
                        self.progress["message"] = f"Processing... ({processed_count}/{total_rows})"
                        
                    except Exception as exc:
                        self.add_log(f"Batch {batch_idx} generated an exception: {exc}")
            
            # Reconstruct in order
            for i in range(len(batches)):
                if i not in batch_results_map or not batch_results_map[i]:
                    # Handle failed or missing batch?
                    # For now, just append original rows as fallback
                    original_batch = batches[i]
                    for _, row in original_batch.iterrows():
                        final_rows.append(row.to_dict())
                    continue

                ai_results = batch_results_map[i]
                original_batch = batches[i]
                
                if len(ai_results) != len(original_batch):
                     self.add_log(f"Warning: Batch {i} result count mismatch. Using original.")
                     for _, row in original_batch.iterrows():
                        final_rows.append(row.to_dict())
                     continue

                for j, ai_result in enumerate(ai_results):
                    original_row = original_batch.iloc[j].to_dict()
                    # Create a copy for the final row
                    final_row = original_row.copy()
                    
                    # Log entry base
                    log_entry = {
                        'term': original_row.get('src', ''),
                        'original': original_row.get('dst', ''),
                        'new': '',
                        'action': '',
                        'reason': ai_result.get('deletion_reason', ''),
                        'justification': ai_result.get('justification', ''),
                        'emoji': ai_result.get('judgment_emoji', '')
                    }

                    if ai_result.get('should_delete'):
                        log_entry['action'] = 'Delete'
                        log_entry['new'] = '(Deleted)'
                        modification_log.append(log_entry)
                        # Do NOT add to final_rows
                    else:
                        recommended = ai_result.get('recommended_translation', '').strip()
                        current = original_row.get('dst', '').strip()
                        
                        if recommended and recommended != current:
                            log_entry['action'] = 'Modify'
                            log_entry['new'] = recommended
                            final_row['dst'] = recommended
                            modification_log.append(log_entry)
                        else:
                            log_entry['action'] = 'Keep'
                            log_entry['new'] = current
                            # Optional: don't log 'Keep' to reduce noise, or log it if you want full audit
                            # User script logs it. Let's log it but maybe frontend filters it?
                            # For now, let's include it but maybe mark it.
                        
                        final_rows.append(final_row)

            # Save Final Glossary
            output_path = os.path.join(directory, 'glossary_output.xlsx')
            df_final = pd.DataFrame(final_rows)
            
            # Use xlsxwriter to add autofilter
            try:
                with pd.ExcelWriter(output_path, engine='xlsxwriter') as writer:
                    df_final.to_excel(writer, index=False, sheet_name='Sheet1')
                    worksheet = writer.sheets['Sheet1']
                    (max_row, max_col) = df_final.shape
                    if max_row > 0:
                        worksheet.autofilter(0, 0, max_row, max_col - 1)
            except Exception as e:
                # Fallback if xlsxwriter fails
                self.add_log(f"Warning: Could not apply autofilter ({e}). Saving normally.")
                df_final.to_excel(output_path, index=False)
                
            self.add_log(f"Finished. Saved glossary to {output_path}")

            # Save Modification Log (Excel)
            log_path_xlsx = os.path.join(directory, 'modified.xlsx')
            pd.DataFrame(modification_log).to_excel(log_path_xlsx, index=False)
            self.add_log(f"Saved modification log to {log_path_xlsx}")

            # Save Modification Log (JSON) for Frontend
            log_path_json = os.path.join(directory, 'modified.json')
            with open(log_path_json, 'w', encoding='utf-8') as f:
                json.dump(modification_log, f, ensure_ascii=False, indent=2)
            self.add_log(f"Saved modification log JSON to {log_path_json}")

        except Exception as e:
            self.add_log(f"Error: {str(e)}")
        finally:
            self.is_running = False
            self.progress["message"] = "Completed" if not self.stop_event.is_set() else "Stopped"

    def add_log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        self.logs.append(f"[{timestamp}] {message}")
        if len(self.logs) > 100:
            self.logs.pop(0)

    def get_status(self):
        return {
            "running": self.is_running,
            "progress": self.progress,
            "logs": self.logs[-20:]
        }
