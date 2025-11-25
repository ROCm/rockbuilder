#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd $SCRIPT_DIR
cd ../..

if [[ -n "$VIRTUAL_ENV" ]]; then
    echo "Virtual environment is active: $VIRTUAL_ENV"
else
     echo "No virtual environment is active."
     source ./init_rcb_env.sh
fi

./rockbuilder.py apps/therock.cfg
RES=$?
if [ ! $RES -eq 0 ]; then
    echo ""
    echo "Failed to build therock, err: $RES"
    exit 1
fi

./rockbuilder.py apps/pytorch_29.apps
RES=$?
if [ ! $RES -eq 0 ]; then
    echo ""
    echo "Failed to build apps/pytorch_29.apps, err: $RES"
    exit 1
fi

./rockbuilder.py apps/vllm_nightly.cfg
RES=$?
if [ ! $RES -eq 0 ]; then
    echo ""
    echo "Failed to build apps/vllm_nightly.cfg, err: $RES"
    exit 1
fi
