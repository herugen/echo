#!/bin/bash

curl -X POST "http://localhost:8000/translate" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://x.com/BarackObama/status/1969421892458041698",
    "target_language": "zh"
  }'
  


ffmpeg -i /Users/herugen/Downloads/download_e26a8e86908c4d02af6af355328e8ea0_video_678d5f70464b4f739de57efcc5701f5d.mp4 -vf subtitles=/Users/herugen/Downloads/subtitle_79134f3cddc049849caead351d8db25f.ass -c:a copy -c:v copy -preset fast -crf 23 -y /Users/herugen/Downloads/translated_subtitled_task_1234567_13efd8ceebcc426d8d3ec74a5f640257.mp4

ffmpeg -i /Users/herugen/Downloads/download_e26a8e86908c4d02af6af355328e8ea0_video_678d5f70464b4f739de57efcc5701f5d.mp4 -vf subtitles=/Users/herugen/Downloads/subtitle_79134f3cddc049849caead351d8db25f.ass -c:a copy -y /Users/herugen/Downloads/translated_subtitled_task_1234567_13efd8ceebcc426d8d3ec74a5f640257.mp4