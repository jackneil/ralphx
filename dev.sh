#!/bin/bash
trap 'kill 0' EXIT
uvicorn ralphx.api.main:app --reload --port 4445 &
cd frontend && npm run dev
