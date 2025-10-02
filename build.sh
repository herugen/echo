#!/bin/bash

pip install -r requirements.txt
docker build -t whisperx-runner:latest docker/whisperx