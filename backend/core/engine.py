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
            
            # --- Pre-flight API Key Validation ---
            self.add_log("Performing pre-flight API key validation...")
            valid_count = self.ai_service.validate_keys(log_callback=self.add_log)
            
            if valid_count == 0:
                self.add_log("CRITICAL ERROR: No valid API keys available. Aborting task.")
                self.progress["message"] = "Error: All API Keys Invalid"
                raise Exception("All API keys failed validation. Please check your settings.")
            
            self.add_log(f"Pre-flight check passed. {valid_count} keys active.")
            # -------------------------------------

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
            import re

            max_workers = self.config.get("MAX_WORKERS", 3)
            batch_size = self.config.get("BATCH_SIZE", 10)
            
            # Master Log to track all changes across all rounds
            master_modification_log = []
            self.term_history = {} 

            # --- Resume Logic ---
            start_round = 1
            latest_round = 0
            
            # Check for existing glossary outputs in log dir
            for f in os.listdir(log_dir):
                match = re.search(r'glossary_output_(\d+)\.xlsx', f)
                if match:
                    r_num = int(match.group(1))
                    if r_num > latest_round:
                        latest_round = r_num
            
            # Use resume data if available and we haven't exceeded requested rounds
            if latest_round > 0 and latest_round < rounds:
                try:
                    resume_file = os.path.join(log_dir, f'glossary_output_{latest_round}.xlsx')
                    self.add_log(f"Found interrupt recovery file: {resume_file}")
                    
                    # Load the latest state
                    current_df = pd.read_excel(resume_file, engine='openpyxl').fillna('')
                    start_round = latest_round + 1
                    
                    # Attempt to load term history
                    history_file = os.path.join(log_dir, 'term_history.json')
                    if os.path.exists(history_file):
                        with open(history_file, 'r', encoding='utf-8') as hf:
                            self.term_history = json.load(hf)
                        self.add_log(f"Loaded term history from {history_file}")
                    else:
                        self.add_log("Warning: No term history found. Consensus skipping may be limited for next round.")

                    # Reconstruct Master Modification Log from previous round logs
                    for r in range(1, start_round):
                        mod_file = os.path.join(log_dir, f'modified_{r}.xlsx')
                        if os.path.exists(mod_file):
                            try:
                                mod_df = pd.read_excel(mod_file, engine='openpyxl').fillna('')
                                master_modification_log.extend(mod_df.to_dict('records'))
                            except Exception as ex:
                                self.add_log(f"Failed to load log for Round {r}: {ex}")
                    
                    self.add_log(f"Resuming task from Round {start_round}...")
                    
                except Exception as e:
                    self.add_log(f"Failed to resume: {e}. Starting from scratch.")
                    # Fallback
                    glossary_df, reference_dict, original_cols = self.processor.load_data(glossary_path, reference_path)
                    current_df = glossary_df.copy()
                    start_round = 1
                    master_modification_log = []
                    self.term_history = {}
            else:
                # Start fresh
                current_df = glossary_df.copy()
            
            for round_num in range(start_round, rounds + 1):
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

                # Initialize term history for consistency checking across rounds
                # self.term_history is already initialized at start of task, no need to re-init here if we want global history
                # But wait, code at line 100 initialized it. 
                # The line 125 "self.term_history = {}" actually CLEARS history every round!
                # That is WRONG if we want multi-round history.
                # AND we are missing batch_results_map.
                
                round_rows = []
                batch_results_map = {}

                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    def process_single_batch(batch_idx, batch_data):
                        if self.stop_event.is_set(): return None
                        
                        # Optimization: Filter out terms that already reached consensus
                        rows_to_process = []
                        cached_results_map = {} # index in batch -> result
                        
                        for local_idx, (idx, row) in enumerate(batch_data.iterrows()):
                            term = str(row['src']).strip()
                            history = self.term_history.get(term, [])
                            
                            # Consensus Check Logic (Skip if Round >= 3 and previous 2 results are identical)
                            skipped = False
                            if round_num >= 3 and len(history) >= 2:
                                r1 = history[-1]
                                r2 = history[-2]
                                # Check consistency of key fields
                                if (r1.get('recommended_translation') == r2.get('recommended_translation') and
                                    r1.get('should_delete') == r2.get('should_delete')):
                                    
                                    # Use the latest result as the cached result
                                    cached_results_map[local_idx] = r1.copy()
                                    skipped = True
                            
                            if not skipped:
                                rows_to_process.append(row)
                        
                        self.add_log(f"Round {round_num}: Processing batch {batch_idx + 1} ({len(rows_to_process)}/{len(batch_data)} terms)...")
                        
                        # If all skipped, return reconstructed immediately
                        ai_results_partial = []
                        if rows_to_process:
                            import pandas as pd
                            partial_df = pd.DataFrame(rows_to_process)
                            try:
                                # Pass term_history to inject history context
                                ai_results_partial = self.processor.process_batch(
                                    partial_df, 
                                    novel_background, 
                                    reference_dict, 
                                    term_history=self.term_history, # Pass history map
                                    log_callback=self.add_log
                                )
                                if ai_results_partial is None:
                                    ai_results_partial = []
                            except Exception as e:
                                raise e
                        
                        # Reconstruct full result list preserving order
                        full_results = []
                        partial_idx = 0
                        
                        for local_idx in range(len(batch_data)):
                            if local_idx in cached_results_map:
                                full_results.append(cached_results_map[local_idx])
                            else:
                                if partial_idx < len(ai_results_partial):
                                    full_results.append(ai_results_partial[partial_idx])
                                    partial_idx += 1
                                else:
                                    # Fallback if partial result missing (shouldn't happen on success)
                                    full_results.append({}) 
                                    
                        return full_results

                    future_to_batch = {executor.submit(process_single_batch, i, batch): i for i, batch in enumerate(batches)}
                    
                    for future in concurrent.futures.as_completed(future_to_batch):
                        batch_idx = future_to_batch[future]
                        if self.stop_event.is_set():
                            executor.shutdown(wait=False, cancel_futures=True)
                            break
                        
                        try:
                            ai_results = future.result()
                            batch_results_map[batch_idx] = ai_results
                            
                            # Update History (Thread-safe here in main loop)
                            if ai_results:
                                batch_rows = batches[batch_idx]
                                for i, res in enumerate(ai_results):
                                    if i < len(batch_rows):
                                        term = str(batch_rows.iloc[i]['src']).strip()
                                        if term not in self.term_history:
                                            self.term_history[term] = []
                                        self.term_history[term].append(res)
                            
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

                        # Safe NaN handling for info column
                        raw_info = original_row.get('info', '')
                        original_cat = '' if (raw_info != raw_info) else str(raw_info).strip()
                        suggested_cat = str(ai_result.get('suggested_category', '') or '').strip()

                        # Log Entry
                        log_entry = {
                            'round': round_num,
                            'term': original_row.get('src', ''),
                            'original': original_row.get('dst', ''),
                            'new': '',
                            'action': '',
                            'reason': ai_result.get('deletion_reason', ''),
                            'justification': ai_result.get('justification', ''),
                            'emoji': ai_result.get('judgment_emoji', ''),
                            'original_category': original_cat,
                            'suggested_category': suggested_cat,
                        }

                        if ai_result.get('should_delete'):
                            log_entry['action'] = 'Delete'
                            log_entry['new'] = '(Deleted)'
                            master_modification_log.append(log_entry)
                        else:
                            recommended = str(ai_result.get('recommended_translation', '') or '').strip()
                            current = original_row.get('dst', '').strip()

                            translation_changed = bool(recommended and recommended != current)
                            category_changed = bool(suggested_cat and suggested_cat != original_cat)

                            if translation_changed:
                                log_entry['action'] = 'Modify'
                                log_entry['new'] = recommended
                                final_row['dst'] = recommended
                                master_modification_log.append(log_entry)
                            elif category_changed:
                                log_entry['action'] = 'Category'
                                log_entry['new'] = current  # translation unchanged
                                master_modification_log.append(log_entry)
                            else:
                                log_entry['action'] = 'Keep'
                                log_entry['new'] = current

                            # Apply category update to final glossary for all non-deleted terms
                            if category_changed:
                                final_row['info'] = suggested_cat

                            round_rows.append(final_row)
                
                # End of Round Processing
                current_df = pd.DataFrame(round_rows)
                
                # Save Intermediate Files (Stash)
                stash_glossary_path = os.path.join(log_dir, f'glossary_output_{round_num}.xlsx')
                self._save_excel(current_df, stash_glossary_path)
                
                # We also need to save the modification log up to this point?
                # The user asked for "intermediate files... in log...". 
                # Let's save a snapshot of the log for this round.
                round_log = [l for l in master_modification_log if l['round'] == round_num]
                stash_log_path = os.path.join(log_dir, f'modified_{round_num}.xlsx')
                pd.DataFrame(round_log).to_excel(stash_log_path, index=False)
                
                # Save Term History for Resume
                history_path = os.path.join(log_dir, 'term_history.json')
                with open(history_path, 'w', encoding='utf-8') as hf:
                    json.dump(self.term_history, hf, ensure_ascii=False, indent=2)

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
