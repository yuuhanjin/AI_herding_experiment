#!/bin/zsh
cd -- "${0:A:h}"
./.venv/bin/python replicate.py pilot
printf "\n按回车关闭窗口"
read -r reply
