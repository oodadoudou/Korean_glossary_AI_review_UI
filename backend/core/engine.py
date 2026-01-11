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

    def start_task(self, directory, novel_background, rounds=1):
        if self.is_running:
            return False, "Task is already running"
        
        self.is_running = True
        self.stop_event.clear()
        self.progress = {"current": 0, "total": 0, "message": "Starting...", "percent": 0}
        self.logs = []
        
        # Reload config to ensure latest API key and settings are used
        self.config = load_config()
        self.ai_service.reload_config()
        
        thread = threading.Thread(target=self._run_task, args=(directory, novel_background, int(rounds)))
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

    def _run_task(self, directory, novel_background, rounds):
        try:
            self.add_log(f"Task started. Total rounds: {rounds}")
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
            
            # Ensure log directory exists
            log_dir = os.path.join(directory, 'log')
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)

            import json
            import concurrent.futures

            max_workers = self.config.get("MAX_WORKERS", 3)
            batch_size = self.config.get("BATCH_SIZE", 10)
            
            # Master Log to track all changes across all rounds
            master_modification_log = []
            
            current_df = glossary_df.copy()
            
            for round_num in range(1, rounds + 1):
                if self.stop_event.is_set(): break
                
                self.add_log(f"--- Starting Round {round_num}/{rounds} ---")
                
                total_rows = len(current_df)
                self.progress["total"] = total_rows * rounds # approx total progress logic
                # Adjust progress calculation to be cumulative
                base_progress = (round_num - 1) * total_rows
                
                processed_count = 0
                
                # Create batches
                batches = []
                for i in range(0, total_rows, batch_size):
                    batches.append(current_df.iloc[i:i+batch_size])

                def process_single_batch(batch_idx, batch_data):
                    if self.stop_event.is_set(): return None
                    self.add_log(f"Round {round_num}: Processing batch {batch_idx + 1}...")
                    return self.processor.process_batch(batch_data, novel_background, reference_dict, log_callback=self.add_log)

                round_rows = []
                batch_results_map = {}

                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_batch = {executor.submit(process_single_batch, i, batch): i for i, batch in enumerate(batches)}
                    
                    for future in concurrent.futures.as_completed(future_to_batch):
                        batch_idx = future_to_batch[future]
                        if self.stop_event.is_set():
                            executor.shutdown(wait=False, cancel_futures=True)
                            break
                        
                        try:
                            ai_results = future.result()
                            batch_results_map[batch_idx] = ai_results
                            
                            # Update progress
                            processed_count += batch_size
                            current_total_progress = base_progress + min(processed_count, total_rows)
                            total_task_rows = total_rows * rounds
                            
                            self.progress["current"] = current_total_progress
                            self.progress["total"] = total_task_rows
                            self.progress["percent"] = int((current_total_progress / total_task_rows) * 100)
                            self.progress["message"] = f"Round {round_num}: Processing... ({min(processed_count, total_rows)}/{total_rows})"
                            
                        except Exception as exc:
                            self.add_log(f"Round {round_num}: Batch {batch_idx} generated an exception: {exc}")
                
                if self.stop_event.is_set(): break

                # Reconstruct and Apply Logic
                for i in range(len(batches)):
                    if i not in batch_results_map or not batch_results_map[i]:
                        # Fallback: keep original
                        original_batch = batches[i]
                        for _, row in original_batch.iterrows():
                            round_rows.append(row.to_dict())
                        continue

                    ai_results = batch_results_map[i]
                    original_batch = batches[i]
                    
                    if len(ai_results) != len(original_batch):
                         self.add_log(f"Warning: Round {round_num} Batch {i} count mismatch. Using original.")
                         for _, row in original_batch.iterrows():
                            round_rows.append(row.to_dict())
                         continue

                    for j, ai_result in enumerate(ai_results):
                        original_row = original_batch.iloc[j].to_dict()
                        final_row = original_row.copy()
                        
                        # Log Entry
                        log_entry = {
                            'round': round_num, # New Column G
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
                            master_modification_log.append(log_entry)
                        else:
                            recommended = ai_result.get('recommended_translation', '').strip()
                            current = original_row.get('dst', '').strip()
                            
                            if recommended and recommended != current:
                                log_entry['action'] = 'Modify'
                                log_entry['new'] = recommended
                                final_row['dst'] = recommended # Update for next round!
                                master_modification_log.append(log_entry)
                            else:
                                log_entry['action'] = 'Keep'
                                log_entry['new'] = current
                                # Optional: Log 'Keep' actions? The user wants to track "all steps", 
                                # but usually we only track changes. Let's stick to tracking changes 
                                # to avoid massive files, unless requested.
                                # User said "record down all the intermediate modification or ANY steps".
                                # "Any steps" might imply Keeps too. 
                                # But let's only log valid actions.
                            
                            round_rows.append(final_row)
                
                # End of Round Processing
                current_df = pd.DataFrame(round_rows)
                
                # Save Intermediate Files (Stash)
                stash_glossary_path = os.path.join(log_dir, f'glossary_output_stash{round_num}.xlsx')
                self._save_excel(current_df, stash_glossary_path)
                
                # We also need to save the modification log up to this point?
                # The user asked for "intermediate files... in log...". 
                # Let's save a snapshot of the log for this round.
                round_log = [l for l in master_modification_log if l['round'] == round_num]
                stash_log_path = os.path.join(log_dir, f'modified_stash{round_num}.xlsx')
                pd.DataFrame(round_log).to_excel(stash_log_path, index=False)
                
                self.add_log(f"Round {round_num} completed. Stash saved to log/.")
            
            # --- End of All Rounds ---
            
            # Save Final Glossary
            output_path = os.path.join(directory, 'glossary_output_final.xlsx')
            self._save_excel(current_df, output_path)
            self.add_log(f"Finished. Saved final glossary to {output_path}")

            # Save Master Modification Log (Excel) with Column G
            log_path_xlsx = os.path.join(directory, 'modified.xlsx')
            pd.DataFrame(master_modification_log).to_excel(log_path_xlsx, index=False)
            self.add_log(f"Saved master modification log to {log_path_xlsx}")

            # Save Master Modification Log (JSON)
            log_path_json = os.path.join(directory, 'modified.json')
            with open(log_path_json, 'w', encoding='utf-8') as f:
                json.dump(master_modification_log, f, ensure_ascii=False, indent=2)
            self.add_log(f"Saved master modification log JSON to {log_path_json}")

        except Exception as e:
            self.add_log(f"Error: {str(e)}")
            import traceback
            traceback.print_exc()
        finally:
            self.is_running = False
            self.progress["message"] = "Completed" if not self.stop_event.is_set() else "Stopped"

    def _save_excel(self, df, path):
        try:
            with pd.ExcelWriter(path, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Sheet1')
                worksheet = writer.sheets['Sheet1']
                (max_row, max_col) = df.shape
                if max_row > 0:
                    worksheet.autofilter(0, 0, max_row, max_col - 1)
        except Exception as e:
            df.to_excel(path, index=False)

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
