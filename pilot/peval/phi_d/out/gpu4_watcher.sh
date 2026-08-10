#!/bin/bash
# Wait for GPU 4 to free, then run the full phi_d extraction+judge chain.
PY=/work1/zixuan/envs/conda_envs/causalmemagent/bin/python
export HF_HOME=/work1/zixuan/cache/huggingface HF_HUB_OFFLINE=1 CUDA_VISIBLE_DEVICES=4
cd /work1/zixuan/projects/agent_memory/pilot/peval/phi_d
for attempt in $(seq 1 10); do
  # wait for a free window (poll every 60s, up to ~4h total)
  for i in $(seq 1 240); do
    used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i 4 2>/dev/null | tr -d ' ')
    if [ -n "$used" ] && [ "$used" -lt 2000 ]; then break; fi
    sleep 60
  done
  used=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i 4 2>/dev/null | tr -d ' ')
  echo "[watcher] attempt=$attempt gpu4_used=${used}MiB $(date -Is)"
  if [ -z "$used" ] || [ "$used" -ge 2000 ]; then continue; fi
  sleep 5
  $PY extract_phi.py > out/run_extract.log 2>&1
  ce=$?
  if [ $ce -ne 0 ]; then echo "[watcher] extract failed code=$ce $(date -Is)"; sleep 30; continue; fi
  $PY decomposed_judge.py > out/run_judge.log 2>&1
  cj=$?
  if [ $cj -ne 0 ]; then echo "[watcher] judge failed code=$cj $(date -Is)"; sleep 30; continue; fi
  echo "[watcher] CHAIN OK $(date -Is)"
  exit 0
done
echo "[watcher] EXHAUSTED attempts"
exit 2
