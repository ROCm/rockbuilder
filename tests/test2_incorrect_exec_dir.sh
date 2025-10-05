#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd $SCRIPT_DIR
cd ..

BLD_DIR="build/testapp_02"

TEST_APP_CFG="./tests/projects/testapp_02.cfg"

echo "${TEST_APP_CFG}"

TEST_RES_FILE1="$BLD_DIR/CMD_CONFIG.done"
TEST_RES_FILE2="$BLD_DIR/CMD_INIT.done"
TEST_RES_FILE3="$BLD_DIR/CMD_POST_CONFIG.done"
TEST_RES_FILE4="$BLD_DIR/CMD_PRE_CONFIG.done"

echo "SCRIPT_DIR: ${SCRIPT_DIR}"
echo "TEST_APP_CFG: ${TEST_APP_CFG}"
echo "BLD_DIR: ${BLD_DIR}"

./rockbuilder.py --project ${TEST_APP_CFG}
if [ ! $? -eq 0 ]; then
    echo "Ok, ${TEST_APP_CFG} failed as expected"
    if [[ -f ${TEST_RES_FILE1} && -f ${TEST_RES_FILE2} && -f ${TEST_RES_FILE3}  && -f ${TEST_RES_FILE4} ]]; then
        echo "OK: ${TEST_APP_CFG}"
    else
        echo "Error: ${TEST_APP_CFG}"
        exit 1
    fi
else
    echo ""
    echo "Error: ${TEST_APP_CFG}"
    exit 2
fi

