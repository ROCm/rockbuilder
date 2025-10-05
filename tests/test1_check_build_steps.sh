#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd $SCRIPT_DIR
cd ..

BLD_DIR="build/testapp_01"

TEST_APP_CFG="./tests/projects/testapp_01.cfg"
TEST_GIT_REPO_FILE=tests/repositories/test1_check_build_steps_git.tar

TEST1_RES_FILE="$BLD_DIR/build_steps_clean.txt"
TEST1_GOLDEN_FILE="tests/resources/test1/build_steps_clean.txt"

TEST2_RES_FILE="$BLD_DIR/build_steps.txt"
TEST2_GOLDEN_FILE="tests/resources/test1/build_steps.txt"

TEST3_RES_FILE="src_apps/testapp_01/hello_world.txt"
TEST3_GOLDEN_FILE="tests/resources/testapp_01/hello_world.txt"

TEST1_OK=0
TEST2_OK=0
TEST3_OK=0

echo "SCRIPT_DIR: $SCRIPT_DIR"
echo "TEST_APP_CFG: ${TEST_APP_CFG}"
echo "BLD_DIR: " $BLD_DIR
echo "TEST1_RES_FILE: " $TEST1_RES_FILE
echo "TEST2_RES_FILE: " $TEST2_RES_FILE
echo "TEST3_RES_FILE: " $TEST3_RES_FILE

if [ -f ${TEST_GIT_REPO_FILE} ]; then
    tar -xvf ${TEST_GIT_REPO_FILE} -C /tmp
else
    echo "Error, could not find test repository files:"
    echo "    ${TEST_GIT_REPO_FILE}"
fi

./rockbuilder.py --project ${TEST_APP_CFG} --clean
if [ ! $? -eq 0 ]; then
    echo ""
    echo "Failed to execute command: "
    echo "    './rockbuilder.py --project ${TEST_APP_CFG} --clean'"
    exit 1
fi

if [ !-d ${BLD_DIR} ]; then
    echo "Could not find build dir:"
    echo "    ${BLD_DIR}"
fi

if cmp -s "$TEST1_RES_FILE" "$TEST1_GOLDEN_FILE"; then
    TEST1_OK=1
fi

./rockbuilder.py --project ${TEST_APP_CFG} --checkout
if [ ! $? -eq 0 ]; then
    echo ""
    echo "Failed to execute command: "
    echo "    './rockbuilder.py --project ${TEST_APP_CFG} --checkout'"
    exit 1
fi

./rockbuilder.py --project ${TEST_APP_CFG}
if [ ! $? -eq 0 ]; then
    echo ""
    echo "Failed to execute command: "
    echo "    './rockbuilder.py --project ${TEST_APP_CFG}'"
    exit 1
fi

if cmp -s "$TEST2_RES_FILE" "$TEST2_GOLDEN_FILE"; then
    TEST2_OK=1
fi

if cmp -s "$TEST3_RES_FILE" "$TEST3_GOLDEN_FILE"; then
    TEST3_OK=1
fi

if [ -v TEST1_OK ]; then
    echo "test1_1: OK"
    #echo "The contents of $TEST2_RES_FILE and $TEST2_GOLDEN_FILE are identical."
else
    echo "test1_1: Failed."
    echo "The contents of files are different:"
    echo "    ${TEST1_GOLDEN_FILE}"
    echo "    ${TEST1_RES_FILE}"
    diff -Naur ${TEST2_GOLDEN_FILE} ${TEST2_RES_FILE}
    exit 1
fi

if [ -v TEST2_OK ]; then
    echo "test1_2: OK"
    #echo "The contents of $TEST1_RES_FILE and $TEST1_GOLDEN_FILE are identical."
else
    diff -Naur ${TEST2_GOLDEN_FILE} ${TEST2_RES_FILE}
    echo "test1_2: Failed"
    echo "The contents of files are different:"
    echo "    ${TEST2_GOLDEN_FILE}"
    echo "    ${TEST2_RES_FILE}"
    exit 1
fi

if [ -v TEST3_OK ]; then
    echo "test1_3: OK"
    #echo "The contents of $TEST3_RES_FILE and $TEST3_GOLDEN_FILE are identical."
else
    echo "test1_3: Failed"
    echo "The contents of files are different:"
    echo "    ${TEST2_GOLDEN_FILE}"
    echo "    ${TEST2_RES_FILE}"
    diff -Naur ${TEST2_GOLDEN_FILE} ${TEST2_RES_FILE}
    exit 1
fi
