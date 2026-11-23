#!/bin/sh
# Copies the contract's sample session and sample task into this folder. Run it from the repo root when contract/ changes:
#   sh web/src/api/mock/sync.sh
set -e
cp contract/mock_session.jsonl contract/mock_task/tables.json contract/mock_task/task.json contract/mock_task/*.csv web/src/api/mock/
