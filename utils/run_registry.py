# -*- coding: utf-8 -*-
"""
Run Registry - Unified traceability system for experiments
运行注册表 / Реестр запусков

Provides unique run_id, config_hash, and centralized metadata logging.
"""

import uuid
import hashlib
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
import subprocess


def generate_run_id() -> str:
    """Generate unique run ID."""
    return str(uuid.uuid4())[:8]


def compute_config_hash(config: Dict[str, Any]) -> str:
    """
    Compute stable hash of configuration.
    
    Keys used: weights, thresholds, blocking_keys, bins, mu_table, 
               eval_mode, enable_cn, dataset_id
    """
    # Sort keys for stability
    stable_str = json.dumps(config, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(stable_str.encode()).hexdigest()[:8]


def get_git_commit() -> Optional[str]:
    """Get current git commit hash if available."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except:
        pass
    return None


class RunRegistry:
    """Registry for tracking experiment runs."""
    
    def __init__(self, metadata_path: str = 'results/run_metadata.jsonl'):
        self.metadata_path = Path(metadata_path)
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
    
    def register_run(
        self,
        method_id: str,
        dataset_id: str,
        enable_cn_name: bool,
        eval_mode: str,
        input_path: str,
        output_dir: str,
        config: Dict[str, Any],
        stress_report_path: Optional[str] = None,
        extra_data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Register a new run and return its metadata.
        
        Returns:
            Run metadata dict with run_id, config_hash, etc.
        """
        run_id = generate_run_id()
        config_hash = compute_config_hash(config)
        
        # Create output directory
        run_output_dir = Path(output_dir)
        run_output_dir.mkdir(parents=True, exist_ok=True)
        
        entry = {
            'run_id': run_id,
            'method_id': method_id,
            'dataset_id': dataset_id,
            'enable_cn_name': enable_cn_name,
            'eval_mode': eval_mode,
            'input_path': str(Path(input_path).resolve()),
            'output_dir': str(run_output_dir.resolve()),
            'pred_clusters_path': str(run_output_dir / 'pred_clusters.json'),
            'metrics_path': str(run_output_dir / 'metrics.csv'),
            'stress_report_path': stress_report_path,
            'config_hash': config_hash,
            'config': config,
            'timestamp': datetime.now().isoformat(),
            'git_commit': get_git_commit()
        }
        
        if extra_data:
            entry.update(extra_data)
        
        # Append to metadata file
        with open(self.metadata_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        
        return entry
    
    def load_all_runs(self) -> list:
        """Load all registered runs."""
        runs = []
        if self.metadata_path.exists():
            with open(self.metadata_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        runs.append(json.loads(line))
        return runs
    
    def find_run(
        self,
        method_id: str,
        dataset_id: str,
        enable_cn_name: bool,
        eval_mode: str = 'ORCID_BLIND'
    ) -> Optional[Dict]:
        """Find a specific run by criteria."""
        for run in self.load_all_runs():
            if (run['method_id'] == method_id and 
                run['dataset_id'] == dataset_id and
                run['enable_cn_name'] == enable_cn_name and
                run['eval_mode'] == eval_mode):
                return run
        return None
    
    def clear(self):
        """Clear all runs (use with caution)."""
        if self.metadata_path.exists():
            self.metadata_path.unlink()


def validate_no_duplicate_outputs(runs: list) -> bool:
    """
    Validate that no two runs share the same output_dir.
    
    Raises:
        Exception if duplicates found
    """
    output_dirs = {}
    for run in runs:
        # Handle both flat and nested output_dir structure
        od = run.get('output_dir', '')
        if not od and 'output_paths' in run:
            od = run['output_paths'].get('output_dir', '')
        
        if not od:
            continue
            
        if od in output_dirs:
            raise Exception(
                f"HARD-FAIL: Duplicate output_dir detected!\n"
                f"  Run 1: {output_dirs[od]['run_id']} ({output_dirs[od]['method_id']})\n"
                f"  Run 2: {run['run_id']} ({run['method_id']})\n"
                f"  output_dir: {od}"
            )
        output_dirs[od] = run
    return True


def validate_table6_not_duplicate(fini_metrics: Dict, system_cn_off_metrics: Dict) -> bool:
    """
    HARD-FAIL: FINI and SYSTEM_CN_OFF must not have identical metrics.
    
    Raises:
        Exception if all columns are identical
    """
    keys = ['b3_f1', 'b3_precision', 'b3_recall', 'pairwise_f1', 'conflict_rate']
    
    all_same = True
    for key in keys:
        if abs(fini_metrics.get(key, 0) - system_cn_off_metrics.get(key, 0)) > 1e-6:
            all_same = False
            break
    
    if all_same:
        raise Exception(
            f"HARD-FAIL [S0.1]: Table 6 FINI == SYSTEM_CN_OFF!\n"
            f"  FINI: {fini_metrics}\n"
            f"  SYSTEM_CN_OFF: {system_cn_off_metrics}\n"
            f"  This indicates a bug in experiment configuration or output re-use."
        )
    return True


def validate_table7_stress_different(
    clean_off: Dict, 
    stress_off: Dict,
    subset: str = 'overall'
) -> bool:
    """
    HARD-FAIL: STRESS/CN_OFF must differ from CLEAN/CN_OFF.
    
    Raises:
        Exception if metrics are identical (STRESS not effective)
    """
    keys = ['b3_f1', 'b3_precision', 'b3_recall', 'pairwise_f1', 'conflict_rate']
    
    all_same = True
    for key in keys:
        if abs(clean_off.get(key, 0) - stress_off.get(key, 0)) > 1e-6:
            all_same = False
            break
    
    if all_same:
        raise Exception(
            f"HARD-FAIL [S0.2]: Table 7 CLEAN/CN_OFF == STRESS/CN_OFF ({subset})!\n"
            f"  CLEAN/OFF: {clean_off}\n"
            f"  STRESS/OFF: {stress_off}\n"
            f"  This indicates STRESS data not affecting evaluation or output re-use."
        )
    return True
