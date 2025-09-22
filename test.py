#!/bin/bash

curl -X POST "http://localhost:8000/translate" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://x.com/BarackObama/status/1969421892458041698",
    "target_language": "zh"
  }'
  