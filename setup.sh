#!/bin/bash
pkg update -y
pkg install python git -y
pip install -r requirements.txt
chmod +x main.py
echo 'Done! Run with: python main.py'
